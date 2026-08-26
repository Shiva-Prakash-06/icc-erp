from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

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
from app.models.production import AttendanceChangeEvent, ContributionRecord, Notification, NotificationPreference, ProjectRisk, RecruitmentApplication
from app.models.project import AcademicYear, BuddyAssignment, BuddyLog, Campus, ProgramType, Project
from app.models.user import User
from app.services.audit import record_audit, record_sensitive_access
from app.services.authorization import can_view_project, has_any_permission, has_permission
from app.services.buddy import validate_buddy_assignment
from app.services.drive import extract_drive_id, refresh_document_metadata
from app.services.imports import STANDARD_IMPORTS, commit_batch, stage_supplied_source, stage_uploaded_source
from app.services.itinerary import (
    ItineraryParseError,
    commit_itinerary_batch,
    create_igp_project_from_itinerary,
    stage_itinerary_import,
)
from app.services.project_quickcreate import create_minimal_project
from app.services.scope import visible_projects
from app.services.buddy_import import BuddyImportError, commit_buddy_batch, stage_buddy_import
from app.models.erp import ReimbursementEntry
from app.services.reimbursements import (
    ReimbursementImportError,
    commit_reimbursement_batch,
    export_reimbursements,
    stage_reimbursement_import,
)
from app.services.icc_import import (
    commit_icc_attendance_batch,
    stage_icc_attendance_import,
    stage_icc_event_folder_import,
)
from app.services.upload_sessions import UploadSessionError, upload_file_single_shot
from app.services.documents import compute_availability
from app.services.report_assembly import ReportIncompleteError, assemble_complete_report, preflight_report
from app.services.lifecycle import TRANSITIONS, closure_blockers, transition_project
from app.services.people import create_and_enroll_participant
from app.services.vocabulary import resolve_vocabulary_value, vocabulary_options
from app.services.publication import decide_project_publication, submit_project_publication
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
    # Merged into the home page -- see dashboard.index / app/services/home.py.
    # Kept as a route so old bookmarks and links still resolve.
    return redirect(url_for("dashboard.index"))


@erp_bp.get("/campuses")
def campuses():
    """Scoped, read-only campus list derived from projects the caller can
    already see -- not a restoration of the deleted legacy campus-hierarchy
    analytics module. See PLAN.md "ICC campus definition" finding."""
    campus_rows = {}
    for project in visible_projects(g.user):
        row = campus_rows.setdefault(project.campus_id, {"campus": project.campus, "project_count": 0, "active_count": 0})
        row["project_count"] += 1
        if project.status in {"Planned", "Active", "Closing"}:
            row["active_count"] += 1
    rows = sorted(campus_rows.values(), key=lambda row: row["campus"].name)
    return render_template("erp/campuses.html", rows=rows)


@erp_bp.get("/campuses/<string:public_id>")
def campus_detail(public_id):
    campus = Campus.query.filter_by(public_id=public_id).first_or_404()
    projects = [project for project in visible_projects(g.user) if project.campus_id == campus.id]
    if not projects:
        abort(404)
    return render_template("erp/campus_detail.html", campus=campus, projects=projects)


@erp_bp.get("/oversight")
def oversight():
    # Merged into the home page's decision queue -- see dashboard.index /
    # app/services/home.py. The 403 gate is kept here (not just on the
    # queue section of "/") because e2e/auth-and-rbac and
    # tests/production_completion_test assert this exact route still 403s
    # for non-approvers.
    if not has_any_permission(g.user, "approve"):
        abort(403)
    return redirect(url_for("dashboard.index", queue="all"))


