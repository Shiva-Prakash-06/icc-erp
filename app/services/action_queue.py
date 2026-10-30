"""What Faculty has to say yes to.

Only three things need someone else's OK now: money, finishing an event,
and putting an event on the public website. Everything else is done when
the person doing it says it is done. Only Faculty approves, and never
something they asked for themselves.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import db
from app.models.erp import ReimbursementEntry
from app.models.user import User
from app.services.authorization import has_permission
from app.services.formatting import money
from app.services.scope import approvable_projects

ACTION_QUEUE_KINDS = (
    "Money",
    "Finish event",
    "Project publication",
)


# The endpoint and its parameters are returned rather than a built URL:
# this service is called from tests and jobs with only an app context, and
# url_for needs a request. The template resolves it. Saying no always needs
# a reason, so "Not now" opens the record; "Approve" is one click.
def _decision(endpoint, *, field, value, version, approve, reject, **params):
    return {
        "decide_endpoint": endpoint,
        "decide_params": params,
        "decide_field": field,
        "approve_value": value,
        "version": version,
        "approve_label": approve,
        "reject_label": reject,
    }


def _name(user):
    if user is None:
        return "someone"
    return user.person.display_name if user.person else user.username


def build_action_queue(user, projects=None):
    """Return the sorted queue of decisions waiting on ``user``.

    Each item is ``{"kind","title","project","tab","anchor","due_at",...}``;
    ``tab``/``anchor`` deep-link to the card on the event page that holds it.
    """
    if projects is None:
        projects = approvable_projects(user)
    projects_by_id = {project.id: project for project in projects}
    now = datetime.now(timezone.utc)
    action_queue = []

    money_project_ids = [project.id for project in projects if has_permission(user, "approve_operational_requests", project)]
    for entry in ReimbursementEntry.query.filter(
        ReimbursementEntry.project_id.in_(money_project_ids or [-1]),
        ReimbursementEntry.status == "Asked",
        db.or_(ReimbursementEntry.created_by_id.is_(None), ReimbursementEntry.created_by_id != user.id),
    ).all():
        entry_project = projects_by_id.get(entry.project_id) or entry.project
        what_for = entry.particular or entry.party_name or "Money"
        action_queue.append({"kind": "Money", "title": f"{what_for} · {money(entry.amount, currency=entry.currency or 'INR')}", "project": entry_project, "tab": "money", "anchor": entry.public_id, "due_at": None,
                             "meta": entry.party_name or "", **_decision("erp.update_reimbursement_status", field="status", value="Approved", version=None, approve="Approve", reject="Not now", public_id=entry_project.public_id, entry_public_id=entry.public_id)})

    waiting = [
        candidate for candidate in projects
        if candidate.finish_requested_at and candidate.status not in {"Completed", "Archived", "Cancelled"}
        and candidate.finish_requested_by_id != user.id
    ]
    requesters = {}
    requester_ids = {candidate.finish_requested_by_id for candidate in waiting if candidate.finish_requested_by_id}
    if requester_ids:
        requesters = {account.id: account for account in User.query.filter(User.id.in_(requester_ids)).all()}
    for candidate in waiting:
        action_queue.append({
            "kind": "Finish event",
            "title": f"{candidate.title} · sent by {_name(requesters.get(candidate.finish_requested_by_id))}",
            "project": candidate, "tab": "finish", "anchor": "finish", "due_at": None,
            "meta": "Ready to sign off",
            **_decision("erp.decide_finish_route", field="decision", value="approve", version=None, approve="Sign off", reject="Not now", public_id=candidate.public_id),
        })

    # A publication asked for on its own (not as part of finishing). One
    # bundled with a finish request is decided by that sign-off.
    pending_publications = [
        candidate for candidate in projects
        if candidate.publication_status == "Pending"
        and candidate.publication_requested_by_id != user.id
        and not candidate.finish_requested_at
        and has_permission(user, "manage_governance", candidate)
    ]
    requesters = {}
    requester_ids = {candidate.publication_requested_by_id for candidate in pending_publications if candidate.publication_requested_by_id}
    if requester_ids:
        requesters = {account.id: account for account in User.query.filter(User.id.in_(requester_ids)).all()}
    for candidate in pending_publications:
        action_queue.append({
            "kind": "Project publication",
            "title": f"{candidate.title} · requested by {_name(requesters.get(candidate.publication_requested_by_id))}",
            "project": candidate, "tab": "finish", "anchor": "publication", "due_at": None,
            "meta": "Show on the public website?",
            **_decision("erp.decide_publication", field="decision", value="Published", version=candidate.version, approve="Show it", reject="Not now", public_id=candidate.public_id),
        })
    action_queue.sort(key=lambda item: (item["due_at"] is None, item["due_at"] or now))
    return action_queue
