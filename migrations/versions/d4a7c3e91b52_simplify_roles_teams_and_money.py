"""simplify roles, hand items to teams, one money list

Phase 1 of the simplification plan:

    work_tasks.assigned_team            a to-do item can be for a team
    checklist_item_statuses.assigned_team  ("media", "culturals", ...) so
                                        the Media and Culturals heads, who
                                        own no events, see their work
    reimbursement_entries.*             the one money list: who approved,
                                        when, why not, the bill, and where
                                        a carried-over line came from

Data changes:

    - checklist items get a team from their template's owner or category
      label ("Media" -> media), the same rule as app/services/teams.py
    - money statuses are mapped onto Asked / Approved / Paid / Not approved
    - ICC head assignments are no longer pinned to a wing
    - associates, buddies, participants and IGP programme leads become
      volunteers; programme leads are marked so Faculty can re-promote them
    - accounts still waiting for approval become volunteers, because
      sign-up no longer needs approval

The data changes are not reversed on downgrade: a downgrade drops the new
columns only.

Revision ID: d4a7c3e91b52
Revises: c2f8a1d40e77
Create Date: 2026-10-29 12:00:00.000000

"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = 'd4a7c3e91b52'
down_revision = 'c2f8a1d40e77'
branch_labels = None
depends_on = None


# A copy of app/services/teams.py's rule. Migrations never import app code:
# the app moves on and an old migration must keep meaning what it meant.
_LABEL_HINTS = (
    ("media", "media"), ("poster", "media"), ("photo", "media"), ("video", "media"), ("publicity", "media"),
    ("cultural", "culturals"), ("performance", "culturals"),
    ("igp", "igp"),
    ("usc", "usc"), ("secretary", "usc"),
    ("faculty", "faculty"),
    ("event", "events"),
)

_MONEY_WORDS = (
    ("Paid", ("paid", "settled", "reimbursed", "completed", "closed", "done")),
    ("Not approved", ("reject", "not approved", "declined", "cancel")),
    ("Approved", ("approved", "sanctioned", "committed")),
)

_RETIRED_ROLES = ("ICC_ASSOCIATE", "BUDDY", "PARTICIPANT", "IGP_PROGRAM_LEAD")


def _team(*labels):
    for label in labels:
        text = (label or "").strip().lower()
        for hint, team in _LABEL_HINTS:
            if text and hint in text:
                return team
    return None


def _money_status(value):
    text = (value or "").strip().lower()
    for status, words in _MONEY_WORDS:
        if any(word in text for word in words):
            return status
    return "Asked"


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Plain ADD COLUMN rather than batch mode: see c2f8a1d40e77 for why a
    # batch rebuild of a referenced table fails on a populated SQLite file.
    op.add_column('work_tasks', sa.Column('assigned_team', sa.String(length=20), nullable=True))
    op.create_index('ix_work_tasks_assigned_team', 'work_tasks', ['assigned_team'])
    op.add_column('checklist_item_statuses', sa.Column('assigned_team', sa.String(length=20), nullable=True))
    op.create_index('ix_checklist_item_statuses_assigned_team', 'checklist_item_statuses', ['assigned_team'])

    op.add_column('reimbursement_entries', sa.Column('approved_by_id', sa.Integer(), nullable=True))
    op.add_column('reimbursement_entries', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('reimbursement_entries', sa.Column('decision_comment', sa.Text(), nullable=True))
    op.add_column('reimbursement_entries', sa.Column('bill_document_id', sa.Integer(), nullable=True))
    op.add_column('reimbursement_entries', sa.Column('source_kind', sa.String(length=30), nullable=True))
    op.add_column('reimbursement_entries', sa.Column('source_id', sa.Integer(), nullable=True))
    if not is_sqlite:
        op.create_foreign_key('fk_reimbursement_entries_approved_by_id_users', 'reimbursement_entries', 'users',
                              ['approved_by_id'], ['id'], ondelete='SET NULL')
        op.create_foreign_key('fk_reimbursement_entries_bill_document_id_document_records', 'reimbursement_entries',
                              'document_records', ['bill_document_id'], ['id'], ondelete='SET NULL')

    checklist_items = sa.table(
        'checklist_item_statuses',
        sa.column('id', sa.Integer), sa.column('template_item_id', sa.Integer),
        sa.column('external_owner', sa.String), sa.column('assigned_team', sa.String),
    )
    template_items = sa.table(
        'checklist_template_items',
        sa.column('id', sa.Integer), sa.column('default_owner_label', sa.String), sa.column('category', sa.String),
    )
    rows = bind.execute(
        sa.select(checklist_items.c.id, checklist_items.c.external_owner,
                  template_items.c.default_owner_label, template_items.c.category)
        .select_from(checklist_items.join(template_items, checklist_items.c.template_item_id == template_items.c.id))
    ).fetchall()
    for row in rows:
        team = _team(row.external_owner, row.default_owner_label, row.category)
        if team:
            bind.execute(checklist_items.update().where(checklist_items.c.id == row.id).values(assigned_team=team))

    money = sa.table('reimbursement_entries', sa.column('id', sa.Integer), sa.column('status', sa.String))
    for row in bind.execute(sa.select(money.c.id, money.c.status)).fetchall():
        status = _money_status(row.status)
        if status != row.status:
            bind.execute(money.update().where(money.c.id == row.id).values(status=status))

    assignments = sa.table(
        'role_assignments',
        sa.column('id', sa.Integer), sa.column('user_id', sa.Integer), sa.column('role_code', sa.String),
        sa.column('wing_id', sa.Integer), sa.column('assignment_reason', sa.String),
        sa.column('campus_id', sa.Integer), sa.column('is_active', sa.Boolean),
        sa.column('public_id', sa.String), sa.column('can_view_sensitive_links', sa.Boolean),
        sa.column('created_at', sa.DateTime), sa.column('updated_at', sa.DateTime),
    )
    bind.execute(
        assignments.update()
        .where(assignments.c.role_code.in_(("ICC_EVENTS_HEAD", "ICC_MEDIA_HEAD", "ICC_CULTURALS_HEAD")))
        .values(wing_id=None)
    )
    bind.execute(
        assignments.update()
        .where(assignments.c.role_code == "IGP_PROGRAM_LEAD")
        .values(role_code="VOLUNTEER", assignment_reason="Was an IGP programme lead: check if they should be IGP head")
    )
    bind.execute(
        assignments.update()
        .where(assignments.c.role_code.in_(_RETIRED_ROLES))
        .values(role_code="VOLUNTEER")
    )

    users = sa.table(
        'users',
        sa.column('id', sa.Integer), sa.column('status', sa.String), sa.column('role', sa.String),
        sa.column('campus_id', sa.Integer), sa.column('approved_at', sa.DateTime),
    )
    now = datetime.now(timezone.utc)
    for user in bind.execute(sa.select(users.c.id, users.c.campus_id).where(users.c.status == "Pending")).fetchall():
        bind.execute(users.update().where(users.c.id == user.id).values(status="Approved", role="Volunteer", approved_at=now))
        bind.execute(assignments.insert().values(
            public_id=str(uuid.uuid4()), user_id=user.id, role_code="VOLUNTEER", campus_id=user.campus_id,
            is_active=True, can_view_sensitive_links=False, assignment_reason="Signed up",
            created_at=now, updated_at=now,
        ))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint('fk_reimbursement_entries_bill_document_id_document_records', 'reimbursement_entries', type_='foreignkey')
        op.drop_constraint('fk_reimbursement_entries_approved_by_id_users', 'reimbursement_entries', type_='foreignkey')
    with op.batch_alter_table('reimbursement_entries') as batch_op:
        for column in ('source_id', 'source_kind', 'bill_document_id', 'decision_comment', 'approved_at', 'approved_by_id'):
            batch_op.drop_column(column)
    op.drop_index('ix_checklist_item_statuses_assigned_team', table_name='checklist_item_statuses')
    with op.batch_alter_table('checklist_item_statuses') as batch_op:
        batch_op.drop_column('assigned_team')
    op.drop_index('ix_work_tasks_assigned_team', table_name='work_tasks')
    with op.batch_alter_table('work_tasks') as batch_op:
        batch_op.drop_column('assigned_team')
