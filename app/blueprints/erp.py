from __future__ import annotations

import io
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlparse

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from app.database import db
from app.models.erp import (
    AuditEvent,
    DocumentRecord,
    ImportBatch,
    Person,
    ProjectSession,
    SessionAttendance,
    TeamAssignment,
)
from app.models.production import ContributionRecord, Notification, NotificationPreference, RecruitmentApplication
from app.models.project import BuddyAssignment, BuddyLog, Project
from app.models.user import User
from app.services.audit import record_audit, record_sensitive_access
from app.services.authorization import can_view_project, has_any_permission, has_permission
from app.services.event_page import build_event_page
from app.services.todo import add_todo
from app.services.teams import can_contribute
from app.services.buddy import validate_buddy_assignment
from app.services.drive import DriveStorageError, extract_drive_id
from app.services.imports import (
    STANDARD_IMPORTS,
    MissingSourceError,
    available_supplied_sources,
    commit_batch,
    stage_supplied_source,
    stage_uploaded_source,
)
from app.services.itinerary import (
    ItineraryParseError,
    commit_itinerary_batch,
    create_igp_project_from_itinerary,
    stage_itinerary_import,
)
from app.services.project_quickcreate import create_minimal_project, creatable_program_types
from app.services.stage import CANCELLED, FINISHED, HAPPENING, NEEDS_FINISHING, STAGE_LABELS, WAITING, event_stage
from app.services.timeutil import to_utc
from app.services.buddy_import import BuddyImportError, commit_buddy_batch, stage_buddy_import
from app.models.erp import ReimbursementEntry
from app.services.reimbursements import (
    MONEY_ASKED,
    MoneyDecisionError,
    ReimbursementImportError,
    change_money_status,
    commit_reimbursement_batch,
    export_reimbursements,
    stage_reimbursement_import,
)
from app.services.icc_import import (
    commit_icc_attendance_batch,
    stage_icc_attendance_import,
)
from app.services.upload_sessions import UploadSessionError, upload_file_single_shot
from app.services.report_assembly import ReportIncompleteError, assemble_complete_report, preflight_report
from app.services.lifecycle import transition_project
from app.services.people import enrol
from app.services.vocabulary import resolve_vocabulary_value
from app.services.publication import decide_project_publication, submit_project_publication
from app.services.operations import decide_recruitment, mark_attendance
from app.services.reporting import compile_project_snapshot


erp_bp = Blueprint("erp", __name__, url_prefix="/erp")


@erp_bp.get("")
def hub():
    # Merged into the home page -- see dashboard.index / app/services/home.py.
    # Kept as a route so old bookmarks and links still resolve.
    return redirect(url_for("dashboard.index"))


# The campus tiles, the ICC/IGP division screens and the analytics
# dashboards are gone: an event is found on the Events list (filtered by
# campus for anyone who can see more than one), and the year's numbers are
# on Reports. The old addresses still work so bookmarks do not break.


@erp_bp.get("/campuses")
def campuses():
    return redirect(url_for("erp.projects"))


@erp_bp.get("/campuses/<string:public_id>")
def campus_detail(public_id):
    return redirect(url_for("erp.projects", campus=public_id))


@erp_bp.get("/campuses/<string:public_id>/<string:division>")
def division(public_id, division):
    return redirect(url_for("erp.projects", campus=public_id))


@erp_bp.get("/analytics")
def analytics():
    from app.services.navigation import REPORT_TEAMS
    from app.services.teams import user_teams

    return redirect(url_for("dashboard.reports") if user_teams(g.user) & REPORT_TEAMS else url_for("erp.projects"))


@erp_bp.get("/analytics/<string:division>")
def analytics_division(division):
    return analytics()


@erp_bp.get("/oversight")
def oversight():
    # Merged into the decision queue -- see dashboard.queue /
    # app/services/home.py. (It pointed at "/" until the Tile System made
    # the home screen the campus tiles and gave the queue its own route.)
    # The 403 gate is kept here, not just on the queue screen, because
    # e2e/auth-and-rbac and tests/production_completion_test assert this
    # exact route still 403s for non-approvers.
    if not has_any_permission(g.user, "approve"):
        abort(403)
    return redirect(url_for("dashboard.queue"))


@erp_bp.get("/projects")
def projects():
    return _render_projects()


