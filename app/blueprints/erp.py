from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from app.database import db
from app.models.erp import (
    AuditEvent,
    BudgetLine,
    ChecklistInstance,
    ChecklistItemStatus,
    ChecklistTemplate,
    DocumentRecord,
    FeedbackForm,
    FeedbackResponse,
    ImportBatch,
    OperatingUnit,
    OperationalRequest,
    Person,
    ProjectSession,
    ReportSnapshot,
    SessionAttendance,
    TeamAssignment,
    Wing,
    WorkTask,
)
from app.models.production import ContributionRecord, Notification, NotificationPreference, ProjectRisk
from app.models.project import AcademicYear, BuddyAssignment, BuddyLog, Campus, ProgramType, Project
from app.services.audit import record_audit, record_sensitive_access
from app.services.authorization import can_view_project, has_permission
from app.services.buddy import validate_buddy_assignment
from app.services.drive import extract_drive_id, refresh_document_metadata
from app.services.imports import STANDARD_IMPORTS, commit_batch, stage_supplied_source, stage_uploaded_source
from app.services.lifecycle import TRANSITIONS, closure_blockers, transition_project
from app.services.operations import (
    change_checklist_status,
    change_task_status,
    decide_budget_line,
    decide_buddy_log,
    decide_contribution,
    decide_document,
    decide_operational_request,
    instantiate_checklist,
    mark_attendance,
    moderate_feedback,
)
from app.services.reporting import compile_project_snapshot


erp_bp = Blueprint("erp", __name__, url_prefix="/erp")


@erp_bp.get("")
def hub():
    projects = [project for project in Project.query.order_by(Project.start_date.desc()).all() if can_view_project(g.user, project)]
    stats = {
        "projects": len(projects),
        "active": sum(project.status in {"Planned", "Active", "Closing"} for project in projects),
        "people": Person.query.count() if has_permission(g.user, "manage_projects") else None,
        "imports": ImportBatch.query.count() if has_permission(g.user, "manage_imports") else None,
    }
    return render_template("erp/hub.html", projects=projects[:8], stats=stats)


@erp_bp.get("/oversight")
def oversight():
    if not has_permission(g.user, "approve"):
        abort(403)
    projects_in_scope = [project for project in Project.query.all() if has_permission(g.user, "approve", project)]
    project_ids = [project.id for project in projects_in_scope]
    now = datetime.now(timezone.utc)

    status_counts = {}
    for project in projects_in_scope:
        status_counts[project.status] = status_counts.get(project.status, 0) + 1

    overdue_tasks = WorkTask.query.filter(
        WorkTask.project_id.in_(project_ids or [-1]), WorkTask.due_at.isnot(None), WorkTask.due_at < now,
        WorkTask.status.notin_(["Approved", "Completed", "Waived"]),
    ).count()

    action_queue = []
    for task in WorkTask.query.filter(WorkTask.project_id.in_(project_ids or [-1]), WorkTask.status == "Submitted").all():
        action_queue.append({"kind": "Task", "title": task.title, "project": task.project, "tab": "operations", "due_at": task.due_at})
    for item in ChecklistItemStatus.query.join(ChecklistInstance).filter(ChecklistInstance.project_id.in_(project_ids or [-1]), ChecklistItemStatus.status == "Submitted").all():
        action_queue.append({"kind": "Checklist", "title": item.template_item.title, "project": item.checklist.project, "tab": "operations", "due_at": item.due_at})
    for document in DocumentRecord.query.filter(DocumentRecord.project_id.in_(project_ids or [-1]), DocumentRecord.status == "Submitted").all():
        action_queue.append({"kind": "Document", "title": document.title, "project": document.project, "tab": "resources", "due_at": None})
    for contribution in ContributionRecord.query.filter(ContributionRecord.project_id.in_(project_ids or [-1]), ContributionRecord.approval_status == "Pending").all():
        action_queue.append({"kind": "Contribution", "title": f"{contribution.person.display_name} · {contribution.activity_type}", "project": contribution.project, "tab": "operations", "due_at": None})
    for request_item in OperationalRequest.query.filter(OperationalRequest.project_id.in_(project_ids or [-1]), OperationalRequest.status == "Submitted").all():
        action_queue.append({"kind": "Operational request", "title": request_item.title, "project": request_item.project, "tab": "operations", "due_at": None})
    for line in BudgetLine.query.filter(BudgetLine.project_id.in_(project_ids or [-1]), BudgetLine.status == "Submitted").all():
        action_queue.append({"kind": "Budget line", "title": f"{line.category} ({line.currency} {line.estimated_amount})", "project": line.project, "tab": "operations", "due_at": None})
    action_queue.sort(key=lambda item: (item["due_at"] is None, item["due_at"] or now))

    budget_totals = db.session.query(
        db.func.coalesce(db.func.sum(BudgetLine.committed_amount), 0),
        db.func.coalesce(db.func.sum(BudgetLine.actual_amount), 0),
    ).filter(BudgetLine.project_id.in_(project_ids or [-1])).one()

    open_critical_risks = ProjectRisk.query.filter(
        ProjectRisk.project_id.in_(project_ids or [-1]), ProjectRisk.status == "Open", ProjectRisk.is_critical.is_(True),
    ).count()

    return render_template(
        "erp/oversight.html",
        projects=sorted(projects_in_scope, key=lambda project: project.start_date, reverse=True),
        status_counts=status_counts,
        overdue_tasks=overdue_tasks,
        pending_count=len(action_queue),
        action_queue=action_queue[:30],
        action_queue_overflow=max(0, len(action_queue) - 30),
        budget_committed=budget_totals[0],
        budget_actual=budget_totals[1],
        open_critical_risks=open_critical_risks,
    )


