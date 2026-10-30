"""Canonical implementation for turning a legacy role label + scope selection
into a real, scoped ``RoleAssignment`` row. Used by the account-approval UI
(``dashboard.py``) and by CLI backfill commands (``app/cli.py``) alike, so
there is exactly one place that encodes the scope rules for each role.
"""

from __future__ import annotations

from app.database import db
from app.models.erp import OperatingUnit, RoleAssignment, Wing
from app.models.project import AcademicYear, Campus, Project
from app.services.authorization import LEGACY_ROLE_MAP, has_permission, invalidate_assignment_cache


HEAD_ROLES_WITHOUT_WING = {"ICC_EVENTS_HEAD", "ICC_MEDIA_HEAD", "ICC_CULTURALS_HEAD"}

#: The roles Faculty can give someone, in the order the picker shows them.
#: Every other role code still resolves (old rows keep working) but is no
#: longer handed out: associates, buddies, participants and programme leads
#: are all volunteers now, and Faculty sees what the auditor role saw.
ASSIGNABLE_ROLES = [
    "Volunteer",
    "ICC Events Head",
    "ICC Media Head",
    "ICC Culturals Head",
    "IGP Head",
    "ICC Secretary / USC",
    "Faculty",
]


def replace_scoped_assignment(user, legacy_role, scope, actor):
    """Deactivate `user`'s existing active assignments and create a new one
    for `legacy_role`, resolving scope fields from `scope` (a dict-like
    object supporting `.get(key)`, e.g. a Flask `request.form`). `actor` is
    the user performing the assignment (used for `delegated_by_id` and for
    the sensitive-links permission check) -- pass explicitly rather than
    reading Flask's `g` so this is callable from CLI/backfill contexts too.
    """
    role_code = LEGACY_ROLE_MAP.get(legacy_role)
    if not role_code:
        raise ValueError("Selected role is not supported by scoped authorization.")
    unit = wing = None
    if role_code.startswith("ICC_"):
        unit = OperatingUnit.query.filter_by(code="ICC").first()
    elif role_code.startswith("IGP_"):
        unit = OperatingUnit.query.filter_by(code="IGP").first()
    # Head roles are no longer pinned to a wing. The Events head runs every
    # ICC event (unwinged ones used to be invisible to them), and the Media
    # and Culturals heads reach events through the items handed to their
    # team, across wings and across ICC/IGP -- see app/services/teams.py.
    if role_code not in HEAD_ROLES_WITHOUT_WING:
        requested_wing = Wing.query.filter_by(public_id=scope.get("wing_public_id")).first() if scope.get("wing_public_id") else None
        if requested_wing:
            if not unit or requested_wing.operating_unit_id != unit.id:
                raise ValueError("The selected wing is outside this role's operating unit.")
            wing = requested_wing
    academic_year = AcademicYear.query.filter_by(public_id=scope.get("academic_year_public_id")).first() if scope.get("academic_year_public_id") else None
    project = Project.query.filter_by(public_id=scope.get("project_public_id")).first() if scope.get("project_public_id") else None
    campus = Campus.query.filter_by(public_id=scope.get("campus_public_id")).first() if scope.get("campus_public_id") else user.campus
    if project:
        if unit and project.operating_unit_id != unit.id:
            raise ValueError("The selected project is outside this role's operating unit.")
        if wing and project.wing_id != wing.id:
            raise ValueError("The selected project is outside this role's wing.")
        campus = project.campus
        academic_year = project.academic_year
    annual_roles = {"ICC_SECRETARY_USC", "ICC_EVENTS_HEAD", "ICC_MEDIA_HEAD", "ICC_CULTURALS_HEAD", "ICC_ASSOCIATE", "IGP_HEAD"}
    if role_code in annual_roles and not academic_year:
        # Faculty promotes someone for this year; nobody should have to say so.
        academic_year = AcademicYear.query.filter_by(is_current=True).first() or \
            AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
    if role_code in annual_roles and not academic_year:
        raise ValueError("Annual ICC/IGP leadership and associate assignments require an academic year.")
    if role_code == "ICC_ASSOCIATE" and not wing:
        raise ValueError("ICC Associate assignments require a wing.")
    if role_code == "IGP_PROGRAM_LEAD" and not project:
        raise ValueError("IGP Program Lead assignments require a specific program.")
    # A volunteer needs no project: what they see is decided by the events
    # they are listed on (TeamAssignment), not by the assignment's scope.
    if role_code in {"BUDDY", "PARTICIPANT"} and not project:
        raise ValueError("Buddy and participant access requires a specific project/program.")
    platform_scope = role_code == "SYSTEM_ADMINISTRATOR" or scope.get("platform_scope") == "on"
    if platform_scope and role_code not in {"SYSTEM_ADMINISTRATOR", "OIA_FACULTY_ADMINISTRATOR", "FACULTY_COORDINATOR"}:
        raise ValueError("Only system and OIA faculty administrators may receive platform scope.")
    sensitive_requested = scope.get("can_view_sensitive_links") == "on"
    sensitive_allowed = role_code in {"OIA_FACULTY_ADMINISTRATOR", "FACULTY_COORDINATOR", "IGP_HEAD"}
    if sensitive_requested and (not sensitive_allowed or not has_permission(actor, "sensitive_links", sensitive=True)):
        raise ValueError("The selected role or approving user cannot grant restricted-reference access.")
    # Resolve and validate the complete replacement before touching the current
    # grants.  A rejected form submission must never leave an account with its
    # valid assignment deactivated in the still-live SQLAlchemy transaction.
    for existing_assignment in RoleAssignment.query.filter_by(user_id=user.id, is_active=True):
        existing_assignment.is_active = False
    assignment = RoleAssignment(
        user_id=user.id,
        role_code=role_code,
        campus_id=None if platform_scope else getattr(campus, "id", None),
        operating_unit_id=getattr(unit, "id", None),
        wing_id=getattr(wing, "id", None),
        academic_year_id=getattr(academic_year, "id", None),
        project_id=getattr(project, "id", None),
        delegated_by_id=getattr(actor, "id", None),
        assignment_reason="Account administration approval",
        can_view_sensitive_links=sensitive_requested,
    )
    db.session.add(assignment)
    db.session.flush()
    # Later permission checks in this same request must see the new grant.
    invalidate_assignment_cache(user)
    return assignment


