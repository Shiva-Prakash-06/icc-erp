"""Transactional operational workflow services shared by HTML and JSON routes."""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import db
from app.models.erp import (
    BudgetLine,
    ChecklistInstance,
    ChecklistItemStatus,
    ChecklistTemplateItem,
    DocumentRecord,
    FeedbackResponse,
    OperationalRequest,
    ProjectSession,
    SessionAttendance,
    TeamAssignment,
    WorkTask,
)
from app.models.production import ApprovalEvent, AttendanceChangeEvent, ContributionRecord, RecruitmentApplication, TaskStatusEvent
from app.models.project import BuddyLog
from app.services.audit import record_audit
from app.services.authorization import has_permission
from app.services.notifications import queue_notification


TASK_STATUSES = {"Not Started", "In Progress", "Blocked", "Submitted", "Approved", "Rejected", "Waived", "Completed"}
DECISION_STATUSES = {"Submitted", "Interview Scheduled", "Selected", "Rejected", "Withdrawn"}
ATTENDANCE_STATUSES = {"Present", "Absent", "Excused", "Late"}
BUDGET_LINE_TRANSITIONS = {
    "Draft": {"Submitted", "Cancelled"},
    "Submitted": {"Approved", "Rejected", "Cancelled"},
    "Rejected": {"Submitted", "Cancelled"},
    "Approved": {"Completed", "Cancelled"},
    "Completed": set(),
    "Cancelled": set(),
}


def session_conflicts(session):
    query = ProjectSession.query.filter(
        ProjectSession.id != getattr(session, "id", None),
        ProjectSession.starts_at < session.ends_at,
        ProjectSession.ends_at > session.starts_at,
    )
    conflicts = []
    if session.venue:
        venue_matches = query.filter(db.func.lower(ProjectSession.venue) == session.venue.strip().lower()).all()
        conflicts.extend(f"Venue overlaps {item.code} · {item.title}." for item in venue_matches)
    if session.owner_person_id:
        owner_matches = query.filter(ProjectSession.owner_person_id == session.owner_person_id).all()
        conflicts.extend(f"Session owner overlaps {item.code} · {item.title}." for item in owner_matches)
    return sorted(set(conflicts))


def _check_version(entity, expected_version):
    if expected_version is None or entity.version != expected_version:
        raise ValueError("Concurrent update conflict; refresh and retry with the current version.")


def change_task_status(task, new_status, actor, *, expected_version, comment=None, evidence_reference=None, waive=False):
    _check_version(task, expected_version)
    if new_status not in TASK_STATUSES:
        raise ValueError("Unsupported task status.")
    if new_status == "Rejected" and not (comment or "").strip():
        raise ValueError("Rejected tasks require a reason.")
    if waive and not (comment or "").strip():
        raise ValueError("Waivers require a justification.")
    previous = task.status
    task.status = "Waived" if waive else new_status
    task.decision_comment = comment
    task.evidence_reference = evidence_reference or task.evidence_reference
    task.waived = waive
    task.waiver_reason = comment if waive else None
    task.waived_by_id = actor.id if waive else None
    task.version += 1
    db.session.add(TaskStatusEvent(task_id=task.id, previous_status=previous, new_status=task.status, comment=comment, evidence_reference=evidence_reference, actor_user_id=actor.id))
    db.session.add(ApprovalEvent(entity_type="WorkTask", entity_public_id=task.public_id, action=task.status, reason=comment, actor_user_id=actor.id))
    record_audit("task.status", task, {"status": previous}, {"status": task.status, "version": task.version}, actor)
    owner = db.session.get(__import__("app.models.erp", fromlist=["Person"]).Person, task.owner_person_id) if task.owner_person_id else None
    if owner and owner.user_account and owner.user_account.id != actor.id:
        queue_notification(
            user=owner.user_account,
            project=task.project,
            event_type="task.status",
            title=f"Task {task.status.lower()}",
            body=f"The status of {task.title} changed to {task.status}.",
            action_url=f"/erp/projects/{task.project.public_id}",
            idempotency_key=f"task-status:{task.public_id}:{task.version}",
            critical=new_status == "Rejected",
        )
    db.session.commit()
    return task


