"""The drill-down the Tile System navigates: campus -> division -> event.

Three things live here and nowhere else.

**The campus roster.** Only Bangalore Central exists as a ``Campus`` row.
Kengeri, Yeshwantpur and Bannerghatta are declared here as a static roster
instead of being seeded, because seeding them would make them selectable in
every project-creation dropdown and in the scope rules -- i.e. it would
promise records that do not exist. "Not open yet" is a *product state*, not
a permission denial, so it is resolved here rather than through
``authorization``: the tile is rendered as plain content with nothing
focusable, and no 403 path is involved.

**The four reserved states.** ``Project.status`` has six values and the
Tile System has four chips, so the mapping is made once, here, and both the
event grid and the dashboards read it. A project past its end date that
nobody has closed is ``overdue`` -- derived, never stored.

**Tile presentation data.** Campus/division identity colours travel with the
tile so a family keeps its hue from the tile you click through to the
dashboard you land on. Endpoint *names* and params are returned rather than
URLs: ``url_for`` needs a request context these callers do not always have
(see the same constraint on ``action_queue.build_action_queue``).
"""

from __future__ import annotations

from datetime import date

from app.models.erp import Person
from app.models.project import Campus
from app.services.scope import visible_projects


# ── Campuses ────────────────────────────────────────────────────────────

# `aliases` exists because the one real row carries code "CEN" while the
# institution calls it BCC; matching on either avoids a data migration for
# what is purely a label.
CAMPUS_ROSTER = (
    {"code": "BCC", "name": "Central", "subtitle": "Bangalore Central Campus", "aliases": ("BCC", "CEN"), "accent": "brass", "open": True},
    {"code": "BKC", "name": "Kengeri", "subtitle": "Campus data arrives in a later release", "aliases": ("BKC", "KEN"), "accent": None, "open": False},
    {"code": "BYC", "name": "Yeshwantpur", "subtitle": "Campus data arrives in a later release", "aliases": ("BYC", "YPR"), "accent": None, "open": False},
    {"code": "BRC", "name": "Bannerghatta", "subtitle": "Campus data arrives in a later release", "aliases": ("BRC", "BGR"), "accent": None, "open": False},
)


def _match_campus(entry, campus_rows):
    for campus in campus_rows:
        if (campus.code or "").upper() in entry["aliases"]:
            return campus
    for campus in campus_rows:
        if entry["name"].lower() in (campus.name or "").lower():
            return campus
    return None


def campus_tiles(user):
    """The four campus tiles, in roster order.

    An open campus with no visible project still renders as open -- the
    campus is live, it simply has nothing in it yet, and saying "opening
    soon" there would be a lie.
    """
    campus_rows = Campus.query.order_by(Campus.name).all()
    projects = visible_projects(user)
    tiles = []
    for entry in CAMPUS_ROSTER:
        campus = _match_campus(entry, campus_rows) if entry["open"] else None
        scoped = [p for p in projects if campus and p.campus_id == campus.id]
        tiles.append({
            "code": entry["code"],
            "name": entry["name"],
            "subtitle": entry["subtitle"],
            "accent": entry["accent"],
            "open": bool(entry["open"] and campus),
            "campus": campus,
            "public_id": campus.public_id if campus else None,
            "divisions": len({p.program_type_id for p in scoped}),
            "events": len(scoped),
        })
    return tiles


def open_campus_public_ids(user):
    return {tile["public_id"] for tile in campus_tiles(user) if tile["open"]}


# ── Divisions ───────────────────────────────────────────────────────────

DIVISIONS = {
    "igp": {"slug": "igp", "program": "IGP", "name": "India Gateway Program", "short": "IGP", "accent": "indigo", "noun": "programmes"},
    "icc": {"slug": "icc", "program": "ICC", "name": "International Christite Community", "short": "ICC", "accent": "pine", "noun": "events"},
}


