from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime

import sqlalchemy as sa


ROOT = os.path.dirname(os.path.dirname(__file__))


def _upgrade(database_url: str, target: str) -> None:
    environment = os.environ.copy()
    environment.update({"DATABASE_URL": database_url, "FLASK_APP": "run.py", "APP_ENV": "development"})
    result = subprocess.run(
        [sys.executable, "-m", "flask", "db", "upgrade", target],
        cwd=ROOT, env=environment, capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


def test_populated_preconsolidation_upgrade_reconciles_every_legacy_entity(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    _upgrade(database_url, "21c74aca53ae")
    engine = sa.create_engine(database_url)
    metadata = sa.MetaData()
    metadata.reflect(bind=engine)
    table = metadata.tables
    now = datetime(2026, 8, 1, 9, 0)

    with engine.begin() as connection:
        campus_id = connection.execute(table["campuses"].insert().values(name="Central", code="CTR", public_id="campus-legacy")).inserted_primary_key[0]
        program_id = connection.execute(table["program_types"].insert().values(name="ICC", public_id="program-legacy")).inserted_primary_key[0]
        year_id = connection.execute(table["academic_years"].insert().values(name="2026-2027", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), is_current=True, public_id="year-legacy")).inserted_primary_key[0]
        project_id = connection.execute(table["projects"].insert().values(
            public_id="project-legacy", code="ICC-2026-CTR-0001", campus_id=campus_id,
            program_type_id=program_id, academic_year_id=year_id, title="Legacy event",
            category="Operational", status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2), version=1,
        )).inserted_primary_key[0]
        user_id = connection.execute(table["users"].insert().values(
            public_id="user-legacy", username="legacy_user", email="legacy@example.test",
            password_hash="not-a-real-password", role="Volunteer", status="Approved",
            needs_password_reset=True, failed_login_count=0, session_version=1, is_archived=False,
            version=1, identity_provider="internal",
        )).inserted_primary_key[0]
        connection.execute(table["project_participants"].insert().values(
            public_id="participant-legacy", project_id=project_id, user_id=user_id,
            participant_type="Volunteer", nationality="India", status="Active", registration_date=now, version=1,
        ))
        connection.execute(table["attendance_records"].insert().values(project_id=project_id, user_id=user_id, date=date(2026, 8, 1), status="Present", verified_by_id=user_id, timestamp=now))
        connection.execute(table["contributions"].insert().values(project_id=project_id, user_id=user_id, activity_type="Logistics", description="Set up room", division="Unmapped legacy wing", duration_hours=2, approval_status="Approved", approved_by_id=user_id, approved_at=now))
        connection.execute(table["documents"].insert().values(project_id=project_id, title="Run sheet", document_type="Schedule", google_drive_link="https://drive.google.com/file/d/abcdefghijk123/view", uploaded_by_id=user_id, created_at=now))
        connection.execute(table["feedback"].insert().values(project_id=project_id, user_id=user_id, rating=5, comments="Useful", suggestions="More time", submission_type="Participant", created_at=now))
        connection.execute(table["reports"].insert().values(report_type="Campus rollup", title="Legacy rollup", description="Historic", campus_id=campus_id, program_type_id=program_id, project_id=None, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31), generated_by_id=user_id, created_at=now))
        connection.execute(table["volunteers"].insert().values(user_id=user_id, skills="Hosting", interests="Culture", current_status="Active legacy volunteer"))

    _upgrade(database_url, "head")
    metadata = sa.MetaData()
    metadata.reflect(bind=engine)
    assert not {"project_participants", "attendance_records", "contributions", "documents", "feedback", "reports", "volunteers"}.intersection(metadata.tables)
    with engine.connect() as connection:
        reconciled = connection.execute(sa.select(metadata.tables["legacy_migration_reconciliation"])).mappings().all()
        assert len(reconciled) == 7
        assert {row["source_table"] for row in reconciled} == {"project_participants", "attendance_records", "contributions", "documents", "feedback", "reports", "volunteers"}
        person = connection.execute(sa.select(metadata.tables["people"])).mappings().one()
        assert person["skills"] == "Hosting"
        assert person["interests"] == "Culture"
        contribution = connection.execute(sa.select(metadata.tables["contribution_records"])).mappings().one()
        assert contribution["evidence_reference"] == "Legacy division: Unmapped legacy wing"
        assert connection.execute(sa.select(sa.func.count()).select_from(metadata.tables["session_attendance"])).scalar_one() == 1
        assert connection.execute(sa.select(sa.func.count()).select_from(metadata.tables["feedback_responses"])).scalar_one() == 1
        assert connection.execute(sa.select(sa.func.count()).select_from(metadata.tables["report_snapshots"])).scalar_one() == 1