def change_checklist_status(item, new_status, actor, *, expected_version, comment=None, evidence_reference=None, waive=False):
    _check_version(item, expected_version)
    if new_status not in TASK_STATUSES:
        raise ValueError("Unsupported checklist status.")
    if new_status == "Rejected" and not (comment or "").strip():
        raise ValueError("Rejected checklist requirements require a reason.")
    if waive and not (comment or "").strip():
        raise ValueError("Checklist waivers require a justification.")
    previous = item.status
    item.status = "Waived" if waive else new_status
    item.decision_comment = comment
    item.evidence_reference = evidence_reference or item.evidence_reference
    item.waived = waive
    item.waiver_reason = comment if waive else None
    item.waived_by_id = actor.id if waive else None
    if new_status in {"Approved", "Completed"}:
        item.verifier_id = actor.id
        item.verified_at = datetime.now(timezone.utc)
    item.version += 1
    db.session.add(ApprovalEvent(entity_type="ChecklistItemStatus", entity_public_id=item.public_id, action=item.status, reason=comment, actor_user_id=actor.id))
    record_audit("checklist.status", item, {"status": previous}, {"status": item.status, "version": item.version}, actor)
    db.session.commit()
    return item


def decide_recruitment(application, decision, actor, *, expected_version, reason=None):
    _check_version(application, expected_version)
    if decision not in DECISION_STATUSES:
        raise ValueError("Unsupported recruitment decision.")
    if decision == "Rejected" and not (reason or "").strip():
        raise ValueError("Rejected applications require a reason.")
    application.decision = decision
    application.decision_reason = reason
    application.decided_by_id = actor.id
    application.decided_at = datetime.now(timezone.utc)
    application.version += 1
    if decision == "Selected" and not TeamAssignment.query.filter_by(person_id=application.person_id, project_id=application.project_id).first():
        db.session.add(TeamAssignment(person_id=application.person_id, project_id=application.project_id, assignment_type="IGP Program Team", role_label=application.desired_role, recruitment_status="Selected"))
    record_audit("recruitment.decision", application, None, {"decision": decision, "version": application.version}, actor)
    db.session.commit()
    return application


def mark_attendance(session, person, status, actor, *, expected_version=None, reason=None, commit=True):
    if status not in ATTENDANCE_STATUSES:
        raise ValueError("Unsupported attendance status.")
    record = SessionAttendance.query.filter_by(session_id=session.id, person_id=person.id).first()
    previous = record.status if record else None
    if record:
        _check_version(record, expected_version)
        if previous != status and not (reason or "").strip():
            raise ValueError("Attendance corrections require a reason.")
        record.status = status
        record.version += 1
    else:
        record = SessionAttendance(session_id=session.id, person_id=person.id, status=status, version=1)
        db.session.add(record)
        db.session.flush()
    record.verified_by_id = actor.id
    record.verified_at = datetime.now(timezone.utc)
    db.session.add(AttendanceChangeEvent(attendance_id=record.id, previous_status=previous, new_status=status, reason=reason, actor_user_id=actor.id))
    record_audit("attendance.mark", record, {"status": previous}, {"status": status, "version": record.version}, actor)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return record


