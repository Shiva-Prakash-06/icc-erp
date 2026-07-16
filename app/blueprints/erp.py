from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from app.database import db
from app.models.erp import AuditEvent, ChecklistItemStatus, DocumentRecord, ImportBatch, OperatingUnit, Person, ProjectSession, ReportSnapshot, Wing, WorkTask
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.production import Notification, NotificationPreference
from app.services.audit import record_audit, record_sensitive_access
from app.services.authorization import can_view_project, has_permission
from app.services.drive import extract_drive_id
from app.services.imports import commit_batch, stage_supplied_source
from app.services.lifecycle import TRANSITIONS, closure_blockers, transition_project
from app.services.operations import change_checklist_status, change_task_status
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
                flash(f"Project {code} created in Draft.", "success")
                return redirect(url_for("erp.project_detail", public_id=project.public_id))
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
    )


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
    return render_template("erp/imports.html", batches=batches)


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
