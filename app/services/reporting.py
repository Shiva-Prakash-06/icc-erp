"""Versioned, reproducible operational report compilation."""

from __future__ import annotations

from datetime import datetime, timezone
import io

from flask import current_app
from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
from docx import Document as WordDocument
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.database import db
from app.models.erp import BudgetLine, DocumentRecord, ReportSnapshot, SessionAttendance, WorkTask
from app.models.production import AggregateAttendance, ContributionRecord, ProjectRisk, ReportDefinition, ReportJob
from app.services.lifecycle import closure_blockers


def compile_project_snapshot(project, *, actor=None, report_type="Project Operational Report", filters=None):
    individual_attendance = (
        SessionAttendance.query.join(__import__("app.models.erp", fromlist=["ProjectSession"]).ProjectSession)
        .filter_by(project_id=project.id)
        .count()
    )
    aggregate_attendance = (
        db.session.query(db.func.coalesce(db.func.sum(AggregateAttendance.count), 0))
        .join(__import__("app.models.erp", fromlist=["ProjectSession"]).ProjectSession)
        .filter_by(project_id=project.id)
        .scalar()
    )
    budget_totals = db.session.query(
        db.func.coalesce(db.func.sum(BudgetLine.estimated_amount), 0),
        db.func.coalesce(db.func.sum(BudgetLine.approved_amount), 0),
        db.func.coalesce(db.func.sum(BudgetLine.actual_amount), 0),
    ).filter(BudgetLine.project_id == project.id).one()
    snapshot_data = {
        "project": {"public_id": project.public_id, "code": project.code, "title": project.title, "status": project.status},
        "reach": {"expected": project.expected_reach, "actual": project.actual_reach, "individual_attendance_records": individual_attendance, "aggregate_attendance": int(aggregate_attendance or 0)},
        "execution": {
            "tasks": WorkTask.query.filter_by(project_id=project.id).count(),
            "documents": DocumentRecord.query.filter_by(project_id=project.id).count(),
            "contributions": ContributionRecord.query.filter_by(project_id=project.id).count(),
            "open_critical_risks": ProjectRisk.query.filter_by(project_id=project.id, status="Open", is_critical=True).count(),
            "closure_blockers": [blocker.__dict__ for blocker in closure_blockers(project)],
        },
        "budget": {"estimated": str(budget_totals[0]), "approved": str(budget_totals[1]), "actual": str(budget_totals[2]), "currency": "INR"},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    next_version = (db.session.query(db.func.max(ReportSnapshot.version)).filter_by(project_id=project.id, report_type=report_type).scalar() or 0) + 1
    snapshot = ReportSnapshot(
        project_id=project.id,
        report_type=report_type,
        title=f"{project.title} — {report_type}",
        version=next_version,
        filters_json=filters or {},
        snapshot_json=snapshot_data,
        source_references=[project.public_id],
        approval_status="Draft",
        generated_by_id=getattr(actor, "id", None),
    )
    db.session.add(snapshot)
    db.session.flush()
    return snapshot


def execute_report_job(job):
    if job.status == "Completed":
        return job
    job.status = "Running"
    job.started_at = datetime.now(timezone.utc)
    try:
        project = db.session.get(__import__("app.models.project", fromlist=["Project"]).Project, job.project_id)
        if not project:
            raise ValueError("Report job has no accessible project.")
        definition = db.session.get(ReportDefinition, job.definition_id)
        snapshot = compile_project_snapshot(project, actor=db.session.get(__import__("app.models.user", fromlist=["User"]).User, job.requested_by_id), report_type=definition.report_type, filters=job.filters_json)
        job.snapshot_id = snapshot.id
        job.status = "Completed"
        job.completed_at = datetime.now(timezone.utc)
    except Exception as error:
        job.status = "Failed"
        job.error_summary = str(error)[:500]
        job.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return job


def enqueue_report_job(job):
    if current_app.config.get("APP_ENV") != "production":
        return None
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(current_app.config["GCP_PROJECT_ID"], current_app.config["GCP_REGION"], current_app.config["CLOUD_TASKS_QUEUE"])
    schedule_time = timestamp_pb2.Timestamp()
    schedule_time.FromDatetime(datetime.now(timezone.utc))
    task = {
        "name": f"{parent}/tasks/report-{job.public_id}",
        "schedule_time": schedule_time,
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{current_app.config['INTERNAL_JOB_BASE_URL'].rstrip('/')}/internal/jobs/reports/{job.public_id}/execute",
            "oidc_token": {
                "service_account_email": current_app.config["TASKS_SERVICE_ACCOUNT"],
                "audience": current_app.config["INTERNAL_JOB_AUDIENCE"],
            },
        },
    }
    try:
        return client.create_task(parent=parent, task=task)
    except Exception:
        current_app.logger.exception("Unable to enqueue report job %s", job.public_id)
        return None


def _flatten(prefix, value, rows):
    if isinstance(value, dict):
        for key, nested in value.items():
            _flatten(f"{prefix}.{key}" if prefix else key, nested, rows)
    elif isinstance(value, list):
        rows.append((prefix, "; ".join(str(item) for item in value)))
    else:
        rows.append((prefix, "" if value is None else str(value)))


def render_snapshot(snapshot, output_format):
    rows = []
    _flatten("", snapshot.snapshot_json, rows)
    output = io.BytesIO()
    if output_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Report"
        sheet.append([snapshot.title, f"Version {snapshot.version}", snapshot.approval_status])
        sheet.append(["Field", "Value"])
        for row in rows:
            sheet.append(row)
        sheet.freeze_panes = "A3"
        workbook.save(output)
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif output_format == "docx":
        document = WordDocument()
        document.add_heading(snapshot.title, 0)
        document.add_paragraph(f"Version {snapshot.version} · {snapshot.approval_status} · {snapshot.created_at}")
        table = document.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        table.rows[0].cells[0].text = "Field"
        table.rows[0].cells[1].text = "Value"
        for field, value in rows:
            cells = table.add_row().cells
            cells[0].text = field
            cells[1].text = value
        document.save(output)
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif output_format == "pdf":
        pdf = canvas.Canvas(output, pagesize=A4)
        width, height = A4
        y = height - 48
        pdf.setTitle(snapshot.title)
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, y, snapshot.title[:90])
        y -= 24
        pdf.setFont("Helvetica", 8)
        for field, value in rows:
            line = f"{field}: {value}"[:150]
            if y < 48:
                pdf.showPage()
                pdf.setFont("Helvetica", 8)
                y = height - 48
            pdf.drawString(40, y, line)
            y -= 12
        pdf.save()
        mime_type = "application/pdf"
    else:
        raise ValueError("Supported report formats are xlsx, docx, and pdf.")
    output.seek(0)
    return output, mime_type