def decide_document(document, status, actor, *, expected_version, reason=None, waive=False):
    _check_version(document, expected_version)
    if status not in {"Submitted", "Approved", "Rejected", "Expired", "Superseded", "Missing"} and not waive:
        raise ValueError("Unsupported document status.")
    if status == "Rejected" and not (reason or "").strip():
        raise ValueError("Rejected documents require a reason.")
    if waive and not (reason or "").strip():
        raise ValueError("Document waivers require a justification.")
    previous = document.status
    document.status = "Waived" if waive else status
    document.waived = waive
    document.waiver_reason = reason if waive else None
    document.waived_by_id = actor.id if waive else None
    document.rejection_reason = reason if status == "Rejected" else None
    if status == "Approved":
        document.approved_by_id = actor.id
        document.approved_at = datetime.now(timezone.utc)
    document.version += 1
    db.session.add(ApprovalEvent(entity_type="DocumentRecord", entity_public_id=document.public_id, action=document.status, reason=reason, actor_user_id=actor.id))
    record_audit("document.status", document, {"status": previous}, {"status": document.status, "version": document.version}, actor)
    db.session.commit()
    return document


def decide_contribution(contribution, status, actor, *, expected_version, reason=None):
    _check_version(contribution, expected_version)
    if status not in {"Approved", "Rejected"}:
        raise ValueError("Contribution decisions must be Approved or Rejected.")
    if status == "Rejected" and not (reason or "").strip():
        raise ValueError("Rejected contributions require a reason.")
    previous = contribution.approval_status
    contribution.approval_status = status
    contribution.decision_reason = reason
    contribution.approved_by_id = actor.id
    contribution.approved_at = datetime.now(timezone.utc)
    contribution.version += 1
    db.session.add(ApprovalEvent(entity_type="ContributionRecord", entity_public_id=contribution.public_id, action=status, reason=reason, actor_user_id=actor.id))
    record_audit("contribution.decision", contribution, {"approval_status": previous}, {"approval_status": status, "version": contribution.version}, actor)
    db.session.commit()
    return contribution


OPERATIONAL_REQUEST_DECISION_STATUSES = {"Approved", "Rejected", "Completed"}


def decide_operational_request(operational_request, status, actor, *, expected_version, reason=None, official_reference=None):
    """Centralized Draft/Submitted/Approved/Rejected/Completed/Cancelled state
    machine for OperationalRequest, shared by the HTML and API blueprints so
    both enforce identical authorization -- see PLAN.md "USC operational
    approvals" finding. Callers must not duplicate the permission or
    self-approval checks below; both interfaces call only this function.
    """
    _check_version(operational_request, expected_version)
    transitions = {
        "Draft": {"Submitted", "Cancelled"},
        "Submitted": {"Approved", "Rejected", "Cancelled"},
        "Rejected": {"Submitted", "Cancelled"},
        "Approved": {"Completed", "Cancelled"},
        "Completed": set(),
        "Cancelled": set(),
    }
    if status not in transitions.get(operational_request.status, set()):
        raise ValueError(f"Operational request cannot move from {operational_request.status} to {status}.")
    if status in OPERATIONAL_REQUEST_DECISION_STATUSES:
        if not has_permission(actor, "approve_operational_requests", operational_request.project):
            raise PermissionError("You are not authorized to approve operational requests for this project.")
        if operational_request.created_by_id is None or operational_request.submitted_by_id is None:
            raise ValueError(
                "This request has incomplete maker/submission history and must be returned to Draft and resubmitted before a decision."
            )
        creator_ids = {operational_request.created_by_id, operational_request.submitted_by_id}
        if status == "Approved" and actor.id in creator_ids:
            raise PermissionError("You cannot approve an operational request you created or submitted.")
    elif not has_permission(actor, "manage_projects", operational_request.project):
        raise PermissionError("You are not authorized to manage this operational request.")
    if status in {"Rejected", "Cancelled"} and not (reason or "").strip():
        raise ValueError(f"{status} operational requests require a reason.")
    previous = operational_request.status
    operational_request.status = status
    if status == "Submitted":
        operational_request.submitted_by_id = actor.id
    operational_request.decision_comment = reason
    operational_request.official_reference = official_reference or operational_request.official_reference
    if status in {"Approved", "Rejected"}:
        operational_request.approver_id = actor.id
    operational_request.version += 1
    db.session.add(ApprovalEvent(entity_type="OperationalRequest", entity_public_id=operational_request.public_id, action=status, reason=reason, actor_user_id=actor.id))
    record_audit("operational_request.transition", operational_request, {"status": previous}, {"status": status, "version": operational_request.version}, actor)
    db.session.commit()
    return operational_request


