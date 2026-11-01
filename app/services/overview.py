"""The landing page for everyone who runs events: look first, act later.

Faculty, the USC and the heads open on this instead of their own to-do
list (which is still one press away as My work). It answers "what is going
on, and who has it?" in three steps, each one a click deeper:

1. The four campuses, as tiles, with how many programs each runs and how
   much is still open or late across them.
2. One campus: its programs, ICC events and IGP programmes side by side,
   each with its dates, where it is, its lead and how far along it is.
3. One program: every action on it, in a list, with who owns each one,
   when it is due and whether it is done.

Read-only and university-wide on purpose. Nothing here is ticked, approved
or changed -- that stays on the event page and My work, under the usual
permission checks -- so a head scoped to one campus can still see how the
others are doing. Volunteers do not get this page; they keep My activities.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from app.models.erp import Person
from app.models.project import Campus, Project
from app.services.glossary import division_name, record_noun
from app.services.stage import CANCELLED, COMING_UP, FINISHED, HAPPENING, NEEDS_FINISHING, STAGE_LABELS, STAGE_TONE, WAITING, event_stage
from app.services.teams import TEAM_LABELS
from app.services.timeutil import to_campus
from app.services.todo import todos_for_project, todos_for_projects

#: The four campuses, in the order the tiles are drawn. `aliases` matches the
#: stored Campus.code, so a campus row with an older code still finds its
#: tile; `accent` is the tile colour (a ``ds-tile--*`` modifier).
CAMPUS_ROSTER = (
    {"code": "BCC", "name": "Central", "aliases": ("BCC", "CEN"), "accent": "brass"},
    {"code": "BKC", "name": "Kengeri", "aliases": ("BKC", "KEN"), "accent": "pine"},
    {"code": "BYC", "name": "Yeshwantpur", "aliases": ("BYC", "YPR"), "accent": "indigo"},
    {"code": "BRC", "name": "Bannerghatta", "aliases": ("BRC", "BGR"), "accent": "plum"},
)

#: ICC first, then IGP: the two kinds of program a campus runs.
DIVISIONS = (("ICC", "pine"), ("IGP", "indigo"))

#: Live programs first, then what is coming, then what is over.
_STAGE_ORDER = {HAPPENING: 0, NEEDS_FINISHING: 1, WAITING: 2, COMING_UP: 3, FINISHED: 4, CANCELLED: 5}


def _today():
    return to_campus(datetime.now(timezone.utc)).date()


def _match_campus(entry, campuses):
    for campus in campuses:
        if (campus.code or "").upper() in entry["aliases"]:
            return campus
    for campus in campuses:
        if entry["name"].lower() in (campus.name or "").lower():
            return campus
    return None


def _counts(items, now):
    done = sum(1 for item in items if item.done)
    late = sum(1 for item in items if item.overdue(now))
    total = len(items)
    return {
        "total": total,
        "done": done,
        "open": total - done,
        "late": late,
        "percent": round(100 * done / total) if total else 0,
    }


def _live(projects):
    return [project for project in projects if project.status not in {"Cancelled", "Archived"}]


def build_campus_tiles():
    """The first screen: one tile per campus, with its numbers."""
    campuses = Campus.query.all()
    now = datetime.now(timezone.utc)
    by_campus = defaultdict(list)
    projects = _live(Project.query.all())
    for project in projects:
        by_campus[project.campus_id].append(project)
    items_by_campus = defaultdict(list)
    for item in todos_for_projects(projects):
        items_by_campus[item.project.campus_id].append(item)

    today = _today()
    tiles = []
    for entry in CAMPUS_ROSTER:
        campus = _match_campus(entry, campuses)
        scoped = by_campus.get(campus.id, []) if campus else []
        tiles.append({
            **entry,
            "campus": campus,
            "full_name": campus.name if campus else f"{entry['name']} Campus",
            "programs": len(scoped),
            "running": sum(1 for project in scoped if event_stage(project, today) == HAPPENING),
            "divisions": {code: sum(1 for p in scoped if p.program_type and p.program_type.name == code) for code, _ in DIVISIONS},
            **{f"actions_{key}": value for key, value in _counts(items_by_campus.get(campus.id, []) if campus else [], now).items()},
        })
    return {
        "tiles": tiles,
        "totals": {
            "programs": sum(tile["programs"] for tile in tiles),
            "open": sum(tile["actions_open"] for tile in tiles),
            "late": sum(tile["actions_late"] for tile in tiles),
        },
    }


def campus_tile(campus):
    for entry in CAMPUS_ROSTER:
        if _match_campus(entry, [campus]) is campus:
            return entry
    return {"code": campus.code or "", "name": campus.name, "accent": "brass"}


def _lead(project, people):
    person = people.get(project.owner_person_id)
    return person.display_name if person else ""


def _people(ids):
    ids = {pid for pid in ids if pid}
    if not ids:
        return {}
    return {person.id: person for person in Person.query.filter(Person.id.in_(ids)).all()}


def build_campus_programs(campus):
    """The second screen: a campus's programs, ICC and IGP side by side."""
    today = _today()
    now = datetime.now(timezone.utc)
    projects = _live(Project.query.filter_by(campus_id=campus.id).all())
    items_by_project = defaultdict(list)
    for item in todos_for_projects(projects):
        items_by_project[item.project.id].append(item)
    people = _people(project.owner_person_id for project in projects)

    rows = []
    for project in projects:
        stage = event_stage(project, today)
        rows.append({
            "project": project,
            "division": project.program_type.name if project.program_type else "ICC",
            "stage": stage,
            "stage_label": STAGE_LABELS[stage],
            "tone": STAGE_TONE[stage],
            "lead": _lead(project, people),
            **_counts(items_by_project.get(project.id, []), now),
        })
    rows.sort(key=lambda row: (_STAGE_ORDER.get(row["stage"], 9), row["project"].start_date or date.max))

    divisions = []
    for code, accent in DIVISIONS:
        shown = [row for row in rows if row["division"] == code]
        divisions.append({
            "code": code,
            "name": division_name(code),
            "noun": record_noun(code, plural=True),
            "accent": accent,
            "rows": shown,
        })
    return {
        "campus": campus,
        "tile": campus_tile(campus),
        "divisions": divisions,
        "totals": {
            "programs": len(rows),
            "open": sum(row["open"] for row in rows),
            "late": sum(row["late"] for row in rows),
        },
    }


