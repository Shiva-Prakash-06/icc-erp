"""The ten-source approver decision queue and its supporting oversight
metrics.

Lifted verbatim out of the old ``erp.oversight`` view body so that the
merged home page (``dashboard.index``) and the ``/erp/oversight`` redirect
target compute the exact same numbers -- previously Mission Control's
"Awaiting your decision" tile counted only ``WorkTask`` + ``OperationalRequest``
(2 of these 10 kinds), while Oversight counted all 10, so the two pages
visibly disagreed. See in-the-operation-checklists-crystalline-dongarra.md
Step 1.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import db
from app.models.erp import (
    BudgetLine,
    ChecklistInstance,
    ChecklistItemStatus,
    DocumentRecord,
    FeedbackForm,
    FeedbackResponse,
    OperationalRequest,
    Person,
    ReportSnapshot,
    WorkTask,
)
from app.models.production import ContributionRecord, ProjectRisk, RecruitmentApplication
from app.models.project import BuddyAssignment, BuddyLog, Project
from app.services.authorization import has_permission
from app.services.scope import approvable_projects

ACTION_QUEUE_KINDS = (
    "Task",
    "Checklist",
    "Document",
    "Contribution",
    "Operational request",
    "Budget line",
    "Buddy log",
    "Feedback moderation",
    "Recruitment",
    "Report approval",
)


def build_action_queue(user, projects=None):
    """Return the sorted, unsliced 10-source action queue for ``user``.

    ``projects`` defaults to :func:`app.services.scope.approvable_projects`;
    callers that already computed that list should pass it in so it isn't
    recomputed. Every ``{"kind","title","project","tab","anchor","due_at"}``
    dict shape and every ``tab`` value must stay exactly as e2e's
    "oversight includes every pending category" test expects, since the
    home/oversight "Review" links resolve to these `tab`/`anchor` pairs.
    """
    if projects is None:
        projects = approvable_projects(user)
    project_ids = [project.id for project in projects]
    now = datetime.now(timezone.utc)

    action_queue = []
    for task in WorkTask.query.filter(WorkTask.project_id.in_(project_ids or [-1]), WorkTask.status == "Submitted").all():
        action_queue.append({"kind": "Task", "title": task.title, "project": task.project, "tab": "delivery", "anchor": task.public_id, "due_at": task.due_at})
    for item in ChecklistItemStatus.query.join(ChecklistInstance).filter(ChecklistInstance.project_id.in_(project_ids or [-1]), ChecklistItemStatus.status == "Submitted").all():
        action_queue.append({"kind": "Checklist", "title": item.template_item.title, "project": item.checklist.project, "tab": "delivery", "anchor": item.public_id, "due_at": item.due_at})
    for document in DocumentRecord.query.filter(DocumentRecord.project_id.in_(project_ids or [-1]), DocumentRecord.status == "Submitted").all():
        action_queue.append({"kind": "Document", "title": document.title, "project": document.project, "tab": "resources", "anchor": document.public_id, "due_at": None})
    for contribution in ContributionRecord.query.filter(ContributionRecord.project_id.in_(project_ids or [-1]), ContributionRecord.approval_status == "Pending").all():
        action_queue.append({"kind": "Contribution", "title": f"{contribution.person.display_name} · {contribution.activity_type}", "project": contribution.project, "tab": "contributions", "anchor": contribution.public_id, "due_at": None})
    operational_request_project_ids = [project.id for project in projects if has_permission(user, "approve_operational_requests", project)]
    for request_item in OperationalRequest.query.filter(OperationalRequest.project_id.in_(operational_request_project_ids or [-1]), OperationalRequest.status == "Submitted").all():
        action_queue.append({"kind": "Operational request", "title": request_item.title, "project": request_item.project, "tab": "finance", "anchor": request_item.public_id, "due_at": None})
    for line in BudgetLine.query.filter(BudgetLine.project_id.in_(project_ids or [-1]), BudgetLine.status == "Submitted").all():
        action_queue.append({"kind": "Budget line", "title": f"{line.category} ({line.currency} {line.estimated_amount})", "project": line.project, "tab": "finance", "anchor": line.public_id, "due_at": None})
    for log in BuddyLog.query.join(BuddyAssignment).filter(BuddyAssignment.project_id.in_(project_ids or [-1]), BuddyLog.status == "Pending").all():
        action_queue.append({"kind": "Buddy log", "title": log.description[:100], "project": log.assignment.project, "tab": "contributions", "anchor": log.public_id, "due_at": None})
    for response in FeedbackResponse.query.join(FeedbackForm).filter(FeedbackForm.project_id.in_(project_ids or [-1]), FeedbackResponse.moderation_status == "Pending").all():
        action_queue.append({"kind": "Feedback moderation", "title": response.form.title, "project": response.form.project, "tab": "insights", "anchor": response.public_id, "due_at": None})
    for application in RecruitmentApplication.query.filter(RecruitmentApplication.project_id.in_(project_ids or [-1]), RecruitmentApplication.decision.in_(["Submitted", "Interview Scheduled"])).all():
        project = db.session.get(Project, application.project_id)
        person = db.session.get(Person, application.person_id)
        action_queue.append({"kind": "Recruitment", "title": f"{person.display_name} · {application.desired_role}", "project": project, "tab": "people", "anchor": application.public_id, "due_at": application.interview_at})
    for snapshot in ReportSnapshot.query.filter(ReportSnapshot.project_id.in_(project_ids or [-1]), ReportSnapshot.approval_status == "Draft").all():
        project = db.session.get(Project, snapshot.project_id)
        action_queue.append({"kind": "Report approval", "title": snapshot.title, "project": project, "tab": "insights", "anchor": snapshot.public_id, "due_at": None})
    action_queue.sort(key=lambda item: (item["due_at"] is None, item["due_at"] or now))
    return action_queue


def build_oversight_metrics(user, projects=None):
    """Status counts, overdue counts and budget/risk totals for the
    approver's scoped projects. Split out of the old ``erp.oversight`` body
    alongside :func:`build_action_queue`."""
    if projects is None:
        projects = approvable_projects(user)
    project_ids = [project.id for project in projects]
    now = datetime.now(timezone.utc)

    status_counts = {}
    for project in projects:
        status_counts[project.status] = status_counts.get(project.status, 0) + 1

    overdue_tasks = WorkTask.query.filter(
        WorkTask.project_id.in_(project_ids or [-1]), WorkTask.due_at.isnot(None), WorkTask.due_at < now,
        WorkTask.status.notin_(["Approved", "Completed", "Waived"]),
    ).count()
    overdue_checklist_items = (
        ChecklistItemStatus.query.join(ChecklistInstance)
        .filter(
            ChecklistInstance.project_id.in_(project_ids or [-1]),
            ChecklistItemStatus.due_at.isnot(None), ChecklistItemStatus.due_at < now,
            ChecklistItemStatus.status.notin_(["Approved", "Completed", "Waived"]),
        ).count()
    )

    budget_totals = db.session.query(
        db.func.coalesce(db.func.sum(BudgetLine.committed_amount), 0),
        db.func.coalesce(db.func.sum(BudgetLine.actual_amount), 0),
    ).filter(BudgetLine.project_id.in_(project_ids or [-1])).one()

    open_critical_risks = ProjectRisk.query.filter(
        ProjectRisk.project_id.in_(project_ids or [-1]), ProjectRisk.status == "Open", ProjectRisk.is_critical.is_(True),
    ).count()

    return {
        "status_counts": status_counts,
        "overdue_tasks": overdue_tasks,
        "overdue_checklist_items": overdue_checklist_items,
        "budget_committed": budget_totals[0],
        "budget_actual": budget_totals[1],
        "open_critical_risks": open_critical_risks,
    }
