"""What `/` shows: the signed-in person's own work, and nothing else.

Every role gets the same page, filled from its own data, and a block with
nothing in it is not drawn:

1. One sentence: how much is due today and how much needs your OK.
2. Needs your OK -- Faculty only: money, events to sign off, the website.
3. To do -- items for you or your team, in Today / This week / Later.
4. Today's event -- a Take attendance button on an event day.
5. Your events -- at most three, with how much is left on each.

A volunteer has nothing to tick, so they get :func:`build_my_activities`
instead: the events they are on, when and where, their job and their buddy.

Whose item is whose
-------------------
An item for a named person is theirs. An item for a team belongs to whoever
holds that team's role (app/services/teams.py). An item for nobody in
particular belongs to the team that runs that kind of event: the Events team
for ICC, the IGP team for IGP. That last rule is what keeps Faculty's list
short -- Faculty runs nothing day to day, so only items handed to Faculty
reach them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.erp import ImportBatch, ProjectSession, SessionAttendance, TeamAssignment
from app.models.production import ApprovalEvent, ContributionRecord
from app.models.project import BuddyAssignment, Project
from app.services.action_queue import build_action_queue
from app.services.authorization import has_any_permission, has_permission
from app.services.roles import (
    ONBOARDING_CHECKLISTS,
    ONBOARDING_CLIENT_SIGNALS,
    onboarding_audience,
)
from app.services.scope import approvable_projects, visible_projects
from app.services.stage import CANCELLED, COMING_UP, FINISHED, HAPPENING, NEEDS_FINISHING, STAGE_LABELS, WAITING, event_stage
from app.services.teams import EVENTS, IGP, contributor_projects, user_teams
from app.services.timeutil import to_campus
from app.services.todo import can_tick, todos_for_projects

#: How many rows a group shows before "Show all".
SHOW = 5

#: Permissions that mean someone works on events rather than only turning up.
_WORKING_PERMISSIONS = ("manage_projects", "approve", "report", "contribute_team", "manage_users", "audit")

#: Words in an item's title that mean it is finished by handing in a file.
_FILE_WORDS = ("poster", "photo", "video", "report", "upload", "file", "bill", "brochure", "certificate", "slides", "flyer")

TODAY = "today"
WEEK = "week"
LATER = "later"
GROUP_LABELS = {TODAY: "Today", WEEK: "This week", LATER: "Later"}


def is_view_only(user):
    """True for a volunteer: someone who is on events but runs none of them."""
    return not any(has_any_permission(user, permission) for permission in _WORKING_PERMISSIONS)


def is_faculty(user):
    return has_any_permission(user, "approve")


def needs_file(item):
    title = (item.title or "").lower()
    return any(word in title for word in _FILE_WORDS)


def _lead_team(project):
    return IGP if project.program_type and project.program_type.name == "IGP" else EVENTS


def _is_mine(item, person_id, teams):
    if item.owner is not None:
        return bool(person_id) and item.owner.id == person_id
    return (item.team or _lead_team(item.project)) in teams


def _when(item):
    """The day an item is for: its due date, else the event's first day."""
    if item.due_at is not None:
        return to_campus(item.due_at if item.due_at.tzinfo else item.due_at.replace(tzinfo=timezone.utc)).date()
    return item.project.start_date


def _group(day, today):
    if day is None or day <= today:
        return TODAY
    if day <= today + timedelta(days=7):
        return WEEK
    return LATER


def projects_in_reach(user):
    """Every unfinished event ``user`` can see or contribute to."""
    found = {project.id: project for project in visible_projects(user)}
    for project in contributor_projects(user):
        found.setdefault(project.id, project)
    return [project for project in found.values() if event_stage(project) not in {FINISHED, CANCELLED}]


