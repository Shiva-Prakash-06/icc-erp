"""Finishing an event: the one sign-off every event gets.

Two things must be true before an event can be sent to Faculty, because
they are what the final report is built from: the event report file is
there, and attendance was taken (if the event had sessions). Open to-do
items are only a warning -- they no longer stop anyone.

Whoever runs the event sends it; Faculty signs it off with one click, which
marks it Completed and, if they asked for it, puts it on the public website.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import db
from app.models.erp import DocumentRecord, ProjectSession, RoleAssignment, SessionAttendance
from app.models.production import AggregateAttendance
from app.models.user import User
from app.services.audit import record_audit
from app.services.authorization import has_permission
from app.services.notifications import queue_notification
from app.services.publication import decide_project_publication, submit_project_publication
from app.services.stage import FINISHED_STATUSES
from app.services.todo import todos_for_project

#: The category report assembly reads as the event's own report.
EVENT_REPORT_CATEGORY = "Event Report"


def _live_sessions(project):
    return ProjectSession.query.filter_by(project_id=project.id, is_active=True).all()


def finish_checklist(project):
    has_report = DocumentRecord.query.filter(
        DocumentRecord.project_id == project.id,
        DocumentRecord.category == EVENT_REPORT_CATEGORY,
        DocumentRecord.status != "Removed",
    ).first() is not None
    sessions = _live_sessions(project)
    session_ids = [session.id for session in sessions]
    attendance_taken = bool(session_ids) and (
        SessionAttendance.query.filter(SessionAttendance.session_id.in_(session_ids)).first() is not None
        or AggregateAttendance.query.filter(AggregateAttendance.session_id.in_(session_ids)).first() is not None
    )
    open_todos = sum(1 for item in todos_for_project(project) if not item.done)
    needs_attendance = bool(sessions)
    return {
        "has_report": has_report,
        "needs_attendance": needs_attendance,
        "attendance_taken": attendance_taken,
        "open_todos": open_todos,
        "ready": has_report and (attendance_taken or not needs_attendance),
    }


def missing_for_finish(project):
    """Plain-language list of what still stops the event being sent."""
    check = finish_checklist(project)
    missing = []
    if not check["has_report"]:
        missing.append("Add the event report file (in Files, pick “Event report”).")
    if check["needs_attendance"] and not check["attendance_taken"]:
        missing.append("Take attendance for at least one session.")
    return missing


def request_finish(project, actor, *, summary=None, show_on_website=False):
    if not has_permission(actor, "manage_projects", project):
        raise PermissionError("You cannot finish this event.")
    if project.status in FINISHED_STATUSES or project.status == "Cancelled":
        raise ValueError("This event is already finished.")
    if project.finish_requested_at:
        raise ValueError("This event is already waiting for Faculty.")
    missing = missing_for_finish(project)
    if missing:
        raise ValueError(" ".join(missing))
    summary = (summary or "").strip()
    if summary:
        project.closure_summary = summary
    project.finish_requested_at = datetime.now(timezone.utc)
    project.finish_requested_by_id = actor.id
    project.finish_note = None
    project.version += 1
    record_audit("project.finish_request", project, after={"show_on_website": bool(show_on_website)}, actor=actor)
    db.session.commit()
    if show_on_website and project.publication_status in {"Private", "Withdrawn"}:
        submit_project_publication(project, actor, expected_version=project.version)
    _tell_faculty(project, actor)
    return project


def _tell_faculty(project, actor):
    faculty_ids = {
        row.user_id for row in RoleAssignment.query.filter(
            RoleAssignment.is_active.is_(True),
            RoleAssignment.role_code.in_(("OIA_FACULTY_ADMINISTRATOR", "FACULTY_COORDINATOR")),
        )
    }
    for user in User.query.filter(User.id.in_(faculty_ids or [-1])).all():
        if user.id == actor.id or not has_permission(user, "approve", project):
            continue
        queue_notification(
            user=user, project=project, event_type="approval_pending",
            title=f"{project.title} is ready to sign off",
            body="Check it and sign it off from your home screen.",
            action_url=f"/erp/projects/{project.public_id}?card=finish",
            idempotency_key=f"finish-request:{project.public_id}:{project.version}",
        )
    db.session.commit()


def decide_finish(project, actor, *, approve, note=None):
    if not has_permission(actor, "approve", project):
        raise PermissionError("Only Faculty can sign off an event.")
    if not project.finish_requested_at:
        raise ValueError("Nobody has sent this event to be signed off.")
    if project.finish_requested_by_id == actor.id:
        raise PermissionError("Someone else has to sign off an event you sent.")
    note = (note or "").strip()
    if approve:
        before = project.status
        project.status = "Completed"
        project.finish_note = None
        project.version += 1
        record_audit("project.finish_signoff", project, before={"status": before}, after={"status": "Completed"}, actor=actor)
        db.session.commit()
        if project.publication_status == "Pending" and project.publication_requested_by_id != actor.id:
            decide_project_publication(project, "Published", actor, expected_version=project.version)
    else:
        if not note:
            raise ValueError("Say what to fix, so they know.")
        project.finish_requested_at = None
        project.finish_note = note
        project.version += 1
        record_audit("project.finish_returned", project, after={"note": note}, actor=actor)
        db.session.commit()
        requester = db.session.get(User, project.finish_requested_by_id) if project.finish_requested_by_id else None
        if requester is not None:
            queue_notification(
                user=requester, project=project, event_type="task.status",
                title=f"{project.title} needs a little more", body=note,
                action_url=f"/erp/projects/{project.public_id}?card=finish",
                idempotency_key=f"finish-returned:{project.public_id}:{project.version}",
            )
            db.session.commit()
    return project
