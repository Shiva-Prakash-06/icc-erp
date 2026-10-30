"""One to-do list per event.

An event's work used to live in two places with two vocabularies: tasks
(eight statuses, an approver) and checklist requirements (the same eight
statuses, a verifier, "evidence"). Both are still stored where they always
were, but everything a person sees and does goes through this module, and
there are only three things to do with an item: tick it, skip it with a
reason, or put it back.

An item is for one person or for a team (app/services/teams.py). Ticking is
open to whoever runs the event, the item's owner, and -- for team items --
the head of that team, even on an event they otherwise cannot open.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload

from app.database import db
from app.models.erp import ChecklistInstance, ChecklistItemStatus, Person, WorkTask
from app.services.audit import record_audit
from app.services.authorization import has_permission
from app.services.operations import change_checklist_status, change_task_status
from app.services.teams import TEAM_LABELS, can_contribute, user_teams

DONE_STATUSES = frozenset({"Completed", "Approved"})
SKIPPED_STATUSES = frozenset({"Waived"})
#: Removed from the list but kept for the record (and for Undo).
GONE_STATUSES = frozenset({"Cancelled", "Removed", "Rejected"})

TASK_PREFIX = "t-"
CHECKLIST_PREFIX = "c-"


@dataclass
class TodoItem:
    ref: str
    record: object
    project: object
    title: str
    team: str | None
    owner: Person | None
    owner_text: str | None
    due_at: datetime | None
    status: str
    skip_reason: str | None
    file_count: int
    sequence: int

    @property
    def is_task(self):
        return self.ref.startswith(TASK_PREFIX)

    @property
    def done(self):
        return self.status in DONE_STATUSES or self.status in SKIPPED_STATUSES

    @property
    def skipped(self):
        return self.status in SKIPPED_STATUSES

    @property
    def who(self):
        """Plain words for whose item this is."""
        if self.owner is not None:
            return self.owner.display_name
        if self.team:
            return TEAM_LABELS.get(self.team, self.team.title())
        return self.owner_text or ""

    def overdue(self, now=None):
        now = now or datetime.now(timezone.utc)
        due = self.due_at
        if due is None or self.done:
            return False
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due < now


def _from_task(task, owners):
    return TodoItem(
        ref=f"{TASK_PREFIX}{task.public_id}", record=task, project=task.project, title=task.title,
        team=task.assigned_team, owner=owners.get(task.owner_person_id), owner_text=task.external_contact,
        due_at=task.due_at, status="Waived" if task.waived else task.status,
        skip_reason=task.waiver_reason, file_count=0, sequence=10_000 + task.id,
    )


def _from_checklist(item, owners):
    return TodoItem(
        ref=f"{CHECKLIST_PREFIX}{item.public_id}", record=item, project=item.checklist.project,
        title=item.template_item.title, team=item.assigned_team, owner=owners.get(item.owner_person_id),
        owner_text=item.external_owner, due_at=item.due_at,
        status="Waived" if item.waived else item.status, skip_reason=item.waiver_reason,
        file_count=len(item.evidence_documents), sequence=item.template_item.sequence or 0,
    )


def _owners(person_ids):
    person_ids = {pid for pid in person_ids if pid}
    if not person_ids:
        return {}
    return {person.id: person for person in Person.query.filter(Person.id.in_(person_ids)).all()}


def _sort_key(item):
    # Open before done; then the earliest due date; undated items in the
    # order their checklist lists them.
    due = item.due_at
    if due is not None and due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return (item.done, due is None, due or datetime.max.replace(tzinfo=timezone.utc), item.sequence)


def _checklist_rows(project_ids):
    return (
        ChecklistItemStatus.query.join(ChecklistInstance)
        .options(
            joinedload(ChecklistItemStatus.template_item),
            joinedload(ChecklistItemStatus.checklist).joinedload(ChecklistInstance.project),
        )
        .filter(ChecklistInstance.project_id.in_(project_ids or [-1]))
        .all()
    )


def _build(tasks, checklist_items):
    tasks = [task for task in tasks if task.status not in GONE_STATUSES]
    checklist_items = [item for item in checklist_items if item.status not in GONE_STATUSES]
    owners = _owners([t.owner_person_id for t in tasks] + [c.owner_person_id for c in checklist_items])
    items = [_from_task(task, owners) for task in tasks] + [_from_checklist(item, owners) for item in checklist_items]
    return sorted(items, key=_sort_key)


def todos_for_project(project):
    """Every live item on the event, open ones first."""
    return _build(list(project.work_tasks), _checklist_rows([project.id]))


def todos_for_projects(projects):
    ids = [project.id for project in projects]
    tasks = WorkTask.query.filter(WorkTask.project_id.in_(ids or [-1])).all()
    return _build(tasks, _checklist_rows(ids))


def find_todo(project, ref):
    ref = (ref or "").strip()
    if ref.startswith(TASK_PREFIX):
        task = WorkTask.query.filter_by(public_id=ref[len(TASK_PREFIX):], project_id=project.id).first()
        return _from_task(task, _owners([task.owner_person_id])) if task else None
    if ref.startswith(CHECKLIST_PREFIX):
        item = (
            ChecklistItemStatus.query.join(ChecklistInstance)
            .filter(ChecklistItemStatus.public_id == ref[len(CHECKLIST_PREFIX):], ChecklistInstance.project_id == project.id)
            .first()
        )
        return _from_checklist(item, _owners([item.owner_person_id])) if item else None
    return None


def can_tick(user, project, item):
    if has_permission(user, "manage_projects", project):
        return True
    if item.owner is not None and user.person_id and item.owner.id == user.person_id:
        return True
    return bool(item.team) and item.team in user_teams(user) and can_contribute(user, project)


def _change(item, status, actor, *, comment=None, waive=False):
    record = item.record
    change = change_task_status if item.is_task else change_checklist_status
    change(record, status, actor, expected_version=record.version, comment=comment, waive=waive)


def mark_done(item, actor):
    if not item.done:
        _change(item, "Completed", actor)


def reopen(item, actor):
    if item.done:
        _change(item, "Not Started", actor)


def skip(item, actor, reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Say why it is being skipped.")
    _change(item, "Waived", actor, comment=reason, waive=True)


def remove(item, actor):
    """Take an item off the list. Checklist items stay in the database (they
    came from a template) and can be put back with :func:`restore`."""
    record = item.record
    before = record.status
    record.status = "Cancelled" if item.is_task else "Removed"
    record.version += 1
    record_audit("todo.remove", record, before={"status": before}, after={"status": record.status}, actor=actor)
    db.session.commit()


def restore(project, ref, actor):
    """Undo :func:`remove`. Looks past the removed filter on purpose."""
    if ref.startswith(TASK_PREFIX):
        record = WorkTask.query.filter_by(public_id=ref[len(TASK_PREFIX):], project_id=project.id).first()
    else:
        record = (
            ChecklistItemStatus.query.join(ChecklistInstance)
            .filter(ChecklistItemStatus.public_id == ref[len(CHECKLIST_PREFIX):], ChecklistInstance.project_id == project.id)
            .first()
        )
    if record is None or record.status not in GONE_STATUSES:
        return None
    record.status = "Not Started"
    record.version += 1
    record_audit("todo.restore", record, after={"status": record.status}, actor=actor)
    db.session.commit()
    return record


def add_todo(project, title, actor, *, who=None, due_at=None):
    """``who`` is "me", a team key, "p-<person public_id>", or empty (the
    event's owner)."""
    title = (title or "").strip()
    if not title:
        raise ValueError("Type what needs doing.")
    task = WorkTask(project_id=project.id, title=title[:220], status="Not Started", due_at=due_at)
    who = (who or "").strip()
    if who == "me":
        task.owner_person_id = actor.person_id
    elif who in TEAM_LABELS:
        task.assigned_team = who
    elif who.startswith("p-"):
        person = Person.query.filter_by(public_id=who[2:]).first()
        if person is None:
            raise ValueError("That person is not on the list any more.")
        task.owner_person_id = person.id
    db.session.add(task)
    db.session.flush()
    record_audit("task.create", task, after={"project": project.public_id, "title": task.title, "who": who}, actor=actor)
    db.session.commit()
    return task


def who_options(project):
    """The "Who?" picker: me, each team, then everyone on the event."""
    from app.models.erp import TeamAssignment

    people = [
        assignment.person for assignment in TeamAssignment.query.filter_by(project_id=project.id, status="Active").all()
        if assignment.person is not None
    ]
    people.sort(key=lambda person: person.display_name.lower())
    return {
        "teams": list(TEAM_LABELS.items()),
        "people": [(f"p-{person.public_id}", person.display_name) for person in people],
    }
