"""Minimal project creation: title and start/end date are the only inputs
asked for. Campus, academic year, unit, type, category, owner, code, and
status are all inferred. See PLAN.md "Lightweight application structure"."""

from __future__ import annotations

from datetime import date as date_cls

from app.database import db
from app.models.erp import OperatingUnit
from app.models.project import AcademicYear, Campus, Project, ProgramType
from app.services.authorization import ROLE_PERMISSIONS, _active_assignments, has_permission


def infer_status_from_dates(start_date, end_date, today=None) -> str:
    today = today or date_cls.today()
    if start_date > today:
        return "Planned"
    if end_date < today:
        return "Completed"
    return "Active"


def create_minimal_project(*, program_type_name: str, title: str, start_date, end_date, actor, venue=None, target_audience=None) -> Project:
    title = (title or "").strip()
    if not title:
        raise ValueError("Title is required.")
    if end_date < start_date:
        raise ValueError("End date cannot precede start date.")

    program = ProgramType.query.filter_by(name=program_type_name).first()
    if not program:
        raise ValueError(f"Unknown program type: {program_type_name}")
    unit = OperatingUnit.query.filter_by(code=program_type_name).first()
    campus = getattr(actor, "campus", None) or Campus.query.order_by(Campus.name).first()
    if not campus:
        raise ValueError("No campus is configured yet; add one before creating a project.")
    academic_year = (
        AcademicYear.query.filter_by(is_current=True).first()
        or AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
    )
    if not academic_year:
        raise ValueError("No academic year is configured yet; add one before creating a project.")

    # Infer the new record from an actual creation scope. In particular, a
    # wing head must not create a wing-less record that they cannot reopen.
    assignments = sorted(_active_assignments(actor), key=lambda row: row.id)
    creation_scope = next((row for row in assignments
        if "manage_projects" in ROLE_PERMISSIONS.get(row.role_code, set())
        and not row.project_id
        and (not row.operating_unit_id or row.operating_unit_id == getattr(unit, "id", None))), None)
    if creation_scope is None:
        raise ValueError("Your role cannot create a project for this program. Choose a program in your assigned scope.")
    if creation_scope.campus_id:
        campus = db.session.get(Campus, creation_scope.campus_id)
    if creation_scope.academic_year_id:
        academic_year = db.session.get(AcademicYear, creation_scope.academic_year_id)

    default_project_type = "IGP inbound program" if program_type_name == "IGP" else "ICC event"
    project = Project(
        title=title, campus_id=campus.id, program_type_id=program.id,
        academic_year_id=academic_year.id, operating_unit_id=getattr(unit, "id", None),
        wing_id=creation_scope.wing_id,
        project_type=default_project_type, category="Operational",
        status=infer_status_from_dates(start_date, end_date),
        start_date=start_date, end_date=end_date,
        venue=(venue or "").strip() or None, target_audience=(target_audience or "").strip() or None,
        owner_person_id=getattr(actor, "person_id", None),
    )
    if not has_permission(actor, "manage_projects", project):
        raise ValueError("The inferred project is outside your assigned scope.")
    db.session.add(project)
    db.session.flush()
    project.code = f"{program.name.upper()}-{start_date.year}-{campus.code or 'CAMP'}-{project.id:04d}"
    db.session.commit()
    return project


def creatable_program_types(actor):
    """Program types ``actor`` can actually create a project for.

    :func:`create_minimal_project` refuses a program outside the actor's
    creation scope, but the New project form was offering every program in
    the system -- so a scoped ICC Events Head could pick IGP and only learn
    it was refused after submitting. Same rule, applied before the choice
    is offered.
    """
    assignments = [row for row in _active_assignments(actor)
                   if "manage_projects" in ROLE_PERMISSIONS.get(row.role_code, set()) and not row.project_id]
    allowed = []
    for program in ProgramType.query.order_by(ProgramType.name).all():
        unit = OperatingUnit.query.filter_by(code=program.name).first()
        if any(not row.operating_unit_id or row.operating_unit_id == getattr(unit, "id", None) for row in assignments):
            allowed.append(program)
    return allowed
