"""Routes behind the rebuilt event page: the to-do list, removing and
putting back, pasting a list of people, the money list's extras, adding
files, the feedback link and finishing an event.

They live on ``erp_bp`` beside the older routes they sit next to; this file
only keeps ``erp.py`` from growing further. Every change answers the same
way: back to the card it came from, with a short message -- and, for a
removal, an Undo button that lasts ten seconds.
"""

from __future__ import annotations

import io
import secrets
from datetime import date, datetime, timezone

from flask import abort, flash, g, redirect, request, send_file, session, url_for
from openpyxl import Workbook

from app.blueprints.erp import _project, erp_bp
from app.database import db
from app.models.erp import (
    ChecklistItemStatus,
    DocumentRecord,
    FeedbackForm,
    ProjectSession,
    ReimbursementEntry,
    TeamAssignment,
)
from app.models.production import ContributionRecord
from app.models.project import Project
from app.services.audit import record_audit
from app.services.authorization import can_view_project, has_permission
from app.services.documents import classify_filename
from app.services.drive import extract_drive_id
from app.services.event_page import FILE_KINDS, JOBS
from app.services.people import enrol, find_or_make_person, parse_people_list
from app.services.finish import decide_finish, request_finish
from app.services.teams import can_contribute
from app.services.timeutil import to_utc
from app.services.todo import can_tick, find_todo, mark_done, remove as remove_todo, reopen, restore, skip
from app.services.upload_sessions import UploadSessionError, upload_file_single_shot

DEFAULT_FEEDBACK_QUESTIONS = ("What did you like most?", "What could be better next time?")


def _event(public_id):
    """The event, for anyone who may work on some part of it: the people who
    run it, volunteers listed on it, and contributors with a team item."""
    project = Project.query.filter_by(public_id=public_id).first_or_404()
    if not (can_view_project(g.user, project) or can_contribute(g.user, project)):
        abort(403)
    return project


def _manage(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "manage_projects", project):
        abort(403)
    return project