@erp_bp.route("/projects", methods=["GET", "POST"])
def projects():
    if request.method == "POST":
        if not has_permission(g.user, "manage_projects"):
            abort(403)
        required = ["title", "campus_public_id", "program_type_public_id", "academic_year_public_id", "start_date", "end_date"]
        if any(not request.form.get(field) for field in required):
            flash("Complete every required project field.", "danger")
        else:
            start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
            end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
            if end_date < start_date:
                flash("End date cannot precede start date.", "danger")
            else:
                program = ProgramType.query.filter_by(public_id=request.form["program_type_public_id"]).first_or_404()
                campus = Campus.query.filter_by(public_id=request.form["campus_public_id"]).first_or_404()
                academic_year = AcademicYear.query.filter_by(public_id=request.form["academic_year_public_id"]).first_or_404()
                unit = OperatingUnit.query.filter_by(code=program.name.upper()).first()
                wing = Wing.query.filter_by(public_id=request.form.get("wing_public_id")).first() if request.form.get("wing_public_id") else None
                if not unit or (wing and wing.operating_unit_id != unit.id):
                    flash("Choose a valid operating unit and wing combination.", "danger")
                    return redirect(url_for("erp.projects"))
                project = Project(
                    title=request.form["title"].strip(),
                    description=request.form.get("description", "").strip(),
                    project_type=request.form.get("project_type", "ICC event"),
                    category=request.form.get("category", "Operational"),
                    campus_id=campus.id,
                    program_type_id=program.id,
                    academic_year_id=academic_year.id,
                    operating_unit_id=unit.id,
                    wing_id=getattr(wing, "id", None),
                    status="Draft",
                    start_date=start_date,
                    end_date=end_date,
                    venue=request.form.get("venue", "").strip(),
                    target_audience=request.form.get("target_audience", "").strip(),
                )
                if not has_permission(g.user, "manage_projects", project):
                    abort(403)
                db.session.add(project)
                db.session.flush()
                project.code = f"{program.name.upper()}-{start_date.year}-{campus.code or 'CAMP'}-{project.id:04d}"
                code = project.code
                record_audit("project.create", project, after={"code": code, "title": project.title})
                db.session.commit()
                flash(f"Project {code} created in Draft. Continue setting it up below.", "success")
                return redirect(url_for("erp.project_setup", public_id=project.public_id))
    visible = [project for project in Project.query.order_by(Project.start_date.desc(), Project.id.desc()).all() if can_view_project(g.user, project)]
    return render_template(
        "erp/projects.html",
        projects=visible,
        campuses=Campus.query.order_by(Campus.name).all(),
        program_types=ProgramType.query.order_by(ProgramType.name).all(),
        academic_years=AcademicYear.query.order_by(AcademicYear.start_date.desc()).all(),
        wings=Wing.query.order_by(Wing.name).all(),
        can_create=has_permission(g.user, "manage_projects"),
    )