def test_populated_operational_request_upgrade_backfills_user_through_person_and_keeps_fk_graph_valid(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'operational-request.db'}"
    _upgrade(database_url, "80118b060084")
    engine = sa.create_engine(database_url)
    metadata = sa.MetaData()
    metadata.reflect(bind=engine)
    table = metadata.tables

    with engine.begin() as connection:
        campus_id = connection.execute(table["campuses"].insert().values(name="Central", code="CTR", public_id="campus-op")).inserted_primary_key[0]
        program_id = connection.execute(table["program_types"].insert().values(name="ICC", public_id="program-op")).inserted_primary_key[0]
        year_id = connection.execute(table["academic_years"].insert().values(name="2026-2027", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), is_current=True, public_id="year-op")).inserted_primary_key[0]
        project_id = connection.execute(table["projects"].insert().values(
            public_id="project-op", code="ICC-2026-CTR-0002", campus_id=campus_id,
            program_type_id=program_id, academic_year_id=year_id, title="Operational event",
            category="Operational", status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2), version=1,
        )).inserted_primary_key[0]
        person_id = connection.execute(table["people"].insert().values(
            public_id="person-op", first_name="Request", person_type="Platform User",
            consent_status="Not Recorded", is_archived=False, contact_visibility={},
        )).inserted_primary_key[0]
        user_id = connection.execute(table["users"].insert().values(
            public_id="user-op", username="request_owner", email="request-owner@example.test",
            password_hash="not-a-real-password", role="Faculty", status="Approved", person_id=person_id,
            needs_password_reset=False, failed_login_count=0, session_version=1, is_archived=False,
            version=1, identity_provider="internal",
        )).inserted_primary_key[0]
        connection.execute(table["operational_requests"].insert().values(
            public_id="request-op", project_id=project_id, request_type="Vehicle",
            title="Existing request", status="Submitted", owner_person_id=person_id,
        ))

    _upgrade(database_url, "head")
    metadata = sa.MetaData()
    metadata.reflect(bind=engine)
    with engine.connect() as connection:
        request_row = connection.execute(sa.select(metadata.tables["operational_requests"])).mappings().one()
        assert request_row["created_by_id"] == user_id
        assert request_row["submitted_by_id"] == user_id
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []

    project_foreign_keys = sa.inspect(engine).get_foreign_keys("projects")
    constrained_columns = {tuple(item["constrained_columns"]) for item in project_foreign_keys}
    assert ("publication_requested_by_id",) in constrained_columns
    assert ("publication_approved_by_id",) in constrained_columns


