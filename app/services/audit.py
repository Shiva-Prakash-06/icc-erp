from __future__ import annotations

from flask import g, request

from app.database import db
from app.models.erp import AuditEvent
from app.models.production import SensitiveAccessEvent


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


def record_sensitive_access(entity, purpose, actor=None, project=None):
    """Record named access to a restricted operational reference."""

    actor = actor or getattr(g, "user", None)
    event = SensitiveAccessEvent(
        actor_user_id=getattr(actor, "id", None),
        entity_type=entity.__class__.__name__,
        entity_public_id=entity.public_id,
        project_public_id=getattr(project, "public_id", None),
        purpose=(purpose or "Operational access")[:180],
        request_id=getattr(g, "request_id", None),
    )
    db.session.add(event)
    return event
