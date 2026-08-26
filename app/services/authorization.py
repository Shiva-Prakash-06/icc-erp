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
    "OIA_FACULTY_ADMINISTRATOR": {"manage_users", "manage_governance", "manage_projects", "manage_people", "manage_imports", "approve", "approve_operational_requests", "waive", "report", "audit", "sensitive_links"},
    "FACULTY_COORDINATOR": {"manage_projects", "manage_people", "manage_imports", "approve", "approve_operational_requests", "waive", "report"},
    "ICC_SECRETARY_USC": {"manage_governance", "manage_projects", "manage_people", "manage_imports", "report"},
    "ICC_EVENTS_HEAD": {"manage_projects", "manage_people", "approve", "approve_operational_requests", "report"},
    "ICC_MEDIA_HEAD": {"manage_projects", "manage_people", "approve", "approve_operational_requests", "report"},
    "ICC_CULTURALS_HEAD": {"manage_projects", "manage_people", "approve", "approve_operational_requests", "report"},
    "ICC_ASSOCIATE": {"contribute", "view_assigned"},
    "IGP_HEAD": {"manage_projects", "manage_people", "manage_imports", "approve", "approve_operational_requests", "waive", "report", "sensitive_links"},
    "IGP_PROGRAM_LEAD": {"manage_projects", "manage_people", "approve", "report"},
    "VOLUNTEER": {"contribute", "view_assigned"},
    "BUDDY": {"contribute", "view_assigned"},
    "PARTICIPANT": {"view_personal"},
    "AUDITOR": {"report", "audit"},
}

# Business approval of operational (expenditure/logistics) requests is deliberately
# narrower than the general "approve" permission: USC (ICC_SECRETARY_USC), IGP
# Program Lead, and System Administrator hold "approve" for other workflows
# (documents, reports, budgets) but must NOT be able to approve operational
# requests on scope or technical-admin status alone -- see PLAN.md "USC operational
# approvals" finding.

# Permissions that are inherently platform-wide (not tied to any single project's
# campus/wing/operating-unit scope). Only these may be granted by an assignment
# scope check performed without a `project` argument.
GLOBAL_PERMISSIONS = {"manage_users", "manage_governance", "manage_imports", "audit"}

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
    # Authorization is decided entirely by scoped RoleAssignment rows -- the
    # legacy free-text User.role string is informational only (see
    # user.py), never read here. Every approved user is guaranteed to have
    # an active RoleAssignment (assigned at approval time, or via the
    # backfill-role-assignments CLI command for any pre-existing account).
    assignments = _active_assignments(user)
    for assignment in assignments:
        if permission not in ROLE_PERMISSIONS.get(assignment.role_code, set()):
            continue
        if sensitive and not assignment.can_view_sensitive_links:
            continue
        is_unscoped = not any((
            assignment.project_id,
            assignment.campus_id,
            assignment.operating_unit_id,
            assignment.wing_id,
            assignment.academic_year_id,
        ))
        if not project:
            # A project-less check can only be satisfied by a genuinely unscoped
            # assignment, or a permission that is inherently platform-wide.
            # Otherwise a wing/campus-scoped assignment would silently grant
            # cross-scope access whenever a caller omits the project argument.
            if is_unscoped or permission in GLOBAL_PERMISSIONS:
                return True
            continue
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


def has_any_permission(user, permission, sensitive=False):
    """Return whether an approved user holds ``permission`` in any active scope.

    This helper is only suitable for navigation and entry-point checks. Callers
    must still use :func:`has_permission` with the concrete project before
    reading or mutating project-owned data.
    """
    if not user or user.status != "Approved":
        return False
    return any(
        permission in ROLE_PERMISSIONS.get(assignment.role_code, set())
        and (not sensitive or assignment.can_view_sensitive_links)
        for assignment in _active_assignments(user)
    )


def can_view_project(user, project):
    if has_permission(user, "manage_projects", project) or has_permission(user, "report", project):
        return True
    if not user or not user.person_id:
        return False
    from app.models.erp import TeamAssignment

    return TeamAssignment.query.filter_by(
        person_id=user.person_id, project_id=project.id, status="Active",
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
