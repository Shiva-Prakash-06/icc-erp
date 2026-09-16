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
        wing_code = {
            "ICC_EVENTS_HEAD": "EVENTS",
            "ICC_MEDIA_HEAD": "MEDIA",
            "ICC_CULTURALS_HEAD": "CULTURALS",
        }.get(role_code)
        wing = Wing.query.filter_by(operating_unit_id=unit.id, code=wing_code).first() if unit and wing_code else None
    elif role_code.startswith("IGP_"):
        unit = OperatingUnit.query.filter_by(code="IGP").first()
    requested_wing = Wing.query.filter_by(public_id=scope.get("wing_public_id")).first() if scope.get("wing_public_id") else None
    if requested_wing:
        if not unit or requested_wing.operating_unit_id != unit.id:
            raise ValueError("The selected wing is outside this role's operating unit.")
        if wing and wing.id != requested_wing.id:
            raise ValueError("This head role is fixed to its designated wing.")
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
        raise ValueError("Annual ICC/IGP leadership and associate assignments require an academic year.")
    if role_code == "ICC_ASSOCIATE" and not wing:
        raise ValueError("ICC Associate assignments require a wing.")
    if role_code == "IGP_PROGRAM_LEAD" and not project:
        raise ValueError("IGP Program Lead assignments require a specific program.")
    if role_code in {"VOLUNTEER", "BUDDY", "PARTICIPANT"} and not project:
        raise ValueError("Volunteer, buddy, and participant access requires a specific project/program.")
    platform_scope = role_code == "SYSTEM_ADMINISTRATOR" or scope.get("platform_scope") == "on"
    if platform_scope and role_code not in {"SYSTEM_ADMINISTRATOR", "OIA_FACULTY_ADMINISTRATOR"}:
        raise ValueError("Only system and OIA faculty administrators may receive platform scope.")
    sensitive_requested = scope.get("can_view_sensitive_links") == "on"
    sensitive_allowed = role_code in {"OIA_FACULTY_ADMINISTRATOR", "IGP_HEAD"}
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
# Three audiences, not fourteen: someone who *decides* (the approve
# permission), someone who *runs the office* (imports, records, audit) and
# someone who *does the work* on one project. The scoped role codes above
# collapse into those three here, and nothing else in the app needs to know
# the difference.
#
# `url_for` is unavailable in a service -- these run in tests and jobs with
# only an app context -- so every step and task carries an endpoint name
# plus params, and the template resolves them. See app/templates/_onboarding.html.
# ──────────────────────────────────────────────────────────────────────────

ONBOARDING_COORDINATOR = "coordinator"
ONBOARDING_OFFICE = "office"
ONBOARDING_VOLUNTEER = "volunteer"

# Copy for the four shared steps is taken verbatim from the redesign artboard's
# TOUR constant ("ICC ERP Redesign.dc.html"); `nav` and `checklist` are new,
# written to the same voice, because the artboard's tour was four fixed cards
# and had no anchored navigation or checklist step.
_STEPS = {
    "queue": {
        "title": "Everything waiting on you is here",
        "body": "One list on the home screen. Approve or send back without leaving the page.",
        "placement": "bottom",
    },
    "counters": {
        "title": "The numbers are links",
        "body": "Tap any counter to see just those records — no separate filter screen.",
        "placement": "bottom",
    },
    "search": {
        "title": "Jump anywhere with ⌘K",
        "body": "Search projects, people and sessions from one box. It also runs actions.",
        "placement": "bottom",
    },
    "blockers": {
        "title": "A project shows what's blocking it",
        "body": "Closure blockers sit at the top of every project, already open.",
        "placement": "bottom",
    },
    "nav": {
        "title": "Everything else is one row up",
        "body": "Projects, reports and your account sit in the top bar. On a phone they are along the bottom.",
        "placement": "bottom",
    },
    "checklist": {
        "title": "A short list to start with",
        "body": "Four things worth doing once. It ticks itself off as you do them, then disappears.",
        "placement": "left",
    },
}