def _project(public_id):
    project = Project.query.filter_by(public_id=public_id).first_or_404()
    if not can_view_project(g.user, project):
        abort(403)
    return project


@erp_bp.get("/projects/<string:public_id>")
def project_detail(public_id):
    project = _project(public_id)
    blockers = closure_blockers(project)
    active_tab = request.args.get("tab") if request.args.get("tab") in {"overview", "people", "operations", "insights", "resources"} else "overview"
    return render_template(
        "erp/project_detail.html",
        project=project,
        blockers=blockers,
        transitions=sorted(TRANSITIONS.get(project.status, set())),
        can_manage=has_permission(g.user, "manage_projects", project),
        can_contribute=has_permission(g.user, "contribute", project),
        current_person_id=g.user.person_id,
        can_approve=has_permission(g.user, "approve", project),
        can_view_sensitive=has_permission(g.user, "sensitive_links", project, sensitive=True),
        active_tab=active_tab,
        is_igp=project.program_type.name == "IGP",
        checklist_templates=ChecklistTemplate.query.filter_by(is_active=True).order_by(ChecklistTemplate.name).all(),
        contribution_statuses=("Approved", "Rejected"),
    )


def _redirect_to_tab(project, tab, anchor=None):
    return redirect(url_for("erp.project_detail", public_id=project.public_id, tab=tab) + (f"#{anchor}" if anchor else ""))


WIZARD_STEPS = ["sessions", "team", "checklist", "documents", "budget"]


def _first_incomplete_step(project):
    if not project.sessions:
        return "sessions"
    if not project.team_assignments:
        return "team"
    if not project.checklists:
        return "checklist"
    if not project.document_records:
        return "documents"
    if not project.budget_lines:
        return "budget"
    return None


