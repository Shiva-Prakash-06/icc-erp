from __future__ import annotations

from datetime import date
from functools import wraps

from flask import abort, g
from sqlalchemy import and_, or_

from app.models.erp import RoleAssignment


ROLE_PERMISSIONS = {
    "SYSTEM_ADMINISTRATOR": {
        "platform_admin", "manage_users", "manage_governance", "manage_projects",
        "manage_people", "manage_imports", "approve", "waive", "report", "audit",
    },
    "OIA_FACULTY_ADMINISTRATOR": {"manage_users", "manage_governance", "manage_projects", "manage_people", "manage_imports", "approve", "waive", "report", "audit", "sensitive_links"},
    "FACULTY_COORDINATOR": {"manage_projects", "manage_people", "manage_imports", "approve", "waive", "report"},
    "ICC_SECRETARY_USC": {"manage_governance", "manage_projects", "manage_people", "manage_imports", "approve", "report"},
    "ICC_EVENTS_HEAD": {"manage_projects", "manage_people", "approve", "report"},
    "ICC_MEDIA_HEAD": {"manage_projects", "manage_people", "approve", "report"},
    "ICC_CULTURALS_HEAD": {"manage_projects", "manage_people", "approve", "report"},
    "ICC_ASSOCIATE": {"contribute", "view_assigned"},
    "IGP_HEAD": {"manage_projects", "manage_people", "manage_imports", "approve", "waive", "report", "sensitive_links"},
    "IGP_PROGRAM_LEAD": {"manage_projects", "manage_people", "approve", "report"},
    "VOLUNTEER": {"contribute", "view_assigned"},
    "BUDDY": {"contribute", "view_assigned"},
    "PARTICIPANT": {"view_personal"},
    "AUDITOR": {"report", "audit"},
}

LEGACY_ROLE_MAP = {
    "System Administrator": "SYSTEM_ADMINISTRATOR",
    "OIA Faculty Administrator": "OIA_FACULTY_ADMINISTRATOR",
    "Faculty Coordinator": "FACULTY_COORDINATOR",
    "Faculty": "OIA_FACULTY_ADMINISTRATOR",
    "ICC Secretary / USC": "ICC_SECRETARY_USC",
    "ICC Core Committee": "ICC_SECRETARY_USC",
    "ICC Events Head": "ICC_EVENTS_HEAD",
    "ICC Events Core": "ICC_EVENTS_HEAD",
    "ICC Culturals Head": "ICC_CULTURALS_HEAD",
    "ICC Cultural Core": "ICC_CULTURALS_HEAD",
    "ICC Media Head": "ICC_MEDIA_HEAD",
    "ICC Media Core": "ICC_MEDIA_HEAD",
    "ICC Associate": "ICC_ASSOCIATE",
    "IGP Head": "IGP_HEAD",
    "IGP Core": "IGP_HEAD",
    "IGP Program Lead": "IGP_PROGRAM_LEAD",
    "Volunteer": "VOLUNTEER",
    "Buddy": "BUDDY",
    "Participant / Exchange Student": "PARTICIPANT",
    "Exchange Student": "PARTICIPANT",
    "Auditor / Read-only": "AUDITOR",
}


def _active_assignments(user):
    if not user:
        return []
    today = date.today()
    return RoleAssignment.query.filter(
        RoleAssignment.user_id == user.id,
        RoleAssignment.is_active.is_(True),
        or_(RoleAssignment.starts_on.is_(None), RoleAssignment.starts_on <= today),
        or_(RoleAssignment.ends_on.is_(None), RoleAssignment.ends_on >= today),
    ).all()


def role_codes(user):
    codes = {assignment.role_code for assignment in _active_assignments(user)}
    legacy = LEGACY_ROLE_MAP.get(getattr(user, "role", None))
    if legacy:
        codes.add(legacy)
    return codes


def has_permission(user, permission, project=None, sensitive=False):
    if not user or user.status != "Approved":
        return False
    assignments = _active_assignments(user)
    legacy_code = LEGACY_ROLE_MAP.get(user.role)
    if legacy_code and permission in ROLE_PERMISSIONS.get(legacy_code, set()):
        # Legacy faculty retains broad access only during demonstrator migration.
        if legacy_code == "OIA_FACULTY_ADMINISTRATOR":
            return not sensitive or permission == "sensitive_links"

    for assignment in assignments:
        if permission not in ROLE_PERMISSIONS.get(assignment.role_code, set()):
            continue
        if sensitive and not assignment.can_view_sensitive_links:
            continue
        if not project:
            return True
        if assignment.project_id and assignment.project_id != project.id:
            continue
        if assignment.campus_id and assignment.campus_id != project.campus_id:
            continue
        if assignment.operating_unit_id and assignment.operating_unit_id != project.operating_unit_id:
            continue
        if assignment.wing_id and assignment.wing_id != project.wing_id:
            continue
        if assignment.academic_year_id and assignment.academic_year_id != project.academic_year_id:
            continue
        return True
    return False


def can_view_project(user, project):
    if has_permission(user, "manage_projects", project) or has_permission(user, "report", project):
        return True
    if not user:
        return False
    from app.models.erp import TeamAssignment
    from app.models.project import ProjectParticipant

    if user.person_id and TeamAssignment.query.filter_by(person_id=user.person_id, project_id=project.id).first() is not None:
        return True
    identity_filter = ProjectParticipant.user_id == user.id
    if user.person_id:
        identity_filter = or_(identity_filter, ProjectParticipant.person_id == user.person_id)
    return ProjectParticipant.query.filter(
        ProjectParticipant.project_id == project.id,
        identity_filter,
        ProjectParticipant.status == "Active",
    ).first() is not None


def permission_required(permission, project_loader=None):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            project = project_loader(*args, **kwargs) if project_loader else None
            if not has_permission(g.user, permission, project):
                abort(403)
            return func(*args, **kwargs)

        return wrapped

    return decorator
