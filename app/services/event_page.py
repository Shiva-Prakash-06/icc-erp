"""Everything the event page shows, gathered in one place.

The page is one to-do list followed by folded cards -- Schedule, People,
Money, Files and, where they apply, Buddies, Feedback and Applications --
each showing one line until it is opened. This module decides what is in
each card, which card is open, and how an old link (``?tab=``,
``?section=``, ``?focus=``) finds its way to the right card.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.models.erp import (
    BudgetLine,
    DocumentRecord,
    OperationalRequest,
    ProjectSession,
    ReimbursementEntry,
    SessionAttendance,
    TeamAssignment,
)
from app.models.production import ContributionRecord, RecruitmentApplication
from app.services.authorization import has_permission
from app.services.finish import finish_checklist
from app.services.people import JOBS
from app.services.reimbursements import MONEY_ASKED, MONEY_APPROVED, MONEY_PAID
from app.services.stage import STAGE_LABELS, STAGE_TONE, can_finish_now, event_stage
from app.services.teams import can_contribute, user_teams
from app.services.todo import can_tick, todos_for_project, who_options

#: Lists show this many rows, then "Show all".
SHOW = 5

CARDS = ("todo", "schedule", "people", "money", "files", "buddies", "feedback", "applications", "details", "finish")

#: Old ``?tab=`` / ``?section=`` values, from links written before the page
#: was rebuilt (notifications, bookmarks, the old decision queue).
_TAB_CARD = {
    "logistics": "todo", "operations": "todo", "delivery": "todo", "overview": "todo",
    "finance": "money", "documents": "files", "resources": "files",
    "people": "people", "contributions": "people",
    "analytics": "finish", "insights": "finish",
}
_SECTION_CARD = {
    "tasks": "todo", "schedule": "schedule", "details": "details",
    "budget": "money", "requests": "money", "reimbursements": "money",
    "index": "files", "reports": "files", "disclosure": "finish",
    "team": "people", "contributions": "people", "recruitment": "applications",
    "buddies": "buddies", "feedback": "feedback",
}

#: "What is this?" -- the six answers a person picks from when adding a
#: file, and the category each is stored as. The event report category is
#: the one report assembly reads.
FILE_KINDS = (
    ("report", "Event report", "Event Report"),
    ("poster", "Poster", "Event Poster"),
    ("photos", "Photos", "Images/Photos"),
    ("schedule", "Schedule", "Program Details"),
    ("bills", "Bills", "Bills"),
    ("other", "Other", None),
)
_KIND_BY_CATEGORY = {category: label for _, label, category in FILE_KINDS if category}
_KIND_BY_CATEGORY.update({"Poster": "Poster", "Photo": "Photos", "Report": "Event report"})



def file_kind_label(category):
    return _KIND_BY_CATEGORY.get(category, category or "Other")


def _card_of_focus(project, focus, todos):
    if focus in {"finish", "publication", "closure-blockers"}:
        return "finish"
    if any(item.ref.endswith(focus) for item in todos):
        return "todo"
    for card, model in (
        ("schedule", ProjectSession), ("people", TeamAssignment), ("money", ReimbursementEntry),
        ("files", DocumentRecord), ("applications", RecruitmentApplication), ("people", ContributionRecord),
    ):
        if model.query.filter_by(public_id=focus, project_id=project.id).first() is not None:
            return card
    # Lines carried over from the retired budget and request lists.
    for model in (BudgetLine, OperationalRequest):
        if model.query.filter_by(public_id=focus, project_id=project.id).first() is not None:
            return "money"
    for assignment in project.buddy_assignments:
        if assignment.public_id == focus or any(log.public_id == focus for log in assignment.logs):
            return "buddies"
    for form in project.feedback_forms:
        if any(response.public_id == focus for response in form.responses):
            return "feedback"
    return None


def choose_card(project, args, todos):
    card = (args.get("card") or "").strip()
    if card in CARDS:
        return card
    focus = (args.get("focus") or "").strip()
    if focus:
        found = _card_of_focus(project, focus, todos)
        if found:
            return found
    section = args.get("section")
    if section in _SECTION_CARD:
        return _SECTION_CARD[section]
    if section and section.startswith("checklist-"):
        return "todo"
    return _TAB_CARD.get(args.get("tab"), "todo")


def build_event_page(project, user, args, today=None):
    today = today or date.today()
    is_igp = project.program_type.name == "IGP"
    can_manage = has_permission(user, "manage_projects", project)
    can_approve = has_permission(user, "approve", project)

    todos = todos_for_project(project)
    if not can_manage:
        # A contributor reaches the event only through their team's items,
        # so those are all they are shown of the list.
        teams = user_teams(user)
        todos = [item for item in todos if item.team in teams or (item.owner and item.owner.id == user.person_id)]
    open_todos = [item for item in todos if not item.done]
    done_todos = [item for item in todos if item.done]

    sessions = sorted(
        ProjectSession.query.filter_by(project_id=project.id, is_active=True).all(),
        key=lambda session: session.starts_at,
    )
    marked = defaultdict(int)
    if sessions:
        for row in SessionAttendance.query.filter(
            SessionAttendance.session_id.in_([s.id for s in sessions]), SessionAttendance.status == "Present",
        ):
            marked[row.session_id] += 1

    team = [a for a in project.team_assignments if a.status == "Active"]
    team.sort(key=lambda a: a.person.display_name.lower())
    hours = defaultdict(float)
    for record in project.contribution_records:
        if record.approval_status != "Rejected":
            hours[record.person_id] += float(record.duration_hours or 0)
    attended = len({row.person_id for row in SessionAttendance.query.filter(
        SessionAttendance.session_id.in_([s.id for s in sessions] or [-1]), SessionAttendance.status == "Present",
    )})

    money = [entry for entry in project.reimbursement_entries if entry.status != "Removed"]
    # Waiting for an answer first, then the newest: what someone is about to
    # act on is never pushed past the fold by older, settled lines.
    money.sort(key=lambda entry: (entry.status != MONEY_ASKED, -entry.date.toordinal(), -entry.id))
    totals = defaultdict(float)
    for entry in money:
        totals[entry.status] += float(entry.amount or 0)

    files = [doc for doc in project.document_records if doc.status != "Removed"]
    if not can_manage:
        # A contributor sees the files they added, never the event's others
        # (an IGP programme's agreements and visa packs among them).
        files = [doc for doc in files if doc.uploaded_by_id == user.id]
    files.sort(key=lambda doc: (doc.category != "Event Report", (doc.title or "").lower()))

    applications = RecruitmentApplication.query.filter_by(project_id=project.id).order_by(RecruitmentApplication.created_at.desc()).all()
    form = next((f for f in project.feedback_forms if f.is_open), None) or (project.feedback_forms[-1] if project.feedback_forms else None)
    responses = sorted(
        (r for f in project.feedback_forms for r in f.responses if r.moderation_status != "Hidden"),
        key=lambda r: (r.created_at is None, r.created_at), reverse=True,
    )

    stage = event_stage(project, today)
    finish = finish_checklist(project)
    next_session = next((s for s in sessions if s.starts_at.date() >= today), None)

    card = choose_card(project, args, todos)
    me = next((a for a in team if user.person_id and a.person_id == user.person_id), None)
    my_buddies = [
        pair for pair in project.buddy_assignments
        if user.person_id and user.person_id in (pair.buddy_person_id, pair.exchange_student_person_id)
    ]
    return {
        "me": me,
        "my_buddies": my_buddies,
        "project": project,
        "today_iso": today.isoformat(),
        "is_igp": is_igp,
        "can_manage": can_manage,
        "can_approve": can_approve,
        "can_contribute": can_contribute(user, project),
        "stage": stage,
        "stage_label": STAGE_LABELS[stage],
        "stage_tone": STAGE_TONE[stage],
        "card": card,
        "show_all": args.get("all") == "1",
        "show": SHOW,
        "open_todos": open_todos,
        "done_todos": done_todos,
        "tickable": {item.ref for item in todos if can_tick(user, project, item)},
        "who": who_options(project) if can_manage else None,
        "sessions": sessions,
        "marked": marked,
        "next_session": next_session,
        "team": team,
        "hours": hours,
        "attended": attended,
        "jobs": JOBS,
        "money": money,
        "money_totals": {"asked": totals[MONEY_ASKED], "approved": totals[MONEY_APPROVED], "paid": totals[MONEY_PAID]},
        "files": files,
        "file_kinds": FILE_KINDS,
        "file_kind_label": file_kind_label,
        "has_report": finish["has_report"],
        "buddy_pairs": list(project.buddy_assignments) if is_igp else [],
        "applications": applications,
        "feedback_form": form,
        "responses": responses,
        "finish": finish,
        "can_finish": can_manage and can_finish_now(project, today) and not project.finish_requested_at,
        "can_sign_off": can_approve and bool(project.finish_requested_at) and project.finish_requested_by_id != user.id
        and project.status not in {"Completed", "Archived", "Cancelled"},
    }
