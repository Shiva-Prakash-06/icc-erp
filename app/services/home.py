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

from app.models.erp import ImportBatch, OperationalRequest, Person, ProjectSession, SessionAttendance, WorkTask
from app.models.production import ApprovalEvent, ContributionRecord, RecruitmentApplication
from app.models.project import BuddyAssignment
from app.services.action_queue import build_action_queue, build_oversight_metrics
from app.services.authorization import has_any_permission, has_permission
from app.services.lifecycle import closure_blockers
from app.services.roles import (
    ONBOARDING_CHECKLISTS,
    ONBOARDING_CLIENT_SIGNALS,
    onboarding_audience,
)
from app.services.scope import approvable_projects, visible_projects

_OPEN_TASK_STATUSES = ("Not Started", "In Progress", "Blocked", "Submitted")


def _onboarding_completion(user):
    """Which getting-started tasks are already done.

    Everything that leaves a row behind is read from that row rather than
    from a flag: a decision the user actually cleared, a roll call they
    actually verified, an import they actually committed. Only the three
    tasks that touch nothing in the database (using the command palette,
    opening a project, reading the audit trail) come from the signals the
    browser reports -- see ONBOARDING_CLIENT_SIGNALS.
    """
    signals = user.onboarding_signals or {}
    done = {key for key in ONBOARDING_CLIENT_SIGNALS if signals.get(key)}

    if ApprovalEvent.query.filter_by(actor_user_id=user.id).first():
        done.add("decision")
    if SessionAttendance.query.filter_by(verified_by_id=user.id).first():
        done.add("roll_call")
    if ImportBatch.query.filter_by(committed_by_id=user.id).first():
        done.add("import_committed")
    if user.person_id and ContributionRecord.query.filter_by(person_id=user.person_id).first():
        done.add("hours_logged")
    return done


def build_onboarding_checklist(user):
    """The getting-started card: the role's three or four tasks, each with a
    real completion flag and the page where it is done. Returns ``None`` once the
    user has hidden it, so the card disappears for good rather than lingering
    as a permanently-ticked decoration. Skipping the *tour* does not hide it --
    that is exactly when a written list is most useful."""
    signals = user.onboarding_signals or {}
    if signals.get("checklist_hidden"):
        return None
    audience = onboarding_audience(user)
    tasks = ONBOARDING_CHECKLISTS.get(audience, [])
    if not tasks:
        return None
    done = _onboarding_completion(user)
    # Not "items": a dict key of that name is shadowed by dict.items in Jinja.
    rows = [{**task, "done": task["key"] in done} for task in tasks]
    completed = sum(row["done"] for row in rows)
    return {
        "audience": audience,
        "tasks": rows,
        "completed": completed,
        "total": len(rows),
        "percent": round(completed * 100 / len(rows)),
    }


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
        # The queue screen marks a row overdue by comparing against this,
        # rather than each template re-deriving "now" and disagreeing.
        "now": now,
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
        "onboarding_checklist": build_onboarding_checklist(user),
        # The tour's "blockers" step anchors to an element that only exists on
        # a project page, so the step needs somewhere to navigate to. Resolved
        # here because `projects_in_scope` is already in hand; on any other
        # page the step has no destination and is skipped rather than shown
        # pointing at nothing.
        "onboarding_tour_project": projects_in_scope[0].public_id if projects_in_scope else None,
    }


def build_campus_home(user):
    """What the campus screen needs beyond its tiles.

    Deliberately much cheaper than :func:`build_home`: the campus screen
    shows four tiles, a count, and a first-run checklist, so it must not pay
    for the ten-source decision queue that now lives on ``/queue``. The
    count is the queue's length, which is the one number that decides
    whether the head shows a "waiting on you" button at all.
    """
    projects_in_scope = visible_projects(user)
    pending = 0
    if has_any_permission(user, "approve") or has_any_permission(user, "approve_operational_requests"):
        pending = len(build_action_queue(user, projects=approvable_projects(user)))
    return {
        "pending_decisions": pending,
        "onboarding_checklist": build_onboarding_checklist(user),
        # The tour's "blockers" step anchors to an element that only exists
        # on a project page, so the step needs somewhere to navigate to.
        "onboarding_tour_project": projects_in_scope[0].public_id if projects_in_scope else None,
    }
