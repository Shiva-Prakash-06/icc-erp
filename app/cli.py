from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

import click
from flask import current_app

from app.database import db
from app.models.user import User
from app.models.erp import BudgetLine, ChecklistTemplate, DocumentRecord, FeedbackForm, FeedbackResponse, ImportBatch, OperationalRequest, Person, ProjectSession, ReportSnapshot, RoleAssignment, TeamAssignment, WorkTask
from app.models.production import ContributionRecord, RecruitmentApplication
from app.models.project import BuddyAssignment, BuddyLog, Project
from app.services.imports import _reference_data
from app.services.imports import backfill_summer_school_sample_content, commit_batch, seed_icc_checklist_template, stage_supplied_source
from app.services.operations import instantiate_checklist
from app.services.roles import replace_scoped_assignment


def register_cli(app):
    @app.cli.command("seed-test-users")
    def seed_test_users():
        """Create the five approved local accounts used for manual testing."""

        test_password = "123"

        role_labels = {
            "OIA_FACULTY_ADMINISTRATOR": "OIA Faculty Administrator",
            "ICC_SECRETARY_USC": "ICC Secretary / USC",
            "IGP_HEAD": "IGP Head",
            "ICC_EVENTS_HEAD": "ICC Events Head",
            "VOLUNTEER": "Volunteer",
        }
        created = 0
        for code, label in role_labels.items():
            username = f"rbac_{code.lower()}"
            email = f"{username}@example.test"
            password = test_password
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(username=username, email=email, role=label, preferred_role=label,
                            status="Approved", needs_password_reset=False)
                user.set_password(password)
                db.session.add(user)
                db.session.flush()
                created += 1
            else:
                user.email = email
                user.role = label
                user.preferred_role = label
                user.status = "Approved"
                user.needs_password_reset = False
            user.set_password(password)
            assignment = RoleAssignment.query.filter_by(user_id=user.id, role_code=code).first()
            if not assignment:
                db.session.add(RoleAssignment(user_id=user.id, role_code=code,
                                              is_active=True,
                                              can_view_sensitive_links=code in {"OIA_FACULTY_ADMINISTRATOR", "IGP_HEAD"}))
        db.session.commit()
        click.echo(f"RBAC test users ready: {len(role_labels)} accounts ({created} created).")

    @app.cli.command("bootstrap-reference-data")
    def bootstrap_reference_data():
        """Create controlled lookup records; never creates login accounts."""

        _reference_data()
        db.session.commit()
        click.echo("Reference data is ready. No user accounts were created.")

    @app.cli.command("bootstrap-admin")
    @click.option("--username", envvar="BOOTSTRAP_ADMIN_USERNAME", required=True)
    @click.option("--email", envvar="BOOTSTRAP_ADMIN_EMAIL", required=True)
    @click.option("--password", envvar="BOOTSTRAP_ADMIN_PASSWORD", required=True, hide_input=True)
    def bootstrap_admin(username, email, password):
        """Create the first administrator through an explicit, audited operator action."""

        if len(password) < 14:
            raise click.ClickException("Bootstrap password must contain at least 14 characters.")
        if User.query.count():
            raise click.ClickException("Users already exist; use account administration instead.")
        user = User(
            username=username.strip(),
            email=email.strip().lower(),
            role="Faculty",
            preferred_role="OIA Faculty Administrator",
            status="Approved",
            needs_password_reset=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        person = Person(
            first_name=username.strip(), primary_email=email.strip().lower(),
            person_type="Faculty / Staff",
        )
        db.session.add(person)
        db.session.flush()
        user.person_id = person.id
        db.session.add(RoleAssignment(
            user_id=user.id,
            role_code="OIA_FACULTY_ADMINISTRATOR",
            is_active=True,
            can_view_sensitive_links=True,
        ))
        db.session.commit()
        click.echo(f"Bootstrap administrator {username} created; password reset is required on first login.")

    @app.cli.command("seed-acceptance")
    def seed_acceptance():
        """Provision deterministic browser-test data in an explicitly isolated database."""
        if os.getenv("ACCEPTANCE_SEED") != "1" or not current_app.config.get("DEMONSTRATOR"):
            raise click.ClickException("Acceptance seeding is allowed only for an explicit demonstrator run.")
        year, campus, icc_type, igp_type, icc, igp, events_wing = _reference_data()
        password = "123"
        role_rows = {
            "e2e_faculty": ("OIA Faculty Administrator", "OIA_FACULTY_ADMINISTRATOR", {}),
            "e2e_usc": ("ICC Secretary / USC", "ICC_SECRETARY_USC", {"campus_id": campus.id, "operating_unit_id": icc.id, "academic_year_id": year.id}),
            "e2e_igp": ("IGP Head", "IGP_HEAD", {"campus_id": campus.id, "operating_unit_id": igp.id, "academic_year_id": year.id}),
            "e2e_events": ("ICC Events Head", "ICC_EVENTS_HEAD", {"campus_id": campus.id, "operating_unit_id": icc.id, "wing_id": events_wing.id, "academic_year_id": year.id}),
            "e2e_volunteer": ("Volunteer", "VOLUNTEER", {}),
        }
        users = {}
        for username, (label, role_code, scope) in role_rows.items():
            user = User.query.filter_by(username=username).first()
            if not user:
                person = Person(first_name=username.replace("e2e_", "").title(), primary_email=f"{username}@example.test", campus_id=campus.id, person_type="Acceptance fixture")
                db.session.add(person)
                db.session.flush()
                user = User(username=username, email=person.primary_email, role=label, preferred_role=label, status="Approved", needs_password_reset=False, person_id=person.id)
                user.set_password(password)
                db.session.add(user)
                db.session.flush()
            assignment = RoleAssignment.query.filter_by(user_id=user.id, role_code=role_code, is_active=True).first()
            if not assignment:
                db.session.add(RoleAssignment(user_id=user.id, role_code=role_code, is_active=True, can_view_sensitive_links=role_code in {"OIA_FACULTY_ADMINISTRATOR", "IGP_HEAD"}, **scope))
            users[username] = user
        db.session.flush()
        event = Project.query.filter_by(code="E2E-ICC-EVENT").first()
        if not event:
            event = Project(code="E2E-ICC-EVENT", title="Acceptance ICC event", campus_id=campus.id, program_type_id=icc_type.id, academic_year_id=year.id, operating_unit_id=icc.id, wing_id=events_wing.id, project_type="ICC event", category="Operational", status="Active", start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), venue="Central Campus")
            db.session.add(event)
            db.session.flush()
            db.session.add(ProjectSession(project_id=event.id, code="MAIN", title="Main event", session_type="Event", starts_at=datetime(2026, 8, 10, 9, tzinfo=timezone.utc), ends_at=datetime(2026, 8, 10, 11, tzinfo=timezone.utc), venue=event.venue))
            db.session.add(WorkTask(project_id=event.id, title="Submit event run sheet", status="Submitted", mandatory_for_closure=True))
            db.session.add(FeedbackForm(project_id=event.id, title="Event feedback", questions_json=[{"key": "rating", "type": "scale", "min": 1, "max": 5, "label": "Overall rating"}, {"key": "q_1", "type": "text", "label": "What worked well?"}], is_open=True))
        igp_project = Project.query.filter_by(code="E2E-IGP").first()
        if not igp_project:
            igp_project = Project(code="E2E-IGP", title="Acceptance IGP programme", campus_id=campus.id, program_type_id=igp_type.id, academic_year_id=year.id, operating_unit_id=igp.id, project_type="IGP inbound program", category="Operational", status="Active", start_date=date(2026, 8, 15), end_date=date(2026, 8, 20), venue="Central Campus")
            db.session.add(igp_project)
        db.session.flush()
        if not TeamAssignment.query.filter_by(project_id=event.id, person_id=users["e2e_volunteer"].person_id).first():
            db.session.add(TeamAssignment(project_id=event.id, person_id=users["e2e_volunteer"].person_id, user_id=users["e2e_volunteer"].id, assignment_type="Project Team", role_label="Volunteer"))
        exchange_student = Person.query.filter_by(primary_email="exchange.student@example.test").first()
        if not exchange_student:
            exchange_student = Person(first_name="Exchange", last_name="Student", primary_email="exchange.student@example.test", person_type="Student")
            db.session.add(exchange_student)
            db.session.flush()
        if not TeamAssignment.query.filter_by(project_id=igp_project.id, person_id=exchange_student.id).first():
            db.session.add(TeamAssignment(person_id=exchange_student.id, project_id=igp_project.id, assignment_type="Participant", role_label="Exchange Student"))
        seed_icc_checklist_template()
        template = ChecklistTemplate.query.filter_by(code="ICC-EVENT-STANDARD", is_active=True).first()
        if template and not event.checklists:
            checklist = instantiate_checklist(event, template)
            checklist.item_statuses[0].status = "Submitted"
        if not DocumentRecord.query.filter_by(project_id=event.id, title="Acceptance run sheet").first():
            db.session.add(DocumentRecord(project_id=event.id, title="Acceptance run sheet", category="Report", status="Submitted", permission_classification="Internal", drive_validation_status="Pending"))
        if not ContributionRecord.query.filter_by(project_id=event.id, description="Acceptance logistics support").first():
            db.session.add(ContributionRecord(project_id=event.id, person_id=users["e2e_volunteer"].person_id, activity_type="Logistics support", description="Acceptance logistics support", duration_hours=2, approval_status="Pending"))
        if not OperationalRequest.query.filter_by(project_id=event.id, title="Acceptance equipment request").first():
            db.session.add(OperationalRequest(
                project_id=event.id, request_type="Equipment",
                title="Acceptance equipment request", status="Submitted",
                owner_person_id=users["e2e_events"].person_id,
                created_by_id=users["e2e_events"].id,
                submitted_by_id=users["e2e_events"].id,
            ))
        if not BudgetLine.query.filter_by(project_id=event.id, description="Acceptance refreshments").first():
            db.session.add(BudgetLine(project_id=event.id, category="Hospitality", description="Acceptance refreshments", estimated_amount=2500, status="Submitted"))
        form = FeedbackForm.query.filter_by(project_id=event.id, is_open=True).first()
        if form and not FeedbackResponse.query.filter_by(form_id=form.id, response_key_hash="acceptance-pending").first():
            db.session.add(FeedbackResponse(form_id=form.id, person_id=users["e2e_volunteer"].person_id, answers_json={"rating": 4, "q_1": "Acceptance feedback"}, moderation_status="Pending", response_key_hash="acceptance-pending"))
        if not RecruitmentApplication.query.filter_by(project_id=event.id, person_id=exchange_student.id).first():
            db.session.add(RecruitmentApplication(project_id=event.id, person_id=exchange_student.id, desired_role="Event volunteer", decision="Submitted", consent_status="Recorded"))
        if not ReportSnapshot.query.filter_by(project_id=event.id, title="Acceptance project report").first():
            db.session.add(ReportSnapshot(project_id=event.id, report_type="Project", title="Acceptance project report", filters_json={}, snapshot_json={"project": event.code}, source_references=[event.public_id], approval_status="Draft", publication_status="Unpublished", generated_by_id=users["e2e_faculty"].id))
        if not BuddyAssignment.query.filter_by(project_id=igp_project.id).first():
            pairing = BuddyAssignment(project_id=igp_project.id, buddy_user_id=users["e2e_volunteer"].id, exchange_student_person_id=exchange_student.id, start_date=igp_project.start_date, end_date=igp_project.end_date, status="Active")
            db.session.add(pairing)
            db.session.flush()
            db.session.add(BuddyLog(buddy_assignment_id=pairing.id, activity_date=igp_project.start_date, description="Acceptance buddy orientation", duration_hours=1, status="Pending"))
        db.session.commit()
        click.echo("Acceptance fixtures ready. Test password: 123")

    @app.cli.command("provision-uat")
    @click.option("--output", type=click.Path(dir_okay=False, path_type=Path), default=Path("instance/UAT_CREDENTIALS.txt"))
    def provision_uat(output):
        """Create first-login UAT accounts and a private, untracked credential sheet."""
        year, campus, _icc_type, _igp_type, icc, igp, events_wing = _reference_data()
        rows = {
            "uat_faculty_admin": ("OIA Faculty Administrator", "OIA_FACULTY_ADMINISTRATOR", None, None, True),
            "uat_usc": ("ICC Secretary / USC", "ICC_SECRETARY_USC", icc, None, False),
            "uat_igp_head": ("IGP Head", "IGP_HEAD", igp, None, True),
            "uat_icc_events_head": ("ICC Events Head", "ICC_EVENTS_HEAD", icc, events_wing, False),
            "uat_volunteer": ("Volunteer", "VOLUNTEER", None, None, False),
        }
        credentials = []
        for username, (label, role_code, unit, wing, sensitive) in rows.items():
            email = f"{username}@example.test"
            password = "123"
            user = User.query.filter_by(username=username).first()
            if not user:
                person = Person(first_name=username.replace("uat_", "").replace("_", " ").title(), primary_email=email, campus_id=campus.id, person_type="UAT User")
                db.session.add(person)
                db.session.flush()
                user = User(username=username, email=email, person_id=person.id)
                user.set_password(password)
                db.session.add(user)
                db.session.flush()
            user.email = email
            user.role = label
            user.preferred_role = label
            user.status = "Approved"
            user.needs_password_reset = False
            user.failed_login_count = 0
            user.locked_until = None
            user.set_password(password)
            RoleAssignment.query.filter_by(user_id=user.id, is_active=True).update({"is_active": False})
            db.session.add(RoleAssignment(
                user_id=user.id,
                role_code=role_code,
                campus_id=None if role_code == "OIA_FACULTY_ADMINISTRATOR" else campus.id,
                operating_unit_id=getattr(unit, "id", None),
                wing_id=getattr(wing, "id", None),
                academic_year_id=None if role_code == "OIA_FACULTY_ADMINISTRATOR" else year.id,
                is_active=True,
                assignment_reason="User acceptance testing",
                can_view_sensitive_links=sensitive,
            ))
            credentials.append(f"{username}\t{password}")
        db.session.commit()
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("ICC ERP UAT one-time credentials\n")
            handle.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
            handle.write("Rotate or delete immediately after acceptance.\n\n")
            handle.write("Username\tOne-time password\n")
            handle.write("\n".join(credentials) + "\n")
        os.chmod(output, 0o600)
        click.echo(f"Provisioned {len(rows)} UAT accounts. Private credentials: {output}")

    @app.cli.command("demo-import-supplied")
    def demo_import_supplied():
        """Stage and commit the supplied sample sources in dependency order."""

        if not current_app.config.get("DEMONSTRATOR"):
            raise click.ClickException("Sample imports are disabled outside demonstrator environments.")
        for import_type in ("events_summary", "coffee_meet", "summer_school"):
            batch = stage_supplied_source(import_type)
            commit_batch(batch)
            click.echo(
                f"{import_type}: staged={batch.staged_count} valid={batch.valid_count} "
                f"errors={batch.error_count} committed={batch.committed_count}"
            )

    @app.cli.command("backfill-user-person-links")
    def backfill_user_person_links():
        """Resolve/create a Person for every User missing one, and link it.

        Idempotent: safe to re-run. Every self-service flow that keys off
        `g.user.person_id` (self-attendance, self-application, contribution
        logging tied to identity) is dead code until this has run for a
        given user.
        """
        linked = created_person = 0
        for user in User.query.filter(User.person_id.is_(None)).all():
            person = Person.query.filter(db.func.lower(Person.primary_email) == user.email.lower()).first()
            if not person:
                person = Person(
                    first_name=user.username,
                    primary_email=user.email,
                    campus_id=user.campus_id,
                    person_type="Platform User",
                )
                db.session.add(person)
                db.session.flush()
                created_person += 1
            user.person_id = person.id
            linked += 1
        db.session.commit()
        click.echo(f"Linked {linked} user(s) to a Person record ({created_person} Person records created).")

    @app.cli.command("backfill-role-assignments")
    def backfill_role_assignments():
        """Create a scoped RoleAssignment for every Approved user missing one.

        Idempotent: safe to re-run. Users whose role requires a project/
        academic-year scope that can't be inferred from existing data are
        reported for manual re-approval through the admin UI instead of
        being guessed at.
        """
        backfilled = 0
        needs_manual_review = []
        query = User.query.filter(User.status == "Approved")
        for user in query.all():
            has_active_assignment = RoleAssignment.query.filter_by(user_id=user.id, is_active=True).first() is not None
            if has_active_assignment:
                continue
            try:
                replace_scoped_assignment(user, user.role, {}, user)
                backfilled += 1
            except ValueError as error:
                db.session.rollback()
                needs_manual_review.append((user.username, str(error)))
        db.session.commit()
        click.echo(f"Backfilled {backfilled} RoleAssignment(s).")
        if needs_manual_review:
            click.echo(f"{len(needs_manual_review)} user(s) need manual re-approval through the admin UI:")
            for username, reason in needs_manual_review:
                click.echo(f"  - {username}: {reason}")

    @app.cli.command("seed-icc-checklist-template")
    def seed_icc_checklist_template_cmd():
        """Seed a generic ICC event checklist template (only an IGP one
        exists from the supplied source data)."""
        result = seed_icc_checklist_template()
        click.echo(", ".join(f"{key}={value}" for key, value in result.items()))

    @app.cli.command("backfill-summer-school-sample")
    def backfill_summer_school_sample():
        """Add schematic sessions/team/documents to the Summer School sample
        project so it's as complete a reference example as Coffee Meet &
        Greet (the supplied source file is a checklist only)."""
        result = backfill_summer_school_sample_content()
        click.echo(", ".join(f"{key}={value}" for key, value in result.items()))

    @app.cli.command("commit-import-batch")
    @click.option("--public-id", envvar="IMPORT_BATCH_PUBLIC_ID", required=True)
    def commit_import_batch(public_id):
        """Commit a previously validated batch from a Cloud Run Job."""

        batch = ImportBatch.query.filter_by(public_id=public_id).first()
        if not batch:
            raise click.ClickException("Import batch was not found.")
        commit_batch(batch)
        click.echo(
            f"batch={batch.public_id} status={batch.status} committed={batch.committed_count} "
            f"difference={batch.reconciliation_json.get('difference')}"
        )