def division_tiles(user, campus):
    projects = [p for p in visible_projects(user) if p.campus_id == campus.id]
    tiles = []
    for division in DIVISIONS.values():
        scoped = [p for p in projects if p.program_type.name == division["program"]]
        counts = state_counts(scoped)
        tiles.append({
            **division,
            "total": len(scoped),
            "active": counts["active"] + counts["overdue"],
            "upcoming": counts["upcoming"],
        })
    return tiles


# ── The four reserved states ────────────────────────────────────────────

_UPCOMING_STATUSES = frozenset({"Draft", "Planned"})
_ACTIVE_STATUSES = frozenset({"Active", "Closing"})
_CLOSED_STATUSES = frozenset({"Completed", "Cancelled"})

STATE_LABELS = {"upcoming": "Upcoming", "active": "Active", "complete": "Complete", "overdue": "Overdue"}
STATE_ORDER = ("active", "overdue", "upcoming", "complete")
FILTER_SEGMENTS = ("all", "active", "upcoming", "complete")


def event_state(project, today=None):
    """One of the four reserved states.

    ``overdue`` is derived from the end date rather than stored: a project
    still Active after its last day is the single thing this grid exists to
    surface, and no column in ``projects`` records it.
    """
    today = today or date.today()
    if project.status in _CLOSED_STATUSES:
        return "complete"
    if project.end_date and project.end_date < today:
        return "overdue"
    if project.status in _ACTIVE_STATUSES:
        return "active"
    if project.status in _UPCOMING_STATUSES:
        return "upcoming"
    return "active"


def state_counts(projects, today=None):
    counts = {key: 0 for key in STATE_LABELS}
    for project in projects:
        counts[event_state(project, today)] += 1
    return counts


def matches_filter(state, segment):
    """``active`` deliberately includes ``overdue``: an overdue event is
    still in flight, and hiding it from the Active filter would hide the
    one thing somebody filtering for Active most needs to see."""
    if segment in (None, "", "all"):
        return True
    if segment == "active":
        return state in ("active", "overdue")
    return state == segment


def filter_counts(projects, today=None):
    counts = state_counts(projects, today)
    return {
        "all": len(projects),
        "active": counts["active"] + counts["overdue"],
        "upcoming": counts["upcoming"],
        "complete": counts["complete"],
    }


def event_cards(user, campus, division, segment=None, today=None):
    """Projects in one division of one campus, newest first, as cards.

    Returns ``(cards, counts)``. The counts describe the whole division and
    do not change as the filter does -- a segment reading "Upcoming 5" has
    to be true before you click it.
    """
    projects = [
        project for project in visible_projects(user)
        if project.campus_id == campus.id and project.program_type.name == division["program"]
    ]
    counts = filter_counts(projects, today)
    # Project has owner_person_id but no owner_person relationship; one
    # query beats a lazy load per card.
    owner_ids = {project.owner_person_id for project in projects if project.owner_person_id}
    owners = {
        person.id: person.display_name
        for person in (Person.query.filter(Person.id.in_(owner_ids)).all() if owner_ids else [])
    }
    cards = []
    for project in projects:
        state = event_state(project, today)
        if not matches_filter(state, segment):
            continue
        cards.append({
            "project": project,
            "state": state,
            "state_label": STATE_LABELS[state],
            "owner": owners.get(project.owner_person_id),
            "progress": task_progress(project),
        })
    cards.sort(key=lambda card: (STATE_ORDER.index(card["state"]), -(card["project"].start_date.toordinal() if card["project"].start_date else 0)))
    return cards, counts


_SETTLED_TASK_STATUSES = frozenset({"Approved", "Waived", "Completed"})


def task_progress(project):
    """``(done, total)`` across the work items an event actually tracks, or
    ``None`` when it tracks none -- a 0/0 bar reads as "nothing done"."""
    items = list(project.work_tasks)
    for checklist in project.checklists:
        items.extend(checklist.item_statuses)
    if not items:
        return None
    done = sum(1 for item in items if item.status in _SETTLED_TASK_STATUSES)
    return done, len(items)
