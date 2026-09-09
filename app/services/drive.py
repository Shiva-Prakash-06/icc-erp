"""Google Drive metadata validation, plus upload/download/export, without
ever changing an existing file's sharing permissions."""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import current_app
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload


class DriveStorageError(RuntimeError):
    """A document could not be stored in or read from Drive.

    Raised instead of letting a raw `HttpError`/`RuntimeError` escape, so
    upload routes can flash a legible cause and, critically, so no
    Available/Indexed `DocumentRecord` is ever created for bytes that were
    not persisted. See BETA-READINESS-PLAN W1.3 and audit finding B08.
    """


DRIVE_ID_PATTERNS = [
    re.compile(r"/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
    re.compile(r"/folders/([a-zA-Z0-9_-]+)"),
]
# Upgraded from metadata-only to the minimum read/write scopes needed to
# upload/download files the app creates (`drive.file`) and to read/export
# content of arbitrary pre-existing shared items pasted as links
# (`drive.readonly`) -- never the unrestricted `drive` scope, and this never
# changes an existing file's sharing permissions. See PLAN.md "IGP repository
# documents".
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
]


def extract_drive_id(url):
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or parsed.hostname not in {"drive.google.com", "docs.google.com"}:
        raise ValueError("Only HTTPS Google Drive or Google Docs links are accepted.")
    for pattern in DRIVE_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    raise ValueError("No Drive file or folder identifier was found.")


def _credentials():
    raw_json = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    filename = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if raw_json:
        return service_account.Credentials.from_service_account_info(json.loads(raw_json), scopes=DRIVE_SCOPES)
    if filename:
        return service_account.Credentials.from_service_account_file(filename, scopes=DRIVE_SCOPES)
    raise RuntimeError("Google Drive service credentials are not configured.")


def _visibility(permissions):
    permission_types = {permission.get("type") for permission in permissions}
    if "anyone" in permission_types:
        return "Public"
    if "domain" in permission_types:
        return "Domain"
    if permission_types:
        return "Restricted"
    return "Unknown"


def validate_drive_link(url, classification="Internal"):
    try:
        file_id = extract_drive_id(url)
    except ValueError as error:
        return {"valid": False, "reason": str(error)}

    if current_app.config.get("DRIVE_VALIDATION_MODE") == "mock":
        return {
            "valid": True,
            "file_id": file_id,
            "mode": "mock",
            "visibility": "unverified",
            "warning": "Metadata and permissions were not checked against the Drive API.",
        }

    try:
        service = build("drive", "v3", credentials=_credentials(), cache_discovery=False)
        metadata = service.files().get(
            fileId=file_id,
            fields="id,name,mimeType,modifiedTime,trashed,permissions(id,type,role,domain,allowFileDiscovery)",
            supportsAllDrives=True,
        ).execute()
    except HttpError as error:
        status = getattr(error.resp, "status", None)
        reason = "Drive item is inaccessible to the configured service identity."
        if status == 404:
            reason = "Drive item was not found or is not shared with the configured service identity."
        return {"valid": False, "reason": reason, "provider_status": status}

    permissions = metadata.get("permissions", [])
    visibility = _visibility(permissions)
    if metadata.get("trashed"):
        return {"valid": False, "reason": "Drive item is in the trash.", "file_id": file_id}
    if classification == "Restricted" and visibility in {"Public", "Domain"}:
        return {
            "valid": False,
            "reason": "Restricted references cannot point to publicly or domain-wide shared Drive items.",
            "file_id": file_id,
            "visibility": visibility,
        }
    safe_permissions = [
        {
            "type": item.get("type"),
            "role": item.get("role"),
            "domain": item.get("domain"),
            "allow_file_discovery": item.get("allowFileDiscovery"),
        }
        for item in permissions
    ]
    return {
        "valid": True,
        "file_id": file_id,
        "mode": "live",
        "name": metadata.get("name"),
        "mime_type": metadata.get("mimeType"),
        "modified_time": metadata.get("modifiedTime"),
        "visibility": visibility,
        "permissions": safe_permissions,
    }


def describe_provider_error(error: HttpError) -> str:
    """Turn a Drive `HttpError` into something a project manager can act on."""
    status = getattr(error.resp, "status", None)
    reason = str(getattr(error, "reason", "") or "")
    if status == 404:
        return "The configured document storage folder was not found, or is not shared with the service identity."
    if status in (401, 403):
        if "quota" in reason.lower():
            return (
                "Document storage rejected the upload for lack of storage quota. The repository root must be a "
                "folder on a Shared Drive; a service account has no personal Drive storage."
            )
        return "The service identity is not permitted to write to the configured document storage folder."
    if status and 500 <= status < 600:
        return "Document storage is temporarily unavailable. Try the upload again shortly."
    return f"Document storage rejected the upload: {reason or error}"


def get_drive_service():
    return build("drive", "v3", credentials=_credentials(), cache_discovery=False)


