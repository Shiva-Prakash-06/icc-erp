from __future__ import annotations

import os

import click
from flask import current_app

from app.database import db
from app.models.user import User
from app.models.erp import ImportBatch, Person, RoleAssignment
from app.services.imports import _reference_data
from app.services.imports import backfill_summer_school_sample_content, commit_batch, seed_icc_checklist_template, stage_supplied_source
from app.services.roles import replace_scoped_assignment
from app.services import legacy_migration


def register_cli(app):
    @app.cli.command("seed-test-users")
    def seed_test_users():
        """Create approved local accounts covering every implemented RBAC role."""

        role_labels = {
            "SYSTEM_ADMINISTRATOR": "System Administrator",
            "OIA_FACULTY_ADMINISTRATOR": "OIA Faculty Administrator",
            "FACULTY_COORDINATOR": "Faculty Coordinator",
            "ICC_SECRETARY_USC": "ICC Secretary / USC",
            "ICC_EVENTS_HEAD": "ICC Events Head",
            "ICC_MEDIA_HEAD": "ICC Media Head",
            "ICC_CULTURALS_HEAD": "ICC Culturals Head",
            "ICC_ASSOCIATE": "ICC Associate",
            "IGP_HEAD": "IGP Head",
            "IGP_PROGRAM_LEAD": "IGP Program Lead",
            "VOLUNTEER": "Volunteer",
            "BUDDY": "Buddy",
            "PARTICIPANT": "Participant / Exchange Student",
            "AUDITOR": "Auditor / Read-only",
        }
        created = 0
        for code, label in role_labels.items():
            username = f"rbac_{code.lower()}"
            email = f"{username}@example.test"
            password = f"ICC-RBAC-2026-{code}!"
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
        db.session.commit()
        click.echo(f"Bootstrap administrator {username} created; password reset is required on first login.")

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

    @app.cli.command("migrate-legacy-data")
    def migrate_legacy_data():
        """Run every legacy-to-production data migration in dependency
        order, ahead of deleting the legacy tables. Idempotent: safe to
        re-run (each step is a no-op the second time)."""
        steps = (
            ("participants -> teams", legacy_migration.migrate_participants_to_teams),
            ("attendance -> sessions", legacy_migration.migrate_attendance_to_sessions),
            ("contributions -> records", legacy_migration.migrate_contributions_to_records),
            ("documents -> records", legacy_migration.migrate_documents_to_records),
            ("feedback -> responses", legacy_migration.migrate_feedback_to_responses),
        )
        for label, step in steps:
            result = step()
            click.echo(f"{label}: " + ", ".join(f"{key}={value}" for key, value in result.items()))

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
