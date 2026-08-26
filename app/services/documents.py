"""Shared document classification, dedupe/supersession, and allow-list rules
used by the IGP repository uploader, the ICC event-folder ingester, and the
resumable Drive upload proxy. See PLAN.md "IGP repository documents" and
"ICC sources and attendance"."""

from __future__ import annotations

import hashlib
import re

from app.database import db
from app.models.erp import DocumentRecord

ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "csv", "pptx", "jpg", "jpeg", "png"}
MAX_TOTAL_BYTES = 100 * 1024 * 1024

# Ordered filename-pattern -> (category, default classification). Matched
# case-insensitively against the whole filename; first match wins, so more
# specific patterns are listed before their looser fallbacks.
CLASSIFICATION_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"screen.*flyer", re.I), "Screen Banner", "Public"),
    (re.compile(r"lamppost", re.I), "Lamppost", "Public"),
    (re.compile(r"invitation.*poster|poster.*invitation", re.I), "Event Poster", "Public"),
    (re.compile(r"welcome\s*notes?", re.I), "Welcome Notes", "Restricted"),
    (re.compile(r"student.*certs?|participant.*certs?", re.I), "Participant Certificates", "Internal"),
    (re.compile(r"budd(y|ies).*certs?", re.I), "Buddy Certificates", "Internal"),
    (re.compile(r"daywise.*budd(y|ies)", re.I), "Daywise Buddy Allocation", "Restricted"),
    (re.compile(r"inaug.*schedule", re.I), "Inauguration Schedule", "Internal"),
    (re.compile(r"valedictory.*schedule", re.I), "Valedictory Schedule", "Internal"),
    (re.compile(r"claim\s*sheet|claimsheet", re.I), "Attendance Claim", "Restricted"),
    (re.compile(r"budd(y|ies).*allocation", re.I), "Buddy Allocation Source", "Restricted"),
    (re.compile(r"check\s*list|checklist", re.I), "Operational Checklist", "Internal"),
    (re.compile(r"backdrop", re.I), "Stage Backdrop", "Public"),
    (re.compile(r"programme.*schedule|program.*schedule|program.*details|programme.*details", re.I), "Program Details", "Internal"),
    (re.compile(r"event.*report|report.*event", re.I), "Event Report", "Internal"),
    (re.compile(r"script", re.I), "Script", "Internal"),
    (re.compile(r"presentation", re.I), "Presentation", "Internal"),
    (re.compile(r"testimonial", re.I), "Testimonial", "Internal"),
    (re.compile(r"photo|image|flicr|flickr", re.I), "Images/Photos", "Internal"),
    (re.compile(r"poster", re.I), "Event Poster", "Public"),
]


def classify_filename(filename: str) -> tuple[str, str]:
    """Return (category, default_classification) inferred from `filename`.
    Falls back to an uncategorized Internal document when nothing matches."""
    for pattern, category, classification in CLASSIFICATION_RULES:
        if pattern.search(filename):
            return category, classification
    return "Other", "Internal"


def is_allowed_extension(filename: str) -> bool:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return suffix in ALLOWED_EXTENSIONS


def checksum_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def find_existing_by_checksum(project_id: int, checksum: str) -> DocumentRecord | None:
    return DocumentRecord.query.filter_by(project_id=project_id, checksum_sha256=checksum).first()


def supersede(old: DocumentRecord, new: DocumentRecord) -> None:
    """Mark `new` as replacing `old` -- an automatic version bump, not a
    manual "supersedes" pick, so no version metadata is asked of the user."""
    new.supersedes_id = old.id
    try:
        new.version_label = str(int(old.version_label) + 1)
    except (TypeError, ValueError):
        new.version_label = "2"


def find_replaceable(project_id: int, title: str, category: str) -> DocumentRecord | None:
    """A document with the same title+category on the project is treated as
    the prior revision when a differently-checksummed replacement arrives."""
    return (
        DocumentRecord.query.filter_by(project_id=project_id, title=title, category=category)
        .order_by(DocumentRecord.created_at.desc())
        .first()
    )


def compute_availability(document: DocumentRecord) -> str:
    """Computed Available/Missing/Inaccessible status shown in the normal
    UI in place of the legacy approval workflow. Legacy `status` values
    remain stored, read-only, for compatibility."""
    if not document.drive_file_id and not document.drive_url:
        return "Missing"
    if document.drive_validation_status == "Invalid":
        return "Inaccessible"
    return "Available"
