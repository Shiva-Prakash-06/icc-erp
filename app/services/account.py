"""Data for "My Account & Activity" -- replaces the old volunteer-oriented,
read-only "My Profile" page, which was commonly empty for USC and other
non-volunteer roles. See PLAN.md "USC My Profile" finding.
"""

from __future__ import annotations

from app.database import db
from app.models.erp import OperatingUnit, OperationalRequest, ProjectSession, RoleAssignment, SessionAttendance, TeamAssignment, Wing
from app.models.production import ContributionRecord, Notification
from app.models.project import AcademicYear, Campus, Project


def _human_role_label(role_code):
    return role_code.replace("_", " ").title() if role_code else "Unassigned"


def _scope_label(assignment):
    if assignment.project_id:
        project = db.session.get(Project, assignment.project_id)
        return f"Project · {project.title}" if project else "Project (removed)"
    parts = []
    if assignment.campus_id:
        campus = db.session.get(Campus, assignment.campus_id)
        if campus:
            parts.append(campus.name)
    if assignment.operating_unit_id:
        unit = db.session.get(OperatingUnit, assignment.operating_unit_id)
        if unit:
            parts.append(unit.name)
    if assignment.wing_id:
        wing = db.session.get(Wing, assignment.wing_id)
        if wing:
            parts.append(wing.name)
    if assignment.academic_year_id:
        year = db.session.get(AcademicYear, assignment.academic_year_id)
        if year:
            parts.append(year.name)
    return " · ".join(parts) if parts else "Platform-wide"


def build_account_activity(user):
    role_assignments = [
        {
            "role_label": _human_role_label(assignment.role_code),
            "scope_label": _scope_label(assignment),
            "is_active": assignment.is_active,
            "starts_on": assignment.starts_on,
            "ends_on": assignment.ends_on,
        }
        for assignment in RoleAssignment.query.filter_by(user_id=user.id).order_by(RoleAssignment.is_active.desc(), RoleAssignment.created_at.desc()).all()
    ]

    assigned_project_ids = set()
    contribution_hours = {}
    person = user.person
    if person:
        assigned_project_ids.update(t.project_id for t in TeamAssignment.query.filter_by(person_id=person.id).all() if t.project_id)
        contributions = ContributionRecord.query.filter_by(person_id=person.id).order_by(ContributionRecord.created_at.desc()).all()
        assigned_project_ids.update(c.project_id for c in contributions)
        for contribution in contributions:
            if contribution.approval_status == "Approved":
                contribution_hours[contribution.activity_type] = contribution_hours.get(contribution.activity_type, 0) + float(contribution.duration_hours)
        session_ids = [a.session_id for a in SessionAttendance.query.filter_by(person_id=person.id).all()]
        if session_ids:
            assigned_project_ids.update(s.project_id for s in ProjectSession.query.filter(ProjectSession.id.in_(session_ids)).all())
    else:
        contributions = []

    assigned_projects = (
        Project.query.filter(Project.id.in_(assigned_project_ids)).order_by(Project.start_date.desc()).all()
        if assigned_project_ids else []
    )

    recent_requests = (
        OperationalRequest.query.filter(
            (OperationalRequest.created_by_id == user.id) | (OperationalRequest.submitted_by_id == user.id)
        )
        .order_by(OperationalRequest.created_at.desc())
        .limit(5)
        .all()
    )

    recent_contributions = contributions[:5] if person else []

    recent_notifications = (
        Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(5).all()
    )

    return {
        "role_assignments": role_assignments,
        "assigned_projects": assigned_projects,
        "contribution_hours": contribution_hours,
        "recent_requests": recent_requests,
        "recent_contributions": recent_contributions,
        "recent_notifications": recent_notifications,
    }
