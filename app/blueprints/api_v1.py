from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import date, datetime, time, timezone
from decimal import Decimal

from flask import Blueprint, current_app, g, jsonify, request, send_file

from app.database import db
from app.database import csrf, limiter
from app.models.erp import (
    AuditEvent,
    BudgetLine,
    ChecklistInstance,
    ChecklistItemStatus,
    ChecklistTemplate,
    ChecklistTemplateItem,
    DocumentRecord,
    FeedbackForm,
    FeedbackResponse,
    ImportBatch,
    OperatingUnit,
    OperationalRequest,
    PartnerInstitution,
    Person,
    ProjectComponent,
    ProjectSession,
    ReportSnapshot,
    RoleAssignment,
    SessionAttendance,
    TeamAssignment,
    Wing,
    WorkTask,
)
from app.models.production import (
    AggregateAttendance,
    Cohort,
    ControlledVocabulary,
    ContributionRecord,
    DocumentRequirement,
    GovernanceTerm,
    Notification,
    NotificationPreference,
    Position,
    ProjectRisk,
    RecruitmentApplication,
    ReportDefinition,
    ReportJob,
)
from app.models.project import AcademicYear, Campus, Project
from app.models.project import BuddyAssignment, BuddyLog, ProjectParticipant
from app.models.operational import Contribution
from app.services.authorization import can_view_project, has_permission
from app.services.audit import record_audit, record_sensitive_access
from app.services.buddy import validate_buddy_assignment
from app.services.drive import refresh_document_metadata, validate_drive_link
from app.services.imports import STANDARD_IMPORTS, build_import_template, commit_batch, stage_supplied_source, stage_uploaded_source
from app.services.lifecycle import closure_blockers, transition_project
from app.services.notifications import queue_notification
from app.services.operations import (
    change_checklist_status,
    change_task_status,
    decide_contribution,
    decide_document,
    decide_operational_request,
    decide_recruitment,
    mark_attendance,
    moderate_feedback,
    session_conflicts,
)
from app.services.reporting import compile_project_snapshot, enqueue_report_job, render_snapshot


api_v1_bp = Blueprint("api_v1", __name__)


RESOURCE_MODELS = {
    "organizations": OperatingUnit,
    "partners": PartnerInstitution,
    "campuses": Campus,
    "academic-years": AcademicYear,
    "role-assignments": RoleAssignment,
    "projects": Project,
    "components": ProjectComponent,
    "sessions": ProjectSession,
    "tasks": WorkTask,
    "checklists": ChecklistInstance,
    "checklist-items": ChecklistItemStatus,
    "checklist-templates": ChecklistTemplate,
    "checklist-template-items": ChecklistTemplateItem,
    "people": Person,
    "teams": TeamAssignment,
    "participants": ProjectParticipant,
    "attendance": SessionAttendance,
    "contributions": ContributionRecord,
    "buddy-assignments": BuddyAssignment,
    "buddy-logs": BuddyLog,
    "documents": DocumentRecord,
    "feedback-forms": FeedbackForm,
    "feedback-responses": FeedbackResponse,
    "budgets": BudgetLine,
    "operational-requests": OperationalRequest,
    "imports": ImportBatch,
    "reports": ReportSnapshot,
    "audit-events": AuditEvent,
    "vocabularies": ControlledVocabulary,
    "positions": Position,
    "governance-terms": GovernanceTerm,
    "cohorts": Cohort,
    "applications": RecruitmentApplication,
    "risks": ProjectRisk,
    "aggregate-attendance": AggregateAttendance,
    "contribution-records": ContributionRecord,
    "document-requirements": DocumentRequirement,
    "notification-preferences": NotificationPreference,
    "notifications": Notification,
    "report-definitions": ReportDefinition,
    "report-jobs": ReportJob,
}


PERMISSION_BY_RESOURCE = {
    "role-assignments": "manage_users",
    "vocabularies": "manage_governance",
    "checklist-templates": "manage_governance",
    "checklist-template-items": "manage_governance",
    "positions": "manage_governance",
    "governance-terms": "manage_governance",
    "people": "manage_people",
    "applications": "manage_people",
    "imports": "manage_imports",
    "audit-events": "audit",
    "feedback-responses": "report",
    "budgets": "manage_projects",
    "operational-requests": "manage_projects",
    "report-definitions": "manage_governance",
    "report-jobs": "report",
}


READ_ONLY_RESOURCES = {"audit-events", "feedback-responses", "imports", "reports", "notifications", "report-jobs"}
ARCHIVABLE_RESOURCES = {"people": "is_archived", "vocabularies": "is_active", "positions": "is_active"}


def _model_by_table(table_name):
    for mapper in db.Model.registry.mappers:
        if mapper.local_table.name == table_name:
            return mapper.class_
    return None


def _cursor_encode(value):
    return base64.urlsafe_b64encode(str(value).encode()).decode().rstrip("=")


def _cursor_decode(value):
    if not value:
        return 0
    try:
        return int(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode())
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Invalid cursor")