# Step order per audience. A step whose target element is not on the page is
# skipped at runtime rather than drawn as an orphan tooltip, so a role that
# cannot see the decision queue simply never sees that card.
ONBOARDING_TOURS = {
    ONBOARDING_COORDINATOR: ["queue", "counters", "search", "blockers", "nav", "checklist"],
    ONBOARDING_VOLUNTEER: ["queue", "counters", "nav", "checklist"],
    ONBOARDING_OFFICE: ["queue", "counters", "nav", "search", "checklist"],
}

ONBOARDING_WELCOME = {
    ONBOARDING_COORDINATOR: {
        "title": "Everything waiting on you, on one page",
        "body": "You approve work for the projects you oversee. The platform is built so that deciding is the fastest thing you can do in it.",
        "bullets": [
            "Home opens on the decisions waiting on you — approve them in place.",
            "Sending something back always opens the record, because it needs a reason.",
            "Every project shows what is blocking its closure before anything else.",
        ],
    },
    ONBOARDING_OFFICE: {
        "title": "The office view of every record",
        "body": "Imports, people, campuses and the audit trail all lead back to the same projects. Nothing here is a copy of anything else.",
        "bullets": [
            "Home collects the work in front of you across every project in scope.",
            "Imports stage first and commit second, so a bad sheet never lands.",
            "The audit trail is append-only — it is the record of who changed what.",
        ],
    },
    ONBOARDING_VOLUNTEER: {
        "title": "Your projects and your open work",
        "body": "You will mostly live on one page: what is open against your name, and the sessions coming up.",
        "bullets": [
            "Home lists your tasks and requests — nothing else competes for the space.",
            "Hours you log go to your coordinator for approval, with the evidence attached.",
            "Your project page holds the sessions, the team and the paperwork.",
        ],
    },
}

# Each task names the signal that completes it (resolved in
# app/services/home.py) and the page where it is done.
ONBOARDING_CHECKLISTS = {
    ONBOARDING_COORDINATOR: [
        {"key": "decision", "label": "Clear your first decision", "endpoint": "dashboard.index", "params": {"queue": "all"}},
        {"key": "project_opened", "label": "Open a project and read its blockers", "endpoint": "erp.projects", "params": {}},
        {"key": "search_used", "label": "Jump somewhere with ⌘K", "endpoint": None, "params": {}},
        {"key": "roll_call", "label": "Take a roll call at a session", "endpoint": "dashboard.index", "params": {}},
    ],
    ONBOARDING_OFFICE: [
        {"key": "project_opened", "label": "Open a project", "endpoint": "erp.projects", "params": {}},
        {"key": "import_committed", "label": "Commit an import batch", "endpoint": "erp.imports", "params": {}},
        {"key": "search_used", "label": "Jump somewhere with ⌘K", "endpoint": None, "params": {}},
        {"key": "audit_viewed", "label": "Read the audit trail", "endpoint": "erp.audit", "params": {}},
    ],
    ONBOARDING_VOLUNTEER: [
        {"key": "project_opened", "label": "Open your project", "endpoint": "erp.projects", "params": {}},
        {"key": "hours_logged", "label": "Log the hours you have worked", "endpoint": "erp.projects", "params": {}},
        {"key": "search_used", "label": "Jump somewhere with ⌘K", "endpoint": None, "params": {}},
    ],
}

# Signals the browser reports (nothing else in the database records them).
ONBOARDING_CLIENT_SIGNALS = {"search_used", "project_opened", "audit_viewed"}


def onboarding_audience(user):
    """Collapse a user's scoped permissions into one of three onboarding
    audiences. Deciding wins over office work, which wins over doing: an OIA
    faculty administrator holds every permission and should be introduced to
    the decision queue first."""
    from app.services.authorization import has_any_permission

    if has_any_permission(user, "approve") or has_any_permission(user, "approve_operational_requests"):
        return ONBOARDING_COORDINATOR
    if has_any_permission(user, "manage_imports") or has_any_permission(user, "audit"):
        return ONBOARDING_OFFICE
    return ONBOARDING_VOLUNTEER


def onboarding_tour_steps(audience):
    """Return the ordered step definitions for an audience, each carrying the
    `data-tour` target it anchors to."""
    return [{"target": key, **_STEPS[key]} for key in ONBOARDING_TOURS.get(audience, [])]