def _event_order(faculty):
    first = {WAITING: 0, HAPPENING: 1, NEEDS_FINISHING: 2, COMING_UP: 3} if faculty else \
        {HAPPENING: 0, NEEDS_FINISHING: 1, WAITING: 2, COMING_UP: 3}

    def key(row):
        return (first.get(row["stage"], 9), row["project"].start_date or date.max)
    return key


def build_my_work(user, *, today=None, show=None):
    """Everything the home page draws for someone who works on events.

    ``show`` names the one group to show in full ("today", "week", "later"
    or "ok"); every other list stops at :data:`SHOW` rows.
    """
    today = today or to_campus(datetime.now(timezone.utc)).date()
    faculty = is_faculty(user)
    contributor_only = has_any_permission(user, "contribute_team") and not has_any_permission(user, "manage_projects")

    needs_ok = build_action_queue(user, projects=approvable_projects(user)) if faculty else []

    reach = projects_in_reach(user)
    teams = user_teams(user)
    person_id = user.person_id
    tickable_cache = {}
    open_items = [item for item in todos_for_projects(reach) if not item.done]
    mine = []
    for item in open_items:
        if not _is_mine(item, person_id, teams):
            continue
        key = (item.project.id, item.ref)
        if key not in tickable_cache:
            tickable_cache[key] = can_tick(user, item.project, item)
        if tickable_cache[key]:
            mine.append(item)

    # Oldest first within each group: what was due longest ago leads.
    mine.sort(key=lambda item: (_when(item) or today, item.due_at is None, item.sequence))
    groups = {TODAY: [], WEEK: [], LATER: []}
    for item in mine:
        groups[_group(_when(item), today)].append(item)
    todo_groups = [
        {"key": key, "label": GROUP_LABELS[key], "items": items, "total": len(items),
         "shown": items if show == key else items[:SHOW]}
        for key, items in groups.items() if items
    ]
    # Only the first group with anything in it starts open: usually Today.
    for index, group in enumerate(todo_groups):
        group["open"] = index == 0 or show == group["key"]

    # Event day: the sessions starting today on events this person runs.
    managed = [project for project in reach if has_permission(user, "manage_projects", project)]
    start = datetime.combine(today, datetime.min.time(), tzinfo=to_campus(datetime.now(timezone.utc)).tzinfo)
    todays_sessions = []
    if managed:
        todays_sessions = (
            ProjectSession.query.filter(
                ProjectSession.project_id.in_([project.id for project in managed]),
                ProjectSession.is_active.is_(True),
                ProjectSession.starts_at >= start.astimezone(timezone.utc),
                ProjectSession.starts_at < (start + timedelta(days=1)).astimezone(timezone.utc),
            ).order_by(ProjectSession.starts_at).limit(3).all()
        )

    # Your events: what each one has left. A contributor counts only their
    # own team's items -- the rest of the event is not theirs to worry about.
    left = {}
    for item in (mine if contributor_only else open_items):
        left[item.project.id] = left.get(item.project.id, 0) + 1
    event_rows = [{"project": project, "stage": event_stage(project, today), "left": left.get(project.id, 0)} for project in reach]
    if contributor_only:
        event_rows = [row for row in event_rows if row["left"]]
    event_rows.sort(key=_event_order(faculty))

    return {
        "today": today,
        "is_faculty": faculty,
        "needs_ok": needs_ok if show == "ok" else needs_ok[:SHOW],
        "needs_ok_total": len(needs_ok),
        "todo_groups": todo_groups,
        "due_today": len(groups[TODAY]),
        "todo_total": len(mine),
        "todays_sessions": todays_sessions,
        "your_events": event_rows[:3],
        "events_total": len(event_rows),
        "can_create": has_any_permission(user, "manage_projects"),
        "needs_file": needs_file,
        "STAGE_LABELS": STAGE_LABELS,
        "onboarding_checklist": build_onboarding_checklist(user),
        "onboarding_tour_project": reach[0].public_id if reach else None,
    }


