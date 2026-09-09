"""widen import_batches.idempotency_key so PostgreSQL accepts every importer key

The column was varchar(120), but two importers build keys longer than that:

    v1:icc_volunteer_attendance:<36-char uuid>:<64-char sha256>   129 chars
    v1:buddy_allocations:<36-char uuid>:<64-char sha256>          122 chars

SQLite ignores a VARCHAR length, so this never surfaced locally; PostgreSQL
enforces it, so in production both importers failed outright with
StringDataRightTruncation. Found while running the suite against PostgreSQL
for the beta readiness work (BETA-READINESS-PLAN W2.3).

255 leaves room for a longer importer name or a versioned prefix without
revisiting this again.

Revision ID: b1c4d7e9f210
Revises: 8a4f0b6c2d31
Create Date: 2026-09-09 11:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c4d7e9f210'
down_revision = '8a4f0b6c2d31'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.alter_column(
            "idempotency_key",
            existing_type=sa.String(120),
            type_=sa.String(255),
            existing_nullable=False,
        )


def downgrade():
    # Rows with a key longer than 120 characters would be truncated into
    # collisions, so refuse rather than corrupt the idempotency ledger.
    connection = op.get_bind()
    overlong = connection.execute(
        sa.text("SELECT COUNT(*) FROM import_batches WHERE LENGTH(idempotency_key) > 120")
    ).scalar()
    if overlong:
        raise RuntimeError(
            f"{overlong} import batch key(s) exceed 120 characters; narrowing the column would collide them."
        )
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.alter_column(
            "idempotency_key",
            existing_type=sa.String(255),
            type_=sa.String(120),
            existing_nullable=False,
        )