def back(project, card, anchor=None):
    """Return to where the form was sent from when it says so (same-site
    paths only), else to ``card`` on the event page."""
    target = (request.form.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//") and "://" not in target:
        return redirect(target)
    url = url_for("erp.project_detail", public_id=project.public_id, card=card)
    return redirect(url + (f"#{anchor}" if anchor else f"#card-{card}"))


def offer_undo(message, endpoint, **params):
    """Show ``message`` with an Undo button for the next page load."""
    session["undo"] = {"message": message, "url": url_for(endpoint, **params)}


def _date(value, default=None):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return default


# ── To do ──────────────────────────────────────────────────────────────


@erp_bp.post("/projects/<string:public_id>/todos/done")
def todos_done(public_id):
    """One button per row marks that row done; the "Mark selected done"
    button marks every ticked box. Both post here."""
    project = _event(public_id)
    refs = [request.form["done"]] if request.form.get("done") else request.form.getlist("items")
    if not refs:
        flash("Tick at least one thing first.", "warning")
        return back(project, "todo")
    count = 0
    for ref in refs:
        item = find_todo(project, ref)
        if item is None or not can_tick(g.user, project, item):
            continue
        mark_done(item, g.user)
        count += 1
    if count:
        flash("Done ✓" if count == 1 else f"{count} things done ✓", "success")
    else:
        flash("Nothing was changed.", "warning")
    return back(project, "todo")


@erp_bp.post("/projects/<string:public_id>/todos/<string:ref>/reopen")
def todo_reopen(public_id, ref):
    project = _event(public_id)
    item = find_todo(project, ref)
    if item is None or not can_tick(g.user, project, item):
        abort(404 if item is None else 403)
    reopen(item, g.user)
    flash("Put back on the list.", "success")
    return back(project, "todo")


@erp_bp.post("/projects/<string:public_id>/todos/<string:ref>/skip")
def todo_skip(public_id, ref):
    project = _event(public_id)
    item = find_todo(project, ref)
    if item is None or not can_tick(g.user, project, item):
        abort(404 if item is None else 403)
    try:
        skip(item, g.user, request.form.get("reason"))
        flash("Skipped.", "success")
    except ValueError as error:
        flash(str(error), "danger")
    return back(project, "todo")


@erp_bp.post("/projects/<string:public_id>/todos/<string:ref>/remove")
def todo_remove(public_id, ref):
    project = _manage(public_id)
    item = find_todo(project, ref)
    if item is None:
        abort(404)
    remove_todo(item, g.user)
    offer_undo(f"Removed “{item.title}”.", "erp.todo_restore", public_id=project.public_id, ref=ref)
    return back(project, "todo")


@erp_bp.post("/projects/<string:public_id>/todos/<string:ref>/restore")
def todo_restore(public_id, ref):
    project = _manage(public_id)
    if restore(project, ref, g.user) is None:
        flash("That could not be put back.", "warning")
    else:
        flash("Put back.", "success")
    return back(project, "todo")


@erp_bp.post("/projects/<string:public_id>/todos/<string:ref>/file")
def todo_file(public_id, ref):
    """Add the file a to-do item asks for ("Upload the poster") and tick it
    in the same step."""
    project = _event(public_id)
    item = find_todo(project, ref)
    if item is None or not can_tick(g.user, project, item):
        abort(404 if item is None else 403)
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Choose a file first.", "warning")
        return back(project, "todo")
    try:
        document = upload_file_single_shot(project, uploaded.filename, uploaded.read(), g.user)
    except UploadSessionError as error:
        flash(f"{uploaded.filename}: {error}", "danger")
        return back(project, "todo")
    if isinstance(item.record, ChecklistItemStatus):
        document.checklist_status_id = item.record.id
    else:
        item.record.evidence_reference = document.public_id
    db.session.commit()
    mark_done(item, g.user)
    flash(f"Added {uploaded.filename} and marked done ✓", "success")
    return back(project, "todo")


# ── Schedule ───────────────────────────────────────────────────────────


def _session(project, session_public_id):
    return ProjectSession.query.filter_by(public_id=session_public_id, project_id=project.id).first_or_404()


@erp_bp.post("/projects/<string:public_id>/sessions/<string:session_public_id>/edit")
def edit_session(public_id, session_public_id):
    project = _manage(public_id)
    item = _session(project, session_public_id)
    day = _date(request.form.get("day"), item.starts_at.date())
    try:
        start = datetime.strptime(request.form.get("start_time") or "", "%H:%M").time()
        end = datetime.strptime(request.form.get("end_time") or "", "%H:%M").time()
    except ValueError:
        flash("Pick a start and end time.", "danger")
        return back(project, "schedule", item.public_id)
    starts_at, ends_at = to_utc(datetime.combine(day, start)), to_utc(datetime.combine(day, end))
    if ends_at < starts_at:
        flash("It has to end after it starts.", "danger")
        return back(project, "schedule", item.public_id)
    item.title = (request.form.get("title") or "").strip() or item.title
    item.venue = (request.form.get("venue") or "").strip() or None
    item.starts_at, item.ends_at = starts_at, ends_at
    record_audit("session.edit", item, after={"title": item.title}, actor=g.user)
    db.session.commit()
    flash("Saved ✓", "success")
    return back(project, "schedule", item.public_id)


@erp_bp.post("/projects/<string:public_id>/sessions/<string:session_public_id>/remove")
def remove_session(public_id, session_public_id):
    project = _manage(public_id)
    item = _session(project, session_public_id)
    item.is_active = False
    record_audit("session.remove", item, actor=g.user)
    db.session.commit()
    offer_undo(f"Removed “{item.title}”.", "erp.restore_session", public_id=project.public_id, session_public_id=item.public_id)
    return back(project, "schedule")


@erp_bp.post("/projects/<string:public_id>/sessions/<string:session_public_id>/restore")
def restore_session(public_id, session_public_id):
    project = _manage(public_id)
    item = _session(project, session_public_id)
    item.is_active = True
    record_audit("session.restore", item, actor=g.user)
    db.session.commit()
    flash("Put back.", "success")
    return back(project, "schedule", item.public_id)


# ── People ─────────────────────────────────────────────────────────────

@erp_bp.post("/projects/<string:public_id>/team/paste")
def paste_people(public_id):
    project = _manage(public_id)
    default_job = request.form.get("job") if request.form.get("job") in JOBS else "Volunteer"
    rows = parse_people_list(request.form.get("people"))
    if not rows:
        flash("Paste at least one name, one per line.", "warning")
        return back(project, "people")
    added, already, problems = 0, 0, []
    for row in rows:
        if not row["name"] and not row["email"]:
            problems.append(f"line {row['line']} has no name")
            continue
        if not row["name"]:
            row["name"] = row["email"].split("@")[0]
        person = find_or_make_person(project, row)
        if enrol(project, person, row["job"] or default_job, g.user):
            added += 1
        else:
            already += 1
    db.session.commit()
    parts = [f"Added {added} {'person' if added == 1 else 'people'}"]
    if already:
        parts.append(f"{already} already on the list")
    flash(" · ".join(parts) + ".", "success")
    if problems:
        flash("Skipped: " + "; ".join(problems) + ".", "warning")
    return back(project, "people")


def _assignment(project, assignment_public_id):
    return TeamAssignment.query.filter_by(public_id=assignment_public_id, project_id=project.id).first_or_404()


@erp_bp.post("/projects/<string:public_id>/team/<string:assignment_public_id>/remove")
def remove_team_member(public_id, assignment_public_id):
    project = _manage(public_id)
    assignment = _assignment(project, assignment_public_id)
    assignment.status = "Removed"
    record_audit("team.remove", assignment, actor=g.user)
    db.session.commit()
    offer_undo(f"Removed {assignment.person.display_name}.", "erp.restore_team_member",
               public_id=project.public_id, assignment_public_id=assignment.public_id)
    return back(project, "people")


@erp_bp.post("/projects/<string:public_id>/team/<string:assignment_public_id>/restore")
def restore_team_member(public_id, assignment_public_id):
    project = _manage(public_id)
    assignment = _assignment(project, assignment_public_id)
    assignment.status = "Active"
    record_audit("team.restore", assignment, actor=g.user)
    db.session.commit()
    flash("Put back.", "success")
    return back(project, "people")


@erp_bp.post("/projects/<string:public_id>/team/<string:assignment_public_id>/job")
def change_job(public_id, assignment_public_id):
    project = _manage(public_id)
    assignment = _assignment(project, assignment_public_id)
    job = request.form.get("job")
    if job in JOBS:
        assignment.role_label = job
        db.session.commit()
        flash("Saved ✓", "success")
    return back(project, "people")


@erp_bp.post("/projects/<string:public_id>/team/<string:assignment_public_id>/hours")
def add_hours(public_id, assignment_public_id):
    """Hours someone worked, entered by whoever runs the event. Counted
    straight away: hours no longer wait for approval."""
    project = _manage(public_id)
    assignment = _assignment(project, assignment_public_id)
    try:
        hours = float(request.form.get("hours") or 0)
    except ValueError:
        hours = 0
    if hours <= 0 or hours > 24:
        flash("Hours must be between 0 and 24.", "danger")
        return back(project, "people")
    record = ContributionRecord(
        project_id=project.id, person_id=assignment.person_id, activity_type="Event support",
        description=(request.form.get("what") or "").strip() or "Helped at the event",
        duration_hours=hours, approval_status="Approved", approved_by_id=g.user.id,
        approved_at=datetime.now(timezone.utc),
    )
    db.session.add(record)
    record_audit("contribution.log", record, after={"project": project.public_id, "hours": hours}, actor=g.user)
    db.session.commit()
    flash(f"Added {hours:g} hours for {assignment.person.display_name}.", "success")
    return back(project, "people")


# ── Money ──────────────────────────────────────────────────────────────


def _money(project, entry_public_id):
    return ReimbursementEntry.query.filter_by(public_id=entry_public_id, project_id=project.id).first_or_404()


@erp_bp.post("/projects/<string:public_id>/reimbursements/<string:entry_public_id>/remove")
def remove_money(public_id, entry_public_id):
    project = _manage(public_id)
    entry = _money(project, entry_public_id)
    if entry.status != "Asked":
        flash("Only money that is still being asked for can be removed.", "warning")
        return back(project, "money")
    entry.status = "Removed"
    record_audit("reimbursement.remove", entry, actor=g.user)
    db.session.commit()
    offer_undo(f"Removed “{entry.particular or 'money line'}”.", "erp.restore_money",
               public_id=project.public_id, entry_public_id=entry.public_id)
    return back(project, "money")


@erp_bp.post("/projects/<string:public_id>/reimbursements/<string:entry_public_id>/restore")
def restore_money(public_id, entry_public_id):
    project = _manage(public_id)
    entry = _money(project, entry_public_id)
    if entry.status == "Removed":
        entry.status = "Asked"
        record_audit("reimbursement.restore", entry, actor=g.user)
        db.session.commit()
        flash("Put back.", "success")
    return back(project, "money")


@erp_bp.get("/projects/<string:public_id>/templates/<string:kind>.xlsx")
def download_template(public_id, kind):
    """A blank sheet with the right column names, so a list filled in
    offline uploads without anyone needing to know the format."""
    _manage(public_id)
    columns = {
        "money": ["Date", "Party Name", "Bill Number", "Amount", "Particular", "Status"],
        "people": ["Name", "Email", "Registration number", "Job"],
    }.get(kind)
    if columns is None:
        abort(404)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Money" if kind == "money" else "People"
    sheet.append(columns)
    if kind == "money":
        sheet.append([date.today().isoformat(), "Shop name", "", 500, "What it was for", "Asked"])
    else:
        sheet.append(["Asha Rao", "asha.rao@christuniversity.in", "2312345", "Volunteer"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer, as_attachment=True, download_name=f"{kind}-template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── Files ──────────────────────────────────────────────────────────────

_KIND_CATEGORY = {key: category for key, _label, category in FILE_KINDS}


@erp_bp.post("/projects/<string:public_id>/files")
def add_files(public_id):
    """One box for every file: pick files (or take a photo on a phone), say
    what they are, done. A Google Drive link can go in the same box."""
    project = _event(public_id)
    if not (has_permission(g.user, "manage_projects", project) or can_contribute(g.user, project)):
        abort(403)
    kind = request.form.get("kind") or "other"
    category = _KIND_CATEGORY.get(kind)
    uploads = [f for f in request.files.getlist("files") if f and f.filename]
    link = (request.form.get("drive_url") or "").strip()
    if not uploads and not link:
        flash("Choose a file or paste a link first.", "warning")
        return back(project, "files")
    added = 0
    for uploaded in uploads:
        try:
            upload_file_single_shot(project, uploaded.filename, uploaded.read(), g.user, category=category or classify_filename(uploaded.filename)[0])
            added += 1
        except UploadSessionError as error:
            flash(f"{uploaded.filename}: {error}", "danger")
    if link:
        title = (request.form.get("title") or "").strip() or ({k: label for k, label, _ in FILE_KINDS}.get(kind) or "Linked file")
        document = DocumentRecord(
            project_id=project.id, title=title[:255], category=category or classify_filename(title)[0],
            status="Submitted", drive_url=link, drive_file_id=extract_drive_id(link),
            uploaded_by_id=g.user.id, owner_person_id=g.user.person_id,
        )
        db.session.add(document)
        db.session.flush()
        record_audit("document.index", document, after={"project": project.public_id}, actor=g.user)
        db.session.commit()
        added += 1
    if added:
        flash("Added ✓" if added == 1 else f"Added {added} files ✓", "success")
    return back(project, "files")


def _document(project, document_public_id):
    return DocumentRecord.query.filter_by(public_id=document_public_id, project_id=project.id).first_or_404()


@erp_bp.post("/projects/<string:public_id>/documents/<string:document_public_id>/kind")
def change_file_kind(public_id, document_public_id):
    project = _manage(public_id)
    document = _document(project, document_public_id)
    category = _KIND_CATEGORY.get(request.form.get("kind"))
    if category:
        document.category = category
        record_audit("document.kind", document, after={"category": category}, actor=g.user)
        db.session.commit()
        flash("Saved ✓", "success")
    return back(project, "files", document.public_id)


@erp_bp.post("/projects/<string:public_id>/documents/<string:document_public_id>/remove")
def remove_file(public_id, document_public_id):
    project = _manage(public_id)
    document = _document(project, document_public_id)
    document.status = "Removed"
    record_audit("document.remove", document, actor=g.user)
    db.session.commit()
    offer_undo(f"Removed “{document.title}”.", "erp.restore_file",
               public_id=project.public_id, document_public_id=document.public_id)
    return back(project, "files")


@erp_bp.post("/projects/<string:public_id>/documents/<string:document_public_id>/restore")
def restore_file(public_id, document_public_id):
    project = _manage(public_id)
    document = _document(project, document_public_id)
    if document.status == "Removed":
        # Files are no longer approved, so there is no earlier state to
        # recover: back on the list is all Undo has to mean.
        document.status = "Submitted"
        record_audit("document.restore", document, actor=g.user)
        db.session.commit()
        flash("Put back.", "success")
    return back(project, "files", document.public_id)


# ── Feedback ───────────────────────────────────────────────────────────


@erp_bp.post("/projects/<string:public_id>/feedback-link")
def make_feedback_link(public_id):
    """Open a feedback form with ready-made questions and a link anyone can
    answer without signing in."""
    project = _manage(public_id)
    form = FeedbackForm.query.filter_by(project_id=project.id, is_open=True).first()
    if form is None:
        lines = [line.strip() for line in (request.form.get("questions") or "").splitlines() if line.strip()]
        questions = [{"key": "rating", "type": "scale", "min": 1, "max": 5, "label": "How was it? (1 to 5)"}]
        questions += [{"key": f"q_{index}", "type": "text", "label": label[:200]}
                      for index, label in enumerate(lines[:20] or DEFAULT_FEEDBACK_QUESTIONS, 1)]
        form = FeedbackForm(project_id=project.id, title=f"Feedback: {project.title}"[:180],
                            questions_json=questions, is_open=True, is_anonymous=True)
        db.session.add(form)
    if not form.public_token:
        form.public_token = secrets.token_urlsafe(16)
    record_audit("feedback_form.link", form, after={"project": project.public_id}, actor=g.user)
    db.session.commit()
    flash("Feedback link ready. Copy it and share it.", "success")
    return back(project, "feedback")


@erp_bp.post("/projects/<string:public_id>/feedback-link/close")
def close_feedback_link(public_id):
    project = _manage(public_id)
    for form in FeedbackForm.query.filter_by(project_id=project.id, is_open=True):
        form.is_open = False
    db.session.commit()
    flash("Feedback link closed. No more answers will come in.", "success")
    return back(project, "feedback")


# ── Finish ─────────────────────────────────────────────────────────────


@erp_bp.post("/projects/<string:public_id>/finish")
def finish_route(public_id):
    project = _manage(public_id)
    try:
        request_finish(
            project, g.user, summary=request.form.get("summary"),
            show_on_website=request.form.get("show_on_website") == "yes",
        )
        flash("Sent to Faculty to sign off ✓", "success")
    except (ValueError, PermissionError) as error:
        flash(str(error), "danger")
    return back(project, "finish")


@erp_bp.post("/projects/<string:public_id>/finish/decision")
def decide_finish_route(public_id):
    project = _project(public_id)
    if not has_permission(g.user, "approve", project):
        abort(403)
    approve = request.form.get("decision") == "approve"
    try:
        decide_finish(project, g.user, approve=approve, note=request.form.get("note"))
        flash("Signed off \u2713" if approve else "Sent back with your note.", "success")
    except (ValueError, PermissionError) as error:
        flash(str(error), "danger")
    return back(project, "finish")
