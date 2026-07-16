"""Google Drive metadata validation without changing sharing permissions."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import current_app
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


DRIVE_ID_PATTERNS = [
    re.compile(r"/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
    re.compile(r"/folders/([a-zA-Z0-9_-]+)"),
]
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]


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