def _problem(status, title, detail=None):
    response = jsonify(
        {
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail or title,
            "instance": request.path,
            "request_id": getattr(g, "request_id", None),
        }
    )
    response.status_code = status
    response.content_type = "application/problem+json"
    return response


def _value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    try:
        return str(value) if value is not None and value.__class__.__module__ == "decimal" else value
    except Exception:
        return value


def _serialize(item):
    excluded = {"password_hash", "drive_url", "before_summary", "after_summary", "ip_address", "password_reset_token_hash"}
    data = {}
    for column in item.__table__.columns:
        if column.name in excluded or column.name == "id":
            continue
        if column.foreign_keys:
            value = getattr(item, column.name)
            foreign_key = next(iter(column.foreign_keys))
            target = _model_by_table(foreign_key.column.table.name)
            target_item = db.session.get(target, value) if target and value is not None else None
            key = f"{column.name[:-3]}_public_id" if column.name.endswith("_id") else f"{column.name}_public_id"
            data[key] = getattr(target_item, "public_id", None)
            continue
        value = getattr(item, column.name)
        if column.name == "drive_file_id" and getattr(item, "permission_classification", None) == "Restricted":
            if not has_permission(g.user, "sensitive_links", sensitive=True):
                value = None
            elif value:
                record_sensitive_access(item, request.headers.get("X-Access-Purpose", "Operational document access"), g.user, getattr(item, "project", None))
        data[column.name] = _value(value)
    return data


def _project_for_item(item):
    if isinstance(item, Project):
        return item
    project = getattr(item, "project", None)
    if project:
        return project
    project_id = getattr(item, "project_id", None)
    if project_id:
        return db.session.get(Project, project_id)
    session_item = getattr(item, "session", None)
    if session_item:
        return session_item.project
    session_id = getattr(item, "session_id", None)
    if session_id:
        session_item = db.session.get(ProjectSession, session_id)
        return session_item.project if session_item else None
    checklist = getattr(item, "checklist", None)
    return checklist.project if checklist else None


def _authorize_item(item, permission="manage_projects"):
    project = _project_for_item(item)
    if project:
        return has_permission(g.user, permission, project)
    return has_permission(g.user, permission)


PROTECTED_MUTATION_FIELDS = {
    "id", "public_id", "created_at", "updated_at", "approved_by_id", "approved_at",
    "waived_by_id", "committed_by_id", "committed_at", "decided_by_id", "decided_at",
    "generated_by_id", "published_at", "password_hash", "password_reset_token_hash",
    "delivery_status", "drive_permission_metadata", "drive_validated_at", "drive_validation_status",
    "status", "decision", "approval_status", "publication_status", "cancellation_reason", "archived_at",
    # Waiver/closure fields must only change through the dedicated workflow
    # endpoints (change_task_status/change_checklist_status), which enforce the
    # "waive" permission and a mandatory justification comment. A raw PATCH must
    # never be able to silently waive a closure requirement.
    "waived", "waiver_reason", "mandatory_for_closure",
}


def _convert_value(column, value):
    if value is None:
        return None
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        return value
    if python_type is datetime and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if python_type is date and isinstance(value, str):
        return date.fromisoformat(value)
    if python_type is time and isinstance(value, str):
        return time.fromisoformat(value)
    if python_type is Decimal:
        return Decimal(str(value))
    if python_type is bool:
        return _boolean_value(value)
    if python_type in {int, float, str}:
        return python_type(value)
    return value


