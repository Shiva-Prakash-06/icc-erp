from __future__ import annotations

from app.models.project import BuddyAssignment


def validate_buddy_assignment(project, buddy_user_id, exchange_student_id, start_date, end_date, override=False, reason=None):
    if project.program_type.name != "IGP":
        raise ValueError("Buddy assignments are restricted to IGP projects.")
    if buddy_user_id == exchange_student_id:
        raise ValueError("A buddy cannot be assigned to themselves.")
    if end_date < start_date:
        raise ValueError("Buddy assignment end date cannot precede its start date.")
    overlap = BuddyAssignment.query.filter(
        BuddyAssignment.status == "Active",
        BuddyAssignment.buddy_user_id == buddy_user_id,
        BuddyAssignment.start_date <= end_date,
        BuddyAssignment.end_date >= start_date,
    ).first()
    duplicate_student = BuddyAssignment.query.filter(
        BuddyAssignment.status == "Active",
        BuddyAssignment.project_id == project.id,
        BuddyAssignment.exchange_student_id == exchange_student_id,
        BuddyAssignment.start_date <= end_date,
        BuddyAssignment.end_date >= start_date,
    ).first()
    if (overlap or duplicate_student) and not override:
        raise ValueError("This period overlaps an active buddy or participant assignment.")
    if (overlap or duplicate_student) and not (reason or "").strip():
        raise ValueError("An approved overlap requires a justification.")
    return True
