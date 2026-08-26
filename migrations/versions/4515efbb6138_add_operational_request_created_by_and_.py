"""add operational request created_by and submitted_by

Revision ID: 4515efbb6138
Revises: 80118b060084
Create Date: 2026-08-11 11:24:18.289975

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4515efbb6138'
down_revision = '80118b060084'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('operational_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('submitted_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_operational_requests_created_by_id_users', 'users', ['created_by_id'], ['id'])
        batch_op.create_foreign_key('fk_operational_requests_submitted_by_id_users', 'users', ['submitted_by_id'], ['id'])

    connection = op.get_bind()
    # Backfill from audit history so existing active requests are attributable
    # for the self-approval guard added alongside this migration.
    audit_events = sa.table(
        'audit_events',
        sa.column('entity_type', sa.String),
        sa.column('entity_public_id', sa.String),
        sa.column('action', sa.String),
        sa.column('actor_user_id', sa.Integer),
        sa.column('occurred_at', sa.DateTime),
    )
    operational_requests = sa.table(
        'operational_requests',
        sa.column('id', sa.Integer),
        sa.column('public_id', sa.String),
        sa.column('status', sa.String),
        sa.column('created_by_id', sa.Integer),
        sa.column('submitted_by_id', sa.Integer),
        sa.column('owner_person_id', sa.Integer),
    )
    users = sa.table('users', sa.column('id', sa.Integer), sa.column('person_id', sa.Integer))

    for request_row in connection.execute(sa.select(operational_requests.c.id, operational_requests.c.public_id, operational_requests.c.owner_person_id)):
        create_event = connection.execute(
            sa.select(audit_events.c.actor_user_id)
            .where(audit_events.c.entity_type == 'OperationalRequest')
            .where(audit_events.c.entity_public_id == request_row.public_id)
            .where(audit_events.c.action == 'operational_request.create')
            .order_by(audit_events.c.occurred_at.asc())
            .limit(1)
        ).first()
        submit_event = connection.execute(
            sa.select(audit_events.c.actor_user_id)
            .where(audit_events.c.entity_type == 'OperationalRequest')
            .where(audit_events.c.entity_public_id == request_row.public_id)
            .where(audit_events.c.action == 'operational_request.transition')
            .order_by(audit_events.c.occurred_at.asc())
            .limit(1)
        ).first()
        created_by_id = create_event.actor_user_id if create_event else None
        if created_by_id is None and request_row.owner_person_id is not None:
            owner = connection.execute(
                sa.select(users.c.id).where(users.c.person_id == request_row.owner_person_id)
            ).first()
            created_by_id = owner.id if owner else None
        submitted_by_id = submit_event.actor_user_id if submit_event else created_by_id
        if created_by_id is not None or submitted_by_id is not None:
            connection.execute(
                operational_requests.update()
                .where(operational_requests.c.id == request_row.id)
                .values(created_by_id=created_by_id, submitted_by_id=submitted_by_id)
            )


def downgrade():
    with op.batch_alter_table('operational_requests', schema=None) as batch_op:
        batch_op.drop_constraint('fk_operational_requests_submitted_by_id_users', type_='foreignkey')
        batch_op.drop_constraint('fk_operational_requests_created_by_id_users', type_='foreignkey')
        batch_op.drop_column('submitted_by_id')
        batch_op.drop_column('created_by_id')
