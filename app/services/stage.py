"""Where an event is in its life, read from its dates.

Nobody moves an event through stages by hand any more. Before its first
day it is coming up; between its first and last day it is happening; after
that it needs finishing until someone sends it to Faculty, and it is
finished once Faculty signs it off. The stored ``Project.status`` only
records the two things dates cannot say: "Completed" (signed off) and
"Cancelled".
"""

from __future__ import annotations

from datetime import date

COMING_UP = "coming_up"
HAPPENING = "happening"
NEEDS_FINISHING = "needs_finishing"
WAITING = "waiting"
FINISHED = "finished"
CANCELLED = "cancelled"

STAGE_LABELS = {
    COMING_UP: "Coming up",
    HAPPENING: "Happening now",
    NEEDS_FINISHING: "Needs finishing",
    WAITING: "Waiting for Faculty",
    FINISHED: "Finished",
    CANCELLED: "Cancelled",
}

#: The Tile System's four colour states, so a stage can reuse state_chip.
STAGE_TONE = {
    COMING_UP: "upcoming",
    HAPPENING: "active",
    NEEDS_FINISHING: "overdue",
    WAITING: "active",
    FINISHED: "complete",
    CANCELLED: "complete",
}

FINISHED_STATUSES = frozenset({"Completed", "Archived"})


def event_stage(project, today=None):
    today = today or date.today()
    if project.status == "Cancelled":
        return CANCELLED
    if project.status in FINISHED_STATUSES:
        return FINISHED
    if getattr(project, "finish_requested_at", None):
        return WAITING
    if project.start_date and project.start_date > today:
        return COMING_UP
    if project.end_date and project.end_date < today:
        return NEEDS_FINISHING
    return HAPPENING


def can_finish_now(project, today=None):
    """The Finish button shows from the event's last day onwards."""
    today = today or date.today()
    return event_stage(project, today) in {HAPPENING, NEEDS_FINISHING} and project.end_date <= today
