from __future__ import annotations

import os

import click
from flask import current_app

from app.database import db
from app.models.user import User
from app.services.imports import _reference_data
from app.services.imports import commit_batch, stage_supplied_source


def register_cli(app):
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
