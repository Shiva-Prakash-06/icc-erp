"""The two dashboards, and the Analytics tab inside one event.

The Tile System deleted the Overview tab. An overview restated facts that
lived one tab away; the questions it was really there to answer -- how much
is committed, what is late, what is unassigned -- need aggregation, which is
what this module does. Every screen it feeds is four KPIs and one chart: a
second chart means the dashboard is answering two questions and should be
scoped down instead.

Two rules the callers depend on:

* **A KPI that has a destination returns one.** ``href`` is an endpoint name
  plus params, never a URL -- ``url_for`` needs a request context this
  module is not guaranteed to have (the same constraint that shaped
  ``action_queue.build_action_queue``). A KPI with no destination returns
  ``None`` and is rendered as plain text rather than given a false
  affordance.
* **Series are the four reserved states, in one fixed order.** They are the
  status palette being used for status, which is what it is reserved for.
  Nothing here ever reaches for a categorical hue.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.erp import ReportSnapshot
from app.services.formatting import percent, pluralise, short_money
from app.services.hierarchy import DIVISIONS, STATE_LABELS, event_state, state_counts
from app.services.scope import visible_projects

# Fixed order, bottom-of-the-stack first. Complete leads because a finished
# stack should read as one settled block rather than a scatter.
CHART_SERIES = ("complete", "active", "upcoming", "overdue")

_OPEN_ITEM_STATUSES = frozenset({"Not Started", "In Progress", "Blocked", "Submitted"})
_SETTLED_ITEM_STATUSES = frozenset({"Approved", "Waived", "Completed"})
_REJECTED_ITEM_STATUSES = frozenset({"Rejected"})


def _due_date(item):
    """``due_at`` is a timestamp on both WorkTask and ChecklistItemStatus;
    the row only ever shows the date, and comparing a date to a date is what
    keeps "due today" from reading as late at 00:01."""
    due = getattr(item, "due_at", None)
    return due.date() if due is not None else None


def _item_state(item, deadline=None, today=None):
    """Map a work item's status onto the four reserved states.

    ``Rejected`` is deliberately ``overdue`` rather than a fifth chip: it is
    the other thing that needs somebody today, and the Tile System has four
    states on purpose.
    """
    if item.status in _SETTLED_ITEM_STATUSES:
        return "complete"
    if item.status in _REJECTED_ITEM_STATUSES:
        return "overdue"
    if deadline and today and deadline < today:
        return "overdue"
    if item.status == "Not Started":
        return "upcoming"
    return "active"


def row_state(item, today=None):
    """The state a work row paints, for any record that carries a ``status``.

    Templates call this with the item alone; the deadline is inferred from
    whichever date column that record actually has (``due_at`` on tasks and
    checklist requirements, ``expires_on`` on documents), so one helper
    covers every list in the workspace instead of each tab re-deriving it
    and disagreeing about what "late" means.
    """
    deadline = _due_date(item) or getattr(item, "expires_on", None)
    return _item_state(item, deadline, today or date.today())


def _project_items(project, today=None):
    """Every item the four tabs show, tagged with its tab and its state."""
    today = today or date.today()
    items = []
    for task in project.work_tasks:
        items.append(("Logistics", _item_state(task, _due_date(task), today)))
    for checklist in project.checklists:
        for status in checklist.item_statuses:
            items.append(("Logistics", _item_state(status, _due_date(status), today)))
    for request in project.operational_requests:
        items.append(("Finance", _item_state(request, None, today)))
    for line in project.budget_lines:
        items.append(("Finance", _item_state(line, None, today)))
    for entry in project.reimbursement_entries:
        items.append(("Finance", "complete" if entry.status in ("Approved", "Paid") else "active"))
    for document in project.document_records:
        items.append(("Documents", _item_state(document, document.expires_on, today)))
    for assignment in project.team_assignments:
        items.append(("People", "complete" if assignment.status == "Active" else "upcoming"))
    return items


def _decimal(value):
    return Decimal(value or 0)


def _budget(projects):
    """``(committed, estimated)``. Committed falls back to approved, then to
    actual: a line that was approved but never explicitly committed is money
    the office has already promised, and treating it as zero made the KPI
    read far lower than the real exposure."""
    committed = estimated = Decimal(0)
    for project in projects:
        for line in project.budget_lines:
            estimated += _decimal(line.estimated_amount)
            committed += _decimal(line.committed_amount or line.approved_amount or line.actual_amount)
    return committed, estimated


def _stack(rows):
    """Turn ``[(label, {state: n})]`` into drawable bars.

    Widths are percentages of the widest row, so bars are comparable across
    rows; a 2px gap between segments is applied by the template.
    """
    biggest = max((sum(counts.values()) for _, counts in rows), default=0) or 1
    bars = []
    for label, counts in rows:
        total = sum(counts.values())
        segments = []
        for state in CHART_SERIES:
            if counts.get(state):
                segments.append({"state": state, "label": STATE_LABELS[state], "count": counts[state],
                                 "width": round(counts[state] * 100 / biggest, 2)})
        bars.append({"label": label, "total": total, "segments": segments})
    return bars


# ── Division dashboard: every event in IGP, or every event in ICC ────────

def division_dashboard(user, division, today=None):
    today = today or date.today()
    projects = [p for p in visible_projects(user) if p.program_type.name == division["program"]]
    states = state_counts(projects, today)

    open_decisions = 0
    overdue_items = 0
    for project in projects:
        for _, state in _project_items(project, today):
            if state == "overdue":
                overdue_items += 1
        open_decisions += sum(1 for line in project.budget_lines if line.status not in ("Approved", "Rejected"))
        open_decisions += sum(1 for r in project.operational_requests if r.status not in ("Completed", "Cancelled", "Rejected"))

    committed, estimated = _budget(projects)
    project_ids = [p.id for p in projects]
    reports = ReportSnapshot.query.filter(ReportSnapshot.project_id.in_(project_ids)).count() if project_ids else 0
    closed = states["complete"]
    # "In flight" is the honest name for what this counts. `event_state`
    # calls a Closing project active (it still needs work) and an Active one
    # past its end date overdue, so the number is neither the count of
    # `status == "Active"` rows nor one anybody can reproduce from the
    # status column -- which is exactly why the old "Active programmes"
    # tile opened an empty list. Audit P0-03.
    in_flight = states["active"] + states["overdue"]

    kpis = [
        {"label": division["noun"].capitalize() + " in flight", "value": in_flight,
         "foot_before": "of ", "foot_value": len(projects), "foot_after": " this year",
         # `state`, not `status`: this is the filter that reproduces the
         # number above, including Closing and overdue records.
         "href": ("erp.projects", {"state": "active"}) if in_flight else None},
        # "across 1 late programmes" was the grammar the old string produced.
        # Both halves also say plainly which thing is late: a programme past
        # its end date is not the same as a work item past its due date, and
        # reading 0 beside 1 with no distinction is what made the pair look
        # broken.
        {"label": "Work items overdue", "value": overdue_items, "tone": "overdue",
         "foot_before": "in ", "foot_value": pluralise(states["overdue"], division["noun"][:-1] + " past its end date",
                                                       division["noun"] + " past their end date"), "foot_after": "",
         "href": ("erp.projects", {"state": "active"}) if overdue_items else None},
        {"label": "Budget committed", "value": percent(committed, estimated),
         "foot_before": "", "foot_value": short_money(committed), "foot_after": " of " + short_money(estimated),
         "href": None},
        # Both halves describe the same population -- every record in the
        # division -- so the pair reads as a sentence. The old foot said
        # "of 0 closed programmes" beside "2 reports filed", inviting the
        # reader to divide two numbers that were never a fraction. P0-04.
        {"label": "Reports filed", "value": reports,
         "foot_before": "", "foot_value": f"{closed} of {len(projects)}", "foot_after": " " + division["noun"] + " closed",
         "href": None},
    ]

    # One row per event, newest first, capped: a stacked bar with thirty rows
    # is a table nobody can read, and the grid one click away IS the table.
    rows = []
    for project in sorted(projects, key=lambda p: p.start_date or date.min, reverse=True)[:8]:
        counts = {}
        for _, state in _project_items(project, today):
            counts[state] = counts.get(state, 0) + 1
        if counts:
            rows.append((project.title, counts))

    return {
        "division": division,
        "kpis": kpis,
        "chart": {
            "title": "Work items by state",
            "note": f"{sum(bar['total'] for bar in _stack(rows))} items · {len(rows)} most recent",
            "bars": _stack(rows),
        } if rows else None,
        "projects": projects,
    }


def division_dashboards(user, today=None):
    """Both dashboard tiles, for the /analytics screen."""
    tiles = []
    for division in DIVISIONS.values():
        projects = [p for p in visible_projects(user) if p.program_type.name == division["program"]]
        states = state_counts(projects, today)
        tiles.append({**division, "total": len(projects),
                      "active": states["active"] + states["overdue"], "complete": states["complete"]})
    return tiles


# ── Event dashboard: the Analytics tab inside one record ─────────────────

def event_dashboard(project, today=None, blockers=None):
    """``blockers`` is the caller's ``closure_blockers(project)``.

    It is passed in rather than recomputed because the Analytics tab shows
    that exact list directly underneath this KPI: counting mandatory tasks
    and documents here instead gave a smaller number than the list beside
    it, which is the one thing a dashboard must never do.
    """
    today = today or date.today()
    items = _project_items(project, today)
    overdue = sum(1 for _, state in items if state == "overdue")
    done = sum(1 for _, state in items if state == "complete")
    committed, estimated = _budget([project])
    team = sum(1 for a in project.team_assignments if a.status == "Active")
    blocking = len(blockers) if blockers is not None else 0

    kpis = [
        {"label": "Items complete", "value": f"{done}/{len(items)}" if items else "—",
         "foot_before": "", "foot_value": f"{done * 100 // len(items)}%" if items else "0%", "foot_after": " of everything tracked", "href": None},
        {"label": "Overdue", "value": overdue, "tone": "overdue",
         "foot_before": "", "foot_value": blocking, "foot_after": " still block closure", "href": None},
        {"label": "Budget committed", "value": percent(committed, estimated),
         "foot_before": "", "foot_value": short_money(committed), "foot_after": " of " + short_money(estimated),
         "href": ("erp.project_detail", {"public_id": project.public_id, "tab": "finance"})},
        {"label": "Team", "value": team,
         "foot_before": "", "foot_value": len(project.buddy_assignments), "foot_after": " buddy pairings",
         "href": ("erp.project_detail", {"public_id": project.public_id, "tab": "people"})},
    ]

    rows = []
    for tab in ("Logistics", "Finance", "Documents", "People"):
        counts = {}
        for item_tab, state in items:
            if item_tab == tab:
                counts[state] = counts.get(state, 0) + 1
        if counts:
            rows.append((tab, counts))

    return {
        "kpis": kpis,
        "chart": {
            "title": "Items by state",
            "note": f"{len(items)} items · {project.code or project.title}",
            "bars": _stack(rows),
        } if rows else None,
    }