@erp_bp.get("/projects/new")
def new_project():
    if not has_any_permission(g.user, "manage_projects"):
        abort(403)
    program_types = creatable_program_types(g.user)
    past_events = [
        project for project in Project.query.order_by(Project.start_date.desc()).limit(60).all()
        if has_permission(g.user, "manage_projects", project)
    ][:20]
    return render_template(
        "erp/create_project.html",
        program_types=program_types,
        past_events=past_events,
        today=date.today(),
    )


def _form_time(field):
    try:
        return datetime.strptime((request.form.get(field) or "").strip(), "%H:%M").time()
    except ValueError:
        return None


@erp_bp.post("/projects/quick-create")
def quick_create_project():
    """New event: a name and a date. A time and a place are optional and
    make the main session; "Start from a past event" copies its to-do list."""
    if not has_any_permission(g.user, "manage_projects"):
        abort(403)
    program_types = creatable_program_types(g.user)
    program_name = request.form.get("program_type_name") or (program_types[0].name if len(program_types) == 1 else None)
    start_date = _form_date("start_date")
    end_date = _form_date("end_date") or start_date
    copy_from = None
    if request.form.get("copy_from"):
        copy_from = Project.query.filter_by(public_id=request.form["copy_from"]).first()
        if copy_from is None or not has_permission(g.user, "manage_projects", copy_from):
            copy_from = None
    if start_date is None:
        flash("Pick the date of the event.", "danger")
        return redirect(url_for("erp.new_project"))
    try:
        project = create_minimal_project(
            program_type_name=program_name or (copy_from.program_type.name if copy_from else None),
            title=request.form.get("title"), start_date=start_date, end_date=end_date,
            actor=g.user, venue=request.form.get("venue"), target_audience=request.form.get("target_audience"),
            start_time=_form_time("start_time"), end_time=_form_time("end_time"),
            copy_from=copy_from, standard_todos=copy_from is None,
        )
    except (ValueError, KeyError) as error:
        flash(str(error), "danger")
        return redirect(url_for("erp.new_project"))
    record_audit("project.create", project, after={"code": project.code, "title": project.title, "source": "quick_create"})
    db.session.commit()
    flash(f"{project.title} is ready \u2713 Here is its to-do list.", "success")
    return redirect(url_for("erp.project_detail", public_id=project.public_id, card="todo"))


@erp_bp.post("/projects/quick-create-from-itinerary")
def quick_create_from_itinerary():
    if not has_any_permission(g.user, "manage_projects"):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose the itinerary file first.", "danger")
        return redirect(url_for("erp.new_project"))
    try:
        project, batch = create_igp_project_from_itinerary(uploaded_file, g.user)
    except (ItineraryParseError, ValueError) as error:
        flash(f"No event was made from that itinerary: {error}", "danger")
        return redirect(url_for("erp.new_project"))
    flash(f"{project.title} is ready ✓ {batch.committed_count} times were added from the itinerary.", "success")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


#: Events shown before "Show all".
EVENTS_SHOWN = 10
#: The old state filter, read as the new one so its links still work.
_OLD_STATE = {"upcoming": "now", "active": "now", "overdue": "now", "complete": "finished", "all": "all"}


def _render_projects():
    """Events: what is on now and next by default, finished ones a press
    away. A search box, and a campus picker for anyone who can see more than
    one campus. Media and Culturals heads see the events their team has
    items on."""
    found = {}
    for project in Project.query.order_by(Project.start_date.desc(), Project.id.desc()).all():
        if can_view_project(g.user, project) or can_contribute(g.user, project):
            found[project.id] = project
    projects = list(found.values())

    campuses = sorted({project.campus for project in projects if project.campus}, key=lambda campus: campus.name)
    campus_filter = (request.args.get("campus") or "").strip()
    if campus_filter and len(campuses) > 1:
        projects = [project for project in projects if project.campus and project.campus.public_id == campus_filter]
    else:
        campus_filter = ""

    search_query = (request.args.get("q") or "").strip()
    if search_query:
        needle = search_query.lower()
        projects = [p for p in projects if needle in (p.title or "").lower() or needle in (p.code or "").lower()]

    today = date.today()
    stages = {project.id: event_stage(project, today) for project in projects}
    counts = {
        "now": sum(stage not in {FINISHED, CANCELLED} for stage in stages.values()),
        "finished": sum(stage == FINISHED for stage in stages.values()),
        "all": len(projects),
    }
    show = (request.args.get("show") or _OLD_STATE.get((request.args.get("state") or "").lower()) or "now").lower()
    if show not in counts:
        show = "now"
    if show == "now":
        projects = sorted(
            (p for p in projects if stages[p.id] not in {FINISHED, CANCELLED}),
            key=lambda p: (stages[p.id] not in {HAPPENING, NEEDS_FINISHING, WAITING}, p.start_date or date.max),
        )
    elif show == "finished":
        projects = [p for p in projects if stages[p.id] == FINISHED]

    show_all = bool(request.args.get("all")) or bool(search_query)
    return render_template(
        "erp/projects.html",
        projects=projects if show_all else projects[:EVENTS_SHOWN],
        total=len(projects),
        stages=stages,
        stage_labels=STAGE_LABELS,
        show=show,
        counts=counts,
        search_query=search_query,
        campuses=campuses if len(campuses) > 1 else [],
        campus_filter=campus_filter,
        can_create=has_any_permission(g.user, "manage_projects"),
    )


