"""Create-and-enroll for participants without a registration number.

The database already permits a Person with no registration_number, but
enrollment and buddy-pairing forms required one anyway -- a confirmed
workflow defect (imports already accept email-or-registration-number). See
PLAN.md "IGP registration number" finding.
"""

from __future__ import annotations

from app.database import db
from app.models.erp import Person, TeamAssignment
from app.services.audit import record_audit


def find_duplicate_person(email, registration_number):
    """Dedupe only on a nonblank email or registration number -- never on
    name alone, which is far too weak a key for a population that includes
    external participants with no other record in the system."""
    email = (email or "").strip().lower() or None
    registration_number = (registration_number or "").strip() or None
    if not email and not registration_number:
        return None
    email_match = (
        Person.query.filter(db.func.lower(Person.primary_email) == email).first()
        if email else None
    )
    registration_match = (
        Person.query.filter(Person.registration_number == registration_number).first()
        if registration_number else None
    )
    if email_match and registration_match and email_match.id != registration_match.id:
        raise ValueError(
            "The email and registration number belong to different people; resolve the identity conflict before enrollment."
        )
    return email_match or registration_match


def create_and_enroll_participant(project, actor, *, first_name, last_name=None, email=None, registration_number=None, assignment_type="Project Team", role_label=None, expected_project_version=None):
    """Atomically find-or-create a Person and enroll them on `project`.
    First name is the only required field; last name, email, and
    registration number are optional so external participants can be
    enrolled without ever having one."""
    first_name = (first_name or "").strip()
    if not first_name:
        raise ValueError("First name is required.")
    email = (email or "").strip() or None
    registration_number = (registration_number or "").strip() or None

    duplicate = find_duplicate_person(email, registration_number)
    created_new_person = duplicate is None
    if duplicate:
        person = duplicate
    else:
        person = Person(
            first_name=first_name, last_name=(last_name or "").strip() or None,
            primary_email=email, registration_number=registration_number, person_type="Student",
        )
        db.session.add(person)
        db.session.flush()
        record_audit("person.create", person, after={"first_name": first_name}, actor=actor)

    if TeamAssignment.query.filter_by(person_id=person.id, project_id=project.id).first():
        raise ValueError(f"{person.display_name} is already on this project's team.")

    assignment = TeamAssignment(
        person_id=person.id, project_id=project.id,
        assignment_type=assignment_type, role_label=role_label or None,
    )
    db.session.add(assignment)
    if expected_project_version is not None:
        if project.version != expected_project_version:
            raise ValueError("Concurrent update conflict; refresh and retry with the current project version.")
        project.version += 1
    record_audit(
        "team.enroll", assignment,
        after={"person": person.public_id, "project": project.public_id, "created_new_person": created_new_person},
        actor=actor,
    )
    db.session.commit()
    return person, assignment, created_new_person