def _boolean_value(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off", "", "none"}:
        return False
    raise ValueError(f"{value!r} is not a valid boolean value.")


def _aware_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _apply_payload(item, payload, *, creating=False):
    columns = {column.name: column for column in item.__table__.columns}
    unknown = set(payload)
    for name, column in columns.items():
        if name in PROTECTED_MUTATION_FIELDS or name == "version":
            unknown.discard(name)
            continue
        if column.foreign_keys:
            public_key = f"{name[:-3]}_public_id" if name.endswith("_id") else f"{name}_public_id"
            if public_key in payload:
                foreign_key = next(iter(column.foreign_keys))
                target_model = _model_by_table(foreign_key.column.table.name)
                target = target_model.query.filter_by(public_id=payload[public_key]).first() if hasattr(target_model, "public_id") else None
                if not target:
                    raise ValueError(f"Unknown {public_key}.")
                setattr(item, name, target.id)
                unknown.discard(public_key)
            unknown.discard(name)
            continue
        if name in payload:
            setattr(item, name, _convert_value(column, payload[name]))
            unknown.discard(name)
    if unknown:
        raise ValueError("Unsupported fields: " + ", ".join(sorted(unknown)))
    if not creating and hasattr(item, "version"):
        expected = payload.get("version")
        if expected is None or expected != item.version:
            raise RuntimeError("Concurrent update conflict")
        item.version += 1
    return item


@api_v1_bp.get("/meta")
def meta():
    return {
        "version": "v1",
        "resources": sorted(RESOURCE_MODELS),
        "pagination": "cursor",
        "error_format": "RFC 7807",
        "environment": "demonstrator" if current_app.config.get("DEMONSTRATOR") else "production",
    }


@api_v1_bp.get("/me")
def current_identity():
    person = g.user.person
    return {
        "data": {
            "user": {
                "public_id": g.user.public_id,
                "username": g.user.username,
                "email": g.user.email,
                "role": g.user.role,
                "status": g.user.status,
            },
            "person": None if not person else {
                "public_id": person.public_id,
                "display_name": person.display_name,
                "registration_number": person.registration_number,
                "primary_email": person.primary_email,
                "phone": person.phone,
                "person_type": person.person_type,
                "nationality_country": person.nationality_country,
                "consent_status": person.consent_status,
            },
        }
    }


@api_v1_bp.get("/<resource>")
def list_resource(resource):
    model = RESOURCE_MODELS.get(resource)
    if not model:
        return _problem(404, "Unknown resource")
    required_permission = PERMISSION_BY_RESOURCE.get(resource)
    if required_permission and not has_permission(g.user, required_permission):
        return _problem(403, "Access denied")
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        cursor = _cursor_decode(request.args.get("cursor"))
    except ValueError:
        return _problem(400, "Invalid pagination parameters")
    query = model.query.filter(model.id > cursor)
    if model in {Notification, NotificationPreference}:
        query = query.filter(model.user_id == g.user.id)
    allowed_filters = {column.name for column in model.__table__.columns if column.name in {"status", "code", "project_type", "category", "event_type", "decision", "is_active"}}
    for key in allowed_filters:
        if key in request.args:
            query = query.filter(getattr(model, key) == request.args[key])
    visible_project_ids = [
        project.id for project in Project.query.order_by(Project.id).all() if can_view_project(g.user, project)
    ]
    if hasattr(model, "project_id"):
        query = query.filter(model.project_id.in_(visible_project_ids or [-1]))
    elif model is BuddyLog:
        query = query.join(BuddyAssignment).filter(BuddyAssignment.project_id.in_(visible_project_ids or [-1]))
    elif model is SessionAttendance:
        query = query.join(ProjectSession, SessionAttendance.session_id == ProjectSession.id).filter(
            ProjectSession.project_id.in_(visible_project_ids or [-1])
        )
    elif model is ChecklistItemStatus:
        query = query.join(ChecklistInstance, ChecklistItemStatus.checklist_instance_id == ChecklistInstance.id).filter(
            ChecklistInstance.project_id.in_(visible_project_ids or [-1])
        )
    query = query.order_by(model.id.asc())
    if model is Project:
        items = [item for item in query.limit(limit + 1).all() if can_view_project(g.user, item)]
    else:
        items = query.limit(limit + 1).all()
    has_more = len(items) > limit
    page = items[:limit]
    payload = {
        "data": [_serialize(item) for item in page],
        "next_cursor": _cursor_encode(page[-1].id) if has_more and page else None,
        "count": len(page),
    }
    if db.session.new:
        db.session.commit()
    return payload


@api_v1_bp.post("/<resource>")
def create_resource(resource):
    model = RESOURCE_MODELS.get(resource)
    if not model:
        return _problem(404, "Unknown resource")
    if resource in READ_ONLY_RESOURCES or model is FeedbackResponse:
        return _problem(405, "Resource is not created through this endpoint")
    permission = PERMISSION_BY_RESOURCE.get(resource, "manage_projects")
    if not has_permission(g.user, permission):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    buddy_override = _boolean_value(payload.pop("overlap_override", False)) if model is BuddyAssignment else False
    warnings = []
    try:
        item = _apply_payload(model(), payload, creating=True)
        if isinstance(item, Project):
            item.status = "Draft"
            item.version = 1
        project = _project_for_item(item)
        if project and not has_permission(g.user, permission, project):
            return _problem(403, "Access denied")
        if isinstance(item, BuddyAssignment):
            if buddy_override and not has_permission(g.user, "approve", project):
                return _problem(403, "An authorized approver is required for an overlapping buddy assignment")
            validate_buddy_assignment(
                project,
                item.buddy_user_id,
                item.exchange_student_id,
                item.start_date,
                item.end_date,
                override=buddy_override,
                reason=item.overlap_override_reason,
            )
            if buddy_override:
                item.overlap_approved_by_id = g.user.id
        if isinstance(item, ProjectSession):
            warnings = session_conflicts(item)
        if isinstance(item, DocumentRecord) and item.drive_url:
            validation = refresh_document_metadata(item)
            if not validation.get("valid"):
                raise ValueError(validation.get("reason", "Drive reference validation failed."))
        db.session.add(item)
        db.session.flush()
        record_audit(f"{resource}.create", item, after=_serialize(item), actor=g.user)
        db.session.commit()
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return _problem(422, "Validation failed", str(error))
    response = {"data": _serialize(item)}
    if warnings:
        response["warnings"] = warnings
    return response, 201


@api_v1_bp.get("/<resource>/<string:public_id>")
def get_resource(resource, public_id):
    model = RESOURCE_MODELS.get(resource)
    if not model:
        return _problem(404, "Unknown resource")
    item = model.query.filter_by(public_id=public_id).first() if hasattr(model, "public_id") else None
    if not item:
        return _problem(404, "Resource not found")
    permission = PERMISSION_BY_RESOURCE.get(resource)
    if permission and not has_permission(g.user, permission):
        return _problem(403, "Access denied")
    project = _project_for_item(item)
    if project and not can_view_project(g.user, project):
        return _problem(403, "Access denied")
    if isinstance(item, Notification) and item.user_id != g.user.id:
        return _problem(403, "Access denied")
    payload = _serialize(item)
    if isinstance(item, Project):
        payload["closure_blockers"] = [blocker.__dict__ for blocker in closure_blockers(item)]
    if db.session.new:
        db.session.commit()
    return {"data": payload}


@api_v1_bp.patch("/<resource>/<string:public_id>")
def patch_resource(resource, public_id):
    model = RESOURCE_MODELS.get(resource)
    if not model:
        return _problem(404, "Unknown resource")
    if resource in READ_ONLY_RESOURCES or model in {
        FeedbackResponse, DocumentRecord, RecruitmentApplication, SessionAttendance,
    }:
        return _problem(405, "Use the resource-specific workflow endpoint")
    item = model.query.filter_by(public_id=public_id).first() if hasattr(model, "public_id") else None
    if not item:
        return _problem(404, "Resource not found")
    permission = PERMISSION_BY_RESOURCE.get(resource, "manage_projects")
    if not _authorize_item(item, permission):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    before = _serialize(item)
    try:
        # Project has its own dedicated PATCH route (update_project) which
        # Flask/Werkzeug always prefers over this generic one, so `item` is
        # never a Project here.
        _apply_payload(item, payload)
        record_audit(f"{resource}.update", item, before=before, after=_serialize(item), actor=g.user)
        db.session.commit()
    except RuntimeError as error:
        db.session.rollback()
        return _problem(409, "Concurrent update conflict", str(error))
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return _problem(422, "Validation failed", str(error))
    return {"data": _serialize(item)}


@api_v1_bp.delete("/<resource>/<string:public_id>")
def archive_resource(resource, public_id):
    model = RESOURCE_MODELS.get(resource)
    archive_field = ARCHIVABLE_RESOURCES.get(resource)
    if not model or not archive_field:
        return _problem(405, "Destructive deletion is not supported; archive the record through its workflow")
    item = model.query.filter_by(public_id=public_id).first()
    if not item:
        return _problem(404, "Resource not found")
    permission = PERMISSION_BY_RESOURCE.get(resource, "manage_projects")
    if not _authorize_item(item, permission):
        return _problem(403, "Access denied")
    before = {archive_field: getattr(item, archive_field)}
    setattr(item, archive_field, False if archive_field == "is_active" else True)
    record_audit(f"{resource}.archive", item, before=before, after={archive_field: getattr(item, archive_field)}, actor=g.user)
    db.session.commit()
    return "", 204


@api_v1_bp.get("/projects/<string:public_id>")
def get_project(public_id):
    project = Project.query.filter_by(public_id=public_id).first()
    if not project:
        return _problem(404, "Project not found")
    if not can_view_project(g.user, project):
        return _problem(403, "Access denied")
    data = _serialize(project)
    data["closure_blockers"] = [blocker.__dict__ for blocker in closure_blockers(project)]
    return {"data": data}


@api_v1_bp.patch("/projects/<string:public_id>")
def update_project(public_id):
    project = Project.query.filter_by(public_id=public_id).first()
    if not project:
        return _problem(404, "Project not found")
    if not has_permission(g.user, "manage_projects", project):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    editable = {
        "title", "description", "objectives", "target_audience", "venue",
        "capacity", "expected_reach", "actual_reach", "closure_summary",
        "start_date", "end_date", "owner_person_public_id", "partner_institution_public_id",
    }
    unsupported = set(payload) - editable - {"version"}
    if unsupported:
        return _problem(422, "Validation failed", "Unsupported fields: " + ", ".join(sorted(unsupported)))
    restricted_payload = {key: payload[key] for key in payload if key in editable}
    restricted_payload["version"] = payload.get("version")
    try:
        _apply_payload(project, restricted_payload)
    except RuntimeError as error:
        db.session.rollback()
        return _problem(409, "Concurrent update conflict", str(error))
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return _problem(422, "Validation failed", str(error))
    record_audit("projects.update", project, after=_serialize(project), actor=g.user)
    db.session.commit()
    return {"data": _serialize(project)}


@api_v1_bp.post("/projects/<string:public_id>/transition")
def project_transition(public_id):
    project = Project.query.filter_by(public_id=public_id).first()
    if not project:
        return _problem(404, "Project not found")
    if not has_permission(g.user, "approve", project):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    try:
        transition_project(project, payload.get("status"), g.user, payload.get("version"), payload.get("reason"))
    except ValueError as error:
        status = 409 if "changed by another" in str(error) else 422
        return _problem(status, "Project transition rejected", str(error))
    return {"data": _serialize(project)}


@api_v1_bp.get("/projects/<string:public_id>/components")
def project_components(public_id):
    project = Project.query.filter_by(public_id=public_id).first()
    if not project:
        return _problem(404, "Project not found")
    if not can_view_project(g.user, project):
        return _problem(403, "Access denied")
    return {"data": [_serialize(item) for item in ProjectComponent.query.filter_by(project_id=project.id).order_by(ProjectComponent.sequence, ProjectComponent.id)]}


@api_v1_bp.post("/documents/validate-drive-link")
def validate_document_link():
    payload = request.get_json(silent=True) or {}
    result = validate_drive_link(payload.get("url"), payload.get("classification", "Internal"))
    return ({"data": result}, 200 if result.get("valid") else 422)


@api_v1_bp.post("/imports/stage")
def stage_import():
    if not has_permission(g.user, "manage_imports"):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return _problem(400, "Idempotency-Key header is required")
    try:
        batch = stage_supplied_source(payload.get("import_type"))
    except (ValueError, FileNotFoundError) as error:
        return _problem(422, "Import could not be staged", str(error))
    return {"data": _serialize(batch)}, 201


@api_v1_bp.get("/import-templates/<string:import_type>.xlsx")
def import_template(import_type):
    if not has_permission(g.user, "manage_imports"):
        return _problem(403, "Access denied")
    try:
        output = build_import_template(import_type)
    except ValueError as error:
        return _problem(404, "Import template not found", str(error))
    return send_file(output, as_attachment=True, download_name=f"icc_erp_{import_type}_template.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@api_v1_bp.post("/imports/upload")
@limiter.limit("20 per hour")
def upload_import():
    if not has_permission(g.user, "manage_imports"):
        return _problem(403, "Access denied")
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return _problem(400, "Idempotency-Key header is required")
    upload = request.files.get("file")
    import_type = request.form.get("import_type")
    if not upload:
        return _problem(422, "Import file is required")
    try:
        batch = stage_uploaded_source(import_type, upload, idempotency_key)
    except (ValueError, UnicodeError) as error:
        db.session.rollback()
        return _problem(422, "Import could not be staged", str(error))
    return {"data": _serialize(batch)}, 201


@api_v1_bp.post("/imports/<string:public_id>/commit")
def commit_import(public_id):
    if not has_permission(g.user, "approve"):
        return _problem(403, "Access denied")
    batch = ImportBatch.query.filter_by(public_id=public_id).first()
    if not batch:
        return _problem(404, "Import batch not found")
    try:
        commit_batch(batch, g.user)
    except ValueError as error:
        return _problem(422, "Import commit rejected", str(error))
    return {"data": _serialize(batch)}


@api_v1_bp.get("/public/feedback/<string:token>")
@limiter.limit("60 per hour")
def public_feedback_form(token):
    form = FeedbackForm.query.filter_by(public_token=token, is_open=True).first()
    now = datetime.now(timezone.utc)
    if not form or (_aware_utc(form.opens_at) and _aware_utc(form.opens_at) > now) or (_aware_utc(form.closes_at) and _aware_utc(form.closes_at) <= now):
        return _problem(404, "Feedback form not found or closed")
    return {
        "data": {
            "title": form.title,
            "questions": form.questions_json,
            "response_policy": form.response_policy,
            "anonymous": form.is_anonymous,
        }
    }


@api_v1_bp.post("/public/feedback/<string:token>")
@csrf.exempt
@limiter.limit("10 per hour")
def submit_public_feedback(token):
    form = FeedbackForm.query.filter_by(public_token=token, is_open=True).first()
    now = datetime.now(timezone.utc)
    if not form or (_aware_utc(form.opens_at) and _aware_utc(form.opens_at) > now) or (_aware_utc(form.closes_at) and _aware_utc(form.closes_at) <= now):
        return _problem(404, "Feedback form not found or closed")
    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers")
    if not isinstance(answers, dict) or not answers:
        return _problem(422, "At least one feedback answer is required")
    response_key = None
    if form.response_policy.lower().startswith("one"):
        fingerprint = "|".join([token, request.remote_addr or "", request.headers.get("User-Agent", "")])
        response_key = hmac.new(current_app.config["SECRET_KEY"].encode(), fingerprint.encode(), hashlib.sha256).hexdigest()
        if FeedbackResponse.query.filter_by(form_id=form.id, response_key_hash=response_key).first():
            return _problem(409, "Feedback already submitted")
    response = FeedbackResponse(
        form_id=form.id,
        answers_json=answers,
        publication_consent=_boolean_value(payload.get("publication_consent", False)),
        moderation_status="Pending",
        response_key_hash=response_key,
    )
    db.session.add(response)
    db.session.commit()
    return {"data": {"public_id": response.public_id, "moderation_status": response.moderation_status}}, 201


@api_v1_bp.post("/tasks/<string:public_id>/status")
def task_status(public_id):
    task = WorkTask.query.filter_by(public_id=public_id).first()
    if not task:
        return _problem(404, "Task not found")
    project = db.session.get(Project, task.project_id)
    owner_update = g.user.person_id and task.owner_person_id == g.user.person_id and has_permission(g.user, "contribute", project)
    if not owner_update and not has_permission(g.user, "manage_projects", project):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    status_value = payload.get("status")
    if status_value in {"Approved", "Rejected"} and not has_permission(g.user, "approve", project):
        return _problem(403, "An approver role is required")
    if status_value == "Waived" and not has_permission(g.user, "waive", project):
        return _problem(403, "A faculty waiver role is required")
    try:
        change_task_status(
            task,
            status_value,
            g.user,
            expected_version=payload.get("version"),
            comment=payload.get("comment"),
            evidence_reference=payload.get("evidence_reference"),
            waive=status_value == "Waived",
        )
    except ValueError as error:
        return _problem(409 if "Concurrent" in str(error) else 422, "Task status rejected", str(error))
    return {"data": _serialize(task)}


@api_v1_bp.post("/checklist-items/<string:public_id>/status")
def checklist_item_status(public_id):
    item = ChecklistItemStatus.query.filter_by(public_id=public_id).first()
    if not item:
        return _problem(404, "Checklist requirement not found")
    project = item.checklist.project
    owner_update = g.user.person_id and item.owner_person_id == g.user.person_id and has_permission(g.user, "contribute", project)
    if not owner_update and not has_permission(g.user, "manage_projects", project):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    status_value = payload.get("status")
    if status_value in {"Approved", "Rejected"} and not has_permission(g.user, "approve", project):
        return _problem(403, "An approver role is required")
    if status_value == "Waived" and not has_permission(g.user, "waive", project):
        return _problem(403, "A faculty waiver role is required")
    try:
        change_checklist_status(
            item,
            status_value,
            g.user,
            expected_version=payload.get("version"),
            comment=payload.get("comment"),
            evidence_reference=payload.get("evidence_reference"),
            waive=status_value == "Waived",
        )
    except ValueError as error:
        return _problem(409 if "Concurrent" in str(error) else 422, "Checklist status rejected", str(error))
    return {"data": _serialize(item)}


@api_v1_bp.post("/contributions/<string:public_id>/decision")
def contribution_decision(public_id):
    contribution = ContributionRecord.query.filter_by(public_id=public_id).first()
    if not contribution:
        return _problem(404, "Contribution not found")
    project = db.session.get(Project, contribution.project_id)
    if not has_permission(g.user, "approve", project):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    try:
        decide_contribution(contribution, payload.get("status"), g.user, expected_version=payload.get("version"), reason=payload.get("reason"))
    except ValueError as error:
        return _problem(409 if "Concurrent" in str(error) else 422, "Contribution decision rejected", str(error))
    return {"data": _serialize(contribution)}


@api_v1_bp.post("/operational-requests/<string:public_id>/transition")
def operational_request_transition(public_id):
    operational_request = OperationalRequest.query.filter_by(public_id=public_id).first()
    if not operational_request:
        return _problem(404, "Operational request not found")
    project = db.session.get(Project, operational_request.project_id)
    payload = request.get_json(silent=True) or {}
    target = payload.get("status")
    permission = "approve" if target in {"Approved", "Rejected", "Completed", "Cancelled"} else "manage_projects"
    if not has_permission(g.user, permission, project):
        return _problem(403, "Access denied")
    try:
        decide_operational_request(
            operational_request,
            target,
            g.user,
            expected_version=payload.get("version"),
            reason=payload.get("reason"),
            official_reference=payload.get("official_reference"),
        )
    except ValueError as error:
        return _problem(409 if "Concurrent" in str(error) else 422, "Operational request transition rejected", str(error))
    return {"data": _serialize(operational_request)}


@api_v1_bp.post("/feedback-responses/<string:public_id>/moderate")
def moderate_feedback_response(public_id):
    response = FeedbackResponse.query.filter_by(public_id=public_id).first()
    if not response:
        return _problem(404, "Feedback response not found")
    form = db.session.get(FeedbackForm, response.form_id)
    project = db.session.get(Project, form.project_id)
    if not has_permission(g.user, "approve", project):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    try:
        moderate_feedback(response, payload.get("status"), g.user, reason=payload.get("reason"))
    except ValueError as error:
        return _problem(422, "Feedback moderation rejected", str(error))
    return {"data": _serialize(response)}


@api_v1_bp.post("/documents/<string:public_id>/validate")
def validate_document_record(public_id):
    document = DocumentRecord.query.filter_by(public_id=public_id).first()
    if not document:
        return _problem(404, "Document not found")
    if not has_permission(g.user, "manage_projects", document.project):
        return _problem(403, "Access denied")
    result = refresh_document_metadata(document)
    record_audit("document.drive_validate", document, after={"valid": result.get("valid"), "visibility": result.get("visibility")}, actor=g.user)
    db.session.commit()
    return ({"data": result}, 200 if result.get("valid") else 422)


@api_v1_bp.post("/documents/<string:public_id>/decision")
def document_decision(public_id):
    document = DocumentRecord.query.filter_by(public_id=public_id).first()
    if not document:
        return _problem(404, "Document not found")
    payload = request.get_json(silent=True) or {}
    try:
        waive = _boolean_value(payload.get("waive", False))
    except ValueError as error:
        return _problem(422, "Document decision rejected", str(error))
    permission = "waive" if waive else "approve"
    if not has_permission(g.user, permission, document.project):
        return _problem(403, "Access denied")
    try:
        decide_document(document, payload.get("status"), g.user, expected_version=payload.get("version"), reason=payload.get("reason"), waive=waive)
    except ValueError as error:
        status = 409 if "Concurrent" in str(error) else 422
        return _problem(status, "Document decision rejected", str(error))
    return {"data": _serialize(document)}


@api_v1_bp.post("/applications/<string:public_id>/decision")
def application_decision(public_id):
    application = RecruitmentApplication.query.filter_by(public_id=public_id).first()
    if not application:
        return _problem(404, "Application not found")
    project = db.session.get(Project, application.project_id)
    if not has_permission(g.user, "manage_people", project):
        return _problem(403, "Access denied")
    payload = request.get_json(silent=True) or {}
    try:
        decide_recruitment(application, payload.get("decision"), g.user, expected_version=payload.get("version"), reason=payload.get("reason"))
    except ValueError as error:
        status = 409 if "Concurrent" in str(error) else 422
        return _problem(status, "Recruitment decision rejected", str(error))
    return {"data": _serialize(application)}


@api_v1_bp.post("/attendance/batch")
def attendance_batch():
    if not has_permission(g.user, "manage_projects"):
        return _problem(403, "Access denied")
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return _problem(400, "Idempotency-Key header is required")
    prior = AuditEvent.query.filter_by(action="attendance.batch", request_id=idempotency_key).first()
    if prior:
        return {"data": {"replayed": True, "batch_key": idempotency_key}}
    payload = request.get_json(silent=True) or {}
    session_item = ProjectSession.query.filter_by(public_id=payload.get("session_public_id")).first()
    if not session_item or not has_permission(g.user, "manage_projects", session_item.project):
        return _problem(404, "Session not found")
    rows = payload.get("records") or []
    if not isinstance(rows, list) or not rows:
        return _problem(422, "Attendance records are required")
    created = updated = 0
    try:
        for row in rows:
            person = Person.query.filter_by(public_id=row.get("person_public_id")).first()
            if not person:
                raise ValueError("Attendance references an unknown person.")
            existing = SessionAttendance.query.filter_by(session_id=session_item.id, person_id=person.id).first()
            mark_attendance(session_item, person, row.get("status"), g.user, expected_version=row.get("version") if existing else None, reason=row.get("reason"), commit=False)
            updated += int(existing is not None)
            created += int(existing is None)
        db.session.add(AuditEvent(actor_user_id=g.user.id, action="attendance.batch", entity_type="ProjectSession", entity_public_id=session_item.public_id, after_summary={"created": created, "updated": updated}, request_id=idempotency_key))
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return _problem(422, "Attendance batch rejected", str(error))
    return {"data": {"created": created, "updated": updated, "replayed": False}}, 201


@api_v1_bp.post("/projects/<string:public_id>/reports")
def generate_project_report(public_id):
    project = Project.query.filter_by(public_id=public_id).first()
    if not project:
        return _problem(404, "Project not found")
    if not has_permission(g.user, "report", project):
        return _problem(403, "Access denied")
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return _problem(400, "Idempotency-Key header is required")
    existing = ReportJob.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return {"data": _serialize(existing)}
    payload = request.get_json(silent=True) or {}
    definition = ReportDefinition.query.filter_by(code=payload.get("definition_code", "PROJECT_OPERATIONAL"), is_active=True).order_by(ReportDefinition.version.desc()).first()
    if not definition:
        return _problem(422, "Report definition is not configured")
    job = ReportJob(definition_id=definition.id, project_id=project.id, requested_by_id=g.user.id, idempotency_key=idempotency_key, filters_json=payload.get("filters") or {}, output_format=payload.get("format", "json"))
    db.session.add(job)
    db.session.flush()
    enqueue_report_job(job)
    db.session.commit()
    return {"data": _serialize(job)}, 202


@api_v1_bp.post("/reports/<string:public_id>/approve")
def approve_report(public_id):
    snapshot = ReportSnapshot.query.filter_by(public_id=public_id).first()
    if not snapshot:
        return _problem(404, "Report not found")
    project = db.session.get(Project, snapshot.project_id) if snapshot.project_id else None
    if not has_permission(g.user, "approve", project):
        return _problem(403, "Access denied")
    if snapshot.approval_status == "Approved":
        return {"data": _serialize(snapshot)}
    snapshot.approval_status = "Approved"
    snapshot.approved_by_id = g.user.id
    snapshot.approved_at = datetime.now(timezone.utc)
    record_audit("report.approve", snapshot, after={"approval_status": "Approved"}, actor=g.user)
    db.session.commit()
    return {"data": _serialize(snapshot)}


@api_v1_bp.get("/reports/<string:public_id>/export.<string:output_format>")
@limiter.limit("30 per hour")
def export_report_snapshot(public_id, output_format):
    snapshot = ReportSnapshot.query.filter_by(public_id=public_id).first()
    if not snapshot:
        return _problem(404, "Report not found")
    project = db.session.get(Project, snapshot.project_id) if snapshot.project_id else None
    if not has_permission(g.user, "report", project):
        return _problem(403, "Access denied")
    try:
        output, mime_type = render_snapshot(snapshot, output_format)
    except ValueError as error:
        return _problem(422, "Report export rejected", str(error))
    filename = f"{(project.code if project else 'ICC-OIA')}-{snapshot.version}.{output_format}"
    return send_file(output, mimetype=mime_type, as_attachment=True, download_name=filename)


@api_v1_bp.post("/reports/<string:public_id>/publish")
def publish_report(public_id):
    snapshot = ReportSnapshot.query.filter_by(public_id=public_id).first()
    if not snapshot:
        return _problem(404, "Report not found")
    project = db.session.get(Project, snapshot.project_id) if snapshot.project_id else None
    if not has_permission(g.user, "approve", project):
        return _problem(403, "Access denied")
    if snapshot.approval_status != "Approved":
        return _problem(422, "Only approved reports may be published")
    snapshot.publication_status = "Published"
    snapshot.published_at = datetime.now(timezone.utc)
    record_audit("report.publish", snapshot, after={"publication_status": "Published"}, actor=g.user)
    db.session.commit()
    return {"data": _serialize(snapshot)}


@api_v1_bp.post("/notifications/<string:public_id>/read")
def mark_notification_read(public_id):
    notification = Notification.query.filter_by(public_id=public_id, user_id=g.user.id).first()
    if not notification:
        return _problem(404, "Notification not found")
    notification.read_at = datetime.now(timezone.utc)
    db.session.commit()
    return {"data": _serialize(notification)}


@api_v1_bp.get("/offline-snapshot")
def offline_snapshot():
    visible = [project for project in Project.query.order_by(Project.start_date).all() if can_view_project(g.user, project)]
    project_ids = [project.id for project in visible]
    sessions = ProjectSession.query.filter(ProjectSession.project_id.in_(project_ids or [-1])).order_by(ProjectSession.starts_at).all()
    tasks = WorkTask.query.filter(WorkTask.project_id.in_(project_ids or [-1])).order_by(WorkTask.due_at).all()
    ttl = current_app.config["OFFLINE_SNAPSHOT_TTL_SECONDS"]
    return {
        "data": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + ttl, timezone.utc).isoformat(),
            "classification": "Nonsensitive read-only",
            "projects": [{"public_id": item.public_id, "code": item.code, "title": item.title, "status": item.status} for item in visible],
            "sessions": [{"public_id": item.public_id, "project_public_id": item.project.public_id, "title": item.title, "starts_at": item.starts_at.isoformat(), "ends_at": item.ends_at.isoformat(), "venue": item.venue} for item in sessions],
            "tasks": [{"public_id": item.public_id, "project_public_id": item.project.public_id, "title": item.title, "status": item.status, "due_at": item.due_at.isoformat() if item.due_at else None} for item in tasks],
        }
    }


