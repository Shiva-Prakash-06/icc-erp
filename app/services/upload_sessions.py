"""Resumable chunked document upload, proxied to Google Drive.

Upload-session state (bytes received so far, plus metadata) is short-lived
and stored in Redis in production or an in-process dict in development --
never in the primary database. See PLAN.md "IGP repository documents".
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

from flask import current_app

from app.database import db
from app.models.erp import DocumentRecord
from app.services.audit import record_audit
from app.services.documents import (
    MAX_TOTAL_BYTES,
    checksum_bytes,
    classify_filename,
    find_existing_by_checksum,
    find_replaceable,
    is_allowed_extension,
    supersede,
)
from app.services.drive import upload_file_to_drive

_MEMORY_STORE: dict[str, dict] = {}

MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


class UploadSessionError(ValueError):
    pass


def _redis_client():
    uri = current_app.config.get("UPLOAD_SESSION_STORAGE_URI", "memory://")
    if uri.startswith("redis://") or uri.startswith("rediss://"):
        import redis
        return redis.from_url(uri)
    return None


def _chunk_size_limit() -> int:
    return current_app.config.get("UPLOAD_CHUNK_SIZE_BYTES", 8 * 1024 * 1024)


def start_upload_session(project, filename: str, total_size: int, actor, *, category: str | None = None, classification: str | None = None) -> str:
    if not filename:
        raise UploadSessionError("A filename is required.")
    if not is_allowed_extension(filename):
        raise UploadSessionError("Unsupported file type; executable and macro-enabled files are rejected.")
    if total_size is None or total_size <= 0:
        raise UploadSessionError("Total file size must be a positive number of bytes.")
    if total_size > MAX_TOTAL_BYTES:
        raise UploadSessionError(f"File exceeds the {MAX_TOTAL_BYTES // (1024 * 1024)} MiB upload limit.")

    session_id = str(uuid.uuid4())
    metadata = {
        "project_id": project.id,
        "filename": filename,
        "total_size": total_size,
        "received": 0,
        "category": category,
        "classification": classification,
        "actor_id": getattr(actor, "id", None),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    client = _redis_client()
    if client:
        client.hset(f"upload:{session_id}:meta", mapping={k: str(v) for k, v in metadata.items()})
        client.expire(f"upload:{session_id}:meta", 3600)
    else:
        _MEMORY_STORE[session_id] = {**metadata, "buffer": bytearray()}
    return session_id


def append_chunk(session_id: str, chunk: bytes) -> int:
    if len(chunk) > _chunk_size_limit():
        raise UploadSessionError(f"Chunk exceeds the {_chunk_size_limit() // (1024 * 1024)} MiB chunk size limit.")
    client = _redis_client()
    if client:
        meta_key = f"upload:{session_id}:meta"
        if not client.exists(meta_key):
            raise UploadSessionError("Unknown or expired upload session.")
        client.append(f"upload:{session_id}:data", chunk)
        total_received = client.strlen(f"upload:{session_id}:data")
        client.hset(meta_key, "received", total_received)
        return total_received
    session = _MEMORY_STORE.get(session_id)
    if session is None:
        raise UploadSessionError("Unknown or expired upload session.")
    session["buffer"].extend(chunk)
    session["received"] = len(session["buffer"])
    return session["received"]


def complete_upload_session(session_id: str, actor) -> DocumentRecord:
    client = _redis_client()
    if client:
        meta_key = f"upload:{session_id}:meta"
        raw_meta = client.hgetall(meta_key)
        if not raw_meta:
            raise UploadSessionError("Unknown or expired upload session.")
        meta = {k.decode(): v.decode() for k, v in raw_meta.items()}
        content = bytes(client.get(f"upload:{session_id}:data") or b"")
        project_id = int(meta["project_id"])
        filename = meta["filename"]
        total_size = int(meta["total_size"])
        category_override = meta.get("category") or None
        classification_override = meta.get("classification") or None
        client.delete(meta_key, f"upload:{session_id}:data")
    else:
        session = _MEMORY_STORE.pop(session_id, None)
        if session is None:
            raise UploadSessionError("Unknown or expired upload session.")
        content = bytes(session["buffer"])
        project_id = session["project_id"]
        filename = session["filename"]
        total_size = session["total_size"]
        category_override = session.get("category")
        classification_override = session.get("classification")

    if len(content) != total_size:
        raise UploadSessionError(
            f"Received {len(content)} bytes but expected {total_size}; upload is incomplete or corrupt."
        )

    from app.models.project import Project
    project = db.session.get(Project, project_id)
    checksum = checksum_bytes(content)
    existing = find_existing_by_checksum(project_id, checksum)
    if existing is not None:
        return existing

    inferred_category, inferred_classification = classify_filename(filename)
    category = category_override or inferred_category
    classification = classification_override or inferred_classification
    suffix = filename.rsplit(".", 1)[-1].lower()
    mime_type = MIME_TYPES.get(suffix, "application/octet-stream")

    drive_result = upload_file_to_drive(project, filename, content, mime_type)
    title = filename.rsplit(".", 1)[0]
    document = DocumentRecord(
        project_id=project_id, category=category, title=title, status="Indexed",
        permission_classification=classification, checksum_sha256=checksum,
        uploaded_by_id=getattr(actor, "id", None),
        drive_file_id=drive_result["file_id"], drive_url=drive_result.get("web_view_link"),
        drive_name=drive_result.get("name"), drive_mime_type=mime_type,
        drive_validation_status="Valid", drive_validated_at=datetime.now(timezone.utc),
    )
    prior = find_replaceable(project_id, title, category)
    if prior is not None:
        supersede(prior, document)
    db.session.add(document)
    db.session.flush()
    record_audit("document.upload", document, after={"filename": filename, "category": category}, actor=actor)
    db.session.commit()
    return document


def upload_file_single_shot(project, filename: str, content: bytes, actor, *, category: str | None = None, classification: str | None = None) -> DocumentRecord:
    """Convenience path for a normal (non-chunked) browser upload: runs the
    same start/append/complete pipeline in one call."""
    session_id = start_upload_session(project, filename, len(content), actor, category=category, classification=classification)
    chunk_size = _chunk_size_limit()
    for offset in range(0, len(content), chunk_size):
        append_chunk(session_id, content[offset:offset + chunk_size])
    return complete_upload_session(session_id, actor)