# ──────────────────────────────────────────────────────────────────────────
# First-run onboarding: role → welcome copy, tour steps, checklist tasks.
#
# Four audiences: Faculty, who says yes (the approve permission); the people
# who run events (heads and the USC); the Media and Culturals heads, who get
# work handed to their team; and volunteers, who only look. Each tour is at
# most three steps, all on the home page or the rail, in plain words.
#
# `url_for` is unavailable in a service -- these run in tests and jobs with
# only an app context -- so every step and task carries an endpoint name
# plus params, and the template resolves them. See app/templates/_onboarding.html.
# ──────────────────────────────────────────────────────────────────────────

ONBOARDING_COORDINATOR = "coordinator"
ONBOARDING_OFFICE = "office"
ONBOARDING_CONTRIBUTOR = "contributor"
ONBOARDING_VOLUNTEER = "volunteer"

_STEPS = {
    "ok": {
        "title": "These need your OK",
        "body": "Money, finished events and the website. Press Approve, or Not now if something is wrong.",
        "placement": "bottom",
    },
    "mywork": {
        "title": "This is your list",
        "body": "Everything you or your team has to do, from every event. Today comes first.",
        "placement": "bottom",
    },
    "tick": {
        "title": "Press the circle when it is done",
        "body": "One press ticks it off. Nothing else to fill in.",
        "placement": "bottom",
    },
    "file": {
        "title": "Hand in a file here",
        "body": "Posters, photos, the report. Press Add file, pick the file, and the item is ticked for you.",
        "placement": "bottom",
    },
    "new": {
        "title": "Make a new event",
        "body": "A name and a date are enough. The to-do list is made for you.",
        "placement": "right",
    },
    "activities": {
        "title": "Your events",
        "body": "When, where, your job and your buddy. Open one to see all its times.",
        "placement": "bottom",
    },
    "nav": {
        "title": "Everything else is here",
        "body": "All events, your account and alerts. On a phone this runs along the bottom.",
        "placement": "right",
    },
}

