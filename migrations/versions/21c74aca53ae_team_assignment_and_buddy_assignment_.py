"""team assignment and buddy assignment schema extensions

Revision ID: 21c74aca53ae
Revises: 9b70b9a2c001
Create Date: 2026-08-01 18:51:54.121281

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '21c74aca53ae'
down_revision = '9b70b9a2c001'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('buddy_assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('buddy_person_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('exchange_student_person_id', sa.Integer(), nullable=True))
        batch_op.alter_column('buddy_user_id',
               existing_type=sa.INTEGER(),
               nullable=True)
        batch_op.alter_column('exchange_student_id',
               existing_type=sa.INTEGER(),
               nullable=True)
        batch_op.create_foreign_key('fk_buddy_assignment_exchange_person', 'people', ['exchange_student_person_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_buddy_assignment_buddy_person', 'people', ['buddy_person_id'], ['id'], ondelete='SET NULL')
        batch_op.create_check_constraint(
            'ck_buddy_identity',
            '(buddy_user_id IS NOT NULL OR buddy_person_id IS NOT NULL) '
            'AND (exchange_student_id IS NOT NULL OR exchange_student_person_id IS NOT NULL)',
        )

    with op.batch_alter_table('team_assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('cohort_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('nationality', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=20), server_default='Active', nullable=False))
        batch_op.create_foreign_key('fk_team_assignment_cohort', 'cohorts', ['cohort_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_team_assignment_user', 'users', ['user_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('team_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_team_assignment_user', type_='foreignkey')
        batch_op.drop_constraint('fk_team_assignment_cohort', type_='foreignkey')
        batch_op.drop_column('status')
        batch_op.drop_column('nationality')
        batch_op.drop_column('cohort_id')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('buddy_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('ck_buddy_identity', type_='check')
        batch_op.drop_constraint('fk_buddy_assignment_buddy_person', type_='foreignkey')
        batch_op.drop_constraint('fk_buddy_assignment_exchange_person', type_='foreignkey')
        batch_op.alter_column('exchange_student_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.alter_column('buddy_user_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.drop_column('exchange_student_person_id')
        batch_op.drop_column('buddy_person_id')
