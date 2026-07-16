from __future__ import annotations

from flask import g, request

from app.database import db
from app.models.erp import AuditEvent


def record_audit(action, entity, before=None, after=None, actor=None):
    """Append an audit event in the caller's transaction."""

    actor = actor or getattr(g, "user", None)
    event = AuditEvent(
        actor_user_id=getattr(actor, "id", None),
        action=action,
        entity_type=entity.__class__.__name__,
        entity_public_id=getattr(entity, "public_id", None),
        before_summary=before,
        after_summary=after,
        request_id=getattr(g, "request_id", None),
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr) if request else None,
    )
    db.session.add(event)
    return event