@api_v1_bp.get("/openapi.json")
def openapi_document():
    paths = {f"/api/v1/{resource}": {"get": {"summary": f"List {resource}", "responses": {"200": {"description": "Cursor-paginated results"}}}} for resource in sorted(RESOURCE_MODELS)}
    paths.update({
        "/api/v1/me": {"get": {"summary": "Return the signed-in account and personal profile", "responses": {"200": {"description": "Personal profile"}}}},
        "/api/v1/projects/{public_id}/transition": {"post": {"summary": "Transition a project", "responses": {"200": {"description": "Transition applied"}, "422": {"description": "Lifecycle rule rejected"}}}},
        "/api/v1/tasks/{public_id}/status": {"post": {"summary": "Apply a task workflow decision", "responses": {"200": {"description": "Status applied"}, "409": {"description": "Optimistic concurrency conflict"}}}},
        "/api/v1/checklist-items/{public_id}/status": {"post": {"summary": "Apply a checklist workflow decision", "responses": {"200": {"description": "Status applied"}, "409": {"description": "Optimistic concurrency conflict"}}}},
        "/api/v1/documents/{public_id}/decision": {"post": {"summary": "Approve, reject, or waive document metadata", "responses": {"200": {"description": "Decision applied"}}}},
        "/api/v1/contributions/{public_id}/decision": {"post": {"summary": "Approve or reject a contribution", "responses": {"200": {"description": "Decision applied"}}}},
        "/api/v1/operational-requests/{public_id}/transition": {"post": {"summary": "Transition an operational request", "responses": {"200": {"description": "Transition applied"}}}},
        "/api/v1/feedback-responses/{public_id}/moderate": {"post": {"summary": "Moderate a feedback response", "responses": {"200": {"description": "Moderation applied"}}}},
        "/api/v1/attendance/batch": {"post": {"summary": "Idempotent attendance batch", "parameters": [{"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string"}}], "responses": {"201": {"description": "Attendance committed"}}}},
    })
    return {"openapi": "3.1.0", "info": {"title": "ICC/OIA ERP API", "version": "1.0.0"}, "paths": paths}
