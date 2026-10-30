from __future__ import annotations

from dataclasses import dataclass

from app.database import db
from app.services.audit import record_audit


# Stages come from dates now (app/services/stage.py), so an open event has
# only two ways to move: finished (Faculty's sign-off) or cancelled. The old
# in-between statuses are kept as keys so rows that still carry them work.
_OPEN_STATUSES = ("Draft", "Pending Approval", "Planned", "Active", "Closing")
TRANSITIONS = {
    **{status: {"Completed", "Cancelled"} for status in _OPEN_STATUSES},
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
    """What still stops the event being finished.

    Only the two things the final report is built from: the event report
    file, and attendance for an event that had sessions. Open to-do items,
    risks and requests used to block closure too; they are now a warning on
    the Finish panel (app/services/finish.py), not a wall.
    """
    from app.services.finish import finish_checklist

    check = finish_checklist(project)
    blockers = []
    if not check["has_report"]:
        blockers.append(ClosureBlocker("Document", None, "Event report", "Missing"))
    if check["needs_attendance"] and not check["attendance_taken"]:
        blockers.append(ClosureBlocker("Attendance", None, "Attendance", "Not taken"))
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