def test_simplification_migration_maps_roles_teams_money_and_pending_signups(tmp_path):
    """d4a7c3e91b52: heads lose their wing pin, retired roles become
    volunteers, checklist items pick up a team from their labels, money
    statuses read as Asked/Approved/Paid/Not approved, and accounts still
    waiting for approval become volunteers."""
    database_url = f"sqlite:///{tmp_path / 'simplify.db'}"
    _upgrade(database_url, "c2f8a1d40e77")
    engine = sa.create_engine(database_url)
    metadata = sa.MetaData()
    metadata.reflect(bind=engine)
    table = metadata.tables

    def user(connection, name, status="Approved"):
        return connection.execute(table["users"].insert().values(
            public_id=f"user-{name}", username=name, email=f"{name}@example.test", password_hash="x",
            role="Legacy", status=status, needs_password_reset=False, failed_login_count=0,
            identity_provider="internal", campus_id=None,
        )).inserted_primary_key[0]

    with engine.begin() as connection:
        campus_id = connection.execute(table["campuses"].insert().values(name="Central", code="CTR", public_id="campus-s")).inserted_primary_key[0]
        program_id = connection.execute(table["program_types"].insert().values(name="ICC", public_id="program-s")).inserted_primary_key[0]
        year_id = connection.execute(table["academic_years"].insert().values(name="2026-2027", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), is_current=True, public_id="year-s")).inserted_primary_key[0]
        unit_id = connection.execute(table["operating_units"].insert().values(code="ICC", name="ICC", is_active=True, public_id="unit-s")).inserted_primary_key[0]
        wing_id = connection.execute(table["wings"].insert().values(operating_unit_id=unit_id, code="MEDIA", name="Media", is_active=True, public_id="wing-s")).inserted_primary_key[0]
        project_id = connection.execute(table["projects"].insert().values(
            public_id="project-s", code="ICC-2026-CTR-0009", campus_id=campus_id, program_type_id=program_id,
            academic_year_id=year_id, title="Simplify event", category="Event", status="Active",
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 2), version=1,
        )).inserted_primary_key[0]

        media_head = user(connection, "media_head")
        lead = user(connection, "programme_lead")
        associate = user(connection, "associate")
        waiting = user(connection, "waiting", status="Pending")
        for name, user_id, role_code, wing in (
            ("media", media_head, "ICC_MEDIA_HEAD", wing_id),
            ("lead", lead, "IGP_PROGRAM_LEAD", None),
            ("assoc", associate, "ICC_ASSOCIATE", wing_id),
        ):
            connection.execute(table["role_assignments"].insert().values(
                public_id=f"ra-{name}", user_id=user_id, role_code=role_code, wing_id=wing,
                is_active=True, can_view_sensitive_links=False,
            ))

        template_id = connection.execute(table["checklist_templates"].insert().values(
            code="T", name="Standard", project_type="ICC event", version=1, is_active=True, public_id="tpl-s",
        )).inserted_primary_key[0]
        instance_id = connection.execute(table["checklist_instances"].insert().values(
            project_id=project_id, template_id=template_id, name="Checklist", status="Active", public_id="inst-s",
        )).inserted_primary_key[0]
        for code, category, owner in (("POSTER", "Media", None), ("VENUE", "Logistics", None), ("ACTS", None, "Cultural team")):
            item_id = connection.execute(table["checklist_template_items"].insert().values(
                template_id=template_id, code=code, title=code.title(), category=category, default_owner_label=owner,
                sequence=1, mandatory=True, sensitive=False, public_id=f"tpli-{code}",
            )).inserted_primary_key[0]
            connection.execute(table["checklist_item_statuses"].insert().values(
                checklist_instance_id=instance_id, template_item_id=item_id, status="Not Started",
                waived=False, public_id=f"cis-{code}",
            ))

        for index, status in enumerate(("Pending", "Reimbursed", "Rejected", "Approved", "")):
            connection.execute(table["reimbursement_entries"].insert().values(
                public_id=f"money-{index}", project_id=project_id, date=date(2026, 8, 1),
                party_name="Vendor", amount=100, status=status,
            ))

    _upgrade(database_url, "head")
    metadata = sa.MetaData()
    metadata.reflect(bind=engine)
    table = metadata.tables
    with engine.connect() as connection:
        roles = {row.public_id: row for row in connection.execute(sa.select(table["role_assignments"]))}
        assert roles["ra-media"].role_code == "ICC_MEDIA_HEAD" and roles["ra-media"].wing_id is None
        assert roles["ra-lead"].role_code == "VOLUNTEER"
        assert "IGP head" in roles["ra-lead"].assignment_reason
        assert roles["ra-assoc"].role_code == "VOLUNTEER"

        teams = {row.public_id: row.assigned_team for row in connection.execute(sa.select(table["checklist_item_statuses"]))}
        assert teams == {"cis-POSTER": "media", "cis-VENUE": None, "cis-ACTS": "culturals"}

        statuses = [row.status for row in connection.execute(
            sa.select(table["reimbursement_entries"]).order_by(table["reimbursement_entries"].c.public_id))]
        assert statuses == ["Asked", "Paid", "Not approved", "Approved", "Asked"]

        account = connection.execute(sa.select(table["users"]).where(table["users"].c.id == waiting)).one()
        assert (account.status, account.role) == ("Approved", "Volunteer")
        volunteer_roles = connection.execute(
            sa.select(table["role_assignments"].c.role_code).where(table["role_assignments"].c.user_id == waiting)
        ).scalars().all()
        assert volunteer_roles == ["VOLUNTEER"]
