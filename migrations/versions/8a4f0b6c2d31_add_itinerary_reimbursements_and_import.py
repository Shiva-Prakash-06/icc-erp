"""add itinerary revisions, reimbursements, and import/document provenance

Revision ID: 8a4f0b6c2d31
Revises: 27b173810b30
Create Date: 2026-08-12 09:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a4f0b6c2d31'
down_revision = '27b173810b30'
branch_labels = None
depends_on = None


def public_columns():
    return [
        sa.Column("public_id", sa.String(36), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    connection = op.get_bind()
    sqlite = connection.dialect.name == 'sqlite'
    if sqlite:
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')

    # -- users.email becomes optional (provisioned buddy accounts may have no
    # email); uniqueness on non-null values is preserved by both SQLite and
    # PostgreSQL, which treat NULL as distinct in a UNIQUE constraint. --
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email', existing_type=sa.String(length=120), nullable=True)

    # -- itinerary_revisions --
    op.create_table(
        'itinerary_revisions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('import_batch_id', sa.Integer(), sa.ForeignKey('import_batches.id', ondelete='SET NULL')),
        sa.Column('source_document', sa.String(500), nullable=False),
        sa.Column('source_sha256', sa.String(64), nullable=False),
        sa.Column('parser_version', sa.String(30), nullable=False, server_default='1'),
        sa.Column('inferred_metadata', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('warnings', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id')),
        *public_columns(),
    )

    # -- reimbursement_entries --
    op.create_table(
        'reimbursement_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('party_name', sa.String(255), nullable=False),
        sa.Column('bill_number', sa.String(120)),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='INR'),
        sa.Column('particular', sa.Text()),
        sa.Column('status', sa.String(30), nullable=False, server_default='Pending'),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('source_import_row_id', sa.Integer(), sa.ForeignKey('import_rows.id', ondelete='SET NULL')),
        *public_columns(),
        sa.CheckConstraint('amount >= 0', name='ck_reimbursement_amount_nonnegative'),
    )

    # -- project_sessions: itinerary provenance, all-day, active flag --
    op.add_column('project_sessions', sa.Column('itinerary_revision_id', sa.Integer(), nullable=True))
    op.add_column('project_sessions', sa.Column('source_key', sa.String(120), nullable=True))
    op.add_column('project_sessions', sa.Column('is_all_day', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('project_sessions', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('project_sessions', sa.Column('import_batch_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('project_sessions', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_project_sessions_itinerary_revision_id', 'itinerary_revisions',
            ['itinerary_revision_id'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_project_sessions_import_batch_id', 'import_batches',
            ['import_batch_id'], ['id'], ondelete='SET NULL',
        )

    # -- document_records: checksum + uploader --
    op.add_column('document_records', sa.Column('checksum_sha256', sa.String(64), nullable=True))
    op.add_column('document_records', sa.Column('uploaded_by_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('document_records', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_document_records_uploaded_by_id_users', 'users',
            ['uploaded_by_id'], ['id'], ondelete='SET NULL',
        )

    # -- import_batches: project + source-document linkage --
    op.add_column('import_batches', sa.Column('project_id', sa.Integer(), nullable=True))
    op.add_column('import_batches', sa.Column('source_document_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('import_batches', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_import_batches_project_id_projects', 'projects',
            ['project_id'], ['id'], ondelete='CASCADE',
        )
        batch_op.create_foreign_key(
            'fk_import_batches_source_document_id_document_records', 'document_records',
            ['source_document_id'], ['id'], ondelete='SET NULL',
        )

    # -- buddy_assignments: optional source-import linkage --
    op.add_column('buddy_assignments', sa.Column('source_import_row_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('buddy_assignments', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_buddy_assignments_source_import_row_id', 'import_rows',
            ['source_import_row_id'], ['id'], ondelete='SET NULL',
        )

    # -- Backfill effective status from dates for ordinary projects. Cancelled
    # and Archived are exceptional administrative states and are preserved
    # untouched; every other status is derived from today's date against the
    # project's start/end envelope. See PLAN.md section 4. --
    projects = sa.table(
        'projects',
        sa.column('id', sa.Integer),
        sa.column('status', sa.String),
        sa.column('start_date', sa.Date),
        sa.column('end_date', sa.Date),
    )
    today = sa.func.current_date()
    op.execute(
        projects.update()
        .where(sa.and_(
            projects.c.status.notin_(['Cancelled', 'Archived']),
            projects.c.start_date > today,
        ))
        .values(status='Planned')
    )
    op.execute(
        projects.update()
        .where(sa.and_(
            projects.c.status.notin_(['Cancelled', 'Archived']),
            projects.c.start_date <= today,
            projects.c.end_date >= today,
        ))
        .values(status='Active')
    )
    op.execute(
        projects.update()
        .where(sa.and_(
            projects.c.status.notin_(['Cancelled', 'Archived']),
            projects.c.end_date < today,
        ))
        .values(status='Completed')
    )

    if sqlite:
        violations = connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise RuntimeError(f'Itinerary/reimbursement migration introduced foreign-key violations: {violations[:5]}')
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')


def downgrade():
    connection = op.get_bind()
    sqlite = connection.dialect.name == 'sqlite'
    if sqlite:
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')

    with op.batch_alter_table('buddy_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_buddy_assignments_source_import_row_id', type_='foreignkey')
    op.drop_column('buddy_assignments', 'source_import_row_id')

    with op.batch_alter_table('import_batches', schema=None) as batch_op:
        batch_op.drop_constraint('fk_import_batches_source_document_id_document_records', type_='foreignkey')
        batch_op.drop_constraint('fk_import_batches_project_id_projects', type_='foreignkey')
    op.drop_column('import_batches', 'source_document_id')
    op.drop_column('import_batches', 'project_id')

    with op.batch_alter_table('document_records', schema=None) as batch_op:
        batch_op.drop_constraint('fk_document_records_uploaded_by_id_users', type_='foreignkey')
    op.drop_column('document_records', 'uploaded_by_id')
    op.drop_column('document_records', 'checksum_sha256')

    with op.batch_alter_table('project_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_project_sessions_import_batch_id', type_='foreignkey')
        batch_op.drop_constraint('fk_project_sessions_itinerary_revision_id', type_='foreignkey')
    op.drop_column('project_sessions', 'import_batch_id')
    op.drop_column('project_sessions', 'is_active')
    op.drop_column('project_sessions', 'is_all_day')
    op.drop_column('project_sessions', 'source_key')
    op.drop_column('project_sessions', 'itinerary_revision_id')

    op.drop_table('reimbursement_entries')
    op.drop_table('itinerary_revisions')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email', existing_type=sa.String(length=120), nullable=False)

    if sqlite:
        violations = connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise RuntimeError(f'Itinerary/reimbursement downgrade introduced foreign-key violations: {violations[:5]}')
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
