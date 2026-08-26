"""Project public-disclosure workflow, kept separate from operational
`Project.status` -- a project can be Completed and never reviewed for public
visibility. Every project defaults to Private; nothing is grandfathered into
public listing. See PLAN.md "Additional release blockers" finding.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import db
from app.models.production import ApprovalEvent
from app.services.audit import record_audit
from app.services.authorization import has_permission

PUBLICATION_TRANSITIONS = {
    "Private": {"Pending"},
    "Pending": {"Published", "Private"},
    "Published": {"Withdrawn"},
    "Withdrawn": {"Pending", "Private"},
}


def submit_project_publication(project, actor, *, expected_version):
    if project.version != expected_version:
        raise ValueError("Concurrent update conflict; refresh and retry with the current version.")
    if not has_permission(actor, "manage_projects", project):
        raise PermissionError("You are not authorized to request publication for this project.")
    if "Pending" not in PUBLICATION_TRANSITIONS.get(project.publication_status, set()):
        raise ValueError(f"Publication cannot move from {project.publication_status} to Pending.")
    previous = project.publication_status
    project.publication_status = "Pending"
    project.publication_requested_by_id = actor.id
    project.version += 1
    db.session.add(ApprovalEvent(entity_type="Project", entity_public_id=project.public_id, action="Publication requested", actor_user_id=actor.id))
    record_audit("project.publication_request", project, {"publication_status": previous}, {"publication_status": "Pending", "version": project.version}, actor)
    db.session.commit()
    return project


def decide_project_publication(project, decision, actor, *, expected_version, reason=None):
    """`decision` is one of Published, Private (reject back to private), or Withdrawn."""
    if project.version != expected_version:
        raise ValueError("Concurrent update conflict; refresh and retry with the current version.")
    if not has_permission(actor, "manage_governance", project):
        raise PermissionError("You are not authorized to decide project publication.")
    if project.publication_status == "Pending" and project.publication_requested_by_id == actor.id:
        raise PermissionError("You cannot review a publication request that you submitted.")
    if decision not in PUBLICATION_TRANSITIONS.get(project.publication_status, set()):
        raise ValueError(f"Publication cannot move from {project.publication_status} to {decision}.")
    if decision in {"Private", "Withdrawn"} and not (reason or "").strip():
        raise ValueError(f"Moving publication to {decision} requires a reason.")
    previous = project.publication_status
    now = datetime.now(timezone.utc)
    project.publication_status = decision
    project.publication_approved_by_id = actor.id
    if decision == "Published":
        project.published_at = now
        project.withdrawn_at = None
    elif decision == "Withdrawn":
        project.withdrawn_at = now
    project.version += 1
    db.session.add(ApprovalEvent(entity_type="Project", entity_public_id=project.public_id, action=f"Publication {decision.lower()}", reason=reason, actor_user_id=actor.id))
    record_audit("project.publication_decision", project, {"publication_status": previous}, {"publication_status": decision, "version": project.version}, actor)
    db.session.commit()
    return project
