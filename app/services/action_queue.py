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

from sqlalchemy.orm import joinedload

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
from app.models.user import User
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
    "Project publication",
)


# Every reject path in app.services.operations refuses a decision without a
# written reason ("Rejected tasks require a reason", and the equivalent for
# checklists, documents, contributions, budget lines, buddy logs, feedback
# and recruitment). So only the *approve* half of a decision can be taken
# from a list: the send-back half opens the record, where the reason field
# lives. Approving never needs one, which is why the common case is one
# click and the exceptional case still gets its audit trail.
# The endpoint and its parameters are returned rather than a built URL:
# this service is called from tests and jobs with only an app context, and
# url_for needs a request. The template resolves it.
def _decision(endpoint, *, field, value, version, approve, reject, **params):
    """``version`` is None for the one decision that carries no optimistic
    concurrency token (``moderate_feedback`` takes no ``expected_version``);
    the template omits the field rather than posting a meaningless 0."""
    return {
        "decide_endpoint": endpoint,
        "decide_params": params,
        "decide_field": field,
        "approve_value": value,
        "version": version,
        "approve_label": approve,
        "reject_label": reject,
    }


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

    # The caller already holds every in-scope project, so resolving a row's
    # project through the identity map costs nothing and saves one query per
    # queue row (audit B13, repeated queries on the home page).
    projects_by_id = {project.id: project for project in projects}

    action_queue = []
    for task in WorkTask.query.filter(WorkTask.project_id.in_(project_ids or [-1]), WorkTask.status == "Submitted").all():
        action_queue.append({"kind": "Task", "title": task.title, "project": task.project, "tab": "delivery", "anchor": task.public_id, "due_at": task.due_at,
                             "meta": task.description or "", **_decision("erp.update_task", field="status", value="Approved", version=task.version, approve="Approve", reject="Send back", public_id=task.project.public_id, task_public_id=task.public_id)})
    # `template_item.title` and `checklist.project` are read for every row, so
    # without eager loading this single source issued two extra queries per
    # queue item -- the bulk of the home page's query count (audit B13).
    checklist_items = (
        ChecklistItemStatus.query.join(ChecklistInstance)
        .options(
            joinedload(ChecklistItemStatus.template_item),
            joinedload(ChecklistItemStatus.checklist).joinedload(ChecklistInstance.project),
        )
        .filter(ChecklistInstance.project_id.in_(project_ids or [-1]), ChecklistItemStatus.status == "Submitted")
        .all()
    )
    for item in checklist_items:
        action_queue.append({"kind": "Checklist", "title": item.template_item.title, "project": item.checklist.project, "tab": "delivery", "anchor": item.public_id, "due_at": item.due_at,
                             "meta": "Blocks closure" if item.template_item.mandatory else "", **_decision("erp.update_checklist_item", field="status", value="Approved", version=item.version, approve="Verify", reject="Send back", public_id=item.checklist.project.public_id, item_public_id=item.public_id)})
    for document in DocumentRecord.query.filter(DocumentRecord.project_id.in_(project_ids or [-1]), DocumentRecord.status == "Submitted").all():
        action_queue.append({"kind": "Document", "title": document.title, "project": document.project, "tab": "resources", "anchor": document.public_id, "due_at": None,
                             "meta": document.permission_classification or "", **_decision("erp.decide_document_route", field="status", value="Approved", version=document.version, approve="Approve", reject="Send back", public_id=document.project.public_id, document_public_id=document.public_id)})
    for contribution in ContributionRecord.query.filter(ContributionRecord.project_id.in_(project_ids or [-1]), ContributionRecord.approval_status == "Pending").all():
        action_queue.append({"kind": "Contribution", "title": f"{contribution.person.display_name} · {contribution.activity_type}", "project": contribution.project, "tab": "contributions", "anchor": contribution.public_id, "due_at": None,
                             "meta": f"{contribution.duration_hours} h" if contribution.duration_hours else "", **_decision("erp.decide_contribution_route", field="status", value="Approved", version=contribution.version, approve="Approve", reject="Send back", public_id=contribution.project.public_id, contribution_public_id=contribution.public_id)})
    operational_request_project_ids = [project.id for project in projects if has_permission(user, "approve_operational_requests", project)]
    for request_item in OperationalRequest.query.filter(OperationalRequest.project_id.in_(operational_request_project_ids or [-1]), OperationalRequest.status == "Submitted").all():
        action_queue.append({"kind": "Operational request", "title": request_item.title, "project": request_item.project, "tab": "finance", "anchor": request_item.public_id, "due_at": None,
                             "meta": request_item.request_type or "", **_decision("erp.decide_operational_request_route", field="status", value="Approved", version=request_item.version, approve="Approve", reject="Query", public_id=request_item.project.public_id, request_public_id=request_item.public_id)})
    for line in BudgetLine.query.filter(BudgetLine.project_id.in_(project_ids or [-1]), BudgetLine.status == "Submitted").all():
        action_queue.append({"kind": "Budget line", "title": f"{line.category} ({line.currency} {line.estimated_amount})", "project": line.project, "tab": "finance", "anchor": line.public_id, "due_at": None,
                             "meta": "", **_decision("erp.decide_budget_line_route", field="status", value="Approved", version=line.version, approve="Approve", reject="Query", public_id=line.project.public_id, line_public_id=line.public_id)})
    for log in BuddyLog.query.join(BuddyAssignment).filter(BuddyAssignment.project_id.in_(project_ids or [-1]), BuddyLog.status == "Pending").all():
        action_queue.append({"kind": "Buddy log", "title": log.description[:100], "project": log.assignment.project, "tab": "contributions", "anchor": log.public_id, "due_at": None,
                             "meta": "", **_decision("erp.decide_buddy_log_route", field="status", value="Approved", version=log.version, approve="Approve", reject="Send back", public_id=log.assignment.project.public_id, log_public_id=log.public_id)})
    for response in FeedbackResponse.query.join(FeedbackForm).filter(FeedbackForm.project_id.in_(project_ids or [-1]), FeedbackResponse.moderation_status == "Pending").all():
        action_queue.append({"kind": "Feedback moderation", "title": response.form.title, "project": response.form.project, "tab": "insights", "anchor": response.public_id, "due_at": None,
                             "meta": "", **_decision("erp.moderate_feedback_route", field="status", value="Approved", version=None, approve="Publish", reject="Hold", public_id=response.form.project.public_id, response_public_id=response.public_id)})
    applications = RecruitmentApplication.query.filter(RecruitmentApplication.project_id.in_(project_ids or [-1]), RecruitmentApplication.decision.in_(["Submitted", "Interview Scheduled"])).all()
    people_by_id = {}
    if applications:
        person_ids = {application.person_id for application in applications}
        people_by_id = {person.id: person for person in Person.query.filter(Person.id.in_(person_ids)).all()}
    for application in applications:
        person = people_by_id.get(application.person_id)
        display_name = person.display_name if person else "Unknown applicant"
        queue_project = projects_by_id.get(application.project_id)
        action_queue.append({"kind": "Recruitment", "title": f"{display_name} · {application.desired_role}", "project": queue_project, "tab": "people", "anchor": application.public_id, "due_at": application.interview_at,
                             "meta": application.decision or "", **_decision("erp.decide_recruitment_route", field="decision", value="Selected", version=application.version, approve="Select", reject="Decline", public_id=queue_project.public_id, application_public_id=application.public_id)})
    for snapshot in ReportSnapshot.query.filter(ReportSnapshot.project_id.in_(project_ids or [-1]), ReportSnapshot.approval_status == "Draft").all():
        snapshot_project = projects_by_id.get(snapshot.project_id)
        action_queue.append({"kind": "Report approval", "title": snapshot.title, "project": snapshot_project, "tab": "insights", "anchor": snapshot.public_id, "due_at": None,
                             "meta": "", **_decision("erp.approve_report_route", field="status", value="Approved", version=snapshot.version, approve="Approve", reject="Send back", public_id=snapshot_project.public_id, snapshot_public_id=snapshot.public_id)})
    # Pending project publications were absent from the queue entirely, so
    # faculty saw 12 items and no publication request while the submitter saw
    # Pending (audit B12). Requests the viewer raised themselves are left out:
    # `decide_project_publication` refuses self-review, so listing them would
    # be another visible action that ends in a denial.
    pending_publications = [
        candidate for candidate in projects
        if candidate.publication_status == "Pending"
        and candidate.publication_requested_by_id != user.id
        and has_permission(user, "manage_governance", candidate)
    ]
    requesters_by_id = {}
    if pending_publications:
        requester_ids = {candidate.publication_requested_by_id for candidate in pending_publications if candidate.publication_requested_by_id}
        if requester_ids:
            requesters_by_id = {account.id: account for account in User.query.filter(User.id.in_(requester_ids)).all()}
    for candidate in pending_publications:
        requester = requesters_by_id.get(candidate.publication_requested_by_id)
        requested_by = "an unknown requester"
        if requester is not None:
            requested_by = requester.person.display_name if requester.person else requester.username
        action_queue.append({
            "kind": "Project publication",
            "title": f"{candidate.title} · requested by {requested_by}",
            "project": candidate,
            "tab": "overview",
            "anchor": "publication",
            "due_at": None,
            "meta": "Awaiting a publication decision",
            **_decision("erp.decide_publication", field="decision", value="Published", version=candidate.version, approve="Publish", reject="Hold", public_id=candidate.public_id),
        })
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
