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
from app.models.project import AcademicYear, Campus, Project, ProgramType


public_bp = Blueprint("public", __name__, url_prefix="/public")

_PUBLIC_PROJECT_STATUSES = ("Planned", "Active", "Closing", "Completed")
_PUBLIC_DOCUMENT_CATEGORIES = ("Poster", "Photo")


def _published_projects_query():
    """Publication is a distinct, explicit gate from workflow `status` --
    nothing is public unless it has been reviewed and moved to Published.
    See PLAN.md "Additional release blockers" finding."""
    return Project.query.filter(
        Project.publication_status == "Published",
        Project.status.in_(_PUBLIC_PROJECT_STATUSES),
    )


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


def _published_analytics_payload():
    """Build the one allow-listed aggregate payload used by both HTML and JSON.

    Keeping the public charts and their accessible data tables on the same
    payload prevents visual/screen-reader values from drifting apart.
    """
    published = _published_projects_query()
    events_per_campus = [
        {"label": campus.name, "value": published.filter(Project.campus_id == campus.id).count()}
        for campus in Campus.query.order_by(Campus.name).all()
    ]
    program_split = [
        {"label": program_type.name, "value": published.filter(Project.program_type_id == program_type.id).count()}
        for program_type in ProgramType.query.order_by(ProgramType.name).all()
    ]
    reach_by_year = (
        db.session.query(AcademicYear.name, db.func.sum(Project.actual_reach))
        .join(Project, Project.academic_year_id == AcademicYear.id)
        .filter(Project.publication_status == "Published", Project.status.in_(_PUBLIC_PROJECT_STATUSES))
        .group_by(AcademicYear.id, AcademicYear.name)
        .order_by(AcademicYear.start_date, AcademicYear.id)
        .all()
    )
    return {
        "events_per_campus": events_per_campus,
        "program_split": program_split,
        "participation_trend": [
            {"label": year_name, "value": int(reach or 0)}
            for year_name, reach in reach_by_year
        ],
    }


@public_bp.get("/")
def landing():
    total_completed = _published_projects_query().filter(Project.status == "Completed").count()
    total_active = _published_projects_query().filter(Project.status.in_(("Planned", "Active", "Closing"))).count()
    analytics = _published_analytics_payload() if (total_completed + total_active) > 0 else None
    return render_template(
        "public/landing.html",
        total_completed=total_completed,
        total_active=total_active,
        analytics=analytics,
        has_published_analytics=analytics is not None,
    )


@public_bp.get("/events")
def events():
    projects = _published_projects_query().order_by(Project.start_date.desc()).all()
    return render_template("public/events.html", events=[_public_project_fields(project) for project in projects])


@public_bp.get("/events/<string:code>")
def event_detail(code):
    project = Project.query.filter_by(code=code).first()
    if not project or project.publication_status != "Published" or project.status not in _PUBLIC_PROJECT_STATUSES:
        abort(404)
    reports = (
        ReportSnapshot.query.filter_by(project_id=project.id, publication_status="Published", approval_status="Approved")
        .order_by(ReportSnapshot.version.desc())
        .all()
    )
    documents = (
        DocumentRecord.query.filter(
            DocumentRecord.project_id == project.id,
            DocumentRecord.status == "Approved",
            DocumentRecord.permission_classification == "Public",
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
        if project and (
            project.publication_status != "Published"
            or project.status not in _PUBLIC_PROJECT_STATUSES
        ):
            continue
        rows.append({**_public_snapshot_fields(snapshot), "project_code": project.code if project else None, "project_title": project.title if project else "Multi-project rollup"})
    return render_template("public/reports.html", reports=rows)


@public_bp.get("/analytics-data")
def analytics_data():
    """JSON feed for the public charts -- aggregate counts only, computed
    server-side from allow-listed fields (never raw per-project detail).
    Only Published projects are counted -- see PLAN.md publication gate."""
    return _published_analytics_payload()
