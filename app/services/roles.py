"""Canonical implementation for turning a legacy role label + scope selection
into a real, scoped ``RoleAssignment`` row. Used by the account-approval UI
(``dashboard.py``) and by CLI backfill commands (``app/cli.py``) alike, so
there is exactly one place that encodes the scope rules for each role.
"""

from __future__ import annotations

from app.database import db
from app.models.erp import OperatingUnit, RoleAssignment, Wing
from app.models.project import AcademicYear, Campus, Project
from app.services.authorization import LEGACY_ROLE_MAP, has_permission


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
    for assignment in RoleAssignment.query.filter_by(user_id=user.id, is_active=True):
        assignment.is_active = False
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
    return assignment
