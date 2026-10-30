"""The Reports page: one year at a glance, then the finished events.

Five numbers and a list. The numbers are the ones people are asked for at
the end of a year -- how many events ran, how many people took part, how
many volunteer hours, how much money went out, how many feedback replies --
and each is counted from the same events the list shows, so nothing on the
page disagrees with anything else on it.
"""

from __future__ import annotations

from decimal import Decimal

from app.database import db
from app.models.erp import FeedbackForm, FeedbackResponse, ReimbursementEntry, TeamAssignment
from app.models.production import ContributionRecord
from app.models.project import AcademicYear
from app.services.scope import visible_projects
from app.services.stage import CANCELLED, FINISHED, event_stage

SHOW = 5


def report_years():
    return AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()


def pick_year(public_id=None):
    years = report_years()
    if public_id:
        chosen = next((year for year in years if year.public_id == public_id), None)
        if chosen is not None:
            return chosen
    return next((year for year in years if year.is_current), years[0] if years else None)


def build_year_report(user, year, *, show_all=False):
    projects = [
        project for project in visible_projects(user)
        if year is None or project.academic_year_id == year.id
    ]
    ran = [project for project in projects if event_stage(project) != CANCELLED]
    finished = sorted(
        (project for project in ran if event_stage(project) == FINISHED),
        key=lambda project: project.end_date or project.start_date, reverse=True,
    )
    ids = [project.id for project in ran] or [-1]

    people = db.session.query(db.func.count(db.distinct(TeamAssignment.person_id))).filter(
        TeamAssignment.project_id.in_(ids), TeamAssignment.status == "Active",
    ).scalar() or 0
    hours = db.session.query(db.func.coalesce(db.func.sum(ContributionRecord.duration_hours), 0)).filter(
        ContributionRecord.project_id.in_(ids), ContributionRecord.approval_status == "Approved",
    ).scalar() or 0
    paid = db.session.query(db.func.coalesce(db.func.sum(ReimbursementEntry.amount), 0)).filter(
        ReimbursementEntry.project_id.in_(ids), ReimbursementEntry.status == "Paid",
    ).scalar() or 0
    replies = FeedbackResponse.query.join(FeedbackForm, FeedbackResponse.form_id == FeedbackForm.id).filter(FeedbackForm.project_id.in_(ids)).count()

    return {
        "year": year,
        "years": report_years(),
        "totals": [
            {"label": "Events", "value": len(ran), "note": f"{len(finished)} finished"},
            {"label": "People took part", "value": people},
            {"label": "Volunteer hours", "value": _number(hours)},
            {"label": "Money paid", "value": Decimal(paid), "money": True},
            {"label": "Feedback replies", "value": replies},
        ],
        "finished": finished if show_all else finished[:SHOW],
        "finished_total": len(finished),
        "show_all": show_all,
    }


def _number(value):
    value = Decimal(value or 0)
    return int(value) if value == value.to_integral_value() else round(value, 1)
