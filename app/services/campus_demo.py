"""Demo programs for the campus overview (app/services/overview.py).

The beta dataset (app/services/beta_seed.py) runs two programs on one
campus. The overview's whole point is four campuses side by side, so this
adds the other three -- Kengeri, Yeshwantpur and Bannerghatta -- and a
handful of ICC events and IGP programmes on every campus, each with a
to-do list whose items have real owners: a named student on that campus,
one of the beta accounts, or a team.

Additive and idempotent: nothing is deleted, a campus or a program that is
already there (matched by code) is left alone, and running it twice adds
nothing the second time. Dates are relative to the day it runs, so there is
always something happening now, something coming up and something late.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.database import db
from app.models.erp import Person, TeamAssignment, WorkTask, Wing
from app.models.project import Campus, Project
from app.models.user import User
from app.services.imports import _reference_data
from app.services.timeutil import to_utc

#: code -> (name). Central already exists as "CEN".
CAMPUSES = (
    ("BKC", "Bangalore Kengeri Campus"),
    ("BYC", "Bangalore Yeshwanthpur Campus"),
    ("BRC", "Bangalore Bannerghatta Road Campus"),
)

# An owner is "u:<username>" (a beta account), "p:<First Last>" (a student on
# that campus, created on first use), "t:<team>" (a team key from
# app/services/teams.py) or None (nobody yet).
#
# Each program: code, campus code, division, wing, title, start offset in
# days from today, length in days, status, venue, lead, actions. Each
# action: title, owner, due offset in days from the program's start, status.
PROGRAMS = (
    # ── Central ──────────────────────────────────────────────────────────
    ("ICC-2026-CEN-002", "CEN", "ICC", "CULTURALS", "Diwali Lights Night", 9, 1, "Planned",
     "Main Auditorium, Central Campus", "u:cultural1", (
         ("Book the main auditorium", "u:events2", -21, "Completed"),
         ("Confirm the rangoli and lamp-lighting teams", "u:cultural1", -10, "In Progress"),
         ("Design the event poster", "t:media", -12, "Completed"),
         ("Order diyas, flowers and sweets", "u:events1", -5, "Not Started"),
         ("Line up the dance and music acts", "u:cultural2", -6, "In Progress"),
         ("Send invites to exchange students", "u:usc", -7, "Not Started"),
         ("Get the money approved", "t:faculty", -8, "Not Started"),
     )),
    ("IGP-2026-CEN-002", "CEN", "IGP", None, "Winter Immersion: Kerala Backwaters", 40, 8, "Planned",
     "Alappuzha, Kerala", "u:igp1", (
         ("Confirm houseboat and homestay bookings", "u:igp1", -25, "In Progress"),
         ("Collect passports and visa copies", "u:igp2", -20, "Not Started"),
         ("Brief the student buddies", "p:Aisha Fernandes", -10, "Not Started"),
         ("Book train tickets for the group", "u:igp2", -30, "Completed"),
         ("Get travel insurance for everyone", "t:faculty", -14, "Not Started"),
     )),

    # ── Kengeri ──────────────────────────────────────────────────────────
    ("ICC-2026-BKC-001", "BKC", "ICC", "EVENTS", "International Food Fest", -1, 3, "Active",
     "Kengeri Campus Amphitheatre", "p:Rhea Thomas", (
         ("Get stall permissions from the campus office", "p:Rhea Thomas", -14, "Completed"),
         ("Confirm 12 country food stalls", "p:Karthik Rao", -7, "Completed"),
         ("Arrange gas cylinders and fire safety", "p:Karthik Rao", -3, "Completed"),
         ("Print stall menus and price cards", "t:media", -2, "In Progress"),
         ("Take photos and short videos on each day", "t:media", 2, "In Progress"),
         ("Count footfall at the gate", "p:Neha Joshi", 2, "Not Started"),
         ("Settle stall bills", "p:Rhea Thomas", 5, "Not Started"),
     )),
    ("ICC-2026-BKC-002", "BKC", "ICC", "EVENTS", "Campus Heritage Walk", 14, 1, "Planned",
     "Kengeri Campus to Bangalore Palace", "p:Neha Joshi", (
         ("Plan the walking route", "p:Neha Joshi", -10, "Completed"),
         ("Book the bus", "p:Karthik Rao", -7, "Not Started"),
         ("Find a heritage guide", "p:Neha Joshi", -6, "In Progress"),
         ("Collect sign-ups", "p:Rhea Thomas", -3, "Not Started"),
         ("Make the route map handout", "t:media", -4, "Not Started"),
     )),
    ("IGP-2026-BKC-001", "BKC", "IGP", None, "Karnataka Culture Immersion", 20, 7, "Planned",
     "Mysuru and Hampi", "u:igp2", (
         ("Fix the day-by-day plan", "u:igp2", -21, "Completed"),
         ("Book hotels in Mysuru and Hampi", "p:Fatima Sheikh", -14, "In Progress"),
         ("Hire a coach and driver", "p:Fatima Sheikh", -12, "Not Started"),
         ("Pair each visitor with a buddy", "p:Rhea Thomas", -7, "Not Started"),
         ("Send the packing list", "u:igp2", -5, "Not Started"),
         ("Get the money approved", "t:faculty", -15, "Not Started"),
     )),
    ("ICC-2026-BKC-003", "BKC", "ICC", "EVENTS", "Welcome Orientation for Exchange Students", -24, 1, "Active",
     "Kengeri Campus Seminar Hall", "p:Karthik Rao", (
         ("Book the seminar hall", "p:Karthik Rao", -14, "Completed"),
         ("Print welcome kits", "t:media", -3, "Completed"),
         ("Run the campus tour", "p:Neha Joshi", 0, "Completed"),
         ("Upload the attendance sheet", "p:Karthik Rao", 3, "Not Started"),
         ("Write the event report", "p:Rhea Thomas", 7, "Not Started"),
     )),

    # ── Yeshwantpur ──────────────────────────────────────────────────────
    ("ICC-2026-BYC-001", "BYC", "ICC", "EVENTS", "Global Games Day", -6, 1, "Active",
     "Yeshwantpur Campus Sports Ground", "p:Sameer Khan", (
         ("Book the sports ground", "p:Sameer Khan", -14, "Completed"),
         ("Borrow equipment from the sports office", "p:Ankit Gupta", -3, "Completed"),
         ("Arrange first aid on the ground", "p:Ankit Gupta", -1, "Completed"),
         ("Hand out prizes and certificates", "t:culturals", 2, "Not Started"),
         ("Share the photo album", "t:media", 3, "Not Started"),
         ("Return borrowed equipment", "p:Ankit Gupta", 2, "Not Started"),
         ("Write the event report", "p:Sameer Khan", 5, "Not Started"),
     )),
    ("ICC-2026-BYC-002", "BYC", "ICC", "CULTURALS", "Language Café", -30, 90, "Active",
     "Yeshwantpur Campus Café", "p:Lakshmi Iyer", (
         ("Set the weekly table schedule", "p:Lakshmi Iyer", -7, "Completed"),
         ("Find volunteer hosts for French, German and Japanese", "p:Lakshmi Iyer", -3, "Completed"),
         ("Put up posters in every block", "t:media", -2, "Completed"),
         ("Keep the sign-in sheet each week", "p:Ankit Gupta", 30, "In Progress"),
         ("Mid-term feedback survey", "p:Lakshmi Iyer", 35, "Not Started"),
         ("Find a Spanish host", None, 40, "Not Started"),
     )),
    ("IGP-2026-BYC-001", "BYC", "IGP", None, "Rural Outreach Programme: Mysuru", 30, 6, "Planned",
     "Villages near Mysuru", "u:igp1", (
         ("Agree activities with the partner NGO", "u:igp1", -20, "In Progress"),
         ("Collect consent forms", "p:Sameer Khan", -10, "Not Started"),
         ("Book the stay at the field centre", "p:Lakshmi Iyer", -15, "Not Started"),
         ("Brief students on safety", "t:faculty", -2, "Not Started"),
     )),

    # ── Bannerghatta ─────────────────────────────────────────────────────
    ("ICC-2026-BRC-001", "BRC", "ICC", "CULTURALS", "Cultural Exchange Evening", 7, 1, "Planned",
     "Bannerghatta Road Campus Open Air Theatre", "p:Maria Joseph", (
         ("Book the open air theatre", "p:Maria Joseph", -14, "Completed"),
         ("Collect performances from each country", "t:culturals", -5, "In Progress"),
         ("Arrange lights and sound", "p:Rohan Das", -3, "Not Started"),
         ("Design the invite and poster", "t:media", -8, "Late"),
         ("Plan dinner for performers", "p:Sana Ali", -2, "Not Started"),
     )),
    ("IGP-2026-BRC-001", "BRC", "IGP", None, "Wildlife and Sustainability Field School", 18, 6, "Planned",
     "Bannerghatta National Park", "u:igp2", (
         ("Get forest department permission", "u:igp2", -15, "In Progress"),
         ("Book the field station", "p:Rohan Das", -12, "Completed"),
         ("Line up the guest lectures", "p:Maria Joseph", -8, "Not Started"),
         ("Hire a coach for the week", "p:Rohan Das", -6, "Not Started"),
         ("Get the money approved", "t:faculty", -10, "Not Started"),
     )),
    ("ICC-2026-BRC-002", "BRC", "ICC", "EVENTS", "Buddy Mixer", -3, 1, "Active",
     "Bannerghatta Road Campus Lawn", "p:Sana Ali", (
         ("Pair new students with buddies", "p:Sana Ali", -7, "Completed"),
         ("Order snacks and drinks", "p:Rohan Das", -2, "Completed"),
         ("Run the ice-breaker games", "t:culturals", 0, "Completed"),
         ("Upload the attendance sheet", "p:Sana Ali", 1, "Not Started"),
         ("Post the photos", "t:media", 2, "In Progress"),
     )),
)


def _campuses():
    """Every campus by code, creating the three that are missing."""
    found, created = {}, 0
    central = Campus.query.filter_by(code="CEN").first()
    if central is not None:
        found["CEN"] = central
    for code, name in CAMPUSES:
        campus = Campus.query.filter_by(code=code).first() or Campus.query.filter_by(name=name).first()
        if campus is None:
            campus = Campus(code=code, name=name)
            db.session.add(campus)
            created += 1
        found[code] = campus
    db.session.flush()
    return found, created


def _due(day):
    return to_utc(datetime.combine(day, datetime.min.time()).replace(hour=17))


def seed_campus_demo(today: date | None = None) -> dict[str, int]:
    """Add the three other campuses and the demo programs. Safe to rerun."""
    today = today or date.today()
    year, _central, icc_type, igp_type, icc, igp, _events_wing = _reference_data()
    campuses, created = _campuses()
    wings = {wing.code: wing for wing in Wing.query.filter_by(operating_unit_id=icc.id).all()}
    accounts = {user.username: user for user in User.query.all()}
    people_cache: dict[tuple[str, int], Person] = {}

    def person(name, campus):
        key = (name, campus.id)
        if key in people_cache:
            return people_cache[key]
        first, _, last = name.partition(" ")
        email = f"{first}.{last}".lower().replace(" ", "") + "@christuniversity.in"
        found = Person.query.filter_by(primary_email=email).first()
        if found is None:
            found = Person(first_name=first, last_name=last or None, primary_email=email, campus_id=campus.id,
                           person_type="Student", consent_status="Recorded", consent_recorded_at=datetime.now(timezone.utc))
            db.session.add(found)
            db.session.flush()
        people_cache[key] = found
        return found

    def owner(ref, campus):
        """(person, team) for an owner reference."""
        if not ref:
            return None, None
        kind, _, value = ref.partition(":")
        if kind == "t":
            return None, value
        if kind == "u":
            user = accounts.get(value)
            return (user.person if user else None), None
        return person(value, campus), None

    added = {"campuses": created, "programs": 0, "actions": 0}
    for code, campus_code, division, wing_code, title, start_offset, length, status, venue, lead, actions in PROGRAMS:
        campus = campuses.get(campus_code)
        if campus is None or Project.query.filter_by(code=code).first() is not None:
            continue
        start = today + timedelta(days=start_offset)
        end = start + timedelta(days=max(length, 1) - 1)
        lead_person, _ = owner(lead, campus)
        project = Project(
            code=code, title=title, campus_id=campus.id,
            program_type_id=(icc_type if division == "ICC" else igp_type).id,
            academic_year_id=year.id,
            operating_unit_id=(icc if division == "ICC" else igp).id,
            wing_id=wings[wing_code].id if wing_code and wing_code in wings else None,
            owner_person_id=lead_person.id if lead_person else None,
            project_type="ICC event" if division == "ICC" else "IGP programme",
            category="Cultural" if wing_code == "CULTURALS" else ("Exchange" if division == "IGP" else "Operational"),
            status=status, start_date=start, end_date=end, venue=venue,
            description=f"{title} at {campus.name}.",
            publication_status="Private",
        )
        db.session.add(project)
        db.session.flush()
        added["programs"] += 1

        on_team = set()
        for action_title, action_owner, due_offset, action_status in actions:
            owner_person, team = owner(action_owner, campus)
            due_day = start + timedelta(days=due_offset)
            # "Late" in the table means an open item whose day has passed.
            stored = "Not Started" if action_status == "Late" else action_status
            if action_status == "Late" and due_day >= today:
                due_day = today - timedelta(days=2)
            db.session.add(WorkTask(
                project_id=project.id, title=action_title, status=stored,
                owner_person_id=owner_person.id if owner_person else None,
                assigned_team=team,
                accountable_person_id=lead_person.id if lead_person else None,
                priority="High" if due_offset < 0 else "Medium",
                due_at=_due(due_day),
                description=f"{action_title} for {title}.",
            ))
            added["actions"] += 1
            if owner_person is not None:
                on_team.add(owner_person.id)
        if lead_person is not None:
            on_team.add(lead_person.id)
        for person_id in on_team:
            db.session.add(TeamAssignment(
                person_id=person_id, project_id=project.id, academic_year_id=year.id,
                wing_id=project.wing_id, assignment_type="Project Team",
                role_label="Program lead" if lead_person and person_id == lead_person.id else "Organiser",
                recruitment_status="Selected", status="Active",
                starts_on=start - timedelta(days=30), ends_on=end + timedelta(days=14),
            ))
    db.session.commit()
    return added
