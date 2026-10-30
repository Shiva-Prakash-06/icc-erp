"""Creating an event from one short form: a name and a date.

Campus, academic year, unit, type, category, owner and code are inferred.
The event also gets, without being asked: a main session on its first day
(so the date, time and venue are not typed twice) and the standard to-do
list for its kind of event. Starting from a past event copies that event's
to-do list and session times, moved to the new date.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.database import db
from app.models.erp import ChecklistTemplate, OperatingUnit, ProjectSession, WorkTask
from app.models.project import AcademicYear, Campus, Project, ProgramType
from app.services.authorization import ROLE_PERMISSIONS, _active_assignments, has_permission
from app.services.timeutil import to_utc


def create_minimal_project(*, program_type_name: str, title: str, start_date, end_date, actor, venue=None, target_audience=None,
                          start_time=None, end_time=None, copy_from=None, standard_todos=False) -> Project:
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
        # Where the event is in its life comes from its dates
        # (app/services/stage.py); "Active" only means "not finished yet".
        status="Active",
        start_date=start_date, end_date=end_date,
        venue=(venue or "").strip() or None, target_audience=(target_audience or "").strip() or None,
        owner_person_id=getattr(actor, "person_id", None),
    )
    if not has_permission(actor, "manage_projects", project):
        raise ValueError("The inferred project is outside your assigned scope.")
    db.session.add(project)
    db.session.flush()
    project.code = f"{program.name.upper()}-{start_date.year}-{campus.code or 'CAMP'}-{project.id:04d}"
    if copy_from is not None:
        _copy_event(copy_from, project)
    else:
        if start_time is not None:
            _main_session(project, start_time, end_time)
        if standard_todos:
            _standard_todos(project, actor)
    db.session.commit()
    return project


def _main_session(project, start_time, end_time):
    end_time = end_time or (datetime.combine(project.start_date, start_time) + timedelta(hours=2)).time()
    starts_at = to_utc(datetime.combine(project.start_date, start_time))
    ends_at = to_utc(datetime.combine(project.start_date, end_time))
    if ends_at < starts_at:
        ends_at = starts_at + timedelta(hours=2)
    db.session.add(ProjectSession(
        project_id=project.id, code="S1", title="Main session", session_type="Session",
        starts_at=starts_at, ends_at=ends_at, venue=project.venue,
    ))


def standard_template(project):
    """The checklist template made for this kind of event, if there is one."""
    return (
        ChecklistTemplate.query.filter_by(project_type=project.project_type, is_active=True)
        .order_by(ChecklistTemplate.version.desc()).first()
    )


def _standard_todos(project, actor):
    from app.services.operations import instantiate_checklist

    template = standard_template(project)
    if template is not None:
        db.session.flush()
        instantiate_checklist(project, template, actor)


def _copy_event(source, project):
    """Copy a past event's to-do list and sessions onto ``project``, moved by
    the gap between the two start dates. People, money and files are not
    copied: those belong to the event that happened."""
    from app.services.todo import todos_for_project

    shift = project.start_date - source.start_date
    for item in todos_for_project(source):
        db.session.add(WorkTask(
            project_id=project.id, title=item.title, status="Not Started", assigned_team=item.team,
            owner_person_id=item.owner.id if item.owner else None,
            due_at=item.due_at + shift if item.due_at else None,
        ))
    for index, old in enumerate(
        sorted((s for s in source.sessions if s.is_active), key=lambda s: s.starts_at), start=1,
    ):
        db.session.add(ProjectSession(
            project_id=project.id, code=f"S{index}", title=old.title, session_type=old.session_type,
            starts_at=old.starts_at + shift, ends_at=old.ends_at + shift, venue=old.venue or project.venue,
        ))


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
