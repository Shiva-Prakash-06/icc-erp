from __future__ import annotations

from datetime import date, datetime, time

from flask import Blueprint, current_app, g, jsonify, request

from app.database import db
from app.database import csrf, limiter
from app.models.erp import (
    AuditEvent,
    BudgetLine,
    ChecklistInstance,
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
from app.models.project import AcademicYear, Campus, Project
from app.models.project import BuddyAssignment, BuddyLog, ProjectParticipant
from app.models.operational import Contribution
from app.services.authorization import can_view_project, has_permission
from app.services.drive import validate_drive_link
from app.services.imports import commit_batch, stage_supplied_source
from app.services.lifecycle import closure_blockers, transition_project


api_v1_bp = Blueprint("api_v1", __name__)


RESOURCE_MODELS = {
    "organizations": OperatingUnit,
    "campuses": Campus,
    "academic-years": AcademicYear,
    "role-assignments": RoleAssignment,
    "projects": Project,
    "components": ProjectComponent,
    "sessions": ProjectSession,
    "tasks": WorkTask,
    "checklists": ChecklistInstance,
    "people": Person,
    "teams": TeamAssignment,
    "applications": TeamAssignment,
    "participants": ProjectParticipant,
    "attendance": SessionAttendance,
    "contributions": Contribution,
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
}


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
    excluded = {"password_hash", "drive_url", "before_summary", "after_summary", "ip_address"}
    data = {}
    for column in item.__table__.columns:
        if column.name in excluded or column.name == "id":
            continue
        value = getattr(item, column.name)
        if column.name == "drive_file_id" and getattr(item, "permission_classification", None) == "Restricted":
            if not has_permission(g.user, "sensitive_links", sensitive=True):
                value = None
        data[column.name] = _value(value)
    return data


@api_v1_bp.get("/meta")
def meta():
    return {
        "version": "v1",
        "resources": sorted(RESOURCE_MODELS),
        "pagination": "cursor",
        "error_format": "RFC 7807",
        "environment": "demonstrator" if current_app.config.get("DEMONSTRATOR") else "production",
    }


@api_v1_bp.get("/<resource>")
def list_resource(resource):
    model = RESOURCE_MODELS.get(resource)
    if not model:
        return _problem(404, "Unknown resource")
    permission_by_resource = {
        "role-assignments": "manage_users",
        "people": "manage_projects",
        "applications": "manage_projects",
        "imports": "manage_projects",
        "audit-events": "audit",
        "feedback-responses": "report",
        "budgets": "manage_projects",
        "operational-requests": "manage_projects",
    }
    required_permission = permission_by_resource.get(resource)
    if required_permission and not has_permission(g.user, required_permission):
        return _problem(403, "Access denied")
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        cursor = int(request.args.get("cursor", 0))
    except ValueError:
        return _problem(400, "Invalid pagination parameters")
    query = model.query.filter(model.id > cursor)
    visible_project_ids = [
        project.id for project in Project.query.order_by(Project.id).all() if can_view_project(g.user, project)
    ]
    if hasattr(model, "project_id"):
        query = query.filter(model.project_id.in_(visible_project_ids or [-1]))
    elif model is BuddyLog:
        query = query.join(BuddyAssignment).filter(BuddyAssignment.project_id.in_(visible_project_ids or [-1]))
    query = query.order_by(model.id.asc())
    if model is Project:
        items = [item for item in query.limit(limit + 1).all() if can_view_project(g.user, item)]
    else:
        items = query.limit(limit + 1).all()
    has_more = len(items) > limit
    page = items[:limit]
    return {
        "data": [_serialize(item) for item in page],
        "next_cursor": page[-1].id if has_more and page else None,
        "count": len(page),
    }


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
    if payload.get("version") != project.version:
        return _problem(409, "Concurrent update conflict", "Refresh the project and retry with its current version.")
    editable = {"title", "description", "objectives", "target_audience", "venue", "capacity", "expected_reach", "actual_reach", "closure_summary"}
    for key in editable:
        if key in payload:
            setattr(project, key, payload[key])
    project.version += 1
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
    result = validate_drive_link(payload.get("url"))
    return ({"data": result}, 200 if result.get("valid") else 422)


@api_v1_bp.post("/imports/stage")
def stage_import():
    if not has_permission(g.user, "manage_projects"):
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
    if not form:
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
    if not form:
        return _problem(404, "Feedback form not found or closed")
    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers")
    if not isinstance(answers, dict) or not answers:
        return _problem(422, "At least one feedback answer is required")
    response = FeedbackResponse(
        form_id=form.id,
        answers_json=answers,
        publication_consent=bool(payload.get("publication_consent")),
        moderation_status="Pending",
    )
    db.session.add(response)
    db.session.commit()
    return {"data": {"public_id": response.public_id, "moderation_status": response.moderation_status}}, 201
