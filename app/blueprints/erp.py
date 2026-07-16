from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from app.database import db
from app.models.erp import AuditEvent, ChecklistItemStatus, ImportBatch, Person, ProjectSession, ReportSnapshot, WorkTask
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.services.audit import record_audit
from app.services.authorization import can_view_project, has_permission
from app.services.imports import commit_batch, stage_supplied_source
from app.services.lifecycle import TRANSITIONS, closure_blockers, transition_project


erp_bp = Blueprint("erp", __name__, url_prefix="/erp")


@erp_bp.get("")
def hub():
    projects = [project for project in Project.query.order_by(Project.start_date.desc()).all() if can_view_project(g.user, project)]
    stats = {
        "projects": len(projects),
        "active": sum(project.status in {"Planned", "Active", "Closing"} for project in projects),
        "people": Person.query.count() if has_permission(g.user, "manage_projects") else None,
        "imports": ImportBatch.query.count() if has_permission(g.user, "manage_projects") else None,
    }
    return render_template("erp/hub.html", projects=projects[:8], stats=stats)


@erp_bp.route("/projects", methods=["GET", "POST"])
def projects():
    if request.method == "POST":
        if not has_permission(g.user, "manage_projects"):
            abort(403)
        required = ["title", "campus_id", "program_type_id", "academic_year_id", "start_date", "end_date"]
        if any(not request.form.get(field) for field in required):
            flash("Complete every required project field.", "danger")
        else:
            start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
            end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()
            if end_date < start_date:
                flash("End date cannot precede start date.", "danger")
            else:
                program = db.session.get(ProgramType, int(request.form["program_type_id"]))
                campus = db.session.get(Campus, int(request.form["campus_id"]))
                count = Project.query.filter_by(program_type_id=program.id, academic_year_id=int(request.form["academic_year_id"]), campus_id=campus.id).count() + 1
                code = f"{program.name}-2026-{campus.code or 'CAMP'}-{count:03d}"
                project = Project(
                    code=code,
                    title=request.form["title"].strip(),
                    description=request.form.get("description", "").strip(),
                    project_type=request.form.get("project_type", "ICC event"),
                    category=request.form.get("category", "Operational"),
                    campus_id=campus.id,
                    program_type_id=program.id,
                    academic_year_id=int(request.form["academic_year_id"]),
                    status="Draft",
                    start_date=start_date,
                    end_date=end_date,
                    venue=request.form.get("venue", "").strip(),
                    target_audience=request.form.get("target_audience", "").strip(),
                )
                db.session.add(project)
                db.session.flush()
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
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    task = WorkTask.query.filter_by(public_id=task_public_id, project_id=project.id).first_or_404()
    status = request.form.get("status")
    comment = request.form.get("comment", "").strip()
    if status not in {"Not Started", "In Progress", "Blocked", "Submitted", "Approved", "Rejected", "Waived", "Completed"}:
        flash("Invalid task status.", "danger")
    elif status == "Rejected" and not comment:
        flash("A rejection reason is required.", "danger")
    elif status == "Waived" and not has_permission(g.user, "approve", project):
        abort(403)
    elif status == "Waived" and not comment:
        flash("A faculty-approved waiver requires justification.", "danger")
    else:
        before = {"status": task.status}
        task.status = status
        task.decision_comment = comment or task.decision_comment
        if status == "Waived":
            task.waived = True
            task.waiver_reason = comment
            task.waived_by_id = g.user.id
        record_audit("task.status", task, before=before, after={"status": status, "comment": comment})
        db.session.commit()
        flash("Task status updated.", "success")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/<string:public_id>/checklist-items/<string:item_public_id>/status")
def update_checklist_item(public_id, item_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    item = (
        ChecklistItemStatus.query.join(ChecklistItemStatus.checklist)
        .filter(ChecklistItemStatus.public_id == item_public_id, ChecklistItemStatus.checklist.has(project_id=project.id))
        .first_or_404()
    )
    status = request.form.get("status")
    comment = request.form.get("comment", "").strip()
    if status not in {"Not Started", "In Progress", "Blocked", "Submitted", "Approved", "Rejected", "Waived", "Completed"}:
        flash("Invalid checklist status.", "danger")
    elif status == "Rejected" and not comment:
        flash("A rejection reason is required.", "danger")
    elif status == "Waived" and (not has_permission(g.user, "approve", project) or not comment):
        flash("A faculty-approved waiver requires justification.", "danger")
    else:
        before = {"status": item.status, "waived": item.waived}
        item.status = status
        item.decision_comment = comment or item.decision_comment
        if status == "Waived":
            item.waived = True
            item.waiver_reason = comment
            item.verifier_id = g.user.id
        elif status in {"Approved", "Completed"}:
            item.verifier_id = g.user.id
            item.verified_at = datetime.utcnow()
        record_audit("checklist.status", item, before=before, after={"status": status, "comment": comment})
        db.session.commit()
        flash("Checklist requirement updated.", "success")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.get("/imports")
def imports():
    if not has_permission(g.user, "manage_projects"):
        abort(403)
    batches = ImportBatch.query.order_by(ImportBatch.created_at.desc()).all()
    return render_template("erp/imports.html", batches=batches)


@erp_bp.post("/imports/stage")
def stage_import():
    if not has_permission(g.user, "manage_projects"):
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
    snapshot = {
        "project": {"code": project.code, "title": project.title, "status": project.status},
        "counts": {
            "team": len(getattr(project, "team_assignments", [])),
            "sessions": len(project.sessions),
            "tasks": len(project.work_tasks),
            "documents": len(project.document_records),
            "closure_blockers": len(closure_blockers(project)),
        },
        "reach": {"expected": project.expected_reach, "actual": project.actual_reach},
        "closure_summary": project.closure_summary,
    }
    report = ReportSnapshot(
        project_id=project.id,
        report_type="Project Operational Report",
        title=f"{project.title} — operational preview",
        snapshot_json=snapshot,
        source_references=[project.public_id],
        generated_by_id=g.user.id,
    )
    db.session.add(report)
    record_audit("report.generate", report, after={"project": project.public_id})
    db.session.commit()
    return render_template("erp/report_preview.html", project=project, report=report, snapshot=snapshot)


@erp_bp.get("/audit")
def audit():
    if not has_permission(g.user, "audit"):
        abort(403)
    events = AuditEvent.query.order_by(AuditEvent.occurred_at.desc()).limit(200).all()
    return render_template("erp/audit.html", events=events)