# A step whose target is not on the page is skipped at runtime rather than
# drawn as an orphan tooltip: someone with nothing to tick never sees "tick".
ONBOARDING_TOURS = {
    ONBOARDING_COORDINATOR: ["ok", "tick", "nav"],
    ONBOARDING_OFFICE: ["mywork", "tick", "new"],
    ONBOARDING_CONTRIBUTOR: ["mywork", "tick", "file"],
    ONBOARDING_VOLUNTEER: ["activities", "nav"],
}

ONBOARDING_WELCOME = {
    ONBOARDING_COORDINATOR: {
        "title": "Your work, on one page",
        "body": "You say yes to money, finished events and the website. The teams do the rest.",
        "bullets": [
            "Home shows what needs your OK. Approve takes one press.",
            "Press the circle next to a to-do item to tick it off.",
            "Each event has one page. Open a part of it only when you need it.",
        ],
    },
    ONBOARDING_OFFICE: {
        "title": "Your work, on one page",
        "body": "You run events. Home shows what is left to do, today first.",
        "bullets": [
            "Press the circle next to a to-do item to tick it off.",
            "A new event needs only a name and a date.",
            "Each event has one page. Open a part of it only when you need it.",
        ],
    },
    ONBOARDING_CONTRIBUTOR: {
        "title": "Your team's work, on one page",
        "body": "Events hand your team things to do, like posters and photos.",
        "bullets": [
            "Home lists your team's to-do items from every event.",
            "Press the circle to tick one off.",
            "Need to hand in a file? Press Add file and pick it.",
        ],
    },
    ONBOARDING_VOLUNTEER: {
        "title": "Your activities",
        "body": "See the events you are on: when, where, your job and your buddy.",
        "bullets": [
            "Home lists your events, soonest first.",
            "Open one to see all its times.",
        ],
    },
}

# Each task names the signal that completes it (resolved in
# app/services/home.py) and the page where it is done. Volunteers have none:
# there is nothing for them to set up.
ONBOARDING_CHECKLISTS = {
    ONBOARDING_COORDINATOR: [
        {"key": "decision", "label": "Approve something, or say not now", "endpoint": "dashboard.index", "params": {}},
        {"key": "project_opened", "label": "Open an event", "endpoint": "erp.projects", "params": {}},
    ],
    ONBOARDING_OFFICE: [
        {"key": "event_created", "label": "Make an event", "endpoint": "erp.new_project", "params": {}},
        {"key": "todo_ticked", "label": "Tick off a to-do item", "endpoint": "dashboard.index", "params": {}},
        {"key": "roll_call", "label": "Take attendance once", "endpoint": "erp.projects", "params": {}},
    ],
    ONBOARDING_CONTRIBUTOR: [
        {"key": "todo_ticked", "label": "Tick off a to-do item", "endpoint": "dashboard.index", "params": {}},
        {"key": "project_opened", "label": "Open an event", "endpoint": "erp.projects", "params": {}},
    ],
}

# Signals the browser reports (nothing else in the database records them).
ONBOARDING_CLIENT_SIGNALS = {"search_used", "project_opened", "audit_viewed"}


def onboarding_audience(user):
    """Faculty first, then the people who run events, then the team heads
    who are handed work; everyone else is a volunteer."""
    from app.services.authorization import has_any_permission

    if has_any_permission(user, "approve"):
        return ONBOARDING_COORDINATOR
    if any(has_any_permission(user, permission) for permission in ("manage_projects", "manage_imports", "audit")):
        return ONBOARDING_OFFICE
    if has_any_permission(user, "contribute_team"):
        return ONBOARDING_CONTRIBUTOR
    return ONBOARDING_VOLUNTEER


def onboarding_tour_steps(audience):
    """Return the ordered step definitions for an audience, each carrying the
    `data-tour` target it anchors to."""
    return [{"target": key, **_STEPS[key]} for key in ONBOARDING_TOURS.get(audience, [])]


# ── Whose view is this? ─────────────────────────────────────────────────
# Audit finding P1-10: an Events Head, a Media Head and the USC each saw a
# near-identical directory and nothing on screen said why those records and
# not others. The answer is always the active role assignment and the scope
# on it, which the server already holds -- it was simply never rendered.