def _state(item, now):
    """One plain word for where an action is, and its chip colour."""
    if item.skipped:
        return "Skipped", "complete"
    if item.done:
        return "Done", "complete"
    if item.overdue(now):
        return "Late", "overdue"
    if item.status in {"In Progress", "Submitted"}:
        return "Under way", "active"
    return "Not started", "upcoming"


def build_program_actions(project):
    """The third screen: every action on one program and who owns it."""
    today = _today()
    now = datetime.now(timezone.utc)
    items = todos_for_project(project)
    stage = event_stage(project, today)
    people = _people([project.owner_person_id])

    actions = []
    for item in items:
        label, tone = _state(item, now)
        owner_team = TEAM_LABELS.get(item.team) if item.owner is not None and item.team else None
        actions.append({
            "item": item,
            "title": item.title,
            "owner": item.who or "Not given to anyone yet",
            "owner_set": bool(item.who),
            "owner_team": owner_team,
            "due": to_campus(item.due_at if item.due_at.tzinfo else item.due_at.replace(tzinfo=timezone.utc)).date() if item.due_at else None,
            "state": label,
            "tone": tone,
        })

    owners = defaultdict(lambda: {"open": 0, "late": 0, "done": 0})
    for row, item in zip(actions, items):
        if not row["owner_set"]:
            continue
        bucket = owners[row["owner"]]
        if item.done:
            bucket["done"] += 1
        else:
            bucket["open"] += 1
            if item.overdue(now):
                bucket["late"] += 1
    by_owner = sorted(
        ({"name": name, **counts} for name, counts in owners.items()),
        key=lambda row: (-row["late"], -row["open"], row["name"].lower()),
    )

    division = project.program_type.name if project.program_type else "ICC"
    return {
        "project": project,
        "campus": project.campus,
        "tile": campus_tile(project.campus),
        "division": division,
        "division_name": division_name(division),
        "stage_label": STAGE_LABELS[stage],
        "tone": STAGE_TONE[stage],
        "lead": _lead(project, people),
        "actions": actions,
        "by_owner": by_owner,
        **_counts(items, now),
    }
