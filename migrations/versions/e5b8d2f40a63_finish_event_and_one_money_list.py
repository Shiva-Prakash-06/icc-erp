"""finish event sign-off; budget and requests join the money list

Phase 2 of the simplification plan:

    projects.finish_requested_at / finish_requested_by_id / finish_note
                                    "Finish event": sent to Faculty, then
                                    signed off or returned with a note

Data changes:

    - stages come from dates now, so Draft / Pending Approval / Planned /
      Closing all become Active (Completed, Archived, Cancelled are kept)
    - every budget line and request is copied onto the event's money list
      (reimbursement_entries, source_kind "budget_line" / "request"); the
      originals stay untouched for the record
    - approvals that no longer exist are settled: submitted tasks and
      checklist items count as done; pending hours, buddy logs and feedback
      count as accepted

Not reversed on downgrade: a downgrade drops the new columns and the
carried-over money lines only.

Revision ID: e5b8d2f40a63
Revises: d4a7c3e91b52
Create Date: 2026-10-29 16:00:00.000000

"""
import uuid
from datetime import date, datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = 'e5b8d2f40a63'
down_revision = 'd4a7c3e91b52'
branch_labels = None
depends_on = None


_BUDGET_STATUS = {"Approved": "Approved", "Rejected": "Not approved"}
_REQUEST_STATUS = {"Approved": "Approved", "Completed": "Paid", "Rejected": "Not approved", "Cancelled": "Not approved"}


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.add_column('projects', sa.Column('finish_requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('finish_requested_by_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('finish_note', sa.Text(), nullable=True))
    if not is_sqlite:
        op.create_foreign_key('fk_projects_finish_requested_by_id_users', 'projects', 'users',
                              ['finish_requested_by_id'], ['id'], ondelete='SET NULL')

    projects = sa.table('projects', sa.column('id', sa.Integer), sa.column('status', sa.String),
                        sa.column('start_date', sa.Date))
    bind.execute(
        projects.update()
        .where(projects.c.status.in_(("Draft", "Pending Approval", "Planned", "Closing")))
        .values(status="Active")
    )
    start_dates = {row.id: row.start_date for row in bind.execute(sa.select(projects.c.id, projects.c.start_date))}

    money = sa.table(
        'reimbursement_entries',
        sa.column('public_id', sa.String), sa.column('project_id', sa.Integer), sa.column('date', sa.Date),
        sa.column('party_name', sa.String), sa.column('amount', sa.Numeric), sa.column('currency', sa.String),
        sa.column('particular', sa.Text), sa.column('status', sa.String), sa.column('created_by_id', sa.Integer),
        sa.column('decision_comment', sa.Text), sa.column('source_kind', sa.String), sa.column('source_id', sa.Integer),
        sa.column('created_at', sa.DateTime), sa.column('updated_at', sa.DateTime),
    )
    now = datetime.now(timezone.utc)
    already = {
        (row.source_kind, row.source_id)
        for row in bind.execute(sa.select(money.c.source_kind, money.c.source_id).where(money.c.source_kind.isnot(None)))
    }

    def carry(kind, source_id, project_id, amount, what_for, status, created_by_id=None, comment=None):
        if (kind, source_id) in already:
            return
        bind.execute(money.insert().values(
            public_id=str(uuid.uuid4()), project_id=project_id,
            date=start_dates.get(project_id) or date.today(), party_name="",
            amount=amount or 0, currency="INR", particular=what_for, status=status,
            created_by_id=created_by_id, decision_comment=comment,
            source_kind=kind, source_id=source_id, created_at=now, updated_at=now,
        ))

    budget = sa.table(
        'budget_lines',
        sa.column('id', sa.Integer), sa.column('project_id', sa.Integer), sa.column('category', sa.String),
        sa.column('description', sa.String), sa.column('estimated_amount', sa.Numeric),
        sa.column('approved_amount', sa.Numeric), sa.column('status', sa.String),
    )
    for row in bind.execute(sa.select(budget)).fetchall():
        status = _BUDGET_STATUS.get(row.status, "Asked")
        amount = row.approved_amount if status == "Approved" and row.approved_amount is not None else row.estimated_amount
        what_for = " · ".join(part for part in (row.category, row.description) if part) or "Budget"
        carry("budget_line", row.id, row.project_id, amount, what_for, status)

    requests = sa.table(
        'operational_requests',
        sa.column('id', sa.Integer), sa.column('project_id', sa.Integer), sa.column('request_type', sa.String),
        sa.column('title', sa.String), sa.column('details', sa.Text), sa.column('amount', sa.Numeric),
        sa.column('status', sa.String), sa.column('created_by_id', sa.Integer), sa.column('decision_comment', sa.Text),
    )
    for row in bind.execute(sa.select(requests)).fetchall():
        status = _REQUEST_STATUS.get(row.status, "Asked")
        comment = row.decision_comment or ("Cancelled" if row.status == "Cancelled" else None)
        what_for = row.title or row.request_type or "Request"
        if row.details:
            what_for = f"{what_for} · {row.details}"
        carry("request", row.id, row.project_id, row.amount, what_for, status, row.created_by_id, comment)

    for table_name, column, old, new in (
        ('work_tasks', 'status', 'Submitted', 'Completed'),
        ('checklist_item_statuses', 'status', 'Submitted', 'Completed'),
        ('contribution_records', 'approval_status', 'Pending', 'Approved'),
        ('buddy_logs', 'status', 'Pending', 'Approved'),
        ('feedback_responses', 'moderation_status', 'Pending', 'Approved'),
    ):
        table = sa.table(table_name, sa.column(column, sa.String))
        bind.execute(table.update().where(table.c[column] == old).values({column: new}))


def downgrade():
    bind = op.get_bind()
    money = sa.table('reimbursement_entries', sa.column('source_kind', sa.String))
    bind.execute(money.delete().where(money.c.source_kind.in_(("budget_line", "request"))))
    if bind.dialect.name != "sqlite":
        op.drop_constraint('fk_projects_finish_requested_by_id_users', 'projects', type_='foreignkey')
    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_column('finish_note')
        batch_op.drop_column('finish_requested_by_id')
        batch_op.drop_column('finish_requested_at')
