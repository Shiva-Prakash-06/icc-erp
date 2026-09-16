"""Deterministic beta-testing dataset.

Wipes every application row and rebuilds a small, fully connected world:
fourteen sign-in accounts covering the ICC/IGP leadership roles, and exactly
two projects -- "Coffee Meet & Greet" (ICC, Events wing) and "Summer School
Exchange Program" (IGP).

Why this exists alongside ``seed-acceptance`` and ``provision-uat``: those
build throwaway fixtures for automated browser tests and for a one-off
acceptance pass, with random one-time passwords and first-login resets. Beta
testers need stable, memorable credentials and data that hangs together well
enough to explore, so the two cannot share an implementation.

Every foreign key points at a row this module also creates. Nothing here
invents a reference that the reader cannot follow: a session's owner is on the
project team, an attendance row's person is a participant, a contribution's
approver actually holds ``approve`` on that project's scope, and a buddy pair
links a real buddy Person to a real exchange-student Person who is also a
recorded participant.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import inspect as sa_inspect

from app.database import db
from app.models.erp import (
    AuditEvent,
    BudgetLine,
    ChecklistTemplate,
    ChecklistTemplateItem,
    DocumentRecord,
    FeedbackForm,
    FeedbackResponse,
    OperationalRequest,
    OperatingUnit,
    PartnerInstitution,
    Person,
    ProjectComponent,
    ProjectSession,
    ReportSnapshot,
    RoleAssignment,
    SessionAttendance,
    TeamAssignment,
    Wing,
    WorkTask,
)
from app.models.production import (
    AggregateAttendance,
    ApprovalEvent,
    Cohort,
    ContributionRecord,
    DocumentRequirement,
    GovernanceTerm,
    Notification,
    NotificationPreference,
    Position,
    ProjectRisk,
    RecruitmentApplication,
    TaskStatusEvent,
)
from app.models.project import BuddyAssignment, BuddyLog, Project
from app.models.user import User
from app.services.imports import _reference_data, seed_icc_checklist_template
from app.services.operations import instantiate_checklist
from app.services.timeutil import to_utc

BETA_PASSWORD = "123"

# Wall-clock reference points. Coffee Meet & Greet has already been delivered
# and is in closure; Summer School ran over the mid-year break and is also in
# closure. Both therefore carry real history *and* leave decisions pending, so
# a tester signing in has something to look at and something to act on.
EVENT_DAY = date(2026, 9, 10)
SUMMER_START = date(2026, 6, 15)
SUMMER_END = date(2026, 7, 25)


# --------------------------------------------------------------------------
# Reset
# --------------------------------------------------------------------------

def reset_all_data() -> dict[str, int]:
    """Delete every application row, leaving schema and migration state alone.

    Ordered by SQLAlchemy's own topological sort, reversed, so a child table is
    always emptied before its parent and no foreign key is ever violated. The
    Alembic version table is not part of ``db.metadata``, so it is untouched --
    the database stays at head and must not be re-migrated afterwards.
    """
    # Only tables the database actually has: `db.metadata` also carries models
    # with no corresponding migration (legacy_migration_reconciliation), and
    # deleting from one of those aborts the whole reset.
    present = set(sa_inspect(db.engine).get_table_names())
    deleted: dict[str, int] = {}
    for table in reversed(db.metadata.sorted_tables):
        if table.name not in present:
            continue
        result = db.session.execute(table.delete())
        if result.rowcount:
            deleted[table.name] = result.rowcount
    db.session.commit()
    return deleted


# --------------------------------------------------------------------------
# People and accounts
# --------------------------------------------------------------------------

# username -> (first, last, role label, role code, scope, person type)
# `scope` is resolved against the reference data below:
#   "platform"  -> no scope fields at all (sees every project)
#   "icc"       -> ICC operating unit, no wing (sees every ICC project)
#   "icc:WING"  -> ICC operating unit + that wing only
#   "igp"       -> IGP operating unit
USER_ROSTER: list[tuple[str, str, str, str, str, str, str]] = [
    ("faculty1", "Anita", "Rao", "OIA Faculty Administrator", "OIA_FACULTY_ADMINISTRATOR", "platform", "Faculty / Staff"),
    ("faculty2", "Joseph", "Mathew", "OIA Faculty Administrator", "OIA_FACULTY_ADMINISTRATOR", "platform", "Faculty / Staff"),
    ("faculty3", "Meera", "Krishnan", "OIA Faculty Administrator", "OIA_FACULTY_ADMINISTRATOR", "platform", "Faculty / Staff"),
    ("faculty4", "Samuel", "George", "OIA Faculty Administrator", "OIA_FACULTY_ADMINISTRATOR", "platform", "Faculty / Staff"),
    ("usc", "Ananya", "Sharma", "ICC Secretary / USC", "ICC_SECRETARY_USC", "icc", "Student"),
    ("secretary", "Rohit", "Menon", "ICC Secretary / USC", "ICC_SECRETARY_USC", "icc", "Student"),
    ("events1", "Kavya", "Nair", "ICC Events Head", "ICC_EVENTS_HEAD", "icc:EVENTS", "Student"),
    ("events2", "Arjun", "Pillai", "ICC Events Head", "ICC_EVENTS_HEAD", "icc:EVENTS", "Student"),
    ("media1", "Sneha", "Iyer", "ICC Media Head", "ICC_MEDIA_HEAD", "icc:MEDIA", "Student"),
    ("media2", "Nikhil", "Verma", "ICC Media Head", "ICC_MEDIA_HEAD", "icc:MEDIA", "Student"),
    ("cultural1", "Divya", "Reddy", "ICC Culturals Head", "ICC_CULTURALS_HEAD", "icc:CULTURALS", "Student"),
    ("cultural2", "Aditya", "Kulkarni", "ICC Culturals Head", "ICC_CULTURALS_HEAD", "icc:CULTURALS", "Student"),
    ("igp1", "Priya", "Desai", "IGP Head", "IGP_HEAD", "igp", "Student"),
    ("igp2", "Vikram", "Shetty", "IGP Head", "IGP_HEAD", "igp", "Student"),
]

# Roles allowed to hold restricted-reference access (mirrors roles.py).
SENSITIVE_ROLES = {"OIA_FACULTY_ADMINISTRATOR", "IGP_HEAD"}


def _person(first, last, person_type, campus_id, *, email=None, **extra) -> Person:
    person = Person(
        first_name=first,
        last_name=last,
        primary_email=email or f"{first}.{last}".lower().replace(" ", "") + "@christuniversity.in",
        campus_id=campus_id,
        person_type=person_type,
        consent_status="Recorded",
        consent_recorded_at=datetime.now(timezone.utc),
        **extra,
    )
    db.session.add(person)
    return person


def _create_accounts(year, campus, icc, igp, wings) -> dict[str, User]:
    """Create the fourteen beta accounts, each with a linked Person and one
    active, correctly scoped RoleAssignment."""
    users: dict[str, User] = {}
    for username, first, last, label, code, scope, person_type in USER_ROSTER:
        person = _person(first, last, person_type, campus.id,
                         email=f"{username}@christuniversity.in")
        db.session.flush()
        user = User(
            username=username,
            email=person.primary_email,
            role=label,
            preferred_role=label,
            status="Approved",
            campus_id=campus.id,
            person_id=person.id,
            # Beta testers share a known password on purpose; forcing a reset
            # would immediately push them into the 12-character policy.
            needs_password_reset=False,
            password_changed_at=datetime.now(timezone.utc),
        )
        user.set_password(BETA_PASSWORD)
        db.session.add(user)
        db.session.flush()

        unit = wing = None
        campus_scope = campus.id
        academic_year_scope = year.id
        if scope == "platform":
            # OIA faculty administrators are deliberately unscoped: an
            # assignment with no scope fields is the only thing that satisfies
            # a project-less permission check for non-global permissions.
            campus_scope = academic_year_scope = None
        elif scope == "icc":
            unit = icc
        elif scope.startswith("icc:"):
            unit, wing = icc, wings[scope.split(":", 1)[1]]
        elif scope == "igp":
            unit = igp

        position = Position.query.filter_by(code=code).first()
        db.session.add(RoleAssignment(
            user_id=user.id,
            role_code=code,
            campus_id=campus_scope,
            operating_unit_id=getattr(unit, "id", None),
            wing_id=getattr(wing, "id", None),
            academic_year_id=academic_year_scope,
            position_id=getattr(position, "id", None),
            is_active=True,
            starts_on=year.start_date,
            ends_on=year.end_date,
            assignment_reason="Beta testing roster",
            can_view_sensitive_links=code in SENSITIVE_ROLES,
        ))
        db.session.add(NotificationPreference(
            user_id=user.id, event_type="approval_pending",
            email_enabled=False, in_app_enabled=True,
        ))
        users[username] = user
    db.session.flush()
    return users


# --------------------------------------------------------------------------
# Coffee Meet & Greet (ICC, Events wing)
# --------------------------------------------------------------------------

def _seed_coffee_meet(year, campus, icc_type, icc, wings, users) -> Project:
    owner = users["events1"]
    project = Project(
        code="ICC-2026-CEN-001",
        title="Coffee Meet & Greet",
        description=(
            "Informal welcome mixer pairing incoming international students with "
            "ICC volunteers over coffee, with a short cultural showcase to close."
        ),
        objectives=(
            "Give every incoming exchange student at least one familiar face on campus "
            "before formal classes begin."
        ),
        target_audience="Incoming exchange students, ICC volunteers and wing members",
        campus_id=campus.id,
        program_type_id=icc_type.id,
        academic_year_id=year.id,
        operating_unit_id=icc.id,
        wing_id=wings["EVENTS"].id,
        owner_person_id=owner.person_id,
        project_type="ICC event",
        category="Operational",
        status="Closing",
        start_date=EVENT_DAY,
        end_date=EVENT_DAY,
        venue="Central Block Quadrangle, Bangalore Central Campus",
        capacity=120,
        expected_reach=120,
        actual_reach=96,
        publication_status="Private",
    )
    db.session.add(project)
    db.session.flush()

    # Components make the cross-wing split explicit: Media and Culturals each
    # own a slice of an event that the Events wing runs.
    components = {}
    for code, title, ctype, seq, owner_user in (
        ("LOGISTICS", "Venue & Hospitality", "Logistics", 1, users["events1"]),
        ("PUBLICITY", "Publicity & Media Coverage", "Communications", 2, users["media1"]),
        ("SHOWCASE", "Cultural Showcase", "Programme", 3, users["cultural1"]),
    ):
        component = ProjectComponent(
            project_id=project.id, code=code, title=title,
            component_type=ctype, sequence=seq,
            owner_person_id=owner_user.person_id,
            description=f"{title} workstream for {project.title}.",
        )
        db.session.add(component)
        components[code] = component
    db.session.flush()

    sessions = {}
    for code, title, stype, comp, s_hour, s_min, e_hour, e_min, owner_user, capacity in (
        ("CMG-REG", "Registration & Welcome Desk", "Registration", "LOGISTICS", 9, 0, 9, 45, users["events2"], 120),
        ("CMG-MIXER", "Coffee Meet & Greet Mixer", "Event", "LOGISTICS", 10, 0, 12, 0, users["events1"], 120),
        ("CMG-SHOWCASE", "Cultural Showcase", "Performance", "SHOWCASE", 12, 0, 12, 45, users["cultural1"], 120),
        ("CMG-DEBRIEF", "Organising Team Debrief", "Meeting", "LOGISTICS", 16, 0, 17, 0, users["events1"], 25),
    ):
        session = ProjectSession(
            project_id=project.id,
            component_id=components[comp].id,
            code=code, title=title, session_type=stype,
            starts_at=to_utc(datetime.combine(EVENT_DAY, datetime.min.time()).replace(hour=s_hour, minute=s_min)),
            ends_at=to_utc(datetime.combine(EVENT_DAY, datetime.min.time()).replace(hour=e_hour, minute=e_min)),
            venue=project.venue,
            owner_person_id=owner_user.person_id,
            capacity=capacity,
            participant_group="Open to all registered attendees",
        )
        db.session.add(session)
        sessions[code] = session
    db.session.flush()
    return project, components, sessions


def _coffee_meet_people(project, campus, wings, users, components, sessions):
    """Volunteers, attendees, team rows, attendance and contributions."""
    # Every leadership account that has a stake in this event is on the team,
    # which is also what grants the Media/Culturals heads view access: their
    # RoleAssignment is scoped to their own wing, not to the Events wing.
    for username, assignment_type, role_label, wing_code in (
        ("events1", "Project Team", "Event Lead", "EVENTS"),
        ("events2", "Project Team", "Logistics Coordinator", "EVENTS"),
        ("media1", "Project Team", "Media Coverage Lead", "MEDIA"),
        ("media2", "Project Team", "Photography", "MEDIA"),
        ("cultural1", "Project Team", "Showcase Curator", "CULTURALS"),
        ("cultural2", "Project Team", "Showcase Compere", "CULTURALS"),
        ("usc", "Oversight", "ICC Secretary / USC", None),
        ("faculty1", "Oversight", "Faculty Advisor", None),
    ):
        db.session.add(TeamAssignment(
            person_id=users[username].person_id,
            user_id=users[username].id,
            project_id=project.id,
            wing_id=wings[wing_code].id if wing_code else None,
            academic_year_id=project.academic_year_id,
            assignment_type=assignment_type,
            role_label=role_label,
            recruitment_status="Selected",
            status="Active",
            starts_on=project.start_date - timedelta(days=21),
            ends_on=project.end_date + timedelta(days=30),
        ))

    # The Media and Culturals heads own a component of an event that sits in the
    # Events wing, so their standing wing-scoped assignment cannot reach it --
    # it would grant them view access through the team row above and nothing
    # more. A second, project-scoped assignment is exactly what RoleAssignment's
    # project_id is for: a delegated stake in one cross-wing event, granted by
    # the Events head, and expiring with the project rather than the term.
    for username in ("media1", "media2", "cultural1", "cultural2"):
        db.session.add(RoleAssignment(
            user_id=users[username].id,
            role_code=RoleAssignment.query.filter_by(
                user_id=users[username].id, is_active=True,
            ).first().role_code,
            project_id=project.id,
            campus_id=project.campus_id,
            operating_unit_id=project.operating_unit_id,
            academic_year_id=project.academic_year_id,
            is_active=True,
            starts_on=project.start_date - timedelta(days=30),
            ends_on=project.end_date + timedelta(days=45),
            delegated_by_id=users["events1"].id,
            assignment_reason=f"Owns a {project.title} workstream for their wing",
        ))

    # Volunteers without sign-in accounts -- the roster a head actually manages.
    volunteers = []
    for first, last in (("Ishaan", "Bhat"), ("Tara", "Lobo"), ("Zoya", "Khan"), ("Rahul", "Dsouza")):
        person = _person(first, last, "Student", campus.id)
        db.session.flush()
        volunteers.append(person)
        db.session.add(TeamAssignment(
            person_id=person.id, project_id=project.id,
            wing_id=wings["EVENTS"].id,
            academic_year_id=project.academic_year_id,
            assignment_type="Volunteer", role_label="Event Volunteer",
            recruitment_status="Selected", status="Active",
            starts_on=project.start_date - timedelta(days=14),
            ends_on=project.end_date + timedelta(days=7),
        ))
        # Each volunteer was recruited through the application workflow, so the
        # application that produced the assignment exists too.
        db.session.add(RecruitmentApplication(
            person_id=person.id, project_id=project.id,
            desired_role="Event Volunteer",
            skills_snapshot="Hospitality, crowd handling",
            availability_snapshot="Full event day",
            statement=f"{first} volunteered to help run the welcome desk and mixer.",
            decision="Selected", decision_reason="Available for the full event day",
            decided_by_id=users["events1"].id,
            decided_at=datetime.now(timezone.utc) - timedelta(days=25),
            consent_status="Recorded",
        ))

    # Attendee cohort: incoming exchange students the event exists for.
    attendees = []
    for first, last, nationality in (
        ("Lena", "Fischer", "Germany"),
        ("Marco", "Rossi", "Italy"),
        ("Yuki", "Tanaka", "Japan"),
        ("Chloe", "Dubois", "France"),
        ("Diego", "Alvarez", "Spain"),
    ):
        person = _person(first, last, "Exchange Student", campus.id, nationality_country=nationality)
        db.session.flush()
        attendees.append(person)
        db.session.add(TeamAssignment(
            person_id=person.id, project_id=project.id,
            academic_year_id=project.academic_year_id,
            assignment_type="Participant", role_label="Attendee",
            nationality=nationality,
            recruitment_status="Selected", status="Active",
            starts_on=project.start_date, ends_on=project.end_date,
        ))

    # Named attendance for the mixer: the people above, nobody else.
    for person in attendees:
        db.session.add(SessionAttendance(
            session_id=sessions["CMG-MIXER"].id, person_id=person.id,
            status="Present", verified_by_id=users["events2"].id,
            verified_at=to_utc(datetime.combine(EVENT_DAY, datetime.min.time()).replace(hour=12, minute=15)),
        ))
    for person in volunteers:
        db.session.add(SessionAttendance(
            session_id=sessions["CMG-REG"].id, person_id=person.id,
            status="Present", verified_by_id=users["events2"].id,
            verified_at=to_utc(datetime.combine(EVENT_DAY, datetime.min.time()).replace(hour=9, minute=50)),
        ))
    db.session.add(SessionAttendance(
        session_id=sessions["CMG-DEBRIEF"].id, person_id=users["events1"].person_id,
        status="Present", verified_by_id=users["events1"].id,
        verified_at=to_utc(datetime.combine(EVENT_DAY, datetime.min.time()).replace(hour=17, minute=0)),
    ))

    # Headcount for the walk-in crowd that was never individually registered.
    # actual_reach (96) = 5 named attendees + 4 volunteers + 87 counted walk-ins.
    db.session.add(AggregateAttendance(
        session_id=sessions["CMG-MIXER"].id, category="Walk-in attendees",
        count=87, verified_by_id=users["events1"].id,
        verified_at=to_utc(datetime.combine(EVENT_DAY, datetime.min.time()).replace(hour=12, minute=30)),
        source_note="Counted at the registration desk against issued badges.",
    ))

    # Volunteer hours: one approved, one still pending a head's decision.
    db.session.add(ContributionRecord(
        project_id=project.id, person_id=volunteers[0].id, wing_id=wings["EVENTS"].id,
        activity_type="Event logistics", description="Ran the welcome desk and badge issue.",
        duration_hours=4, approval_status="Approved",
        approved_by_id=users["events1"].id,
        approved_at=datetime.now(timezone.utc) - timedelta(days=4),
        evidence_reference="Registration desk roster",
    ))
    db.session.add(ContributionRecord(
        project_id=project.id, person_id=volunteers[1].id, wing_id=wings["EVENTS"].id,
        activity_type="Event logistics", description="Coordinated refreshments and table reset.",
        duration_hours=3, approval_status="Pending",
    ))
    db.session.add(ContributionRecord(
        project_id=project.id, person_id=users["media2"].person_id, wing_id=wings["MEDIA"].id,
        activity_type="Media coverage", description="Event photography and social media reel.",
        duration_hours=5, approval_status="Pending",
    ))
    return volunteers, attendees


def _coffee_meet_operations(project, components, users, volunteers, attendees):
    """Tasks, documents, budget, requests, feedback, risk and reporting."""
    tasks = {}
    for code, title, comp, status, owner_user, mandatory, due_offset in (
        ("VENUE", "Confirm quadrangle booking with Estate Office", "LOGISTICS", "Completed", users["events2"], True, -30),
        ("POSTER", "Design and circulate event poster", "PUBLICITY", "Completed", users["media1"], True, -20),
        ("ROSTER", "Finalise volunteer roster", "LOGISTICS", "Completed", users["events1"], True, -10),
        ("SHOWCASE", "Confirm showcase performers and running order", "SHOWCASE", "Completed", users["cultural1"], False, -7),
        ("REPORT", "Submit post-event report", "LOGISTICS", "Submitted", users["events1"], True, 7),
        ("REEL", "Publish post-event highlight reel", "PUBLICITY", "In Progress", users["media2"], False, 10),
    ):
        task = WorkTask(
            project_id=project.id, component_id=components[comp].id,
            title=title, status=status, priority="High" if mandatory else "Medium",
            owner_person_id=owner_user.person_id,
            accountable_person_id=users["events1"].person_id,
            mandatory_for_closure=mandatory,
            due_at=to_utc(datetime.combine(EVENT_DAY + timedelta(days=due_offset), datetime.min.time()).replace(hour=17)),
            description=f"{title} for {project.title}.",
        )
        db.session.add(task)
        db.session.flush()
        tasks[code] = task
        # A status that is not the model default got there by a transition, so
        # the transition is recorded rather than implied.
        if status != "Not Started":
            db.session.add(TaskStatusEvent(
                task_id=task.id, previous_status="In Progress" if status != "In Progress" else "Not Started",
                new_status=status, actor_user_id=owner_user.id,
                comment=f"Marked {status.lower()} by {owner_user.username}.",
                occurred_at=datetime.now(timezone.utc) - timedelta(days=max(1, -due_offset)),
            ))

    for category, title, classification, mandatory, due_offset in (
        ("Approval", "Event approval note", "Internal", True, -30),
        ("Report", "Post-event report", "Internal", True, 7),
        ("Attendance", "Attendance record", "Restricted", True, 3),
        ("Media", "Event photograph set", "Public", False, 10),
    ):
        db.session.add(DocumentRequirement(
            project_id=project.id, category=category, title=title,
            classification=classification, mandatory_for_closure=mandatory,
            owner_person_id=users["events1"].person_id,
            due_at=to_utc(datetime.combine(EVENT_DAY + timedelta(days=due_offset), datetime.min.time()).replace(hour=17)),
            source_template_code="ICC-EVENT-STANDARD",
        ))

    for category, title, status, classification, owner_user, approved in (
        ("Approval", "Event approval note", "Approved", "Internal", users["events1"], True),
        ("Report", "Post-event report", "Submitted", "Internal", users["events1"], False),
        ("Attendance", "Attendance record", "Submitted", "Restricted", users["events2"], False),
        ("Media", "Event photograph set", "Submitted", "Public", users["media1"], False),
    ):
        db.session.add(DocumentRecord(
            project_id=project.id, category=category, title=title,
            version_label="1", status=status,
            permission_classification=classification,
            owner_person_id=owner_user.person_id,
            uploaded_by_id=owner_user.id,
            approved_by_id=users["faculty1"].id if approved else None,
            approved_at=datetime.now(timezone.utc) - timedelta(days=30) if approved else None,
            mandatory_for_closure=category in {"Approval", "Report", "Attendance"},
            drive_validation_status="Pending",
        ))

    for category, description, estimated, approved_amount, actual, status in (
        ("Hospitality", "Coffee, tea and snacks for 120", 18000, 18000, 16450, "Approved"),
        ("Publicity", "Poster printing and standees", 4500, 4500, 4500, "Approved"),
        ("Logistics", "Table, chair and PA hire", 7000, 7000, 6800, "Approved"),
        ("Culturals", "Showcase costume and prop hire", 5000, None, None, "Submitted"),
    ):
        db.session.add(BudgetLine(
            project_id=project.id, category=category, description=description,
            estimated_amount=estimated, approved_amount=approved_amount,
            committed_amount=approved_amount, actual_amount=actual,
            status=status, currency="INR",
            official_reference=f"ICC/2026/{category[:3].upper()}/001" if status == "Approved" else None,
        ))

    db.session.add(OperationalRequest(
        project_id=project.id, request_type="Equipment",
        title="PA system and two cordless microphones",
        details="Required for the showcase segment between 12:00 and 12:45.",
        amount=3500, status="Approved",
        owner_person_id=users["events2"].person_id,
        created_by_id=users["events2"].id, submitted_by_id=users["events2"].id,
        approver_id=users["events1"].id,
        decision_comment="Approved against the logistics line.",
        official_reference="ICC/2026/OPS/014",
    ))
    db.session.add(OperationalRequest(
        project_id=project.id, request_type="Reimbursement",
        title="Reimbursement for additional refreshments",
        details="Walk-in numbers exceeded the catered count by roughly 30 people.",
        amount=2400, status="Submitted",
        owner_person_id=users["events2"].person_id,
        created_by_id=users["events2"].id, submitted_by_id=users["events2"].id,
    ))

    form = FeedbackForm(
        project_id=project.id, title="Coffee Meet & Greet feedback",
        response_policy="One response", is_anonymous=False,
        questions_json=[
            {"key": "rating", "type": "scale", "min": 1, "max": 5, "label": "Overall, how was the event?"},
            {"key": "met_someone", "type": "choice", "options": ["Yes", "No"], "label": "Did you meet someone new?"},
            {"key": "comments", "type": "text", "label": "Anything we should change next time?"},
        ],
        is_open=True,
        opens_at=to_utc(datetime.combine(EVENT_DAY, datetime.min.time()).replace(hour=13)),
        closes_at=to_utc(datetime.combine(EVENT_DAY + timedelta(days=21), datetime.min.time()).replace(hour=23, minute=59)),
    )
    db.session.add(form)
    db.session.flush()
    for person, rating, met, comment, moderation in (
        (attendees[0], 5, "Yes", "Loved it -- met three people from my hostel block.", "Approved"),
        (attendees[1], 4, "Yes", "Good, but the coffee queue was long at the start.", "Approved"),
        (attendees[2], 5, "Yes", "The cultural showcase was the highlight.", "Pending"),
        (attendees[3], 3, "No", "Hard to hear people over the music during the mixer.", "Pending"),
    ):
        db.session.add(FeedbackResponse(
            form_id=form.id, person_id=person.id,
            answers_json={"rating": rating, "met_someone": met, "comments": comment},
            publication_consent=moderation == "Approved",
            moderation_status=moderation,
            response_key_hash=f"cmg-{person.id}",
        ))

    db.session.add(ProjectRisk(
        project_id=project.id, title="Walk-in numbers exceed catering",
        description="Registration is open, so attendance can overshoot the catered count.",
        likelihood="High", impact="Low",
        mitigation="Cater to 120 and keep a reimbursement route open for a top-up order.",
        owner_person_id=users["events2"].person_id,
        status="Realised", is_critical=False,
    ))
    db.session.add(ProjectRisk(
        project_id=project.id, title="Outdoor venue is weather dependent",
        description="The quadrangle has no cover; September rain would force a move indoors.",
        likelihood="Medium", impact="Medium",
        mitigation="Hold Room 301 as a standby until the morning of the event.",
        owner_person_id=users["events1"].person_id,
        status="Closed", is_critical=False,
    ))

    snapshot = ReportSnapshot(
        project_id=project.id, report_type="Project Operational Report",
        title="Coffee Meet & Greet - operational report",
        filters_json={"project": project.code, "academic_year": "2026-2027"},
        snapshot_json={
            "project": project.code,
            "title": project.title,
            "expected_reach": project.expected_reach,
            "actual_reach": project.actual_reach,
            "sessions": 4,
            "named_attendance": len(attendees) + len(volunteers),
            "aggregate_attendance": 87,
            "budget_estimated": 34500,
            "budget_actual": 27750,
        },
        source_references=[project.public_id],
        approval_status="Submitted", publication_status="Unpublished",
        generated_by_id=users["events1"].id,
    )
    db.session.add(snapshot)
    return tasks


# --------------------------------------------------------------------------
# Summer School Exchange Program (IGP)
# --------------------------------------------------------------------------

def _seed_summer_school(year, campus, igp_type, igp, users):
    partner = PartnerInstitution(
        code="UNI-HEID", name="Heidelberg University", country="Germany",
        primary_contact_name="Dr. Klara Weiss",
        primary_contact_email="klara.weiss@partner.example",
    )
    db.session.add(partner)
    db.session.flush()

    owner = users["igp1"]
    project = Project(
        code="IGP-2026-CEN-001",
        title="Summer School Exchange Program",
        description=(
            "Six-week inbound summer school for partner-university students, combining "
            "coursework, cultural immersion and a buddy pairing with a host student."
        ),
        objectives=(
            "Deliver an academically credited immersion term and return every participant "
            "home with a completed transcript and mobility report."
        ),
        target_audience="Inbound exchange students from partner universities",
        campus_id=campus.id,
        program_type_id=igp_type.id,
        academic_year_id=year.id,
        operating_unit_id=igp.id,
        partner_institution_id=partner.id,
        owner_person_id=owner.person_id,
        project_type="IGP inbound program",
        category="Academic",
        status="Closing",
        start_date=SUMMER_START,
        end_date=SUMMER_END,
        venue="Bangalore Central Campus",
        capacity=24,
        expected_reach=24,
        actual_reach=18,
        publication_status="Private",
    )
    db.session.add(project)
    db.session.flush()

    cohort = Cohort(
        code="SS-2026-A", name="Summer School 2026 Cohort A",
        partner_institution_id=partner.id, project_id=project.id,
        starts_on=SUMMER_START, ends_on=SUMMER_END,
        expected_participants=24, status="Completed",
    )
    db.session.add(cohort)
    db.session.flush()

    sessions = {}
    for code, title, stype, day_offset, s_hour, e_hour in (
        ("SS-ORIENT", "Orientation & Welcome", "Orientation", 0, 9, 13),
        ("SS-IMMERSION", "Cultural Immersion Week", "Workshop Series", 7, 9, 17),
        ("SS-EXCURSION", "Campus & City Excursion", "Excursion", 21, 9, 18),
        ("SS-CLOSING", "Closing Ceremony & Certification", "Ceremony", 40, 15, 18),
    ):
        day = SUMMER_START + timedelta(days=day_offset)
        session = ProjectSession(
            project_id=project.id, code=code, title=title, session_type=stype,
            starts_at=to_utc(datetime.combine(day, datetime.min.time()).replace(hour=s_hour)),
            ends_at=to_utc(datetime.combine(day, datetime.min.time()).replace(hour=e_hour)),
            venue=project.venue, owner_person_id=users["igp1"].person_id,
            capacity=24, programme_sequence=len(sessions) + 1,
            participant_group="Summer School 2026 Cohort A",
        )
        db.session.add(session)
        sessions[code] = session
    db.session.flush()
    return project, partner, cohort, sessions


def _summer_school_people(project, cohort, campus, users, sessions):
    for username, assignment_type, role_label in (
        ("igp1", "Project Team", "Program Director"),
        ("igp2", "Project Team", "Program Coordinator"),
        ("faculty2", "Oversight", "Faculty Advisor"),
        ("faculty3", "Oversight", "Academic Coordinator"),
    ):
        db.session.add(TeamAssignment(
            person_id=users[username].person_id, user_id=users[username].id,
            project_id=project.id, academic_year_id=project.academic_year_id,
            assignment_type=assignment_type, role_label=role_label,
            recruitment_status="Selected", status="Active",
            starts_on=project.start_date - timedelta(days=60),
            ends_on=project.end_date + timedelta(days=45),
        ))

    # Six inbound participants, each paired with a host buddy.
    participants = []
    for first, last, nationality in (
        ("Jonas", "Weber", "Germany"),
        ("Emilia", "Schmitt", "Germany"),
        ("Noah", "Braun", "Germany"),
        ("Mia", "Hoffmann", "Germany"),
        ("Felix", "Wagner", "Germany"),
        ("Hannah", "Koch", "Germany"),
    ):
        person = _person(first, last, "Exchange Student", campus.id,
                         nationality_country=nationality,
                         privacy_classification="Restricted")
        db.session.flush()
        participants.append(person)
        db.session.add(TeamAssignment(
            person_id=person.id, project_id=project.id, cohort_id=cohort.id,
            academic_year_id=project.academic_year_id,
            assignment_type="Participant", role_label="Exchange Student",
            nationality=nationality, recruitment_status="Selected", status="Active",
            starts_on=project.start_date, ends_on=project.end_date,
        ))

    buddies = []
    for first, last in (
        ("Sanjay", "Hegde"), ("Fatima", "Sheikh"), ("Neha", "Bhat"),
        ("Karan", "Malhotra"), ("Lakshmi", "Iyengar"), ("Imran", "Qureshi"),
    ):
        person = _person(first, last, "Student", campus.id)
        db.session.flush()
        buddies.append(person)
        db.session.add(TeamAssignment(
            person_id=person.id, project_id=project.id,
            academic_year_id=project.academic_year_id,
            assignment_type="Buddy", role_label="Host Buddy",
            recruitment_status="Selected", status="Active",
            starts_on=project.start_date, ends_on=project.end_date,
        ))
        db.session.add(RecruitmentApplication(
            person_id=person.id, project_id=project.id,
            desired_role="Host Buddy",
            skills_snapshot="Campus orientation, conversational German",
            availability_snapshot="Weekday evenings and weekends",
            statement=f"{first} applied to host an inbound summer school student.",
            decision="Selected", decision_reason="Matched on language and availability",
            decided_by_id=users["igp2"].id,
            decided_at=datetime.now(timezone.utc) - timedelta(days=120),
            consent_status="Recorded",
        ))

    # One-to-one pairing, buddy <-> participant, both real Person rows.
    for index, (buddy, participant) in enumerate(zip(buddies, participants)):
        pairing = BuddyAssignment(
            project_id=project.id,
            buddy_person_id=buddy.id,
            exchange_student_person_id=participant.id,
            start_date=project.start_date, end_date=project.end_date,
            status="Completed", assignment_type="One-to-one",
        )
        db.session.add(pairing)
        db.session.flush()
        # Two logs each: one verified, one still awaiting verification, so the
        # IGP heads have a real queue.
        db.session.add(BuddyLog(
            buddy_assignment_id=pairing.id,
            activity_date=project.start_date + timedelta(days=2),
            description="Campus orientation walk and SIM card setup.",
            duration_hours=2, status="Verified",
            verified_by_id=users["igp2"].id,
            verified_at=datetime.now(timezone.utc) - timedelta(days=80),
        ))
        db.session.add(BuddyLog(
            buddy_assignment_id=pairing.id,
            activity_date=project.start_date + timedelta(days=18),
            description="Weekend city excursion and food trail.",
            duration_hours=5, status="Pending",
            concern_level="None" if index % 3 else "Low",
        ))

    # Attendance for the two sessions where a register was actually taken.
    for code, absent_index in (("SS-ORIENT", None), ("SS-CLOSING", 4)):
        for index, person in enumerate(participants):
            db.session.add(SessionAttendance(
                session_id=sessions[code].id, person_id=person.id,
                status="Absent" if index == absent_index else "Present",
                verified_by_id=users["igp2"].id,
                verified_at=datetime.now(timezone.utc) - timedelta(days=70),
            ))
    db.session.add(AggregateAttendance(
        session_id=sessions["SS-IMMERSION"].id, category="Workshop participants",
        count=18, verified_by_id=users["igp1"].id,
        verified_at=datetime.now(timezone.utc) - timedelta(days=75),
        source_note="Daily workshop register totalled across the immersion week.",
    ))
    return participants, buddies


def _summer_school_operations(project, partner, users, participants):
    for title, status, owner_user, mandatory, day_offset in (
        ("Confirm partner MoU addendum for 2026 intake", "Completed", users["igp1"], True, -120),
        ("Collect visa and insurance documents from all participants", "Completed", users["igp2"], True, -45),
        ("Publish final academic timetable", "Completed", users["igp2"], True, -20),
        ("Issue completion certificates", "Completed", users["igp1"], True, 5),
        ("Submit mobility report to partner university", "Submitted", users["igp1"], True, 20),
        ("Reconcile programme budget", "In Progress", users["igp2"], True, 25),
    ):
        task = WorkTask(
            project_id=project.id, title=title, status=status,
            priority="High" if mandatory else "Medium",
            owner_person_id=owner_user.person_id,
            accountable_person_id=users["igp1"].person_id,
            mandatory_for_closure=mandatory,
            due_at=to_utc(datetime.combine(SUMMER_END + timedelta(days=day_offset), datetime.min.time()).replace(hour=17)),
            description=f"{title} for {project.title}.",
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(TaskStatusEvent(
            task_id=task.id, previous_status="In Progress",
            new_status=status, actor_user_id=owner_user.id,
            comment=f"Marked {status.lower()} by {owner_user.username}.",
            occurred_at=datetime.now(timezone.utc) - timedelta(days=30),
        ))

    for category, title, classification, mandatory, offset in (
        ("Agreement", "Partner MoU addendum 2026", "Restricted", True, -120),
        ("Compliance", "Visa and insurance pack", "Restricted", True, -45),
        ("Academic", "Final academic timetable", "Internal", True, -20),
        ("Report", "Mobility report to partner", "Internal", True, 20),
    ):
        db.session.add(DocumentRequirement(
            project_id=project.id, category=category, title=title,
            classification=classification, mandatory_for_closure=mandatory,
            owner_person_id=users["igp1"].person_id,
            due_at=to_utc(datetime.combine(SUMMER_END + timedelta(days=offset), datetime.min.time()).replace(hour=17)),
        ))

    for category, title, status, classification, owner_user, approver in (
        ("Agreement", "Partner MoU addendum 2026", "Approved", "Restricted", users["igp1"], users["faculty2"]),
        ("Compliance", "Visa and insurance pack", "Approved", "Restricted", users["igp2"], users["faculty2"]),
        ("Academic", "Final academic timetable", "Approved", "Internal", users["igp2"], users["faculty3"]),
        ("Report", "Mobility report to partner", "Submitted", "Internal", users["igp1"], None),
    ):
        db.session.add(DocumentRecord(
            project_id=project.id, category=category, title=title,
            version_label="1", status=status,
            permission_classification=classification,
            owner_person_id=owner_user.person_id,
            uploaded_by_id=owner_user.id,
            approved_by_id=approver.id if approver else None,
            approved_at=datetime.now(timezone.utc) - timedelta(days=60) if approver else None,
            mandatory_for_closure=True,
            drive_validation_status="Pending",
        ))

    for category, description, estimated, approved_amount, actual, status in (
        ("Accommodation", "Hostel block for 24 participants, six weeks", 480000, 480000, 372000, "Approved"),
        ("Academic", "Visiting faculty honorarium and materials", 150000, 150000, 148500, "Approved"),
        ("Excursions", "Campus and city excursion transport", 90000, 90000, 84300, "Approved"),
        ("Contingency", "Closing ceremony and certification", 45000, None, None, "Submitted"),
    ):
        db.session.add(BudgetLine(
            project_id=project.id, category=category, description=description,
            estimated_amount=estimated, approved_amount=approved_amount,
            committed_amount=approved_amount, actual_amount=actual,
            status=status, currency="INR",
            official_reference=f"IGP/2026/{category[:3].upper()}/001" if status == "Approved" else None,
        ))

    db.session.add(OperationalRequest(
        project_id=project.id, request_type="Transport",
        title="Two coaches for the city excursion",
        details="48-seat coaches for the full-day excursion, including driver allowance.",
        amount=42000, status="Approved",
        owner_person_id=users["igp2"].person_id,
        created_by_id=users["igp2"].id, submitted_by_id=users["igp2"].id,
        approver_id=users["igp1"].id,
        decision_comment="Approved against the excursions line.",
        official_reference="IGP/2026/OPS/007",
    ))

    form = FeedbackForm(
        project_id=project.id, title="Summer School 2026 exit survey",
        response_policy="One response", is_anonymous=False,
        questions_json=[
            {"key": "rating", "type": "scale", "min": 1, "max": 5, "label": "Overall programme rating"},
            {"key": "buddy", "type": "scale", "min": 1, "max": 5, "label": "How helpful was your buddy?"},
            {"key": "comments", "type": "text", "label": "What should we improve for the next cohort?"},
        ],
        is_open=False,
        opens_at=to_utc(datetime.combine(SUMMER_END, datetime.min.time()).replace(hour=9)),
        closes_at=to_utc(datetime.combine(SUMMER_END + timedelta(days=14), datetime.min.time()).replace(hour=23, minute=59)),
    )
    db.session.add(form)
    db.session.flush()
    for person, rating, buddy_rating, comment, moderation in (
        (participants[0], 5, 5, "The buddy pairing made the whole term easier.", "Approved"),
        (participants[1], 4, 5, "Excellent hosts; the coursework was heavier than advertised.", "Approved"),
        (participants[2], 5, 4, "Loved the excursion week.", "Approved"),
        (participants[3], 3, 3, "Hostel wifi was unreliable for coursework.", "Pending"),
    ):
        db.session.add(FeedbackResponse(
            form_id=form.id, person_id=person.id,
            answers_json={"rating": rating, "buddy": buddy_rating, "comments": comment},
            publication_consent=moderation == "Approved",
            moderation_status=moderation,
            response_key_hash=f"ss-{person.id}",
        ))

    db.session.add(ProjectRisk(
        project_id=project.id, title="Visa processing delays reduce intake",
        description="Participants depend on a student visa issued in their home country.",
        likelihood="Medium", impact="High",
        mitigation="Open applications 16 weeks ahead and track each visa individually.",
        owner_person_id=users["igp2"].person_id,
        status="Realised", is_critical=True,
    ))
    db.session.add(ProjectRisk(
        project_id=project.id, title="Buddy attrition during examination weeks",
        description="Host buddies sit their own examinations mid-programme.",
        likelihood="Medium", impact="Medium",
        mitigation="Pair each participant with a reserve buddy for the examination fortnight.",
        owner_person_id=users["igp1"].person_id,
        status="Closed", is_critical=False,
    ))

    db.session.add(ReportSnapshot(
        project_id=project.id, report_type="Project Operational Report",
        title="Summer School Exchange Program - operational report",
        filters_json={"project": project.code, "academic_year": "2026-2027"},
        snapshot_json={
            "project": project.code,
            "title": project.title,
            "partner": partner.name,
            "expected_reach": project.expected_reach,
            "actual_reach": project.actual_reach,
            "participants": len(participants),
            "buddy_pairs": len(participants),
            "budget_estimated": 765000,
            "budget_actual": 604800,
        },
        source_references=[project.public_id],
        approval_status="Submitted", publication_status="Unpublished",
        generated_by_id=users["igp1"].id,
    ))


# --------------------------------------------------------------------------
# Cross-cutting records
# --------------------------------------------------------------------------

def _governance(year, icc, igp, users):
    for unit, name in ((icc, "ICC Core Committee 2026-2027"), (igp, "IGP Core Team 2026-2027")):
        db.session.add(GovernanceTerm(
            academic_year_id=year.id, operating_unit_id=unit.id, name=name,
            starts_on=year.start_date, ends_on=year.end_date, status="Active",
        ))


def _notifications(coffee, summer, users):
    """In-app notifications that point at work that genuinely is pending."""
    rows = [
        ("events1", coffee, "approval_pending", "Warning",
         "Reimbursement request awaiting your decision",
         "A reimbursement request for additional refreshments is waiting on the Events wing.",
         f"/projects/{coffee.public_id}"),
        ("events1", coffee, "feedback_moderation", "Info",
         "Two feedback responses need moderation",
         "Coffee Meet & Greet has two responses pending moderation before publication.",
         f"/projects/{coffee.public_id}"),
        ("media1", coffee, "task_due", "Info",
         "Highlight reel still in progress",
         "The post-event highlight reel task is still open for the Media wing.",
         f"/projects/{coffee.public_id}"),
        ("faculty1", coffee, "approval_pending", "Info",
         "Post-event report submitted for approval",
         "Coffee Meet & Greet has submitted its post-event report.",
         f"/projects/{coffee.public_id}"),
        ("igp1", summer, "approval_pending", "Warning",
         "Mobility report awaiting approval",
         "The Summer School mobility report has been submitted and needs faculty approval.",
         f"/projects/{summer.public_id}"),
        ("igp2", summer, "task_due", "Warning",
         "Buddy logs pending verification",
         "Six buddy logs are still awaiting verification before the programme can close.",
         f"/projects/{summer.public_id}"),
        ("faculty2", summer, "approval_pending", "Info",
         "Summer School is ready for closure review",
         "All mandatory Summer School documents are approved except the mobility report.",
         f"/projects/{summer.public_id}"),
    ]
    for index, (username, project, event_type, severity, title, body, url) in enumerate(rows):
        db.session.add(Notification(
            user_id=users[username].id, project_id=project.id,
            event_type=event_type, severity=severity,
            title=title, body=body, action_url=url,
            idempotency_key=f"beta-seed-{index}-{users[username].id}",
            is_critical=severity == "Warning",
            delivery_status="Delivered",
        ))


def _approval_trail(coffee, summer, users):
    """The approvals that produced the Approved rows above."""
    for entity_type, public_id, action, actor, reason in (
        ("Project", coffee.public_id, "Approved", users["faculty1"], "Event plan and budget approved."),
        ("Project", summer.public_id, "Approved", users["faculty2"], "Programme approved for the 2026 intake."),
    ):
        db.session.add(ApprovalEvent(
            entity_type=entity_type, entity_public_id=public_id,
            action=action, reason=reason, actor_user_id=actor.id,
            occurred_at=datetime.now(timezone.utc) - timedelta(days=90),
        ))
        db.session.add(AuditEvent(
            actor_user_id=actor.id, action="project.approve",
            entity_type=entity_type, entity_public_id=public_id,
            after_summary=reason,
            occurred_at=datetime.now(timezone.utc) - timedelta(days=90),
        ))


def _igp_checklist_template():
    """An IGP-side checklist template. The ICC one is seeded by
    ``seed_icc_checklist_template``; the only IGP template in the codebase
    arrives through the Summer School spreadsheet import, which is not
    bundled into every deployment."""
    template = ChecklistTemplate.query.filter_by(code="IGP-PROGRAM-STANDARD", is_active=True).first()
    if template:
        return template
    template = ChecklistTemplate(
        code="IGP-PROGRAM-STANDARD", name="IGP Inbound Program Checklist",
        project_type="IGP inbound program", version=1, source_reference="Beta seed",
    )
    db.session.add(template)
    db.session.flush()
    for sequence, (code, title, category) in enumerate((
        ("MOU", "Partner agreement / MoU addendum signed", "Agreements"),
        ("VISA", "Visa and insurance documents collected", "Compliance"),
        ("ACCOM", "Accommodation block confirmed", "Logistics"),
        ("TIMETABLE", "Academic timetable published", "Academic"),
        ("BUDDY", "Buddy pairings confirmed", "People"),
        ("REPORT", "Mobility report submitted to partner", "Reporting"),
    ), start=1):
        db.session.add(ChecklistTemplateItem(
            template_id=template.id, code=code, title=title,
            category=category, sequence=sequence, mandatory=True,
        ))
    db.session.flush()
    return template


def _attach_checklists(coffee, summer, users):
    seed_icc_checklist_template()
    icc_template = ChecklistTemplate.query.filter_by(code="ICC-EVENT-STANDARD", is_active=True).first()
    if icc_template:
        instance = instantiate_checklist(coffee, icc_template, actor=users["events1"])
        # Everything except the post-event report is done; that is what keeps
        # the project in closure rather than complete.
        for status_row in instance.item_statuses:
            item = status_row.template_item
            done = item.code != "REPORT"
            status_row.status = "Approved" if done else "Submitted"
            status_row.owner_person_id = users["events1"].person_id
            if done:
                status_row.verifier_id = users["events1"].id
                status_row.verified_at = datetime.now(timezone.utc) - timedelta(days=5)

    igp_template = _igp_checklist_template()
    instance = instantiate_checklist(summer, igp_template, actor=users["igp1"])
    for status_row in instance.item_statuses:
        item = status_row.template_item
        done = item.code != "REPORT"
        status_row.status = "Approved" if done else "Submitted"
        status_row.owner_person_id = users["igp1"].person_id
        if done:
            status_row.verifier_id = users["igp2"].id
            status_row.verified_at = datetime.now(timezone.utc) - timedelta(days=40)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def seed_beta(*, reset: bool = True) -> dict[str, object]:
    """Reset the database and build the complete beta dataset."""
    summary: dict[str, object] = {}
    if reset:
        summary["deleted"] = sum(reset_all_data().values())

    year, campus, icc_type, igp_type, icc, igp, _events_wing = _reference_data()
    wings = {
        wing.code: wing
        for wing in Wing.query.filter_by(operating_unit_id=icc.id).all()
    }
    db.session.flush()

    users = _create_accounts(year, campus, icc, igp, wings)
    _governance(year, icc, igp, users)

    coffee, components, coffee_sessions = _seed_coffee_meet(year, campus, icc_type, icc, wings, users)
    volunteers, attendees = _coffee_meet_people(coffee, campus, wings, users, components, coffee_sessions)
    _coffee_meet_operations(coffee, components, users, volunteers, attendees)

    summer, partner, cohort, summer_sessions = _seed_summer_school(year, campus, igp_type, igp, users)
    participants, buddies = _summer_school_people(summer, cohort, campus, users, summer_sessions)
    _summer_school_operations(summer, partner, users, participants)

    _notifications(coffee, summer, users)
    _approval_trail(coffee, summer, users)
    db.session.commit()

    # instantiate_checklist commits internally, so it runs after the main commit.
    _attach_checklists(coffee, summer, users)
    db.session.commit()

    summary.update({
        "users": len(users),
        "projects": 2,
        "people": Person.query.count(),
        "sessions": ProjectSession.query.count(),
        "team_assignments": TeamAssignment.query.count(),
        "buddy_pairs": BuddyAssignment.query.count(),
    })
    return summary
