from __future__ import annotations

import re
from urllib.parse import urlparse

from flask import current_app


DRIVE_ID_PATTERNS = [
    re.compile(r"/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
    re.compile(r"/folders/([a-zA-Z0-9_-]+)"),
]


def validate_drive_link(url):
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or parsed.hostname not in {"drive.google.com", "docs.google.com"}:
        return {"valid": False, "reason": "Only HTTPS Google Drive or Google Docs links are accepted."}
    file_id = None
    for pattern in DRIVE_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            file_id = match.group(1)
            break
    if not file_id:
        return {"valid": False, "reason": "No Drive file or folder identifier was found."}
    if current_app.config.get("DRIVE_VALIDATION_MODE") == "mock":
        return {
            "valid": True,
            "file_id": file_id,
            "mode": "mock",
            "visibility": "unverified",
            "warning": "Metadata and permissions were not checked against the Drive API.",
        }
    raise RuntimeError("Drive API validation is not configured for this environment.")
