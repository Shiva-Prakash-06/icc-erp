"""add project publication workflow

Revision ID: 27b173810b30
Revises: 4515efbb6138
Create Date: 2026-08-11 11:30:07.120875

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '27b173810b30'
down_revision = '4515efbb6138'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    sqlite = connection.dialect.name == 'sqlite'
    if sqlite:
        # SQLite cannot add a named FK without recreating the table. Disable
        # enforcement only for that schema-copy operation; `foreign_key_check`
        # below proves the populated graph remains valid before enforcement is
        # restored. PostgreSQL uses ordinary ALTER TABLE constraints.
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
    # Every existing project defaults to Private -- nothing is grandfathered
    # into public visibility. See PLAN.md "Additional release blockers".
    #
    # Add the nullable columns first so existing rows remain private. The
    # identity columns are then constrained in the database as well as the
    # ORM; otherwise `flask db check` reports schema drift and production
    # loses referential integrity.
    op.add_column('projects', sa.Column('publication_status', sa.String(length=20), nullable=False, server_default='Private'))
    op.add_column('projects', sa.Column('publication_requested_by_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('publication_approved_by_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_projects_publication_requested_by_id_users',
            'users', ['publication_requested_by_id'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_projects_publication_approved_by_id_users',
            'users', ['publication_approved_by_id'], ['id'], ondelete='SET NULL',
        )
    if sqlite:
        violations = connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise RuntimeError(f'Publication migration introduced foreign-key violations: {violations[:5]}')
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')


def downgrade():
    connection = op.get_bind()
    sqlite = connection.dialect.name == 'sqlite'
    if sqlite:
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_constraint('fk_projects_publication_approved_by_id_users', type_='foreignkey')
        batch_op.drop_constraint('fk_projects_publication_requested_by_id_users', type_='foreignkey')
    op.drop_column('projects', 'withdrawn_at')
    op.drop_column('projects', 'published_at')
    op.drop_column('projects', 'publication_approved_by_id')
    op.drop_column('projects', 'publication_requested_by_id')
    op.drop_column('projects', 'publication_status')
    if sqlite:
        violations = connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise RuntimeError(f'Publication downgrade introduced foreign-key violations: {violations[:5]}')
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
