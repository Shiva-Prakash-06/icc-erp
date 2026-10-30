"""Create-and-enroll for participants without a registration number.

The database already permits a Person with no registration_number, but
enrollment and buddy-pairing forms required one anyway -- a confirmed
workflow defect (imports already accept email-or-registration-number). See
PLAN.md "IGP registration number" finding.
"""

from __future__ import annotations

import re

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


# ── Adding people to an event by the list ──────────────────────────────

#: The one "Job" a person has on an event (it replaced Assignment type +
#: Role, which asked the same question twice).
JOBS = ("Volunteer", "Buddy", "Student", "Guest", "Organiser")

_EMAIL = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+")
_HEADER_WORDS = {
    "name", "full name", "student name", "first name", "last name", "email", "e-mail", "email id",
    "registration number", "register number", "reg no", "reg. no.", "reg no.", "job", "role", "class", "s. no", "s.no",
}
_REG_NO = re.compile(r"^\d{5,}$|^[A-Z]{1,4}\d{4,}$", re.I)


def parse_people_list(text):
    """Read a pasted list -- one person per line, as typed or as copied
    from a spreadsheet (tab- or comma-separated). Each line may hold a
    name, an email, a registration number and a job, in any order.

    Returns ``[{"name", "email", "reg_no", "job", "line"}]``; lines with no
    name are returned with ``name`` empty so the caller can say which.
    """
    jobs = {job.lower(): job for job in JOBS}
    rows = []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"\t|,|;", line) if part.strip()]
        row = {"name": "", "email": None, "reg_no": None, "job": None, "line": number}
        rest = []
        for part in parts:
            if _EMAIL.fullmatch(part):
                row["email"] = part.lower()
            elif _REG_NO.match(part):
                row["reg_no"] = part.upper()
            elif part.lower() in jobs:
                row["job"] = jobs[part.lower()]
            else:
                rest.append(part)
        row["name"] = " ".join(rest)[:200]
        if not rows and parts and all(part.lower() in _HEADER_WORDS for part in parts):
            continue  # the column headings, copied along with the data
        rows.append(row)
    return rows


def find_or_make_person(project, row):
    person = None
    if row["email"]:
        person = Person.query.filter(db.func.lower(Person.primary_email) == row["email"]).first()
    if person is None and row["reg_no"]:
        person = Person.query.filter_by(registration_number=row["reg_no"]).first()
    if person is None:
        first, _, last = row["name"].partition(" ")
        person = Person(
            first_name=first or row["name"], last_name=last or None, primary_email=row["email"],
            registration_number=row["reg_no"], campus_id=project.campus_id, person_type="Student",
        )
        db.session.add(person)
        db.session.flush()
    return person


def enrol(project, person, job, actor):
    """Put ``person`` on the event as ``job``. Returns False if they were
    already on it (and puts them back if they had been removed)."""
    existing = TeamAssignment.query.filter_by(person_id=person.id, project_id=project.id).first()
    if existing is not None:
        if existing.status == "Active":
            return False
        existing.status = "Active"
        existing.role_label = job or existing.role_label
        return True
    assignment = TeamAssignment(
        person_id=person.id, project_id=project.id, assignment_type="Project Team",
        role_label=job or "Volunteer", academic_year_id=project.academic_year_id,
        user_id=person.user_account.id if person.user_account else None,
    )
    db.session.add(assignment)
    db.session.flush()
    record_audit("team.enroll", assignment, after={"person": person.public_id, "project": project.public_id}, actor=actor)
    return True
