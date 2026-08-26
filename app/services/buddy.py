from __future__ import annotations

from app.database import db
from app.models.project import BuddyAssignment
from app.models.user import User


def _resolve_person_id(user_id, person_id):
    if person_id:
        return person_id
    if user_id:
        user = db.session.get(User, user_id)
        return getattr(user, "person_id", None)
    return None


def validate_buddy_assignment(
    project, buddy_user_id, exchange_student_id, start_date, end_date,
    override=False, reason=None, buddy_person_id=None, exchange_student_person_id=None,
):
    """Validate a buddy pairing. Either side may be identified by a User
    account (buddy_user_id/exchange_student_id) or a bare Person record
    (buddy_person_id/exchange_student_person_id) -- exchange students in
    particular are the population least likely to have a login account.
    Overlap-checking is resolved to a single person_id axis internally so a
    person represented via their User account on one row and directly via
    Person on another is still correctly detected as the same person.
    """
    if project.program_type.name != "IGP":
        raise ValueError("Buddy assignments are restricted to IGP projects.")
    if not (buddy_user_id or buddy_person_id):
        raise ValueError("A buddy identity (account or person) is required.")
    if not (exchange_student_id or exchange_student_person_id):
        raise ValueError("An exchange student identity (account or person) is required.")
    if end_date < start_date:
        raise ValueError("Buddy assignment end date cannot precede its start date.")

    buddy_person = _resolve_person_id(buddy_user_id, buddy_person_id)
    student_person = _resolve_person_id(exchange_student_id, exchange_student_person_id)
    same_person = buddy_person and student_person and buddy_person == student_person
    same_account = buddy_user_id and exchange_student_id and buddy_user_id == exchange_student_id
    if same_person or same_account:
        raise ValueError("A buddy cannot be assigned to themselves.")

    candidates = BuddyAssignment.query.filter(
        BuddyAssignment.status == "Active",
        BuddyAssignment.start_date <= end_date,
        BuddyAssignment.end_date >= start_date,
    ).all()

    def _is_same_buddy(candidate):
        if buddy_user_id and candidate.buddy_user_id == buddy_user_id:
            return True
        return bool(buddy_person) and candidate.buddy_identity_person_id == buddy_person

    def _is_same_student(candidate):
        if exchange_student_id and candidate.exchange_student_id == exchange_student_id:
            return True
        return bool(student_person) and candidate.exchange_student_identity_person_id == student_person

    overlap = next((c for c in candidates if _is_same_buddy(c)), None)
    duplicate_student = next(
        (c for c in candidates if c.project_id == project.id and _is_same_student(c)), None,
    )

    if (overlap or duplicate_student) and not override:
        raise ValueError("This period overlaps an active buddy or participant assignment.")
    if (overlap or duplicate_student) and not (reason or "").strip():
        raise ValueError("An approved overlap requires a justification.")
    return True
