"""add first-run onboarding state to users

Four columns behind the welcome modal, the anchored tour and the
getting-started checklist:

    onboarding_seen         the welcome modal has been shown once
    onboarding_step         1-based tour step, 0 when no tour is running
    onboarding_dismissed_at when the user skipped or finished
    onboarding_signals      JSON set of getting-started tasks that leave no
                            other row behind (command palette used, project
                            opened, audit trail read)

Existing accounts are backfilled to seen=True: everyone already using the
platform has found their way around, and showing them a first-run modal on
their next page load would be a regression, not an introduction.

Revision ID: c2f8a1d40e77
Revises: b1c4d7e9f210
Create Date: 2026-09-16 10:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c2f8a1d40e77'
down_revision = 'b1c4d7e9f210'
branch_labels = None
depends_on = None


def upgrade():
    # Plain ADD COLUMN, not batch_alter_table. Adding a column is the one
    # schema change SQLite supports natively, and batch mode instead
    # recreates the table -- copy out, DROP, rename in. With
    # `PRAGMA foreign_keys=ON` (app/database.py sets it on every
    # connection) that DROP runs an implicit DELETE and trips every
    # non-cascading reference to `users`, so upgrading a populated SQLite
    # database died with "FOREIGN KEY constraint failed" on a migration
    # that only adds columns. CI missed it because its fixtures hold too
    # few referencing rows. PostgreSQL is unaffected either way: batch
    # mode degrades to exactly these ALTERs there.
    op.add_column('users', sa.Column('onboarding_seen', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('onboarding_step', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('onboarding_dismissed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('onboarding_signals', sa.JSON(), nullable=False, server_default='{}'))
    op.execute("UPDATE users SET onboarding_seen = 1" if op.get_bind().dialect.name == "sqlite"
               else "UPDATE users SET onboarding_seen = TRUE")


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('onboarding_signals')
        batch_op.drop_column('onboarding_dismissed_at')
        batch_op.drop_column('onboarding_step')
        batch_op.drop_column('onboarding_seen')
