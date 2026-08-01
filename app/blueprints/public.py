"""Public, no-login transparency site for ICC/IGP.

Hard rule for every route in this file: never join to TeamAssignment,
Person, BuddyAssignment, RecruitmentApplication, ContributionRecord, or any
other table carrying an individual's name/contact/PII. Only aggregate
counts, published report snapshots (via an explicit field allow-list), and
non-Restricted curated-category documents may be surfaced here.
"""

from __future__ import annotations

from flask import Blueprint, abort, render_template

from app.database import db
from app.models.erp import DocumentRecord, ReportSnapshot
from app.models.project import Campus, Project, ProgramType


public_bp = Blueprint("public", __name__, url_prefix="/public")

_PUBLIC_PROJECT_STATUSES = ("Planned", "Active", "Closing", "Completed")
_PUBLIC_DOCUMENT_CATEGORIES = ("Poster", "Photo")


def _public_project_fields(project):
    """Explicit allow-list -- never widen this to `project.__dict__` or a
    generic serializer, since that would leak internal fields (owner,
    version, closure_summary, etc.) onto the public site by accident."""
    return {
        "code": project.code,
        "title": project.title,
        "description": project.description,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "venue": project.venue,
        "status": project.status,
        "campus_name": project.campus.name if project.campus else None,
        "program_type_name": project.program_type.name if project.program_type else None,
    }


def _public_snapshot_fields(snapshot):
    """Project only the aggregate figures appropriate for public display --
    never the raw snapshot_json, which can carry internal operational
    detail (closure blockers, contribution counts, budget)."""
    data = snapshot.snapshot_json or {}
    reach = data.get("reach", {})
    return {
        "public_id": snapshot.public_id,
        "title": snapshot.title,
        "version": snapshot.version,
        "generated_at": data.get("generated_at"),
        "actual_reach": reach.get("actual"),
    }


@public_bp.get("/")
def landing():
    total_completed = Project.query.filter_by(status="Completed").count()
    total_active = Project.query.filter(Project.status.in_(("Planned", "Active", "Closing"))).count()
    return render_template("public/landing.html", total_completed=total_completed, total_active=total_active)


@public_bp.get("/events")
def events():
    projects = (
        Project.query.filter(Project.status.in_(_PUBLIC_PROJECT_STATUSES))
        .order_by(Project.start_date.desc())
        .all()
    )
    return render_template("public/events.html", events=[_public_project_fields(project) for project in projects])


@public_bp.get("/events/<string:code>")
def event_detail(code):
    project = Project.query.filter_by(code=code).first()
    if not project or project.status not in _PUBLIC_PROJECT_STATUSES:
        abort(404)
    reports = (
        ReportSnapshot.query.filter_by(project_id=project.id, publication_status="Published", approval_status="Approved")
        .order_by(ReportSnapshot.version.desc())
        .all()
    )
    documents = (
        DocumentRecord.query.filter(
            DocumentRecord.project_id == project.id,
            DocumentRecord.permission_classification != "Restricted",
            DocumentRecord.category.in_(_PUBLIC_DOCUMENT_CATEGORIES),
            DocumentRecord.drive_url.isnot(None),
        ).all()
    )
    return render_template(
        "public/event_detail.html",
        event=_public_project_fields(project),
        reports=[_public_snapshot_fields(snapshot) for snapshot in reports],
        documents=[{"title": document.title, "category": document.category, "drive_url": document.drive_url} for document in documents],
    )


@public_bp.get("/reports")
def reports():
    snapshots = (
        ReportSnapshot.query.filter_by(publication_status="Published", approval_status="Approved")
        .order_by(ReportSnapshot.id.desc())
        .limit(100)
        .all()
    )
    rows = []
    for snapshot in snapshots:
        project = db.session.get(Project, snapshot.project_id) if snapshot.project_id else None
        rows.append({**_public_snapshot_fields(snapshot), "project_code": project.code if project else None, "project_title": project.title if project else "Multi-project rollup"})
    return render_template("public/reports.html", reports=rows)


@public_bp.get("/analytics-data")
def analytics_data():
    """JSON feed for the public charts -- aggregate counts only, computed
    server-side from allow-listed fields (never raw per-project detail)."""
    campuses = Campus.query.order_by(Campus.name).all()
    events_per_campus = [
        {"label": campus.name, "value": Project.query.filter_by(campus_id=campus.id).count()}
        for campus in campuses
    ]
    program_split = [
        {"label": program_type.name, "value": Project.query.filter_by(program_type_id=program_type.id).count()}
        for program_type in ProgramType.query.order_by(ProgramType.name).all()
    ]
    reach_by_year = (
        db.session.query(db.func.sum(Project.actual_reach))
        .join(Project.academic_year)
        .group_by(Project.academic_year_id)
        .order_by(Project.academic_year_id)
        .all()
    )
    return {
        "events_per_campus": events_per_campus,
        "program_split": program_split,
        "participation_trend": [int(row[0] or 0) for row in reach_by_year],
    }