def enclosing_shared_drive_id(service, root_id):
    """Return the Shared Drive ID containing `root_id`, or None when the
    folder lives in an ordinary My Drive.

    A service account has no My Drive storage quota of its own, so the
    repository root is expected to be a folder on a Shared Drive. Knowing
    which drive it is on lets folder lookups search that drive's corpus
    instead of the (empty) service-account corpus. See BETA-READINESS-PLAN
    W1.2.
    """
    metadata = service.files().get(fileId=root_id, fields="id,driveId", supportsAllDrives=True).execute()
    return metadata.get("driveId")


def ensure_project_folder(project):
    """Return the Drive folder ID for `project`, creating one under
    `GOOGLE_DRIVE_REPOSITORY_ROOT_ID` if it doesn't exist yet. Mock mode
    returns a deterministic synthetic ID without calling the Drive API, so
    development/tests never require live credentials."""
    if current_app.config.get("DRIVE_VALIDATION_MODE") == "mock":
        return f"mock-folder-{project.public_id}"
    root_id = current_app.config.get("GOOGLE_DRIVE_REPOSITORY_ROOT_ID")
    if not root_id:
        raise DriveStorageError(
            "Document storage is not configured: GOOGLE_DRIVE_REPOSITORY_ROOT_ID is missing."
        )
    service = get_drive_service()
    folder_name = project.code or project.public_id
    escaped_name = folder_name.replace("'", "\\'")
    query = (
        f"'{root_id}' in parents and name = '{escaped_name}' and "
        "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    # Without the shared-drive parameters this lookup searches only the
    # service account's own (always empty) corpus, so it would recreate the
    # project folder on every upload and then fail on My Drive quota.
    list_arguments = {"q": query, "fields": "files(id,name)", "supportsAllDrives": True, "includeItemsFromAllDrives": True}
    drive_id = enclosing_shared_drive_id(service, root_id)
    if drive_id:
        list_arguments.update({"corpora": "drive", "driveId": drive_id})
    else:
        list_arguments["spaces"] = "drive"
    response = service.files().list(**list_arguments).execute()
    files = response.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder", "parents": [root_id]}
    created = service.files().create(body=metadata, fields="id", supportsAllDrives=True).execute()
    return created["id"]


def upload_file_to_drive(project, filename, content: bytes, mime_type: str):
    """Upload `content` as a new file inside the project's Drive folder.
    Mock mode fabricates a stable synthetic file ID instead of calling the
    Drive API, so upload flows are fully testable offline."""
    if current_app.config.get("DRIVE_VALIDATION_MODE") == "mock":
        fake_id = "mock-" + hashlib.sha256(f"{project.public_id}:{filename}:{len(content)}".encode()).hexdigest()[:24]
        return {"file_id": fake_id, "name": filename, "web_view_link": f"https://drive.google.com/file/d/{fake_id}/view"}
    try:
        folder_id = ensure_project_folder(project)
        service = get_drive_service()
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=True)
        metadata = {"name": filename, "parents": [folder_id]}
        created = service.files().create(
            body=metadata, media_body=media, fields="id,name,webViewLink", supportsAllDrives=True
        ).execute()
    except HttpError as error:
        raise DriveStorageError(describe_provider_error(error)) from error
    except DriveStorageError:
        raise
    except Exception as error:
        raise DriveStorageError(f"Document storage is unavailable: {error}") from error
    return {"file_id": created["id"], "name": created.get("name"), "web_view_link": created.get("webViewLink")}


def download_drive_file(file_id: str, *, export_mime_type: str | None = None) -> bytes:
    """Fetch a Drive file's bytes into memory. Native Google Docs/Slides
    files must be exported to a concrete `export_mime_type`; ordinary
    binary files (PDF, DOCX, images) are fetched as-is."""
    if current_app.config.get("DRIVE_VALIDATION_MODE") == "mock":
        raise RuntimeError("Cannot download real Drive content while DRIVE_VALIDATION_MODE=mock.")
    try:
        service = get_drive_service()
        request = (
            service.files().export_media(fileId=file_id, mimeType=export_mime_type)
            if export_mime_type else service.files().get_media(fileId=file_id, supportsAllDrives=True)
        )
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    except HttpError as error:
        raise DriveStorageError(describe_provider_error(error)) from error
    buffer.seek(0)
    return buffer.read()


def refresh_document_metadata(document):
    result = validate_drive_link(document.drive_url, document.permission_classification)
    document.drive_validated_at = datetime.now(timezone.utc)
    document.drive_validation_status = "Valid" if result.get("valid") else "Invalid"
    if result.get("valid"):
        document.drive_file_id = result["file_id"]
        document.drive_name = result.get("name")
        document.drive_mime_type = result.get("mime_type")
        document.drive_visibility = result.get("visibility")
        document.drive_permission_metadata = result.get("permissions", [])
        modified = result.get("modified_time")
        document.drive_modified_at = datetime.fromisoformat(modified.replace("Z", "+00:00")) if modified else None
    return result
