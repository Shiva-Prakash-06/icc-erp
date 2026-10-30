"""Teams: who a to-do item is for when it is not for one named person.

An item on any event can be handed to a team -- "Media", "Culturals" and so
on -- instead of a person. Whoever holds that team's role sees the item on
their own home screen. This is how the Media and Culturals heads get work:
they own no events, and their access to an event extends exactly as far as
the items handed to their team (see :func:`can_contribute`).

The keys are stored on ``WorkTask.assigned_team`` and
``ChecklistItemStatus.assigned_team``.
"""

from __future__ import annotations

from app.database import db
from app.models.erp import ChecklistInstance, ChecklistItemStatus, WorkTask


EVENTS = "events"
MEDIA = "media"
CULTURALS = "culturals"
IGP = "igp"
USC = "usc"
FACULTY = "faculty"

#: Display order and plain-language names, for the "Who?" picker.
TEAM_LABELS = {
    EVENTS: "Events team",
    MEDIA: "Media team",
    CULTURALS: "Culturals team",
    IGP: "IGP team",
    USC: "USC",
    FACULTY: "Faculty",
}

ROLE_TEAM = {
    "ICC_EVENTS_HEAD": EVENTS,
    "ICC_MEDIA_HEAD": MEDIA,
    "ICC_CULTURALS_HEAD": CULTURALS,
    "IGP_HEAD": IGP,
    "ICC_SECRETARY_USC": USC,
    "OIA_FACULTY_ADMINISTRATOR": FACULTY,
    "FACULTY_COORDINATOR": FACULTY,
}

#: Roles whose only way into an event is an item handed to their team.
CONTRIBUTOR_ROLES = {"ICC_MEDIA_HEAD", "ICC_CULTURALS_HEAD"}

# Checked in order: "Media & Culturals" is a Media item first.
_LABEL_HINTS = (
    ("media", MEDIA), ("poster", MEDIA), ("photo", MEDIA), ("video", MEDIA), ("publicity", MEDIA),
    ("cultural", CULTURALS), ("performance", CULTURALS),
    ("igp", IGP),
    ("usc", USC), ("secretary", USC),
    ("faculty", FACULTY),
    ("event", EVENTS),
)


def team_from_label(*labels):
    """Best guess at a team from free-text owner or category labels.

    Checklist templates carry the owner as text ("Media", "IGP office",
    "Faculty coordinator"). Returns ``None`` when nothing matches, which
    leaves the item with whoever owns the event.
    """
    for label in labels:
        text = (label or "").strip().lower()
        if not text:
            continue
        for hint, team in _LABEL_HINTS:
            if hint in text:
                return team
    return None


def user_teams(user):
    """The team keys ``user`` answers for, from their active assignments."""
    from app.services.authorization import _active_assignments

    if not user or getattr(user, "status", None) != "Approved":
        return set()
    return {ROLE_TEAM[a.role_code] for a in _active_assignments(user) if a.role_code in ROLE_TEAM}


def _contributor_assignments(user):
    from app.services.authorization import _active_assignments

    if not user or getattr(user, "status", None) != "Approved":
        return []
    return [a for a in _active_assignments(user) if a.role_code in CONTRIBUTOR_ROLES]


def _team_item_project_ids(teams):
    """Ids of every project with at least one item handed to one of ``teams``."""
    if not teams:
        return set()
    task_ids = {
        row[0] for row in db.session.query(WorkTask.project_id).filter(WorkTask.assigned_team.in_(teams)).distinct()
    }
    checklist_ids = {
        row[0]
        for row in db.session.query(ChecklistInstance.project_id)
        .join(ChecklistItemStatus, ChecklistItemStatus.checklist_instance_id == ChecklistInstance.id)
        .filter(ChecklistItemStatus.assigned_team.in_(teams))
        .distinct()
    }
    return task_ids | checklist_ids


def _within(assignment, project):
    # A contributor crosses wings and the ICC/IGP line on purpose, but never
    # campuses or academic years: those still bound what they can reach.
    if assignment.campus_id and assignment.campus_id != project.campus_id:
        return False
    if assignment.academic_year_id and assignment.academic_year_id != project.academic_year_id:
        return False
    return True


def can_contribute(user, project):
    """Whether a contributor (Media or Culturals head) may work on ``project``.

    True only when the project has an item handed to their team and the
    project sits inside their campus and year. This grants the event header,
    their team's items and the files they add -- never the people list,
    money or restricted links, which stay behind ``manage_projects``.
    """
    if project is None:
        return False
    for assignment in _contributor_assignments(user):
        team = ROLE_TEAM[assignment.role_code]
        if _within(assignment, project) and project.id in _team_item_project_ids({team}):
            return True
    return False


def contributor_projects(user):
    """Every project a contributor can reach through their team's items."""
    from app.models.project import Project

    assignments = _contributor_assignments(user)
    if not assignments:
        return []
    teams = {ROLE_TEAM[a.role_code] for a in assignments}
    ids = _team_item_project_ids(teams)
    if not ids:
        return []
    projects = Project.query.filter(Project.id.in_(ids)).order_by(Project.start_date.desc()).all()
    return [p for p in projects if any(_within(a, p) for a in assignments)]