@erp_bp.get("/projects/<string:public_id>/setup")
def project_setup(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    requested_step = request.args.get("step")
    step = requested_step if requested_step in WIZARD_STEPS else _first_incomplete_step(project)
    if step is None:
        flash("This project's setup is complete — you're on the full project page.", "success")
        return redirect(url_for("erp.project_detail", public_id=project.public_id))
    return render_template(
        "erp/project_setup.html",
        project=project, step=step, steps=WIZARD_STEPS,
        is_igp=project.program_type.name == "IGP",
        checklist_templates=ChecklistTemplate.query.filter_by(is_active=True).order_by(ChecklistTemplate.name).all(),
        completed={
            "sessions": bool(project.sessions), "team": bool(project.team_assignments),
            "checklist": bool(project.checklists), "documents": bool(project.document_records),
            "budget": bool(project.budget_lines),
        },
    )


def _redirect_after_action(project, default_tab):
    """Forms shared between the project_detail tabs and the wizard
    (`project_setup`) pass a hidden `next=setup` field so the same route
    can return the user to whichever flow they came from."""
    if request.form.get("next") == "setup":
        return redirect(url_for("erp.project_setup", public_id=project.public_id))
    return _redirect_to_tab(project, default_tab)


@erp_bp.post("/projects/<string:public_id>/sessions")
def add_session(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Session title is required.", "danger")
        return _redirect_after_action(project, "overview")
    try:
        starts_at = datetime.strptime(request.form["starts_at"], "%Y-%m-%dT%H:%M")
        ends_at = datetime.strptime(request.form["ends_at"], "%Y-%m-%dT%H:%M")
    except (KeyError, ValueError):
        flash("Provide valid start and end times.", "danger")
        return _redirect_after_action(project, "overview")
    if ends_at < starts_at:
        flash("Session end time cannot precede its start time.", "danger")
        return _redirect_after_action(project, "overview")
    existing_count = ProjectSession.query.filter_by(project_id=project.id).count()
    session_item = ProjectSession(
        project_id=project.id, code=request.form.get("code") or f"S{existing_count + 1}",
        title=title, session_type=request.form.get("session_type") or "Session",
        starts_at=starts_at, ends_at=ends_at, venue=request.form.get("venue") or project.venue,
    )
    db.session.add(session_item)
    record_audit("session.create", session_item, after={"project": project.public_id, "title": title}, actor=g.user)
    db.session.commit()
    flash("Session added.", "success")
    return _redirect_after_action(project, "overview")


@erp_bp.post("/projects/<string:public_id>/checklists")
def instantiate_project_checklist(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    template = ChecklistTemplate.query.filter_by(public_id=request.form.get("template_public_id")).first()
    if not template:
        flash("Choose a valid checklist template.", "danger")
    else:
        instantiate_checklist(project, template, actor=g.user)
        flash(f"{template.name} checklist added to this project.", "success")
    return _redirect_after_action(project, "overview")


@erp_bp.post("/projects/<string:public_id>/team")
def add_team_member(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    registration_number = (request.form.get("registration_number") or "").strip()
    person = Person.query.filter_by(registration_number=registration_number).first() if registration_number else None
    if not person:
        flash("No person found with that registration number.", "danger")
        return _redirect_after_action(project, "people")
    if TeamAssignment.query.filter_by(person_id=person.id, project_id=project.id).first():
        flash(f"{person.display_name} is already on this project's team.", "warning")
        return _redirect_after_action(project, "people")
    assignment = TeamAssignment(
        person_id=person.id, project_id=project.id,
        assignment_type=request.form.get("assignment_type") or "Project Team",
        role_label=request.form.get("role_label") or None,
    )
    db.session.add(assignment)
    record_audit("team.enroll", assignment, after={"person": person.public_id, "project": project.public_id}, actor=g.user)
    db.session.commit()
    flash(f"{person.display_name} added to the project team.", "success")
    return _redirect_after_action(project, "people")


@erp_bp.post("/projects/<string:public_id>/buddy-assignments")
def add_buddy_assignment(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    buddy_reg = (request.form.get("buddy_registration_number") or "").strip()
    student_reg = (request.form.get("exchange_student_registration_number") or "").strip()
    buddy_person = Person.query.filter_by(registration_number=buddy_reg).first() if buddy_reg else None
    student_person = Person.query.filter_by(registration_number=student_reg).first() if student_reg else None
    if not buddy_person or not student_person:
        flash("Both the buddy and exchange student must match a known registration number.", "danger")
        return _redirect_to_tab(project, "people")
    try:
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
        validate_buddy_assignment(
            project, None, None, start_date, end_date,
            buddy_person_id=buddy_person.id, exchange_student_person_id=student_person.id,
        )
        assignment = BuddyAssignment(
            project_id=project.id, buddy_person_id=buddy_person.id, exchange_student_person_id=student_person.id,
            start_date=start_date, end_date=end_date,
        )
        db.session.add(assignment)
        record_audit("buddy_assignment.create", assignment, after={"project": project.public_id}, actor=g.user)
        db.session.commit()
        flash(f"Paired {buddy_person.display_name} with {student_person.display_name}.", "success")
    except (ValueError, KeyError) as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "people")


@erp_bp.get("/projects/<string:public_id>/sessions/<string:session_public_id>/attendance")
def attendance_roll_call(public_id, session_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    session_item = ProjectSession.query.filter_by(public_id=session_public_id, project_id=project.id).first_or_404()
    records = {record.person_id: record for record in SessionAttendance.query.filter_by(session_id=session_item.id).all()}
    return render_template("erp/attendance_roll_call.html", project=project, session=session_item, team=project.team_assignments, records=records)


@erp_bp.post("/projects/<string:public_id>/sessions/<string:session_public_id>/attendance")
def mark_session_attendance(public_id, session_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    session_item = ProjectSession.query.filter_by(public_id=session_public_id, project_id=project.id).first_or_404()
    for team_assignment in project.team_assignments:
        field = f"status_{team_assignment.person_id}"
        if field not in request.form:
            continue
        status = request.form[field]
        existing = SessionAttendance.query.filter_by(session_id=session_item.id, person_id=team_assignment.person_id).first()
        try:
            mark_attendance(
                session_item, team_assignment.person, status, g.user,
                expected_version=existing.version if existing else None,
                reason="Roll-call update" if existing else None,
            )
        except ValueError:
            continue
    flash("Attendance recorded.", "success")
    return _redirect_to_tab(project, "people")


@erp_bp.post("/projects/<string:public_id>/contributions")
def log_contribution(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "contribute", project):
        abort(403)
    if not g.user.person_id:
        flash("Your account has no linked person record; contact an administrator.", "danger")
        return _redirect_to_tab(project, "operations")
    contribution = ContributionRecord(
        project_id=project.id, person_id=g.user.person_id,
        activity_type=request.form.get("activity_type") or "Event support",
        description=(request.form.get("description") or "").strip() or "Contribution",
        duration_hours=request.form.get("duration_hours") or 1,
    )
    db.session.add(contribution)
    record_audit("contribution.log", contribution, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Contribution logged for approval.", "success")
    return _redirect_to_tab(project, "operations")


@erp_bp.post("/projects/<string:public_id>/contributions/<string:contribution_public_id>/decision")
def decide_contribution_route(public_id, contribution_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "approve", project):
        abort(403)
    contribution = ContributionRecord.query.filter_by(public_id=contribution_public_id, project_id=project.id).first_or_404()
    try:
        decide_contribution(contribution, request.form.get("status"), g.user, expected_version=int(request.form.get("version") or contribution.version), reason=request.form.get("reason"))
        flash("Contribution decision recorded.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "operations")


@erp_bp.post("/projects/<string:public_id>/buddy-assignments/<string:assignment_public_id>/logs")
def log_buddy_interaction(public_id, assignment_public_id):
    project = _project(public_id)
    assignment = BuddyAssignment.query.filter_by(public_id=assignment_public_id, project_id=project.id).first_or_404()
    if not has_permission(g.user, "contribute", project):
        abort(403)
    log = BuddyLog(
        buddy_assignment_id=assignment.id,
        activity_date=datetime.strptime(request.form["activity_date"], "%Y-%m-%d").date(),
        description=(request.form.get("description") or "").strip(),
        duration_hours=request.form.get("duration_hours") or 1,
    )
    db.session.add(log)
    record_audit("buddy_log.create", log, after={"assignment": assignment.public_id}, actor=g.user)
    db.session.commit()
    flash("Buddy interaction logged for approval.", "success")
    return _redirect_to_tab(project, "operations")


@erp_bp.post("/projects/<string:public_id>/buddy-logs/<string:log_public_id>/decision")
def decide_buddy_log_route(public_id, log_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "approve", project):
        abort(403)
    log = BuddyLog.query.join(BuddyAssignment).filter(BuddyLog.public_id == log_public_id, BuddyAssignment.project_id == project.id).first_or_404()
    try:
        decide_buddy_log(log, request.form.get("status"), g.user, expected_version=int(request.form.get("version") or log.version), reason=request.form.get("reason"))
        flash("Buddy log decision recorded.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "operations")


@erp_bp.post("/projects/<string:public_id>/operational-requests")
def add_operational_request(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    operational_request = OperationalRequest(
        project_id=project.id, request_type=request.form.get("request_type") or "General",
        title=(request.form.get("title") or "").strip() or "Operational request",
        details=(request.form.get("details") or "").strip(), amount=request.form.get("amount") or None,
        owner_person_id=g.user.person_id,
    )
    db.session.add(operational_request)
    record_audit("operational_request.create", operational_request, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Operational request created in Draft.", "success")
    return _redirect_to_tab(project, "operations")


@erp_bp.post("/projects/<string:public_id>/operational-requests/<string:request_public_id>/decision")
def decide_operational_request_route(public_id, request_public_id):
    project = _project(public_id)
    operational_request = OperationalRequest.query.filter_by(public_id=request_public_id, project_id=project.id).first_or_404()
    status = request.form.get("status")
    if status in {"Approved", "Rejected", "Completed"} and not has_permission(g.user, "approve", project):
        abort(403)
    elif not has_permission(g.user, "manage_projects", project):
        abort(403)
    try:
        decide_operational_request(operational_request, status, g.user, expected_version=int(request.form.get("version") or operational_request.version), reason=request.form.get("reason"))
        flash("Operational request updated.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "operations")


@erp_bp.post("/projects/<string:public_id>/budgets")
def add_budget_line(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    line = BudgetLine(
        project_id=project.id, category=(request.form.get("category") or "").strip() or "General",
        description=(request.form.get("description") or "").strip(),
        estimated_amount=request.form.get("estimated_amount") or 0,
    )
    db.session.add(line)
    record_audit("budget_line.create", line, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Budget line added in Draft.", "success")
    return _redirect_after_action(project, "operations")


@erp_bp.post("/projects/<string:public_id>/budgets/<string:line_public_id>/decision")
def decide_budget_line_route(public_id, line_public_id):
    project = _project(public_id)
    line = BudgetLine.query.filter_by(public_id=line_public_id, project_id=project.id).first_or_404()
    status = request.form.get("status")
    if status in {"Approved", "Rejected", "Completed"} and not has_permission(g.user, "approve", project):
        abort(403)
    elif not has_permission(g.user, "manage_projects", project):
        abort(403)
    try:
        decide_budget_line(line, status, g.user, expected_version=int(request.form.get("version") or line.version), reason=request.form.get("reason"))
        flash("Budget line updated.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "operations")


@erp_bp.post("/projects/<string:public_id>/feedback-forms")
def add_feedback_form(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    if FeedbackForm.query.filter_by(project_id=project.id, is_open=True).first():
        flash("An open feedback form already exists for this project.", "warning")
        return _redirect_to_tab(project, "insights")
    questions = [
        {"key": "rating", "type": "scale", "min": 1, "max": 5, "label": "Overall rating"},
        {"key": "comments", "type": "text", "label": "Comments"},
        {"key": "suggestions", "type": "text", "label": "Suggestions"},
    ]
    form = FeedbackForm(project_id=project.id, title=(request.form.get("title") or "Project Feedback").strip(), questions_json=questions, is_open=True)
    db.session.add(form)
    record_audit("feedback_form.create", form, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Feedback form opened.", "success")
    return _redirect_to_tab(project, "insights")


@erp_bp.post("/projects/<string:public_id>/feedback-responses")
def submit_feedback_response(public_id):
    project = _project(public_id)
    form = FeedbackForm.query.filter_by(project_id=project.id, is_open=True).order_by(FeedbackForm.id.desc()).first()
    if not form:
        flash("There is no open feedback form for this project.", "danger")
        return _redirect_to_tab(project, "insights")
    answers = {
        "rating": request.form.get("rating"), "comments": request.form.get("comments"),
        "suggestions": request.form.get("suggestions"),
    }
    response = FeedbackResponse(form_id=form.id, person_id=g.user.person_id, answers_json=answers)
    db.session.add(response)
    record_audit("feedback_response.submit", response, after={"form": form.public_id}, actor=g.user)
    db.session.commit()
    flash("Thank you — your feedback has been recorded.", "success")
    return _redirect_to_tab(project, "insights")


@erp_bp.post("/projects/<string:public_id>/feedback-responses/<string:response_public_id>/moderate")
def moderate_feedback_route(public_id, response_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    response = FeedbackResponse.query.join(FeedbackForm).filter(FeedbackResponse.public_id == response_public_id, FeedbackForm.project_id == project.id).first_or_404()
    try:
        moderate_feedback(response, request.form.get("status"), g.user, reason=request.form.get("reason"))
        flash("Feedback moderation updated.", "success")
    except ValueError as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "insights")


@erp_bp.post("/projects/<string:public_id>/documents")
def add_document(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Document title is required.", "danger")
        return _redirect_after_action(project, "resources")
    classification = request.form.get("permission_classification") or "Internal"
    drive_url = (request.form.get("drive_url") or "").strip() or None
    document = DocumentRecord(
        project_id=project.id, title=title, category=request.form.get("category") or "Other",
        status="Submitted", drive_url=drive_url, permission_classification=classification,
        mandatory_for_closure=bool(request.form.get("mandatory_for_closure")),
    )
    db.session.add(document)
    db.session.flush()
    if drive_url:
        try:
            refresh_document_metadata(document)
        except ValueError as error:
            flash(f"Document added, but Drive validation failed: {error}", "warning")
    record_audit("document.create", document, after={"project": project.public_id, "title": title}, actor=g.user)
    db.session.commit()
    flash("Document added.", "success")
    return _redirect_after_action(project, "resources")


@erp_bp.post("/projects/<string:public_id>/documents/<string:document_public_id>/decision")
def decide_document_route(public_id, document_public_id):
    project = _project(public_id)
    document = DocumentRecord.query.filter_by(public_id=document_public_id, project_id=project.id).first_or_404()
    status = request.form.get("status")
    waive = status == "Waived"
    if waive and not has_permission(g.user, "waive", project):
        abort(403)
    elif not waive and not has_permission(g.user, "approve", project):
        abort(403)
    try:
        decide_document(document, status, g.user, expected_version=int(request.form.get("version") or document.version), reason=request.form.get("reason"), waive=waive)
        flash("Document decision recorded.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "resources")


@erp_bp.post("/projects/<string:public_id>/transition")
def transition(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "approve", project):
        abort(403)
    try:
        transition_project(
            project,
            request.form.get("target_status"),
            g.user,
            int(request.form.get("version")),
            request.form.get("reason"),
        )
        flash(f"Project moved to {project.status}.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/<string:public_id>/tasks")
def add_task(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    title = request.form.get("title", "").strip()
    if not title:
        flash("Task title is required.", "danger")
    else:
        task = WorkTask(
            project_id=project.id,
            title=title,
            description=request.form.get("description", "").strip(),
            status="Not Started",
            priority=request.form.get("priority", "Medium"),
            mandatory_for_closure=bool(request.form.get("mandatory_for_closure")),
        )
        db.session.add(task)
        record_audit("task.create", task, after={"title": title, "project": project.public_id})
        db.session.commit()
        flash("Task added.", "success")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/<string:public_id>/tasks/<string:task_public_id>/status")
def update_task(public_id, task_public_id):
    project = _project(public_id)
    task = WorkTask.query.filter_by(public_id=task_public_id, project_id=project.id).first_or_404()
    owner_update = g.user.person_id and task.owner_person_id == g.user.person_id and has_permission(g.user, "contribute", project)
    if not owner_update and not has_permission(g.user, "manage_projects", project):
        abort(403)
    status = request.form.get("status")
    comment = request.form.get("comment", "").strip()
    if status in {"Approved", "Rejected"} and not has_permission(g.user, "approve", project):
        abort(403)
    if status == "Waived" and not has_permission(g.user, "waive", project):
        abort(403)
    try:
        change_task_status(task, status, g.user, expected_version=int(request.form.get("version") or task.version), comment=comment, waive=status == "Waived")
        flash("Task status updated.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/<string:public_id>/checklist-items/<string:item_public_id>/status")
def update_checklist_item(public_id, item_public_id):
    project = _project(public_id)
    item = (
        ChecklistItemStatus.query.join(ChecklistItemStatus.checklist)
        .filter(ChecklistItemStatus.public_id == item_public_id, ChecklistItemStatus.checklist.has(project_id=project.id))
        .first_or_404()
    )
    owner_update = g.user.person_id and item.owner_person_id == g.user.person_id and has_permission(g.user, "contribute", project)
    if not owner_update and not has_permission(g.user, "manage_projects", project):
        abort(403)
    status = request.form.get("status")
    comment = request.form.get("comment", "").strip()
    if status in {"Approved", "Rejected"} and not has_permission(g.user, "approve", project):
        abort(403)
    if status == "Waived" and not has_permission(g.user, "waive", project):
        abort(403)
    try:
        change_checklist_status(item, status, g.user, expected_version=int(request.form.get("version") or item.version), comment=comment, waive=status == "Waived")
        flash("Checklist requirement updated.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.get("/imports")
def imports():
    if not has_permission(g.user, "manage_imports"):
        abort(403)
    batches = ImportBatch.query.order_by(ImportBatch.created_at.desc()).all()
    return render_template("erp/imports.html", batches=batches, standard_import_types=sorted(STANDARD_IMPORTS))


@erp_bp.post("/imports/upload")
def upload_import():
    if not has_permission(g.user, "manage_imports"):
        abort(403)
    uploaded_file = request.files.get("source_file")
    import_type = request.form.get("import_type")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a file to upload.", "danger")
    else:
        try:
            batch = stage_uploaded_source(import_type, uploaded_file, g.user.public_id)
            flash(f"Batch staged: {batch.staged_count} rows, {batch.error_count} errors.", "success")
        except (ValueError, KeyError) as error:
            flash(str(error), "danger")
    return redirect(url_for("erp.imports"))


@erp_bp.post("/imports/stage")
def stage_import():
    if not has_permission(g.user, "manage_imports"):
        abort(403)
    try:
        batch = stage_supplied_source(request.form.get("import_type"))
        flash(f"Batch staged: {batch.staged_count} rows, {batch.error_count} errors.", "success")
    except (ValueError, FileNotFoundError) as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.imports"))


@erp_bp.post("/imports/<string:public_id>/commit")
def commit_import(public_id):
    if not has_permission(g.user, "approve"):
        abort(403)
    batch = ImportBatch.query.filter_by(public_id=public_id).first_or_404()
    try:
        commit_batch(batch, g.user)
        flash(f"Batch committed with {batch.committed_count} records reconciled.", "success")
    except ValueError as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.imports"))


@erp_bp.get("/projects/<string:public_id>/report-preview")
def report_preview(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    report = compile_project_snapshot(project, actor=g.user)
    snapshot = report.snapshot_json
    record_audit("report.generate", report, after={"project": project.public_id})
    db.session.commit()
    return render_template("erp/report_preview.html", project=project, report=report, snapshot=snapshot)


@erp_bp.get("/documents/<string:public_id>/open")
def open_document(public_id):
    document = DocumentRecord.query.filter_by(public_id=public_id).first_or_404()
    project = _project(document.project.public_id)
    if not document.drive_url:
        abort(404)
    try:
        extract_drive_id(document.drive_url)
    except ValueError:
        abort(404)
    if document.permission_classification == "Restricted":
        if not has_permission(g.user, "sensitive_links", project, sensitive=True):
            abort(403)
        record_sensitive_access(document, "Open restricted document reference", g.user, project)
        db.session.commit()
    return redirect(document.drive_url)


@erp_bp.get("/audit")
def audit():
    if not has_permission(g.user, "audit"):
        abort(403)
    events = AuditEvent.query.order_by(AuditEvent.occurred_at.desc()).limit(200).all()
    return render_template("erp/audit.html", events=events)


@erp_bp.get("/notifications")
def notifications():
    items = Notification.query.filter_by(user_id=g.user.id).order_by(Notification.created_at.desc()).limit(200).all()
    preferences = {item.event_type: item for item in NotificationPreference.query.filter_by(user_id=g.user.id).all()}
    return render_template("erp/notifications.html", notifications=items, preferences=preferences)


@erp_bp.post("/notifications/<string:public_id>/read")
def notification_read(public_id):
    item = Notification.query.filter_by(public_id=public_id, user_id=g.user.id).first_or_404()
    item.read_at = datetime.now(timezone.utc)
    db.session.commit()
    return redirect(url_for("erp.notifications"))


@erp_bp.post("/notification-preferences")
def notification_preferences():
    event_type = (request.form.get("event_type") or "").strip()
    if not event_type:
        abort(422)
    preference = NotificationPreference.query.filter_by(user_id=g.user.id, event_type=event_type).first()
    if not preference:
        preference = NotificationPreference(user_id=g.user.id, event_type=event_type)
        db.session.add(preference)
    preference.email_enabled = bool(request.form.get("email_enabled"))
    preference.in_app_enabled = bool(request.form.get("in_app_enabled"))
    db.session.commit()
    flash("Notification preference saved. Critical security and direct-assignment alerts remain enabled.", "success")
    return redirect(url_for("erp.notifications"))
