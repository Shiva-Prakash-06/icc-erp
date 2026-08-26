"""Role-aware data for the `/` home page.

Formerly ``mission_control.py``, absorbing what used to be three separate
pages: Mission Control (person-scoped: my projects/tasks/requests), the ERP
hub (portfolio-scoped: visible/active project counts, people/import
records), and Oversight (approver-scoped: the 10-source decision queue and
its metrics). See in-the-operation-checklists-crystalline-dongarra.md
Step 2 -- the merge exists because those three pages showed contradictory
numbers for the same thing (Mission Control's decision count covered 2 of
Oversight's 10 sources) and duplicated the same KPI-row-plus-list shape
three times.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.erp import ImportBatch, OperationalRequest, Person, ProjectSession, WorkTask
from app.models.production import RecruitmentApplication
from app.models.project import BuddyAssignment
from app.services.action_queue import build_action_queue, build_oversight_metrics
from app.services.authorization import has_any_permission, has_permission
from app.services.lifecycle import closure_blockers
from app.services.scope import approvable_projects, visible_projects

_OPEN_TASK_STATUSES = ("Not Started", "In Progress", "Blocked", "Submitted")


def build_home(user, *, show_all_queue=False):
    now = datetime.now(timezone.utc)
    projects_in_scope = visible_projects(user)
    project_ids = [project.id for project in projects_in_scope]

    upcoming_sessions = (
        ProjectSession.query.filter(
            ProjectSession.project_id.in_(project_ids or [-1]),
            ProjectSession.starts_at >= now,
        )
        .order_by(ProjectSession.starts_at)
        .limit(8)
        .all()
    )

    my_tasks = []
    if user.person_id:
        my_tasks = (
            WorkTask.query.filter(
                WorkTask.owner_person_id == user.person_id,
                WorkTask.status.in_(_OPEN_TASK_STATUSES),
            )
            .order_by(WorkTask.due_at.is_(None), WorkTask.due_at)
            .limit(8)
            .all()
        )

    my_requests = (
        OperationalRequest.query.filter(
            OperationalRequest.project_id.in_(project_ids or [-1]),
            (OperationalRequest.created_by_id == user.id) | (OperationalRequest.submitted_by_id == user.id),
        )
        .order_by(OperationalRequest.created_at.desc())
        .limit(8)
        .all()
    )

    # can_act gates the full decision queue + oversight metrics -- matches
    # the old /erp/oversight 403 gate exactly (has_any_permission(user, "approve")).
    can_act = has_any_permission(user, "approve")
    can_view_decision_queue = can_act or has_any_permission(user, "approve_operational_requests")

    action_queue = []
    action_queue_total = 0
    oversight_metrics = None
    if can_view_decision_queue:
        approve_projects = approvable_projects(user)
        full_queue = build_action_queue(user, projects=approve_projects)
        action_queue_total = len(full_queue)
        action_queue = full_queue if show_all_queue else full_queue[:8]
        if can_act:
            oversight_metrics = build_oversight_metrics(user, projects=approve_projects)

    portfolio = {
        "projects": len(projects_in_scope),
        "active": sum(project.status in {"Planned", "Active", "Closing"} for project in projects_in_scope),
        "people": Person.query.count() if has_any_permission(user, "manage_projects") else None,
        "imports": ImportBatch.query.count() if has_permission(user, "manage_imports") else None,
    }

    igp_projects = [project for project in projects_in_scope if project.program_type.name == "IGP"]
    igp_indicators = None
    if igp_projects:
        igp_project_ids = [project.id for project in igp_projects]
        pending_applications = RecruitmentApplication.query.filter(
            RecruitmentApplication.project_id.in_(igp_project_ids),
            RecruitmentApplication.decision.in_(["Submitted", "Interview Scheduled"]),
        ).count()
        active_buddy_pairs = BuddyAssignment.query.filter(BuddyAssignment.project_id.in_(igp_project_ids)).count()
        open_closure_blockers = sum(len(closure_blockers(project)) for project in igp_projects)
        igp_indicators = {
            "pending_applications": pending_applications,
            "active_buddy_pairs": active_buddy_pairs,
            "open_closure_blockers": open_closure_blockers,
        }

    return {
        "projects_in_scope": projects_in_scope[:8],
        "project_count": len(projects_in_scope),
        "portfolio": portfolio,
        "upcoming_sessions": upcoming_sessions,
        "my_tasks": my_tasks,
        "my_requests": my_requests,
        "can_act": can_act,
        "can_view_decision_queue": can_view_decision_queue,
        "action_queue": action_queue,
        "action_queue_total": action_queue_total,
        "show_all_queue": show_all_queue,
        "oversight_metrics": oversight_metrics,
        "igp_indicators": igp_indicators,
    }