def _project(public_id):
    project = Project.query.filter_by(public_id=public_id).first_or_404()
    if not can_view_project(g.user, project):
        abort(403)
    return project


@erp_bp.get("/projects/<string:public_id>")
def project_detail(public_id):
    """One page per event: what is left to do, then folded cards.

    ``?card=`` opens a card; the older ``?tab=``, ``?section=`` and
    ``?focus=`` links still land on the card that now holds what they
    pointed at (app/services/event_page.py).
    """
    project = Project.query.filter_by(public_id=public_id).first_or_404()
    if not (can_view_project(g.user, project) or can_contribute(g.user, project)):
        abort(403)
    context = build_event_page(project, g.user, request.args)
    if not (context["can_manage"] or context["can_approve"]) and not has_permission(g.user, "report", project) \
            and not context["can_contribute"]:
        # A volunteer listed on the event sees only what concerns them.
        return render_template("erp/event_volunteer.html", **context)
    return render_template("erp/event.html", return_to=request.full_path.rstrip("?"), **context)


#: Where each old tab's work now lives on the event page.
_TAB_CARD = {"logistics": "todo", "finance": "money", "documents": "files", "people": "people", "analytics": "finish"}


def _redirect_to_tab(project, tab, anchor=None, *, reveal=False):
    """Return to the record's tab, unless the form asked to come back to
    where the decision was actually taken.

    Home and the project Overview now decide items in place, so posting a
    verdict must not teleport the approver into a tab they never opened.
    Only same-origin relative paths are honoured -- anything carrying a
    scheme or a host is discarded rather than followed.

    ``reveal`` is for a record just created. A verdict returns to the page
    it was taken on, because the approver is working down that page; a new
    record is appended to its list and can land on a later page, and
    "created" with nothing new on screen reads as "lost". So when `next` is
    this project's workspace, its `page` gives way to `focus`, which opens
    the page that holds the new record."""
    target = (request.form.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        parsed = urlparse(target)
        if not parsed.scheme and not parsed.netloc:
            workspace = url_for("erp.project_detail", public_id=project.public_id)
            if reveal and anchor and parsed.path == workspace:
                query = [(key, value) for key, value in parse_qsl(parsed.query) if key not in {"page", "focus"}]
                return redirect(f"{workspace}?{urlencode(query + [('focus', anchor)])}#{anchor}")
            return redirect(target)
    # `focus` resolves to the section and page that actually hold the record,
    # which a bare fragment cannot do now that a section is paged.
    card = _TAB_CARD.get(tab, tab)
    target = url_for("erp.project_detail", public_id=project.public_id, card=card)
    return redirect(target + (f"#{anchor}" if anchor else f"#card-{card}"))


@erp_bp.post("/projects/<string:public_id>/applications/<string:application_public_id>/decision")
def decide_recruitment_route(public_id, application_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_people", project):
        abort(403)
    application = RecruitmentApplication.query.filter_by(public_id=application_public_id, project_id=project.id).first_or_404()
    try:
        decision = request.form.get("decision")
        decide_recruitment(
            application, decision, g.user,
            expected_version=int(request.form.get("version") or application.version),
            reason=(request.form.get("reason") or "").strip() or ("Not picked" if decision == "Rejected" else None),
        )
        flash("Saved \u2713", "success")
    except ValueError as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "people", application.public_id)


@erp_bp.get("/projects/<string:public_id>/setup")
def project_setup(public_id):
    """The six-step setup wizard is gone: everything it asked for is added
    in place on the event page. Old links land on the matching card."""
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    card = {"basics": "details", "sessions": "schedule", "team": "people", "checklist": "todo",
            "documents": "files", "budget": "money"}.get(request.args.get("step"), "todo")
    return redirect(url_for("erp.project_detail", public_id=project.public_id, card=card) + f"#card-{card}")


@erp_bp.post("/projects/<string:public_id>/basics")
def update_project_basics(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    title = (request.form.get("title") or "").strip()
    start_date = _form_date("start_date")
    end_date = _form_date("end_date") or start_date
    if not title or start_date is None:
        flash("Give the event a name and a date.", "danger")
        return _redirect_to_tab(project, "details")
    if end_date < start_date:
        flash("The last day cannot be before the first day.", "danger")
        return _redirect_to_tab(project, "details")
    before = {"title": project.title, "start_date": str(project.start_date), "end_date": str(project.end_date)}
    project.title = title
    if "description" in request.form:
        project.description = (request.form.get("description") or "").strip()
    project.venue = (request.form.get("venue") or "").strip()
    project.target_audience = (request.form.get("target_audience") or "").strip()
    project.start_date = start_date
    project.end_date = end_date
    project.version += 1
    record_audit("project.basics", project, before=before, after={"title": title, "start_date": str(start_date), "end_date": str(end_date)}, actor=g.user)
    db.session.commit()
    flash("Saved \u2713", "success")
    return _redirect_to_tab(project, "details")


def _form_date(field, default=None):
    try:
        return datetime.strptime((request.form.get(field) or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return default


def _redirect_after_action(project, default_tab):
    """Kept for the routes that called it; ``next=setup`` (the retired
    wizard) now simply means "back to the event page"."""
    if request.form.get("next") == "setup":
        return redirect(url_for("erp.project_detail", public_id=project.public_id))
    return _redirect_to_tab(project, default_tab)


@erp_bp.post("/projects/<string:public_id>/sessions")
def add_session(public_id):
    """Add a session from a day and two times. Name, day and venue all
    default from the event, so the common case is just the two times."""
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    existing_count = ProjectSession.query.filter_by(project_id=project.id).count()
    title = (request.form.get("title") or "").strip() or ("Main session" if existing_count == 0 else f"Session {existing_count + 1}")
    try:
        if request.form.get("starts_at"):
            # The API and older forms send one campus-local datetime each;
            # storage is UTC throughout (audit B09).
            starts_at = to_utc(datetime.strptime(request.form["starts_at"], "%Y-%m-%dT%H:%M"))
            ends_at = to_utc(datetime.strptime(request.form["ends_at"], "%Y-%m-%dT%H:%M"))
        else:
            day = _form_date("day", project.start_date)
            start = datetime.strptime(request.form.get("start_time") or "", "%H:%M").time()
            end = datetime.strptime(request.form.get("end_time") or "", "%H:%M").time()
            starts_at, ends_at = to_utc(datetime.combine(day, start)), to_utc(datetime.combine(day, end))
    except (KeyError, ValueError):
        flash("Pick a start time and an end time.", "danger")
        return _redirect_after_action(project, "schedule")
    if ends_at < starts_at:
        flash("It has to end after it starts.", "danger")
        return _redirect_after_action(project, "schedule")
    try:
        session_type = resolve_vocabulary_value(request.form.get("session_type") or "Session", request.form.get("session_type_other"), domain="session_type")
    except ValueError as error:
        flash(str(error), "danger")
        return _redirect_after_action(project, "schedule")
    session_item = ProjectSession(
        project_id=project.id, code=request.form.get("code") or f"S{existing_count + 1}",
        title=title, session_type=session_type,
        starts_at=starts_at, ends_at=ends_at, venue=request.form.get("venue") or project.venue,
    )
    db.session.add(session_item)
    record_audit("session.create", session_item, after={"project": project.public_id, "title": title}, actor=g.user)
    db.session.commit()
    flash("Added \u2713 Add another?", "success")
    return _redirect_after_action(project, "schedule")


def _active_participant(project, person_public_id):
    """Resolve `person_public_id` to a Person only if they hold an Active
    TeamAssignment on `project` -- rejects inactive membership and
    cross-project IDs server-side. See PLAN.md "IGP registration number"
    finding: buddy selection must list only eligible project participants."""
    person_public_id = (person_public_id or "").strip()
    if not person_public_id:
        return None
    return (
        Person.query.join(TeamAssignment, TeamAssignment.person_id == Person.id)
        .filter(Person.public_id == person_public_id, TeamAssignment.project_id == project.id, TeamAssignment.status == "Active")
        .first()
    )


@erp_bp.post("/projects/<string:public_id>/buddy-assignments")
def add_buddy_assignment(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    buddy_person = _active_participant(project, request.form.get("buddy_person_public_id"))
    student_person = _active_participant(project, request.form.get("exchange_student_person_public_id"))
    if not buddy_person or not student_person:
        flash("Both people need to be on this event first. Add them under People.", "danger")
        return _redirect_to_tab(project, "people")
    if buddy_person.id == student_person.id:
        flash("A buddy cannot be paired with themselves.", "danger")
        return _redirect_to_tab(project, "people")
    try:
        start_date = _form_date("start_date", project.start_date)
        end_date = _form_date("end_date", project.end_date)
        validate_buddy_assignment(
            project, None, None, start_date, end_date,
            buddy_person_id=buddy_person.id, exchange_student_person_id=student_person.id,
        )
        assignment = BuddyAssignment(
            project_id=project.id, buddy_person_id=buddy_person.id, exchange_student_person_id=student_person.id,
            start_date=start_date, end_date=end_date,
        )
        db.session.add(assignment)
        record_audit("buddy_assignment.create", assignment, after={"project": project.public_id}, actor=g.user)
        db.session.commit()
        flash(f"Paired {buddy_person.display_name} with {student_person.display_name}.", "success")
    except (ValueError, KeyError) as error:
        flash(str(error), "danger")
    return _redirect_to_tab(project, "people")


@erp_bp.get("/projects/<string:public_id>/sessions/<string:session_public_id>/attendance")
def attendance_roll_call(public_id, session_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    session_item = ProjectSession.query.filter_by(public_id=session_public_id, project_id=project.id).first_or_404()
    records = {record.person_id: record for record in SessionAttendance.query.filter_by(session_id=session_item.id).all()}
    team = sorted((a for a in project.team_assignments if a.status == "Active"), key=lambda a: a.person.display_name.lower())
    back_to = request.args.get("from") if (request.args.get("from") or "").startswith("/") else None
    return render_template(
        "erp/attendance_roll_call.html", project=project, session=session_item,
        team=team, records=records, back_to=back_to,
    )


@erp_bp.post("/projects/<string:public_id>/sessions/<string:session_public_id>/attendance")
def mark_session_attendance(public_id, session_public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    session_item = ProjectSession.query.filter_by(public_id=session_public_id, project_id=project.id).first_or_404()
    # Walk-ins: someone who turned up but was not on the list. They are
    # added to the event and marked present in the same save.
    walk_ins = []
    for name in (request.form.get("walk_ins") or "").splitlines():
        name = name.strip()
        if name:
            first, _, last = name.partition(" ")
            person = Person(first_name=first, last_name=last or None, campus_id=project.campus_id, person_type="Guest")
            db.session.add(person)
            db.session.flush()
            enrol(project, person, "Guest", g.user)
            mark_attendance(session_item, person, "Present", g.user, commit=False)
            walk_ins.append(person)
    failures = []
    present = list(walk_ins)
    # The roll-call screen sends one tick box per person (ticked = here);
    # the API and older forms send a status per person.
    roster = set(request.form.getlist("roster"))
    for team_assignment in [a for a in project.team_assignments if a.status == "Active" and a.person not in walk_ins]:
        field = f"status_{team_assignment.person_id}"
        if field in request.form:
            status = request.form[field]
        elif str(team_assignment.person_id) in roster:
            status = "Present" if request.form.get(f"present_{team_assignment.person_id}") else "Absent"
        else:
            continue
        existing = SessionAttendance.query.filter_by(session_id=session_item.id, person_id=team_assignment.person_id).first()
        try:
            mark_attendance(
                session_item, team_assignment.person, status, g.user,
                expected_version=existing.version if existing else None,
                # A reason helps the record but no longer stops the save.
                reason=((request.form.get(f"reason_{team_assignment.person_id}") or "").strip() or "Changed at roll call") if existing else None,
                commit=False,
            )
        except ValueError as error:
            failures.append(f"{team_assignment.person.display_name}: {error}")
        if status == "Present":
            present.append(team_assignment.person)
    if failures:
        db.session.rollback()
        flash("Nothing was saved. " + " ".join(failures), "danger")
        return redirect(url_for("erp.attendance_roll_call", public_id=project.public_id, session_public_id=session_item.public_id))
    try:
        hours = float(request.form.get("hours") or 0)
    except ValueError:
        hours = 0
    if 0 < hours <= 24:
        for person in present:
            db.session.add(ContributionRecord(
                project_id=project.id, person_id=person.id, activity_type="Event support",
                description=f"Attended {session_item.title}", duration_hours=hours,
                approval_status="Approved", approved_by_id=g.user.id, approved_at=datetime.now(timezone.utc),
            ))
    db.session.commit()
    message = f"Attendance saved \u2713 {len(present)} present."
    if 0 < hours <= 24 and present:
        message += f" {hours:g} hours given to each."
    flash(message, "success")
    target = (request.form.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect(url_for("erp.project_detail", public_id=project.public_id, card="schedule") + "#card-schedule")


@erp_bp.post("/projects/<string:public_id>/buddy-assignments/<string:assignment_public_id>/logs")
def log_buddy_interaction(public_id, assignment_public_id):
    project = _project(public_id)
    assignment = BuddyAssignment.query.filter_by(public_id=assignment_public_id, project_id=project.id).first_or_404()
    if not (has_permission(g.user, "contribute", project) or has_permission(g.user, "manage_people", project)):
        abort(403)
    description = (request.form.get("description") or "").strip()
    if not description:
        flash("Write a line about what they did together.", "danger")
        return _redirect_to_tab(project, "buddies")
    log = BuddyLog(
        buddy_assignment_id=assignment.id,
        activity_date=_form_date("activity_date", date.today()),
        description=description,
        duration_hours=request.form.get("duration_hours") or 1,
        status="Approved", verified_by_id=g.user.id, verified_at=datetime.now(timezone.utc),
    )
    db.session.add(log)
    record_audit("buddy_log.create", log, after={"assignment": assignment.public_id}, actor=g.user)
    db.session.commit()
    flash("Saved \u2713", "success")
    return _redirect_to_tab(project, "people")


@erp_bp.post("/projects/<string:public_id>/transition")
def transition(public_id):
    project = _project(public_id)
    # Running an event day to day is the event owner's call. Finishing it
    # (Completed, then Archived) is the one sign-off, and only Faculty
    # gives it.
    sign_off = request.form.get("target_status") in {"Completed", "Archived"}
    if not has_permission(g.user, "approve" if sign_off else "manage_projects", project):
        abort(403)
    try:
        transition_project(
            project,
            request.form.get("target_status"),
            g.user,
            int(request.form.get("version")),
            request.form.get("reason"),
        )
        flash("Saved ✓", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/<string:public_id>/publication/submit")
def submit_publication(public_id):
    project = _project(public_id)
    try:
        submit_project_publication(project, g.user, expected_version=int(request.form.get("version") or project.version))
        flash("Sent to Faculty to show on the website.", "success")
    except PermissionError:
        abort(403)
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/<string:public_id>/publication/decision")
def decide_publication(public_id):
    project = _project(public_id)
    try:
        decide_project_publication(
            project, request.form.get("decision"), g.user,
            expected_version=int(request.form.get("version") or project.version),
            reason=request.form.get("reason"),
        )
        flash("Saved ✓ " + ("It is on the website now." if project.publication_status == "Published" else "It is not on the website."), "success")
    except PermissionError:
        abort(403)
    except (ValueError, TypeError) as error:
        flash(str(error), "danger")
    return redirect(url_for("erp.project_detail", public_id=project.public_id))


@erp_bp.post("/projects/<string:public_id>/tasks")
def add_task(public_id):
    """Add a to-do item: what, who (a person, a team or "me") and by when."""
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    due = _form_date("due")
    try:
        task = add_todo(
            project, request.form.get("title"), g.user, who=request.form.get("who"),
            due_at=to_utc(datetime.combine(due, datetime.min.time()).replace(hour=17)) if due else None,
        )
    except ValueError as error:
        flash(str(error), "danger")
        return _redirect_to_tab(project, "todo")
    if request.form.get("description"):
        task.description = request.form["description"].strip()
    if request.form.get("mandatory_for_closure"):
        task.mandatory_for_closure = True
    db.session.commit()
    flash("Added \u2713", "success")
    return _redirect_to_tab(project, "todo")


@erp_bp.post("/projects/<string:public_id>/itinerary/upload")
def upload_itinerary(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose the itinerary file first.", "danger")
        return _redirect_after_action(project, "logistics")
    try:
        batch = stage_itinerary_import(project, uploaded_file, g.user.public_id)
        commit_itinerary_batch(batch, g.user)
        flash(
            f"Itinerary imported: {batch.committed_count} sessions across "
            f"{(batch.reconciliation_json or {}).get('day_count', '?')} days.",
            "success",
        )
    except (ItineraryParseError, ValueError) as error:
        flash(f"That itinerary could not be read: {error}", "danger")
    return _redirect_after_action(project, "logistics")


@erp_bp.post("/projects/<string:public_id>/buddies/upload")
def upload_buddy_allocation(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose the buddy sheet first.", "danger")
        return _redirect_after_action(project, "people")
    try:
        batch = stage_buddy_import(project, uploaded_file, g.user.public_id)
        commit_buddy_batch(batch, g.user)
        message = f"Buddy allocation imported: {batch.committed_count} of {batch.staged_count} rows committed."
        if batch.error_count:
            message += f" {batch.error_count} row(s) need correction (see import batch for details)."
        flash(message, "success" if not batch.error_count else "warning")
    except (BuddyImportError, ValueError) as error:
        flash(f"That buddy sheet could not be read: {error}", "danger")
    return _redirect_after_action(project, "people")


@erp_bp.post("/projects/<string:public_id>/reimbursements")
def add_reimbursement(public_id):
    """Ask for money: what for and how much. Who it is paid to, the date
    (today) and a photo of the bill are all optional."""
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    what_for = (request.form.get("particular") or "").strip()
    try:
        amount = Decimal((request.form.get("amount") or "").replace(",", "").replace("\u20b9", "").strip())
        if amount < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        flash("Type how much, as a number.", "danger")
        return _redirect_after_action(project, "money")
    if not what_for:
        flash("Say what the money is for.", "danger")
        return _redirect_after_action(project, "money")
    entry = ReimbursementEntry(
        project_id=project.id, date=_form_date("date", date.today()),
        party_name=(request.form.get("party_name") or "").strip(),
        bill_number=(request.form.get("bill_number") or "").strip() or None,
        amount=amount, particular=what_for, status=MONEY_ASKED, created_by_id=g.user.id,
    )
    db.session.add(entry)
    db.session.flush()
    bill = request.files.get("bill")
    if bill and bill.filename:
        try:
            document = upload_file_single_shot(project, bill.filename, bill.read(), g.user, category="Bills")
            entry.bill_document_id = document.id
        except UploadSessionError as error:
            flash(f"The money was added, but the bill could not be: {error}", "warning")
    record_audit("reimbursement.create", entry, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Added \u2713 Faculty will see it.", "success")
    return _redirect_after_action(project, "money")


@erp_bp.post("/projects/<string:public_id>/reimbursements/<string:entry_public_id>/status")
def update_reimbursement_status(public_id, entry_public_id):
    project = _project(public_id)
    entry = ReimbursementEntry.query.filter_by(public_id=entry_public_id, project_id=project.id).first_or_404()
    status = (request.form.get("status") or "").strip()
    if not status:
        flash("Pick what happened to this money.", "danger")
        return _redirect_after_action(project, "money")
    try:
        change_money_status(entry, status, g.user, request.form.get("comment"))
    except MoneyDecisionError as error:
        db.session.rollback()
        flash(str(error), "danger")
        return _redirect_after_action(project, "money")
    db.session.commit()
    flash(f"Marked {entry.status.lower()} \u2713", "success")
    return _redirect_after_action(project, "money")


@erp_bp.post("/projects/<string:public_id>/reimbursements/upload")
def upload_reimbursements(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose the money sheet first.", "danger")
        return _redirect_after_action(project, "finance")
    try:
        batch = stage_reimbursement_import(project, uploaded_file, g.user.public_id)
        commit_reimbursement_batch(batch, g.user)
        flash(f"Added {batch.committed_count} of {batch.staged_count} rows to the money list ✓", "success")
    except (ReimbursementImportError, ValueError) as error:
        flash(f"That sheet could not be read: {error}", "danger")
    return _redirect_after_action(project, "finance")


@erp_bp.get("/projects/<string:public_id>/reimbursements/export.<string:output_format>")
def export_reimbursements_route(public_id, output_format):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    if output_format not in {"csv", "xlsx"}:
        abort(404)
    buffer = export_reimbursements(project, output_format)
    mimetype = "text/csv" if output_format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=f"reimbursements-{project.code or project.public_id}.{output_format}")


@erp_bp.post("/projects/<string:public_id>/icc-attendance/upload")
def upload_icc_attendance(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    uploaded_file = request.files.get("source_file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose the attendance sheet first.", "danger")
        return _redirect_after_action(project, "people")
    try:
        batch = stage_icc_attendance_import(project, uploaded_file, g.user.public_id)
        commit_icc_attendance_batch(batch, g.user)
        flash(f"Added attendance for {batch.committed_count} of {batch.staged_count} rows ✓", "success")
    except ValueError as error:
        flash(f"That attendance sheet could not be read: {error}", "danger")
    return _redirect_after_action(project, "people")


@erp_bp.get("/imports")
def imports():
    if not has_permission(g.user, "manage_imports"):
        abort(403)
    batches = ImportBatch.query.order_by(ImportBatch.created_at.desc()).all()
    return render_template(
        "erp/imports.html",
        batches=batches if request.args.get("all") else batches[:5],
        batch_total=len(batches),
        standard_import_types=sorted(STANDARD_IMPORTS),
        supplied_sources=available_supplied_sources(),
        # Committing a batch needs the global approval capability. Showing the
        # button to everyone who can reach this page sent USC into a 403
        # (audit B11).
        can_commit=has_permission(g.user, "approve"),
    )


@erp_bp.post("/imports/upload")
def upload_import():
    if not has_permission(g.user, "manage_imports"):
        abort(403)
    uploaded_file = request.files.get("source_file")
    import_type = request.form.get("import_type")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a file first.", "danger")
    else:
        try:
            batch = stage_uploaded_source(import_type, uploaded_file, g.user.public_id)
            flash(f"Checked: {batch.staged_count - batch.error_count} rows are fine, {batch.error_count} have problems. Nothing is saved yet.", "success")
        except (ValueError, KeyError) as error:
            flash(str(error), "danger")
    return redirect(url_for("erp.imports"))


@erp_bp.post("/imports/stage")
def stage_import():
    if not has_permission(g.user, "manage_imports"):
        abort(403)
    try:
        batch = stage_supplied_source(request.form.get("import_type"))
        flash(f"Checked: {batch.staged_count - batch.error_count} rows are fine, {batch.error_count} have problems. Nothing is saved yet.", "success")
    except MissingSourceError as error:
        flash(str(error), "warning")
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
        flash(f"Saved ✓ {batch.committed_count} rows added.", "success")
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


@erp_bp.get("/projects/<string:public_id>/report/complete")
def complete_report_preview(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    preflight = preflight_report(project)
    return render_template("erp/complete_report_preview.html", project=project, preflight=preflight)


@erp_bp.get("/projects/<string:public_id>/report/complete.pdf")
def download_complete_report(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "report", project):
        abort(403)
    allow_incomplete = request.args.get("allow_incomplete") == "1"
    try:
        pdf_bytes, snapshot = assemble_complete_report(project, g.user, allow_incomplete=allow_incomplete)
    except ReportIncompleteError:
        flash("Some files could not be opened. See which ones below, then download it anyway if that is fine.", "warning")
        return redirect(url_for("erp.complete_report_preview", public_id=project.public_id))
    except DriveStorageError as error:
        flash(f"A file could not be opened: {error}", "danger")
        return redirect(url_for("erp.complete_report_preview", public_id=project.public_id))
    record_audit("report.download_complete_pdf", snapshot, after={"project": project.public_id, "allow_incomplete": allow_incomplete})
    db.session.commit()
    return send_file(
        io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True,
        download_name=f"{project.code or project.public_id}-complete-report.pdf",
    )


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
    actor_ids = {event.actor_user_id for event in events if event.actor_user_id}
    actors = {user.id: user.username for user in User.query.filter(User.id.in_(actor_ids or [-1])).all()}
    return render_template("erp/audit.html", events=events, actors=actors)


#: The alerts a person may turn off. Anything else -- an account change, or
#: something handed straight to them -- always arrives.
OPTIONAL_ALERTS = ("task.deadline", "checklist.deadline", "task.status")


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
    """One switch, "Email me when something needs me", which sets every alert
    that can be switched off. A single ``event_type`` still sets just that
    one, for anything that posted it before."""
    event_type = (request.form.get("event_type") or "").strip()
    if not event_type:
        abort(422)
    event_types = OPTIONAL_ALERTS if event_type == "all" else (event_type,)
    for kind in event_types:
        preference = NotificationPreference.query.filter_by(user_id=g.user.id, event_type=kind).first()
        if not preference:
            preference = NotificationPreference(user_id=g.user.id, event_type=kind)
            db.session.add(preference)
        preference.email_enabled = bool(request.form.get("email_enabled"))
        preference.in_app_enabled = bool(request.form.get("in_app_enabled")) or event_type == "all"
    db.session.commit()
    flash("Saved ✓", "success")
    return redirect(url_for("erp.notifications"))


# The rebuilt event page's routes register on erp_bp; imported last so the
# blueprint and the helpers they share already exist.
from app.blueprints import erp_event  # noqa: E402,F401
