from __future__ import annotations

from dataclasses import dataclass

from app.database import db
from app.models.erp import ChecklistItemStatus, DocumentRecord, WorkTask
from app.services.audit import record_audit


TRANSITIONS = {
    "Draft": {"Pending Approval", "Cancelled"},
    "Pending Approval": {"Draft", "Planned", "Cancelled"},
    "Planned": {"Active", "Cancelled"},
    "Active": {"Closing", "Cancelled"},
    "Closing": {"Active", "Completed", "Cancelled"},
    "Completed": {"Archived"},
    "Cancelled": {"Archived"},
    "Archived": set(),
}


@dataclass(frozen=True)
class ClosureBlocker:
    kind: str
    public_id: str | None
    title: str
    reason: str


def closure_blockers(project):
    blockers = []
    for task in WorkTask.query.filter_by(project_id=project.id, mandatory_for_closure=True).all():
        if not task.waived and task.status not in {"Approved", "Completed"}:
            blockers.append(ClosureBlocker("Task", task.public_id, task.title, task.status))

    item_statuses = (
        ChecklistItemStatus.query.join(ChecklistItemStatus.checklist)
        .filter_by(project_id=project.id)
        .all()
    )
    for item in item_statuses:
        if item.template_item.mandatory and not item.waived and item.status not in {"Approved", "Completed"}:
            blockers.append(
                ClosureBlocker("Checklist", item.public_id, item.template_item.title, item.status)
            )

    for document in DocumentRecord.query.filter_by(project_id=project.id, mandatory_for_closure=True).all():
        if not document.waived and document.status != "Approved":
            blockers.append(ClosureBlocker("Document", document.public_id, document.title, document.status))

    if not (project.closure_summary or "").strip():
        blockers.append(ClosureBlocker("Report", project.public_id, "Closure summary", "Missing"))
    return blockers


def transition_project(project, target_status, actor, expected_version=None, reason=None):
    if expected_version is not None and project.version != expected_version:
        raise ValueError("This project was changed by another user; refresh before retrying.")
    if target_status not in TRANSITIONS.get(project.status, set()):
        raise ValueError(f"Transition from {project.status} to {target_status} is not allowed.")
    if target_status == "Cancelled" and not (reason or "").strip():
        raise ValueError("A cancellation reason is required.")
    if target_status == "Completed":
        blockers = closure_blockers(project)
        if blockers:
            raise ValueError(f"Project has {len(blockers)} unresolved closure blocker(s).")

    before = {"status": project.status, "version": project.version}
    project.status = target_status
    project.version += 1
    if target_status == "Cancelled":
        project.cancellation_reason = reason.strip()
    record_audit(
        "project.transition",
        project,
        before=before,
        after={"status": project.status, "version": project.version, "reason": reason},
        actor=actor,
    )
    db.session.commit()
    return project