def instantiate_checklist(project, template, actor=None):
    """Create a ChecklistInstance for `project` from `template`, populating
    one ChecklistItemStatus per ChecklistTemplateItem. Idempotent: returns
    the existing instance untouched if project+template already has one.
    This is the reusable form of the logic the import pipeline builds
    inline row-by-row (`app/services/imports.py`), needed so the
    wing-leader wizard can instantiate a whole template in one step.
    """
    existing = ChecklistInstance.query.filter_by(project_id=project.id, template_id=template.id).first()
    if existing:
        return existing
    instance = ChecklistInstance(project_id=project.id, template_id=template.id, name=f"{project.title} Checklist")
    db.session.add(instance)
    db.session.flush()
    template_items = ChecklistTemplateItem.query.filter_by(template_id=template.id).order_by(ChecklistTemplateItem.sequence).all()
    for template_item in template_items:
        db.session.add(ChecklistItemStatus(
            checklist_instance_id=instance.id,
            template_item_id=template_item.id,
            external_owner=template_item.default_owner_label,
        ))
    record_audit(
        "checklist.instantiate", instance,
        after={"template_id": template.id, "items": len(template_items)},
        actor=actor,
    )
    db.session.commit()
    return instance


def decide_budget_line(line, status, actor, *, expected_version, reason=None, official_reference=None):
    _check_version(line, expected_version)
    if status not in BUDGET_LINE_TRANSITIONS.get(line.status, set()):
        raise ValueError(f"Budget line cannot move from {line.status} to {status}.")
    if status in {"Rejected", "Cancelled"} and not (reason or "").strip():
        raise ValueError(f"{status} budget lines require a reason.")
    previous = line.status
    line.status = status
    line.official_reference = official_reference or line.official_reference
    if status == "Approved" and line.approved_amount is None:
        line.approved_amount = line.estimated_amount
    line.version += 1
    db.session.add(ApprovalEvent(entity_type="BudgetLine", entity_public_id=line.public_id, action=status, reason=reason, actor_user_id=actor.id))
    record_audit("budget_line.transition", line, {"status": previous}, {"status": status, "version": line.version}, actor)
    db.session.commit()
    return line


def decide_buddy_log(log, status, actor, *, expected_version, reason=None):
    _check_version(log, expected_version)
    if status not in {"Approved", "Rejected"}:
        raise ValueError("Buddy log decisions must be Approved or Rejected.")
    if status == "Rejected" and not (reason or "").strip():
        raise ValueError("Rejected buddy logs require a reason.")
    previous = log.status
    log.status = status
    log.verified_by_id = actor.id
    log.verified_at = datetime.now(timezone.utc)
    log.version += 1
    db.session.add(ApprovalEvent(entity_type="BuddyLog", entity_public_id=log.public_id, action=status, reason=reason, actor_user_id=actor.id))
    record_audit("buddy_log.decision", log, {"status": previous}, {"status": status, "version": log.version}, actor)
    db.session.commit()
    return log


def moderate_feedback(response, status, actor, *, reason=None):
    if status not in {"Approved", "Rejected", "Hidden"}:
        raise ValueError("Unsupported feedback moderation status.")
    if status in {"Rejected", "Hidden"} and not (reason or "").strip():
        raise ValueError("Rejected or hidden feedback requires a moderation reason.")
    previous = response.moderation_status
    response.moderation_status = status
    db.session.add(ApprovalEvent(entity_type="FeedbackResponse", entity_public_id=response.public_id, action=status, reason=reason, actor_user_id=actor.id))
    record_audit("feedback.moderate", response, {"moderation_status": previous}, {"moderation_status": status}, actor)
    db.session.commit()
    return response