def build_my_activities(user, *, today=None):
    """A volunteer's events: when, where, their job and their buddy.

    Upcoming and running events first, soonest first; past ones fold away
    under one line.
    """
    today = today or to_campus(datetime.now(timezone.utc)).date()
    person_id = user.person_id
    by_project = {}

    def row(project):
        return by_project.setdefault(project.id, {"project": project, "job": None, "buddies": []})

    if person_id:
        for assignment in TeamAssignment.query.filter_by(person_id=person_id).all():
            if assignment.status == "Active" and assignment.project is not None:
                row(assignment.project)["job"] = assignment.role_label or "Volunteer"
    pairs = BuddyAssignment.query.filter(
        (BuddyAssignment.buddy_user_id == user.id)
        | ((BuddyAssignment.buddy_person_id == person_id) if person_id else False)
        | ((BuddyAssignment.exchange_student_person_id == person_id) if person_id else False)
    ).all()
    for pair in pairs:
        project = Project.query.get(pair.project_id)
        if project is None:
            continue
        mine_as_buddy = pair.buddy_user_id == user.id or (person_id and pair.buddy_person_id == person_id)
        other = pair.exchange_student_person if mine_as_buddy else pair.buddy_person
        entry = row(project)
        entry["job"] = entry["job"] or ("Buddy" if mine_as_buddy else "Student")
        if other is not None:
            entry["buddies"].append(other.display_name)

    now = datetime.now(timezone.utc)
    upcoming, past = [], []
    for entry in by_project.values():
        project = entry["project"]
        if project.status == "Cancelled":
            continue
        sessions = sorted((s for s in project.sessions if s.is_active), key=lambda s: s.starts_at)
        entry["next_session"] = next((s for s in sessions if _aware(s.ends_at) >= now), None)
        entry["venue"] = (entry["next_session"].venue if entry["next_session"] and entry["next_session"].venue else None) or project.venue
        (upcoming if (project.end_date or project.start_date) >= today else past).append(entry)
    upcoming.sort(key=lambda entry: entry["project"].start_date)
    past.sort(key=lambda entry: entry["project"].start_date, reverse=True)
    return {"today": today, "activities": upcoming, "past_activities": past}


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ── Getting started ────────────────────────────────────────────────────


def _onboarding_completion(user):
    """Which getting-started tasks are already done, read from the rows the
    work leaves behind wherever there is one."""
    from app.models.erp import AuditEvent

    signals = user.onboarding_signals or {}
    done = {key for key in ONBOARDING_CLIENT_SIGNALS if signals.get(key)}

    if ApprovalEvent.query.filter_by(actor_user_id=user.id).first() or \
            AuditEvent.query.filter(AuditEvent.actor_user_id == user.id, AuditEvent.action.in_(("reimbursement.status", "project.finish_signoff", "project.finish_returned"))).first():
        done.add("decision")
    if SessionAttendance.query.filter_by(verified_by_id=user.id).first():
        done.add("roll_call")
    if ImportBatch.query.filter_by(committed_by_id=user.id).first():
        done.add("import_committed")
    if user.person_id and ContributionRecord.query.filter_by(person_id=user.person_id).first():
        done.add("hours_logged")
    if AuditEvent.query.filter(AuditEvent.actor_user_id == user.id, AuditEvent.action.in_(("task.status", "checklist.status"))).first():
        done.add("todo_ticked")
    if AuditEvent.query.filter(AuditEvent.actor_user_id == user.id, AuditEvent.action == "project.create").first():
        done.add("event_created")
    return done


def build_onboarding_checklist(user):
    """The getting-started card: two or three things worth doing once, each
    ticked from real data. ``None`` once hidden, or for a role with none."""
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
    if completed == len(rows):
        return None
    return {
        "audience": audience,
        "tasks": rows,
        "completed": completed,
        "total": len(rows),
        "percent": round(completed * 100 / len(rows)),
    }