@erp_bp.route("/projects", methods=["GET", "POST"])
def projects():
    if request.method == "POST":
        if not has_any_permission(g.user, "manage_projects"):
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
                try:
                    category = resolve_vocabulary_value(request.form.get("category", "Operational"), request.form.get("category_other"), domain="project_category")
                    project_type = resolve_vocabulary_value(request.form.get("project_type", "ICC event"), request.form.get("project_type_other"), domain="project_type")
                except ValueError as error:
                    flash(str(error), "danger")
                    return redirect(url_for("erp.projects"))
                project = Project(
                    title=request.form["title"].strip(),
                    description=request.form.get("description", "").strip(),
                    project_type=project_type,
                    category=category,
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
                return redirect(url_for("erp.project_setup", public_id=project.public_id, step="sessions"))
    return _render_projects(show_create=request.args.get("new") == "1")


@erp_bp.get("/projects/new")
def new_project():
    if not has_any_permission(g.user, "manage_projects"):
        abort(403)
    return render_template(
        "erp/create_project.html",
        program_types=ProgramType.query.order_by(ProgramType.name).all(),
    )


@erp_bp.post("/projects/quick-create")
def quick_create_project():
    if not has_any_permission(g.user, "manage_projects"):
        abort(403)
    try:
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
        project = create_minimal_project(
            program_type_name=request.form.get("program_type_name"),
            title=request.form.get("title"), start_date=start_date, end_date=end_date,
            actor=g.user, venue=request.form.get("venue"), target_audience=request.form.get("target_audience"),
        )
    except (ValueError, KeyError) as error:
        flash(str(error), "danger")
        return redirect(url_for("erp.new_project"))
    record_audit("project.create", project, after={"code": project.code, "title": project.title, "source": "quick_create"})
    db.session.commit()
    flash(f"Project {project.code} created.", "success")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/quick-create-from-itinerary")
def quick_create_from_itinerary():
    if not has_any_permission(g.user, "manage_projects"):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose an itinerary file to upload.", "danger")
        return redirect(url_for("erp.new_project"))
    try:
        project, batch = create_igp_project_from_itinerary(uploaded_file, g.user)
    except (ItineraryParseError, ValueError) as error:
        flash(f"Could not create the project from this itinerary: {error}", "danger")
        return redirect(url_for("erp.new_project"))
    flash(f"Project {project.code} created with {batch.committed_count} itinerary sessions.", "success")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/quick-create-with-documents")
def quick_create_with_documents():
    if not has_any_permission(g.user, "manage_projects"):
        abort(403)
    uploaded_files = [f for f in request.files.getlist("source_files") if f and f.filename]
    try:
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
        project = create_minimal_project(
            program_type_name=request.form.get("program_type_name"),
            title=request.form.get("title"), start_date=start_date, end_date=end_date, actor=g.user,
        )
    except (ValueError, KeyError) as error:
        flash(str(error), "danger")
        return redirect(url_for("erp.new_project"))
    attached = 0
    for uploaded_file in uploaded_files:
        try:
            upload_file_single_shot(project, uploaded_file.filename, uploaded_file.read(), g.user)
            attached += 1
        except UploadSessionError as error:
            flash(f"{uploaded_file.filename}: {error}", "danger")
    flash(f"Project {project.code} created with {attached} document(s) uploaded.", "success")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


def _render_projects(*, show_create=False):
    visible = [project for project in Project.query.order_by(Project.start_date.desc(), Project.id.desc()).all() if can_view_project(g.user, project)]
    search_query = (request.args.get("q") or "").strip()
    if search_query:
        needle = search_query.lower()
        visible = [
            project for project in visible
            if needle in (project.title or "").lower() or needle in (project.code or "").lower()
        ]
    campuses = Campus.query.order_by(Campus.name).all()
    programs = ProgramType.query.order_by(ProgramType.name).all()
    academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    wings = Wing.query.order_by(Wing.name).all()

    # Do not offer a value that cannot participate in at least one project
    # candidate authorized by the caller's active assignments.
    allowed_campus_ids, allowed_program_ids, allowed_year_ids, allowed_wing_ids = set(), set(), set(), set()
    for campus in campuses:
        for program in programs:
            unit = OperatingUnit.query.filter_by(code=program.name.upper()).first()
            if not unit:
                continue
            program_wings = [None] + [wing for wing in wings if wing.operating_unit_id == unit.id]
            for academic_year in academic_years:
                for wing in program_wings:
                    candidate = Project(
                        campus_id=campus.id, program_type_id=program.id,
                        operating_unit_id=unit.id, wing_id=getattr(wing, "id", None),
                        academic_year_id=academic_year.id,
                    )
                    if has_permission(g.user, "manage_projects", candidate):
                        allowed_campus_ids.add(campus.id)
                        allowed_program_ids.add(program.id)
                        allowed_year_ids.add(academic_year.id)
                        if wing:
                            allowed_wing_ids.add(wing.id)
    return render_template(
        "erp/projects.html",
        projects=visible,
        campuses=[item for item in campuses if item.id in allowed_campus_ids],
        program_types=[item for item in programs if item.id in allowed_program_ids],
        academic_years=[item for item in academic_years if item.id in allowed_year_ids],
        wings=[item for item in wings if item.id in allowed_wing_ids],
        can_create=has_any_permission(g.user, "manage_projects"),
        show_create=show_create,
        search_query=search_query,
        project_category_options=vocabulary_options("project_category"),
        project_type_options=vocabulary_options("project_type"),
    )


def _project(public_id):
    project = Project.query.filter_by(public_id=public_id).first_or_404()
    if not can_view_project(g.user, project):
        abort(403)
    return project


# A record is "settled" once nobody needs to act on it further -- used to
# split each operational section into an always-visible "needs action" list
# and a same-shaped list behind a "show settled" disclosure, so a deep link
# from the home decision queue always lands on visible content. See
# in-the-operation-checklists-crystalline-dongarra.md Step 8.
SETTLED_WORK_STATUSES = frozenset({"Approved", "Rejected", "Waived", "Completed", "Cancelled"})

_PROJECT_TABS = {"overview", "people", "delivery", "contributions", "finance", "insights", "resources"}
# "operations" used to be the single tab holding tasks, checklists,
# contributions, requests and budget behind one mega-disclosure; it is kept
# as a permanent read-only alias for old bookmarks/emailed links, resolving
# to "delivery" -- see in-the-operation-checklists-crystalline-dongarra.md Step 8.
_PROJECT_TAB_ALIASES = {"operations": "delivery"}


@erp_bp.get("/projects/<string:public_id>")
def project_detail(public_id):
    project = _project(public_id)
    blockers = closure_blockers(project)
    requested_tab = _PROJECT_TAB_ALIASES.get(request.args.get("tab"), request.args.get("tab"))
    active_tab = requested_tab if requested_tab in _PROJECT_TABS else "overview"
    people_query = (request.args.get("people_q") or "").strip()
    people_matches = []
    if active_tab == "people" and len(people_query) >= 2:
        like = f"%{people_query}%"
        member_person_ids = {
            row.person_id for row in TeamAssignment.query.filter_by(project_id=project.id, status="Active").with_entities(TeamAssignment.person_id).all()
        }
        matches = (
            Person.query.filter(
                Person.is_archived.is_(False),
                db.or_(
                    Person.first_name.ilike(like), Person.last_name.ilike(like),
                    Person.preferred_name.ilike(like), Person.primary_email.ilike(like),
                    Person.registration_number.ilike(like),
                ),
            ).order_by(Person.first_name).limit(20).all()
        )
        people_matches = [
            {"public_id": p.public_id, "display_name": p.display_name, "registration_number": p.registration_number, "is_member": p.id in member_person_ids}
            for p in matches
        ]
    approved_responses = [
        response for form in project.feedback_forms for response in form.responses
        if response.moderation_status == "Approved"
    ]
    feedback_distribution = {value: 0 for value in range(1, 6)}
    for response in approved_responses:
        try:
            rating = int((response.answers_json or {}).get("rating"))
        except (TypeError, ValueError):
            continue
        if rating in feedback_distribution:
            feedback_distribution[rating] += 1
    return render_template(
        "erp/project_detail.html",
        project=project,
        blockers=blockers,
        transitions=sorted(TRANSITIONS.get(project.status, set())),
        can_manage=has_permission(g.user, "manage_projects", project),
        can_contribute=has_permission(g.user, "contribute", project),
        current_person_id=g.user.person_id,
        current_user_id=g.user.id,
        can_approve=has_permission(g.user, "approve", project),
        can_approve_operational_requests=has_permission(g.user, "approve_operational_requests", project),
        can_decide_publication=has_permission(g.user, "manage_governance", project),
        can_waive=has_permission(g.user, "waive", project),
        can_view_sensitive=has_permission(g.user, "sensitive_links", project, sensitive=True),
        active_tab=active_tab,
        is_igp=project.program_type.name == "IGP",
        checklist_templates=ChecklistTemplate.query.filter_by(is_active=True).order_by(ChecklistTemplate.name).all(),
        contribution_statuses=("Approved", "Rejected"),
        feedback_distribution=feedback_distribution,
        approved_feedback_count=sum(feedback_distribution.values()),
        recruitment_applications=RecruitmentApplication.query.filter_by(project_id=project.id).order_by(RecruitmentApplication.created_at.desc()).all(),
        report_snapshots=ReportSnapshot.query.filter_by(project_id=project.id).order_by(ReportSnapshot.created_at.desc()).all(),
        people_query=people_query,
        people_matches=people_matches,
        eligible_participants=[assignment.person for assignment in project.team_assignments if assignment.status == "Active"],
        assignment_role_options=vocabulary_options("assignment_role"),
        operational_request_type_options=vocabulary_options("operational_request_type"),
        budget_category_options=vocabulary_options("budget_category"),
        contribution_activity_options=vocabulary_options("contribution_activity"),
        document_category_options=vocabulary_options("document_category"),
        compute_availability=compute_availability,
        settled_statuses=SETTLED_WORK_STATUSES,
        open_tasks=[task for task in project.work_tasks if task.status not in SETTLED_WORK_STATUSES],
        settled_tasks=[task for task in project.work_tasks if task.status in SETTLED_WORK_STATUSES],
        open_contributions=[c for c in project.contribution_records if c.approval_status == "Pending"],
        settled_contributions=[c for c in project.contribution_records if c.approval_status != "Pending"],
        open_requests=[r for r in project.operational_requests if r.status not in {"Approved", "Rejected", "Completed", "Cancelled"}],
        settled_requests=[r for r in project.operational_requests if r.status in {"Approved", "Rejected", "Completed", "Cancelled"}],
        open_budget_lines=[b for b in project.budget_lines if b.status not in {"Approved", "Rejected"}],
        settled_budget_lines=[b for b in project.budget_lines if b.status in {"Approved", "Rejected"}],
    )


def _redirect_to_tab(project, tab, anchor=None):
    return redirect(url_for("erp.project_detail", public_id=project.public_id, tab=tab) + (f"#{anchor}" if anchor else ""))


@erp_bp.post("/projects/<string:public_id>/applications/<string:application_public_id>/decision")
def decide_recruitment_route(public_id, application_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_people", project):
        abort(403)
    application = RecruitmentApplication.query.filter_by(public_id=application_public_id, project_id=project.id).first_or_404()
    try:
        decide_recruitment(
            application, request.form.get("decision"), g.user,
            expected_version=request.form.get("version"), reason=request.form.get("reason"),
        )
        flash("Recruitment decision recorded.", "success")
    except ValueError as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "people", application.public_id)


@erp_bp.post("/projects/<string:public_id>/reports/<string:snapshot_public_id>/approve")
def approve_report_route(public_id, snapshot_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "approve", project):
        abort(403)
    snapshot = ReportSnapshot.query.filter_by(public_id=snapshot_public_id, project_id=project.id).first_or_404()
    if snapshot.approval_status != "Approved":
        snapshot.approval_status = "Approved"
        snapshot.approved_by_id = g.user.id
        snapshot.approved_at = datetime.now(timezone.utc)
        record_audit("report.approve", snapshot, after={"approval_status": "Approved"}, actor=g.user)
        db.session.commit()
    flash("Report approved.", "success")
    return _redirect_to_tab(project, "insights", snapshot.public_id)


WIZARD_STEPS = ["basics", "sessions", "team", "checklist", "documents", "budget"]


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
    people_query = (request.args.get("people_q") or "").strip()
    people_matches = []
    if step == "team" and len(people_query) >= 2:
        like = f"%{people_query}%"
        member_person_ids = {
            row.person_id for row in TeamAssignment.query.filter_by(project_id=project.id, status="Active").with_entities(TeamAssignment.person_id).all()
        }
        matches = (
            Person.query.filter(
                Person.is_archived.is_(False),
                db.or_(
                    Person.first_name.ilike(like), Person.last_name.ilike(like),
                    Person.preferred_name.ilike(like), Person.primary_email.ilike(like),
                    Person.registration_number.ilike(like),
                ),
            ).order_by(Person.first_name).limit(20).all()
        )
        people_matches = [
            {"public_id": p.public_id, "display_name": p.display_name, "registration_number": p.registration_number, "is_member": p.id in member_person_ids}
            for p in matches
        ]
    return render_template(
        "erp/project_setup.html",
        project=project, step=step, steps=WIZARD_STEPS,
        is_igp=project.program_type.name == "IGP",
        checklist_templates=ChecklistTemplate.query.filter_by(is_active=True).order_by(ChecklistTemplate.name).all(),
        completed={
            "basics": True,
            "sessions": bool(project.sessions), "team": bool(project.team_assignments),
            "checklist": bool(project.checklists), "documents": bool(project.document_records),
            "budget": bool(project.budget_lines),
        },
        people_query=people_query,
        people_matches=people_matches,
        session_type_options=vocabulary_options("session_type"),
        assignment_role_options=vocabulary_options("assignment_role"),
        budget_category_options=vocabulary_options("budget_category"),
    )


@erp_bp.post("/projects/<string:public_id>/basics")
def update_project_basics(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    title = (request.form.get("title") or "").strip()
    try:
        start_date = datetime.strptime(request.form.get("start_date", ""), "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form.get("end_date", ""), "%Y-%m-%d").date()
    except ValueError:
        flash("Provide valid project start and end dates.", "danger")
        return redirect(url_for("erp.project_setup", public_id=project.public_id, step="basics"))
    if not title or end_date < start_date:
        flash("A title is required and the end date cannot precede the start date.", "danger")
        return redirect(url_for("erp.project_setup", public_id=project.public_id, step="basics"))
    before = {"title": project.title, "start_date": str(project.start_date), "end_date": str(project.end_date)}
    project.title = title
    project.description = (request.form.get("description") or "").strip()
    project.venue = (request.form.get("venue") or "").strip()
    project.target_audience = (request.form.get("target_audience") or "").strip()
    project.start_date = start_date
    project.end_date = end_date
    project.version += 1
    record_audit("project.basics", project, before=before, after={"title": title, "start_date": str(start_date), "end_date": str(end_date)}, actor=g.user)
    db.session.commit()
    flash("Project basics updated.", "success")
    return redirect(url_for("erp.project_setup", public_id=project.public_id, step="sessions"))


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
    try:
        session_type = resolve_vocabulary_value(request.form.get("session_type") or "Session", request.form.get("session_type_other"), domain="session_type")
    except ValueError as error:
        flash(str(error), "danger")
        return _redirect_after_action(project, "overview")
    existing_count = ProjectSession.query.filter_by(project_id=project.id).count()
    session_item = ProjectSession(
        project_id=project.id, code=request.form.get("code") or f"S{existing_count + 1}",
        title=title, session_type=session_type,
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
    person_public_id = (request.form.get("person_public_id") or "").strip()
    registration_number = (request.form.get("registration_number") or "").strip()
    person = None
    if person_public_id:
        person = Person.query.filter_by(public_id=person_public_id).first()
    elif registration_number:
        # Compatibility path for the legacy registration-number lookup;
        # UI enrollment now uses person_public_id via the scoped search.
        person = Person.query.filter_by(registration_number=registration_number).first()
    if not person:
        flash("No matching person found.", "danger")
        return _redirect_after_action(project, "people")
    if TeamAssignment.query.filter_by(person_id=person.id, project_id=project.id).first():
        flash(f"{person.display_name} is already on this project's team.", "warning")
        return _redirect_after_action(project, "people")
    try:
        role_label = _resolve_role_label()
    except ValueError as error:
        flash(str(error), "danger")
        return _redirect_after_action(project, "people")
    assignment = TeamAssignment(
        person_id=person.id, project_id=project.id,
        assignment_type=request.form.get("assignment_type") or "Project Team",
        role_label=role_label,
    )
    db.session.add(assignment)
    record_audit("team.enroll", assignment, after={"person": person.public_id, "project": project.public_id}, actor=g.user)
    db.session.commit()
    flash(f"{person.display_name} added to the project team.", "success")
    return _redirect_after_action(project, "people")


@erp_bp.post("/projects/<string:public_id>/team/create-and-enroll")
def create_and_enroll_team_member(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    try:
        role_label = _resolve_role_label()
        person, _assignment, created_new_person = create_and_enroll_participant(
            project, g.user,
            first_name=request.form.get("first_name"),
            last_name=request.form.get("last_name"),
            email=request.form.get("email"),
            registration_number=request.form.get("registration_number"),
            assignment_type=request.form.get("assignment_type") or "Project Team",
            role_label=role_label,
        )
        verb = "created and added" if created_new_person else "found and added"
        flash(f"{person.display_name} {verb} to the project team.", "success")
    except ValueError as error:
        flash(str(error), "danger")
    return _redirect_after_action(project, "people")


def _resolve_role_label():
    value = (request.form.get("role_label") or "").strip()
    if not value:
        return None
    return resolve_vocabulary_value(value, request.form.get("role_label_other"), domain="assignment_role")


def _active_participant(project, person_public_id):
    """Resolve `person_public_id` to a Person only if they hold an Active
    TeamAssignment on `project` -- rejects inactive membership and
    cross-project IDs server-side. See PLAN.md "IGP registration number"
    finding: buddy selection must list only eligible project participants."""
    person_public_id = (person_public_id or "").strip()
    if not person_public_id:
        return None
    return (
        Person.query.join(TeamAssignment, TeamAssignment.person_id == Person.id)
        .filter(Person.public_id == person_public_id, TeamAssignment.project_id == project.id, TeamAssignment.status == "Active")
        .first()
    )


@erp_bp.post("/projects/<string:public_id>/buddy-assignments")
def add_buddy_assignment(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    buddy_person = _active_participant(project, request.form.get("buddy_person_public_id"))
    student_person = _active_participant(project, request.form.get("exchange_student_person_public_id"))
    if not buddy_person or not student_person:
        flash("Both the buddy and exchange student must be active participants of this project.", "danger")
        return _redirect_to_tab(project, "people")
    if buddy_person.id == student_person.id:
        flash("A buddy cannot be paired with themselves.", "danger")
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
    events = (
        AttendanceChangeEvent.query.join(SessionAttendance)
        .filter(SessionAttendance.session_id == session_item.id)
        .order_by(AttendanceChangeEvent.occurred_at.desc(), AttendanceChangeEvent.id.desc())
        .all()
    )
    actor_ids = {event.actor_user_id for event in events if event.actor_user_id}
    actors = {user.id: user.username for user in User.query.filter(User.id.in_(actor_ids or [-1])).all()}
    return render_template(
        "erp/attendance_roll_call.html", project=project, session=session_item,
        team=project.team_assignments, records=records, events=events, actors=actors,
    )


@erp_bp.post("/projects/<string:public_id>/sessions/<string:session_public_id>/attendance")
def mark_session_attendance(public_id, session_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    session_item = ProjectSession.query.filter_by(public_id=session_public_id, project_id=project.id).first_or_404()
    failures = []
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
                reason=(request.form.get(f"reason_{team_assignment.person_id}") or "").strip() if existing else None,
                commit=False,
            )
        except ValueError as error:
            failures.append(f"{team_assignment.person.display_name}: {error}")
    if failures:
        db.session.rollback()
        flash("No attendance changes were saved. " + " ".join(failures), "danger")
        return redirect(url_for("erp.attendance_roll_call", public_id=project.public_id, session_public_id=session_item.public_id))
    db.session.commit()
    flash("Attendance recorded.", "success")
    return _redirect_to_tab(project, "people")


@erp_bp.post("/projects/<string:public_id>/contributions")
def log_contribution(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "contribute", project):
        abort(403)
    if not g.user.person_id:
        flash("Your account has no linked person record; contact an administrator.", "danger")
        return _redirect_to_tab(project, "contributions")
    try:
        activity_type = resolve_vocabulary_value(
            request.form.get("activity_type") or "Event support",
            request.form.get("activity_type_other"),
            domain="contribution_activity",
        )
    except ValueError as error:
        flash(str(error), "danger")
        return _redirect_to_tab(project, "contributions")
    contribution = ContributionRecord(
        project_id=project.id, person_id=g.user.person_id,
        activity_type=activity_type,
        description=(request.form.get("description") or "").strip() or "Contribution",
        duration_hours=request.form.get("duration_hours") or 1,
    )
    db.session.add(contribution)
    record_audit("contribution.log", contribution, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Contribution logged for approval.", "success")
    return _redirect_to_tab(project, "contributions")


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
    return _redirect_to_tab(project, "contributions")


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
    return _redirect_to_tab(project, "contributions")


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
    return _redirect_to_tab(project, "contributions")


@erp_bp.post("/projects/<string:public_id>/operational-requests")
def add_operational_request(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    try:
        request_type = resolve_vocabulary_value(request.form.get("request_type") or "Other", request.form.get("request_type_other"), domain="operational_request_type")
    except ValueError as error:
        flash(str(error), "danger")
        return _redirect_to_tab(project, "finance")
    operational_request = OperationalRequest(
        project_id=project.id, request_type=request_type,
        title=(request.form.get("title") or "").strip() or "Operational request",
        details=(request.form.get("details") or "").strip(), amount=request.form.get("amount") or None,
        owner_person_id=g.user.person_id, created_by_id=g.user.id,
    )
    db.session.add(operational_request)
    db.session.flush()
    record_audit("operational_request.create", operational_request, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Operational request created in Draft.", "success")
    return _redirect_to_tab(project, "finance")


@erp_bp.post("/projects/<string:public_id>/operational-requests/<string:request_public_id>/decision")
def decide_operational_request_route(public_id, request_public_id):
    project = _project(public_id)
    operational_request = OperationalRequest.query.filter_by(public_id=request_public_id, project_id=project.id).first_or_404()
    status = request.form.get("status")
    try:
        decide_operational_request(operational_request, status, g.user, expected_version=int(request.form.get("version") or operational_request.version), reason=request.form.get("reason"))
        flash("Operational request updated.", "success")
    except PermissionError:
        abort(403)
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "finance")


@erp_bp.post("/projects/<string:public_id>/budgets")
def add_budget_line(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    try:
        category = resolve_vocabulary_value(request.form.get("category") or "Other", request.form.get("category_other"), domain="budget_category")
    except ValueError as error:
        flash(str(error), "danger")
        return _redirect_after_action(project, "finance")
    line = BudgetLine(
        project_id=project.id, category=category,
        description=(request.form.get("description") or "").strip(),
        estimated_amount=request.form.get("estimated_amount") or 0,
    )
    db.session.add(line)
    record_audit("budget_line.create", line, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Budget line added in Draft.", "success")
    return _redirect_after_action(project, "finance")


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
    return _redirect_to_tab(project, "finance")


@erp_bp.post("/projects/<string:public_id>/feedback-forms")
def add_feedback_form(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    if FeedbackForm.query.filter_by(project_id=project.id, is_open=True).first():
        flash("An open feedback form already exists for this project.", "warning")
        return _redirect_to_tab(project, "insights")
    raw_questions = (request.form.get("questions") or "").splitlines()
    labels = [line.strip() for line in raw_questions]
    if any(not label for label in labels):
        flash("Remove blank question lines; each question must contain text.", "danger")
        return _redirect_to_tab(project, "insights")
    if len(labels) > 20:
        flash("A feedback form may contain at most 20 additional questions.", "danger")
        return _redirect_to_tab(project, "insights")
    if any(len(label) > 200 for label in labels):
        flash("Each feedback question must be 200 characters or fewer.", "danger")
        return _redirect_to_tab(project, "insights")
    questions = [{"key": "rating", "type": "scale", "min": 1, "max": 5, "label": "Overall rating"}]
    questions.extend({"key": f"q_{index}", "type": "text", "label": label} for index, label in enumerate(labels, 1))
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
    try:
        rating = int(request.form.get("rating", ""))
    except ValueError:
        rating = 0
    if rating not in range(1, 6):
        flash("Choose an overall rating from 1 to 5.", "danger")
        return _redirect_to_tab(project, "insights")
    answers = {"rating": rating}
    for question in form.questions_json or []:
        if question.get("type") == "text":
            answers[question["key"]] = (request.form.get(question["key"]) or "").strip()
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
    try:
        category = resolve_vocabulary_value(
            request.form.get("category") or "Other",
            request.form.get("category_other"),
            domain="document_category",
        )
    except ValueError as error:
        flash(str(error), "danger")
        return _redirect_after_action(project, "resources")
    drive_url = (request.form.get("drive_url") or "").strip() or None
    document = DocumentRecord(
        project_id=project.id, title=title, category=category,
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


@erp_bp.post("/projects/<string:public_id>/publication/submit")
def submit_publication(public_id):
    project = _project(public_id)
    try:
        submit_project_publication(project, g.user, expected_version=int(request.form.get("version") or project.version))
        flash("Publication requested; awaiting review.", "success")
    except PermissionError:
        abort(403)
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/<string:public_id>/publication/decision")
def decide_publication(public_id):
    project = _project(public_id)
    try:
        decide_project_publication(
            project, request.form.get("decision"), g.user,
            expected_version=int(request.form.get("version") or project.version),
            reason=request.form.get("reason"),
        )
        flash(f"Publication moved to {project.publication_status}.", "success")
    except PermissionError:
        abort(403)
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
    return _redirect_to_tab(project, "delivery")


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
    return _redirect_to_tab(project, "delivery", task.public_id)


def _checklist_item(project, item_public_id):
    return (
        ChecklistItemStatus.query.join(ChecklistItemStatus.checklist)
        .filter(ChecklistItemStatus.public_id == item_public_id, ChecklistItemStatus.checklist.has(project_id=project.id))
        .first_or_404()
    )


def _can_edit_checklist_item(project, item):
    owner_update = g.user.person_id and item.owner_person_id == g.user.person_id and has_permission(g.user, "contribute", project)
    return bool(owner_update or has_permission(g.user, "manage_projects", project))


@erp_bp.post("/projects/<string:public_id>/checklist-items/<string:item_public_id>/status")
def update_checklist_item(public_id, item_public_id):
    project = _project(public_id)
    item = _checklist_item(project, item_public_id)
    if not _can_edit_checklist_item(project, item):
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
    return _redirect_to_tab(project, "delivery", item.public_id)


@erp_bp.post("/projects/<string:public_id>/checklist-items/<string:item_public_id>/documents")
def attach_checklist_document(public_id, item_public_id):
    """Link an existing project document to a checklist requirement as
    evidence. Neither this nor detach/upload bumps `item.version` or
    `document.version` -- both are FK-only writes, deliberately, so
    attaching evidence never makes an already-rendered status/decision form
    go stale (409) for someone else. See
    in-the-operation-checklists-crystalline-dongarra.md Step 3."""
    project = _project(public_id)
    item = _checklist_item(project, item_public_id)
    if not _can_edit_checklist_item(project, item):
        abort(403)
    document_public_id = (request.form.get("document_public_id") or "").strip()
    if not document_public_id:
        flash("Choose a document to attach.", "danger")
        return _redirect_to_tab(project, "delivery", item.public_id)
    document = DocumentRecord.query.filter_by(public_id=document_public_id, project_id=project.id).first_or_404()
    # Restricted documents are masked with 404, not 403 -- a 403 would let a
    # caller confirm a restricted document's public_id exists.
    if document.permission_classification == "Restricted" and not has_permission(g.user, "sensitive_links", project, sensitive=True):
        abort(404)
    if document.checklist_status_id == item.id:
        flash("That document is already linked to this requirement.", "info")
        return _redirect_to_tab(project, "delivery", item.public_id)
    if document.checklist_status_id is not None and not has_permission(g.user, "manage_projects", project):
        flash("That document is linked to another requirement. Ask a coordinator to move it.", "danger")
        return _redirect_to_tab(project, "delivery", item.public_id)
    before = {"checklist_status_id": document.checklist_status_id}
    document.checklist_status_id = item.id
    record_audit("document.link_checklist", document, before=before, after={"checklist_status": item.public_id, "project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Document linked to the requirement.", "success")
    return _redirect_to_tab(project, "delivery", item.public_id)


@erp_bp.post("/projects/<string:public_id>/checklist-items/<string:item_public_id>/documents/upload")
def upload_checklist_document(public_id, item_public_id):
    """Upload a new document and attach it to a checklist requirement in
    one step, reusing the same single-shot pipeline as the Resources tab's
    multi-file uploader (auto-classification, Drive storage, checksum
    dedupe/supersession)."""
    project = _project(public_id)
    item = _checklist_item(project, item_public_id)
    if not _can_edit_checklist_item(project, item):
        abort(403)
    uploaded = request.files.get("source_file")
    if not uploaded or not uploaded.filename:
        flash("Choose a file to upload.", "danger")
        return _redirect_to_tab(project, "delivery", item.public_id)
    category = None
    if request.form.get("category"):
        try:
            category = resolve_vocabulary_value(request.form.get("category"), request.form.get("category_other"), domain="document_category")
        except ValueError as error:
            flash(str(error), "danger")
            return _redirect_to_tab(project, "delivery", item.public_id)
    classification = request.form.get("permission_classification") or None
    try:
        document = upload_file_single_shot(project, uploaded.filename, uploaded.read(), g.user, category=category, classification=classification)
    except (UploadSessionError, ValueError) as error:
        flash(str(error), "danger")
        return _redirect_to_tab(project, "delivery", item.public_id)
    if document.checklist_status_id in (None, item.id) or has_permission(g.user, "manage_projects", project):
        document.checklist_status_id = item.id
        record_audit("document.link_checklist", document, after={"checklist_status": item.public_id, "project": project.public_id, "via": "upload"}, actor=g.user)
        db.session.commit()
        flash("Document uploaded and linked to the requirement.", "success")
    else:
        flash("Document uploaded, but it is already linked to another requirement.", "warning")
    return _redirect_to_tab(project, "delivery", item.public_id)


@erp_bp.post("/projects/<string:public_id>/checklist-items/<string:item_public_id>/documents/<string:document_public_id>/detach")
def detach_checklist_document(public_id, item_public_id, document_public_id):
    """Unlink a document from a checklist requirement. This never deletes
    the document, calls Drive, or changes its status -- the document simply
    returns to the unlinked resources index."""
    project = _project(public_id)
    item = _checklist_item(project, item_public_id)
    if not _can_edit_checklist_item(project, item):
        abort(403)
    document = DocumentRecord.query.filter_by(public_id=document_public_id, project_id=project.id, checklist_status_id=item.id).first_or_404()
    document.checklist_status_id = None
    record_audit("document.unlink_checklist", document, before={"checklist_status": item.public_id}, after={"checklist_status": None}, actor=g.user)
    db.session.commit()
    flash("Document unlinked.", "success")
    return _redirect_to_tab(project, "delivery", item.public_id)


@erp_bp.post("/projects/<string:public_id>/itinerary/upload")
def upload_itinerary(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose an itinerary file to upload.", "danger")
        return _redirect_after_action(project, "resources")
    try:
        batch = stage_itinerary_import(project, uploaded_file, g.user.public_id)
        commit_itinerary_batch(batch, g.user)
        flash(
            f"Itinerary imported: {batch.committed_count} sessions across "
            f"{(batch.reconciliation_json or {}).get('day_count', '?')} days.",
            "success",
        )
    except (ItineraryParseError, ValueError) as error:
        flash(f"Itinerary import failed: {error}", "danger")
    return _redirect_after_action(project, "resources")


@erp_bp.post("/projects/<string:public_id>/buddies/upload")
def upload_buddy_allocation(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a buddy allocation file to upload.", "danger")
        return _redirect_after_action(project, "people")
    try:
        batch = stage_buddy_import(project, uploaded_file, g.user.public_id)
        commit_buddy_batch(batch, g.user)
        message = f"Buddy allocation imported: {batch.committed_count} of {batch.staged_count} rows committed."
        if batch.error_count:
            message += f" {batch.error_count} row(s) need correction (see import batch for details)."
        flash(message, "success" if not batch.error_count else "warning")
    except (BuddyImportError, ValueError) as error:
        flash(f"Buddy allocation import failed: {error}", "danger")
    return _redirect_after_action(project, "people")


@erp_bp.post("/projects/<string:public_id>/reimbursements")
def add_reimbursement(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    try:
        amount = Decimal(request.form.get("amount") or "")
        if amount < 0:
            raise ValueError("Amount cannot be negative.")
        entry_date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
    except (InvalidOperation, ValueError, TypeError):
        flash("A valid date and non-negative amount are required.", "danger")
        return _redirect_after_action(project, "resources")
    party_name = (request.form.get("party_name") or "").strip()
    if not party_name:
        flash("Party name is required.", "danger")
        return _redirect_after_action(project, "resources")
    entry = ReimbursementEntry(
        project_id=project.id, date=entry_date, party_name=party_name,
        bill_number=(request.form.get("bill_number") or "").strip() or None,
        amount=amount, particular=(request.form.get("particular") or "").strip() or None,
        status=(request.form.get("status") or "").strip() or "Pending",
        created_by_id=g.user.id,
    )
    db.session.add(entry)
    db.session.commit()
    record_audit("reimbursement.create", entry, after={"project": project.public_id}, actor=g.user)
    flash("Reimbursement entry added.", "success")
    return _redirect_after_action(project, "resources")


@erp_bp.post("/projects/<string:public_id>/reimbursements/<string:entry_public_id>/status")
def update_reimbursement_status(public_id, entry_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    entry = ReimbursementEntry.query.filter_by(public_id=entry_public_id, project_id=project.id).first_or_404()
    status = (request.form.get("status") or "").strip()
    if not status:
        flash("Status cannot be blank.", "danger")
        return _redirect_after_action(project, "resources")
    entry.status = status
    db.session.commit()
    record_audit("reimbursement.status", entry, after={"status": status}, actor=g.user)
    flash("Reimbursement status updated.", "success")
    return _redirect_after_action(project, "resources")


@erp_bp.post("/projects/<string:public_id>/reimbursements/upload")
def upload_reimbursements(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a reimbursements file to upload.", "danger")
        return _redirect_after_action(project, "resources")
    try:
        batch = stage_reimbursement_import(project, uploaded_file, g.user.public_id)
        commit_reimbursement_batch(batch, g.user)
        flash(f"Reimbursements imported: {batch.committed_count} of {batch.staged_count} rows committed.", "success")
    except (ReimbursementImportError, ValueError) as error:
        flash(f"Reimbursement import failed: {error}", "danger")
    return _redirect_after_action(project, "resources")


@erp_bp.get("/projects/<string:public_id>/reimbursements/export.<string:output_format>")
def export_reimbursements_route(public_id, output_format):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    if output_format not in {"csv", "xlsx"}:
        abort(404)
    buffer = export_reimbursements(project, output_format)
    mimetype = "text/csv" if output_format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=f"reimbursements-{project.code or project.public_id}.{output_format}")


@erp_bp.post("/projects/<string:public_id>/icc-attendance/upload")
def upload_icc_attendance(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a volunteer attendance file to upload.", "danger")
        return _redirect_after_action(project, "people")
    try:
        batch = stage_icc_attendance_import(project, uploaded_file, g.user.public_id)
        commit_icc_attendance_batch(batch, g.user)
        flash(f"Volunteer attendance imported: {batch.committed_count} of {batch.staged_count} rows committed.", "success")
    except ValueError as error:
        flash(f"Attendance import failed: {error}", "danger")
    return _redirect_after_action(project, "people")


@erp_bp.post("/projects/<string:public_id>/event-folder/upload")
def upload_icc_event_folder(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_files = [f for f in request.files.getlist("source_files") if f and f.filename]
    if not uploaded_files:
        flash("Choose one or more event-folder files to upload.", "danger")
        return _redirect_after_action(project, "resources")
    try:
        results = stage_icc_event_folder_import(project, uploaded_files, g.user)
        attached = sum(1 for r in results if r["status"] == "attached")
        duplicates = sum(1 for r in results if r["status"] == "duplicate")
        rejected = sum(1 for r in results if r["status"] == "rejected")
        flash(f"Event folder import: {attached} attached, {duplicates} duplicate, {rejected} rejected.", "success")
    except ValueError as error:
        flash(f"Event folder import failed: {error}", "danger")
    return _redirect_after_action(project, "resources")


@erp_bp.get("/imports")
def imports():
    if not has_permission(g.user, "manage_imports"):
        abort(403)
    batches = ImportBatch.query.order_by(ImportBatch.created_at.desc()).all()
    return render_template("erp/imports.html", batches=batches, standard_import_types=sorted(STANDARD_IMPORTS))


@erp_bp.post("/projects/<string:public_id>/documents/upload")
def upload_documents(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_files = [f for f in request.files.getlist("source_files") if f and f.filename]
    if not uploaded_files:
        flash("Choose one or more files to upload.", "danger")
        return _redirect_after_action(project, "resources")
    attached, failed = 0, []
    for uploaded_file in uploaded_files:
        try:
            content = uploaded_file.read()
            upload_file_single_shot(project, uploaded_file.filename, content, g.user)
            attached += 1
        except UploadSessionError as error:
            failed.append(f"{uploaded_file.filename}: {error}")
    if attached:
        flash(f"{attached} document(s) uploaded to Drive and indexed.", "success")
    for message in failed:
        flash(message, "danger")
    return _redirect_after_action(project, "resources")


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


@erp_bp.get("/projects/<string:public_id>/report/complete")
def complete_report_preview(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    preflight = preflight_report(project)
    return render_template("erp/complete_report_preview.html", project=project, preflight=preflight)


@erp_bp.get("/projects/<string:public_id>/report/preflight")
def report_preflight_route(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    return preflight_report(project)


@erp_bp.get("/projects/<string:public_id>/report/complete.pdf")
def download_complete_report(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    allow_incomplete = request.args.get("allow_incomplete") == "1"
    try:
        pdf_bytes, snapshot = assemble_complete_report(project, g.user, allow_incomplete=allow_incomplete)
    except ReportIncompleteError:
        flash("Some report dependencies are missing, inaccessible, or unsupported. Review them below before downloading.", "warning")
        return redirect(url_for("erp.complete_report_preview", public_id=project.public_id))
    record_audit("report.download_complete_pdf", snapshot, after={"project": project.public_id, "allow_incomplete": allow_incomplete})
    db.session.commit()
    return send_file(
        io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True,
        download_name=f"{project.code or project.public_id}-complete-report.pdf",
    )


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
    actor_ids = {event.actor_user_id for event in events if event.actor_user_id}
    actors = {user.id: user.username for user in User.query.filter(User.id.in_(actor_ids or [-1])).all()}
    return render_template("erp/audit.html", events=events, actors=actors)


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