#: The rail is 72px wide, so the full title needs a short form beside it.
#: The full one is still what the phone drawer, the account screen and
#: assistive tech read; this is only the badge.
ROLE_SHORT = {
    "SYSTEM_ADMINISTRATOR": "Admin",
    "OIA_FACULTY_ADMINISTRATOR": "Faculty",
    "FACULTY_COORDINATOR": "Faculty",
    "ICC_SECRETARY_USC": "USC",
    "ICC_EVENTS_HEAD": "Events head",
    "ICC_CULTURALS_HEAD": "Culturals head",
    "ICC_MEDIA_HEAD": "Media head",
    "ICC_ASSOCIATE": "Volunteer",
    "IGP_HEAD": "IGP head",
    "IGP_PROGRAM_LEAD": "Volunteer",
    "VOLUNTEER": "Volunteer",
    "BUDDY": "Volunteer",
    "PARTICIPANT": "Volunteer",
    "AUDITOR": "Read-only",
}

ROLE_TITLES = {
    "SYSTEM_ADMINISTRATOR": "System administrator",
    "OIA_FACULTY_ADMINISTRATOR": "Faculty",
    "FACULTY_COORDINATOR": "Faculty",
    "ICC_SECRETARY_USC": "ICC Secretary / USC",
    "ICC_EVENTS_HEAD": "ICC Events head",
    "ICC_CULTURALS_HEAD": "ICC Culturals head",
    "ICC_MEDIA_HEAD": "ICC Media head",
    "ICC_ASSOCIATE": "Volunteer",
    "IGP_HEAD": "IGP head",
    "IGP_PROGRAM_LEAD": "Volunteer",
    "VOLUNTEER": "Volunteer",
    "BUDDY": "Volunteer",
    "PARTICIPANT": "Volunteer",
    "AUDITOR": "Auditor (read-only)",
}


def role_context(user):
    """One line per active assignment: the title, then what it covers.

    Returns ``[{"title": ..., "scope": ..., "sensitive": bool}]``, newest
    scope first. Never invents an assignment: a user with none gets an empty
    list and the shell says so rather than implying a permission.
    """
    from app.services.authorization import LEGACY_ROLE_MAP, _active_assignments
    from app.services.glossary import division_name

    # RoleAssignment carries scope as foreign keys with no relationships
    # declared, so each one is resolved here rather than by adding ORM
    # attributes for a caption.
    def _load(model, identifier):
        return db.session.get(model, identifier) if identifier else None

    rows = []
    for assignment in _active_assignments(user):
        scope_parts = []
        campus = _load(Campus, assignment.campus_id)
        unit = _load(OperatingUnit, assignment.operating_unit_id)
        wing = _load(Wing, assignment.wing_id)
        year = _load(AcademicYear, assignment.academic_year_id)
        project = _load(Project, assignment.project_id)
        if campus is not None:
            scope_parts.append(campus.name)
        if unit is not None:
            scope_parts.append(division_name(unit))
        if wing is not None:
            scope_parts.append(f"{wing.name} wing")
        if year is not None:
            scope_parts.append(year.name)
        if project is not None:
            scope_parts.append(project.title or project.code)
        rows.append({
            "title": ROLE_TITLES.get(assignment.role_code, assignment.role_code.replace("_", " ").title()),
            "short": ROLE_SHORT.get(assignment.role_code, assignment.role_code.split("_")[0].title()),
            # "Every campus" is the truthful reading of an unscoped
            # assignment; an empty string would read as a missing value.
            "scope": " · ".join(scope_parts) if scope_parts else "Every campus and division",
            "sensitive": bool(assignment.can_view_sensitive_links),
        })
    if not rows:
        legacy = LEGACY_ROLE_MAP.get(getattr(user, "role", None))
        if legacy:
            rows.append({"title": ROLE_TITLES.get(legacy, legacy.replace("_", " ").title()),
                         "short": ROLE_SHORT.get(legacy, legacy.split("_")[0].title()),
                         "scope": "No scope recorded", "sensitive": False})
    return rows
