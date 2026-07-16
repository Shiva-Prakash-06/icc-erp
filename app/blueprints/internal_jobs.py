"""OIDC-protected endpoints for Cloud Scheduler and Cloud Tasks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify

from app.database import csrf, db
from app.models.erp import AuditEvent, DocumentRecord
from app.models.project import Project
from app.models.production import RecruitmentApplication, ReportJob, SensitiveAccessEvent
from app.services.drive import refresh_document_metadata
from app.services.job_auth import verify_internal_job_request
from app.services.notifications import deliver_pending, generate_deadline_notifications
from app.services.reporting import execute_report_job


internal_jobs_bp = Blueprint("internal_jobs", __name__, url_prefix="/internal/jobs")
csrf.exempt(internal_jobs_bp)


def _authorize(*config_keys):
    accounts = [current_app.config.get(key) for key in config_keys]
    return verify_internal_job_request(accounts)


@internal_jobs_bp.post("/reminders")
def reminders():
    _authorize("SCHEDULER_SERVICE_ACCOUNT")
    result = generate_deadline_notifications()
    return {"status": "ok", "result": result}


@internal_jobs_bp.post("/notifications/deliver")
def notifications_deliver():
    _authorize("TASKS_SERVICE_ACCOUNT", "SCHEDULER_SERVICE_ACCOUNT")
    return {"status": "ok", "result": deliver_pending()}


@internal_jobs_bp.post("/reports/<string:public_id>/execute")
def report_execute(public_id):
    _authorize("TASKS_SERVICE_ACCOUNT")
    job = ReportJob.query.filter_by(public_id=public_id).first_or_404()
    execute_report_job(job)
    return {"status": job.status, "job": job.public_id, "snapshot_id": getattr(job, "snapshot_id", None)}


@internal_jobs_bp.post("/drive/validate")
def drive_validate():
    _authorize("SCHEDULER_SERVICE_ACCOUNT")
    if current_app.config.get("DRIVE_VALIDATION_MODE") != "live":
        return jsonify({"status": "disabled", "reason": "Drive validation is not live."}), 503
    checked = invalid = 0
    for document in DocumentRecord.query.filter(DocumentRecord.drive_url.isnot(None)).order_by(DocumentRecord.id).limit(500):
        checked += 1
        result = refresh_document_metadata(document)
        invalid += int(not result.get("valid"))
    db.session.commit()
    return {"status": "ok", "checked": checked, "invalid": invalid}


@internal_jobs_bp.post("/retention")
def retention():
    _authorize("SCHEDULER_SERVICE_ACCOUNT")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=current_app.config["REJECTED_APPLICATION_RETENTION_DAYS"])
    expired = RecruitmentApplication.query.filter(
        RecruitmentApplication.decision == "Rejected",
        RecruitmentApplication.decided_at.isnot(None),
        RecruitmentApplication.decided_at < cutoff,
    ).all()
    count = len(expired)
    for application in expired:
        db.session.delete(application)
    audit_cutoff = now - timedelta(days=current_app.config["AUDIT_RETENTION_DAYS"])
    audit_removed = AuditEvent.query.filter(AuditEvent.occurred_at < audit_cutoff).delete(synchronize_session=False)
    sensitive_events_removed = SensitiveAccessEvent.query.filter(SensitiveAccessEvent.occurred_at < audit_cutoff).delete(synchronize_session=False)
    operational_cutoff = now - timedelta(days=current_app.config["OPERATIONAL_RETENTION_DAYS"])
    expired_restricted_documents = (
        DocumentRecord.query.join(Project)
        .filter(
            Project.archived_at.isnot(None),
            Project.archived_at < operational_cutoff,
            DocumentRecord.permission_classification == "Restricted",
            DocumentRecord.drive_url.isnot(None),
        )
        .all()
    )
    for document in expired_restricted_documents:
        document.drive_url = None
        document.drive_file_id = None
        document.drive_permission_metadata = []
        document.drive_validation_status = "Retention Removed"
        document.version += 1
    result = {
        "rejected_applications_removed": count,
        "audit_events_removed": audit_removed,
        "sensitive_access_events_removed": sensitive_events_removed,
        "restricted_references_removed": len(expired_restricted_documents),
    }
    db.session.add(AuditEvent(action="retention.execute", entity_type="RetentionPolicy", after_summary=result))
    db.session.commit()
    return {"status": "ok", **result}
