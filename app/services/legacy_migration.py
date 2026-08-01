"""One-off, idempotent data migrations from the legacy operational tables
(`app/models/operational.py`, plus legacy `ProjectParticipant`) into their
production-schema equivalents. Each function is safe to re-run: it looks
for an already-migrated equivalent before creating a new row, so running a
migration twice does not duplicate data. Intended to be invoked once each
via the matching `flask migrate-*` CLI command (see `app/cli.py`) ahead of
deleting the legacy tables entirely.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database import db
from app.models.erp import DocumentRecord, FeedbackForm, FeedbackResponse, Person, ProjectSession, SessionAttendance, TeamAssignment, Wing
from app.models.operational import AttendanceRecord, Contribution, Document, Feedback
from app.models.production import ContributionRecord
from app.models.project import ProjectParticipant
from app.services.drive import validate_drive_link


def _resolve_person(user):
    """Resolve a User to a Person, creating one if necessary. Mirrors the
    pattern already used by `dashboard.py::approve_user` and the
    `backfill-user-person-links` CLI command, so if that backfill has
    already run this is just `user.person`."""
    if user is None:
        return None
    if user.person_id:
        return user.person
    person = Person.query.filter(db.func.lower(Person.primary_email) == user.email.lower()).first()
    if not person:
        person = Person(first_name=user.username, primary_email=user.email, campus_id=user.campus_id, person_type="Platform User")
        db.session.add(person)
        db.session.flush()
    user.person_id = person.id
    return person


_PARTICIPANT_TYPE_MAP = {
    "Volunteer": ("Project Team", "Volunteer"),
    "Buddy": ("Project Team", "Buddy"),
    "Faculty": ("Governance", "Faculty"),
    "Core Committee": ("Governance", "Core Committee Member"),
    "Attendee": ("Participant", None),
    "Exchange Student": ("Exchange Program", "Exchange Student"),
}


def migrate_participants_to_teams():
    """ProjectParticipant -> TeamAssignment. Cohort membership has no
    TeamAssignment analog and is not tracked by legacy data, so no
    cohort_id is set here -- that's a genuinely new capability, not a
    migrated field."""
    migrated = skipped = 0
    for participant in ProjectParticipant.query.all():
        person = Person.query.get(participant.person_id) if participant.person_id else None
        if not person and participant.user_id:
            person = _resolve_person(participant.user)
        if not person:
            skipped += 1
            continue
        assignment_type, role_label = _PARTICIPANT_TYPE_MAP.get(participant.participant_type, ("Project Team", participant.participant_type))
        existing = TeamAssignment.query.filter_by(person_id=person.id, project_id=participant.project_id, assignment_type=assignment_type).first()
        if existing:
            skipped += 1
            continue
        if person.nationality_country is None and participant.nationality:
            person.nationality_country = participant.nationality
        db.session.add(TeamAssignment(
            person_id=person.id,
            project_id=participant.project_id,
            user_id=participant.user_id,
            assignment_type=assignment_type,
            role_label=role_label,
            status=participant.status,
            starts_on=participant.registration_date.date() if participant.registration_date else None,
        ))
        migrated += 1
    db.session.commit()
    return {"migrated": migrated, "skipped": skipped}


def migrate_attendance_to_sessions():
    """AttendanceRecord (per-project-per-date) -> SessionAttendance
    (per-session-per-person). Legacy attendance has no session concept, so
    one synthetic ProjectSession is created per distinct (project, date)
    pair, tagged session_type="Legacy Attendance Import" so the UI can
    visually distinguish these from real scheduled sessions."""
    migrated = skipped = 0
    sessions_created = 0
    session_cache = {}
    for record in AttendanceRecord.query.order_by(AttendanceRecord.project_id, AttendanceRecord.date).all():
        person = _resolve_person(record.user)
        if not person:
            skipped += 1
            continue
        cache_key = (record.project_id, record.date)
        session = session_cache.get(cache_key)
        if session is None:
            code = f"LEGACY-ATT-{record.date.isoformat()}"
            session = ProjectSession.query.filter_by(project_id=record.project_id, code=code).first()
            if not session:
                day_start = datetime.combine(record.date, datetime.min.time())
                session = ProjectSession(
                    project_id=record.project_id,
                    code=code,
                    title=f"Attendance — {record.date.strftime('%b %d, %Y')}",
                    session_type="Legacy Attendance Import",
                    starts_at=day_start,
                    ends_at=day_start + timedelta(hours=23, minutes=59),
                )
                db.session.add(session)
                db.session.flush()
                sessions_created += 1
            session_cache[cache_key] = session
        existing = SessionAttendance.query.filter_by(session_id=session.id, person_id=person.id).first()
        if existing:
            skipped += 1
            continue
        db.session.add(SessionAttendance(
            session_id=session.id, person_id=person.id, status=record.status,
            verified_by_id=record.verified_by_id,
        ))
        migrated += 1
    db.session.commit()
    return {"migrated": migrated, "skipped": skipped, "sessions_created": sessions_created}


_DIVISION_TO_WING_CODE = {
    "Graphic design": "MEDIA",
    "Photography": "MEDIA",
    "Operations": "EVENTS",
}


def migrate_contributions_to_records():
    """Contribution -> ContributionRecord. `division` (a free string) maps
    to `wing_id` where a clean mapping exists (Media/Events); anything that
    doesn't map cleanly (e.g. "Translation") is preserved by prefixing the
    original division into the description instead of being silently
    dropped, since ContributionRecord has no free-text division column."""
    migrated = skipped = 0
    for contribution in Contribution.query.all():
        person = _resolve_person(contribution.user)
        if not person:
            skipped += 1
            continue
        existing = ContributionRecord.query.filter_by(
            project_id=contribution.project_id, person_id=person.id,
            activity_type=contribution.activity_type,
        ).first()
        if existing:
            skipped += 1
            continue
        wing_id = None
        description = contribution.description or f"{contribution.activity_type} contribution"
        if contribution.division:
            wing_code = _DIVISION_TO_WING_CODE.get(contribution.division)
            if wing_code:
                wing = Wing.query.filter_by(code=wing_code).first()
                wing_id = wing.id if wing else None
            if not wing_id:
                description = f"[{contribution.division}] {description}"
        db.session.add(ContributionRecord(
            project_id=contribution.project_id, person_id=person.id, wing_id=wing_id,
            activity_type=contribution.activity_type, description=description,
            duration_hours=contribution.duration_hours,
            approval_status=contribution.approval_status,
            approved_by_id=contribution.approved_by_id, approved_at=contribution.approved_at,
        ))
        migrated += 1
    db.session.commit()
    return {"migrated": migrated, "skipped": skipped}


def migrate_documents_to_records():
    """Document -> DocumentRecord, revalidating the Drive link through
    validate_drive_link (legacy Document never ran any validation).
    Migrated rows enter as "Submitted" rather than pre-approved, since
    legacy documents never went through an approval workflow."""
    migrated = skipped = 0
    for document in Document.query.all():
        existing = DocumentRecord.query.filter_by(project_id=document.project_id, title=document.title).first()
        if existing:
            skipped += 1
            continue
        owner_person = _resolve_person(document.uploaded_by)
        validation = {}
        if document.google_drive_link:
            try:
                validation = validate_drive_link(document.google_drive_link, "Internal")
            except Exception:
                validation = {}
        record = DocumentRecord(
            project_id=document.project_id, title=document.title, category=document.document_type,
            status="Submitted", drive_url=document.google_drive_link,
            drive_file_id=validation.get("file_id"),
            owner_person_id=owner_person.id if owner_person else None,
        )
        db.session.add(record)
        db.session.flush()
        record.created_at = document.created_at
        migrated += 1
    db.session.commit()
    return {"migrated": migrated, "skipped": skipped}


_SUBMISSION_QUESTIONS = [
    {"key": "rating", "type": "scale", "min": 1, "max": 5, "label": "Overall rating"},
    {"key": "comments", "type": "text", "label": "Comments"},
    {"key": "suggestions", "type": "text", "label": "Suggestions"},
    {"key": "submission_type", "type": "choice", "options": ["Event feedback", "IGP feedback", "Buddy feedback", "Experience sharing"], "label": "Feedback type"},
]


def migrate_feedback_to_responses():
    """Feedback -> FeedbackForm/FeedbackResponse. Synthesizes one canonical
    FeedbackForm per project (created lazily) whose questions_json follows
    the fixed {"rating": {"type": "scale", ...}} convention documented on
    FeedbackForm/FeedbackResponse -- the platform-wide standard for every
    feedback form, not just migrated legacy ones. Migrated responses are
    marked pre-Approved (legacy had no moderation gate) with
    publication_consent left False (legacy had no consent concept)."""
    migrated = skipped = 0
    forms_created = 0
    form_cache = {}
    for feedback in Feedback.query.all():
        person = _resolve_person(feedback.user)
        form = form_cache.get(feedback.project_id)
        if form is None:
            form = FeedbackForm.query.filter_by(project_id=feedback.project_id, title="Migrated Legacy Feedback").first()
            if not form:
                form = FeedbackForm(
                    project_id=feedback.project_id, title="Migrated Legacy Feedback",
                    questions_json=_SUBMISSION_QUESTIONS, is_open=False,
                )
                db.session.add(form)
                db.session.flush()
                forms_created += 1
            form_cache[feedback.project_id] = form
        answers = {
            "rating": feedback.rating, "comments": feedback.comments,
            "suggestions": feedback.suggestions, "submission_type": feedback.submission_type,
        }
        existing = FeedbackResponse.query.filter_by(
            form_id=form.id, person_id=person.id if person else None,
        ).first() if person else None
        if existing:
            skipped += 1
            continue
        response = FeedbackResponse(
            form_id=form.id, person_id=person.id if person else None,
            answers_json=answers, publication_consent=False, moderation_status="Approved",
        )
        db.session.add(response)
        db.session.flush()
        response.created_at = feedback.created_at
        migrated += 1
    db.session.commit()
    return {"migrated": migrated, "skipped": skipped, "forms_created": forms_created}
