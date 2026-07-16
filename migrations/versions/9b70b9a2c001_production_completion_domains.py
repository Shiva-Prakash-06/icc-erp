"""Production completion domains

Revision ID: 9b70b9a2c001
Revises: 3d011a633fd7
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa
import uuid


revision = "9b70b9a2c001"
down_revision = "3d011a633fd7"
branch_labels = None
depends_on = None


def public_columns():
    return [
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("public_id"),
    ]


def upgrade():
    op.create_table(
        "controlled_vocabularies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain", sa.String(80), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *public_columns(),
        sa.UniqueConstraint("domain", "code", "version", name="uq_vocabulary_version"),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(60), unique=True, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("operating_unit_id", sa.Integer(), sa.ForeignKey("operating_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wing_id", sa.Integer(), sa.ForeignKey("wings.id", ondelete="SET NULL")),
        sa.Column("fixed_for_academic_year", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *public_columns(),
    )
    op.create_table(
        "governance_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("academic_year_id", sa.Integer(), sa.ForeignKey("academic_years.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operating_unit_id", sa.Integer(), sa.ForeignKey("operating_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="Planned"),
        *public_columns(),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_governance_term_dates"),
        sa.UniqueConstraint("academic_year_id", "operating_unit_id", "name", name="uq_governance_term"),
    )
    op.create_table(
        "identity_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_subject", sa.String(255), nullable=False),
        sa.Column("email_at_link", sa.String(255), nullable=False),
        sa.Column("linked_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        *public_columns(),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_identity_provider_subject"),
    )
    op.create_table(
        "cohorts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(60), unique=True, nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("partner_institution_id", sa.Integer(), sa.ForeignKey("partner_institutions.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("expected_participants", sa.Integer()),
        sa.Column("status", sa.String(30), nullable=False, server_default="Planned"),
        *public_columns(),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_cohort_dates"),
        sa.CheckConstraint("expected_participants IS NULL OR expected_participants >= 0", name="ck_cohort_size"),
    )
    op.create_table(
        "recruitment_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("people.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("desired_role", sa.String(100), nullable=False),
        sa.Column("skills_snapshot", sa.Text()),
        sa.Column("availability_snapshot", sa.Text()),
        sa.Column("statement", sa.Text()),
        sa.Column("interview_at", sa.DateTime(timezone=True)),
        sa.Column("interview_notes", sa.Text()),
        sa.Column("decision", sa.String(30), nullable=False, server_default="Submitted"),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("consent_status", sa.String(30), nullable=False, server_default="Not Recorded"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *public_columns(),
        sa.UniqueConstraint("person_id", "project_id", "desired_role", name="uq_recruitment_application"),
    )
    op.create_table(
        "project_risks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("likelihood", sa.String(20), nullable=False, server_default="Medium"),
        sa.Column("impact", sa.String(20), nullable=False, server_default="Medium"),
        sa.Column("mitigation", sa.Text()),
        sa.Column("owner_person_id", sa.Integer(), sa.ForeignKey("people.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(30), nullable=False, server_default="Open"),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *public_columns(),
    )
    op.create_table(
        "task_status_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("work_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_status", sa.String(30)),
        sa.Column("new_status", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("evidence_reference", sa.String(500)),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("public_id", sa.String(36), unique=True, nullable=False),
    )
    op.create_table(
        "attendance_change_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attendance_id", sa.Integer(), sa.ForeignKey("session_attendance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_status", sa.String(20)),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("public_id", sa.String(36), unique=True, nullable=False),
    )
    op.create_table(
        "aggregate_attendance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("project_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("verified_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("source_note", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *public_columns(),
        sa.CheckConstraint("count >= 0", name="ck_aggregate_attendance_nonnegative"),
        sa.UniqueConstraint("session_id", "category", name="uq_aggregate_attendance_category"),
    )
    op.create_table(
        "contribution_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("people.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wing_id", sa.Integer(), sa.ForeignKey("wings.id", ondelete="SET NULL")),
        sa.Column("activity_type", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_hours", sa.Numeric(7, 2), nullable=False),
        sa.Column("evidence_reference", sa.String(500)),
        sa.Column("approval_status", sa.String(30), nullable=False, server_default="Pending"),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *public_columns(),
        sa.CheckConstraint("duration_hours >= 0", name="ck_contribution_hours"),
    )
    op.create_table(
        "document_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False, server_default="Internal"),
        sa.Column("mandatory_for_closure", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("owner_person_id", sa.Integer(), sa.ForeignKey("people.id", ondelete="SET NULL")),
        sa.Column("source_template_code", sa.String(80)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *public_columns(),
    )
    op.create_table(
        "approval_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_public_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("public_id", sa.String(36), unique=True, nullable=False),
    )
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        *public_columns(),
        sa.UniqueConstraint("user_id", "event_type", name="uq_notification_preference"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="Info"),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(500)),
        sa.Column("idempotency_key", sa.String(160), unique=True, nullable=False),
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_status", sa.String(30), nullable=False, server_default="Pending"),
        *public_columns(),
    )
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("notification_id", sa.Integer(), sa.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provider_reference", sa.String(255)),
        sa.Column("error_summary", sa.String(500)),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("public_id", sa.String(36), unique=True, nullable=False),
        sa.UniqueConstraint("notification_id", "channel", "attempt_number", name="uq_notification_attempt"),
    )
    op.create_table(
        "report_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("report_type", sa.String(60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schema_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *public_columns(),
        sa.UniqueConstraint("code", "version", name="uq_report_definition_version"),
    )
    op.create_table(
        "report_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("definition_id", sa.Integer(), sa.ForeignKey("report_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("idempotency_key", sa.String(160), unique=True, nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(30), nullable=False, server_default="Queued"),
        sa.Column("output_format", sa.String(10), nullable=False, server_default="json"),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("report_snapshots.id", ondelete="SET NULL")),
        sa.Column("error_summary", sa.String(500)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *public_columns(),
    )
    op.create_table(
        "sensitive_access_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_public_id", sa.String(36), nullable=False),
        sa.Column("project_public_id", sa.String(36)),
        sa.Column("purpose", sa.String(180), nullable=False),
        sa.Column("request_id", sa.String(80)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("public_id", sa.String(36), unique=True, nullable=False),
    )
    op.create_table(
        "import_mapping_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_id", sa.Integer(), sa.ForeignKey("import_rows.id", ondelete="CASCADE")),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("source_value", sa.String(500)),
        sa.Column("normalized_value", sa.String(500)),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("rationale", sa.Text()),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *public_columns(),
        sa.UniqueConstraint("batch_id", "row_id", "field_name", name="uq_import_mapping_decision"),
    )

    with op.batch_alter_table("people") as batch:
        batch.add_column(sa.Column("consent_recorded_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("privacy_classification", sa.String(30), nullable=False, server_default="Internal"))
        batch.add_column(sa.Column("emergency_contact_name", sa.String(150)))
        batch.add_column(sa.Column("emergency_contact_phone", sa.String(40)))
        batch.add_column(sa.Column("contact_visibility", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("public_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("password_changed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("password_reset_token_hash", sa.String(128)))
        batch.add_column(sa.Column("password_reset_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    users = sa.table("users", sa.column("id", sa.Integer()), sa.column("public_id", sa.String(36)))
    connection = op.get_bind()
    for user_id in connection.execute(sa.select(users.c.id)).scalars():
        connection.execute(users.update().where(users.c.id == user_id).values(public_id=str(uuid.uuid4())))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("public_id", existing_type=sa.String(36), nullable=False)
        batch.create_unique_constraint("uq_users_public_id", ["public_id"])
    with op.batch_alter_table("role_assignments") as batch:
        batch.add_column(sa.Column("position_id", sa.Integer()))
        batch.add_column(sa.Column("governance_term_id", sa.Integer()))
        batch.add_column(sa.Column("assignment_reason", sa.Text()))
        batch.create_foreign_key("fk_role_position", "positions", ["position_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_role_governance_term", "governance_terms", ["governance_term_id"], ["id"], ondelete="SET NULL")
    with op.batch_alter_table("feedback_responses") as batch:
        batch.add_column(sa.Column("response_key_hash", sa.String(64)))
        batch.create_unique_constraint("uq_feedback_response_key", ["form_id", "response_key_hash"])
    with op.batch_alter_table("project_participants") as batch:
        batch.add_column(sa.Column("public_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("person_id", sa.Integer()))
        batch.add_column(sa.Column("cohort_id", sa.Integer()))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch.create_foreign_key("fk_participant_person", "people", ["person_id"], ["id"], ondelete="CASCADE")
        batch.create_foreign_key("fk_participant_cohort", "cohorts", ["cohort_id"], ["id"], ondelete="SET NULL")
        batch.create_unique_constraint("uq_project_person_participant", ["project_id", "person_id"])
    _backfill_public_ids("project_participants")
    with op.batch_alter_table("project_participants") as batch:
        batch.alter_column("public_id", existing_type=sa.String(36), nullable=False)
        batch.create_unique_constraint("uq_project_participants_public_id", ["public_id"])
        batch.create_check_constraint("ck_participant_identity", "user_id IS NOT NULL OR person_id IS NOT NULL")
    with op.batch_alter_table("buddy_assignments") as batch:
        batch.add_column(sa.Column("public_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    _backfill_public_ids("buddy_assignments")
    with op.batch_alter_table("buddy_assignments") as batch:
        batch.alter_column("public_id", existing_type=sa.String(36), nullable=False)
        batch.create_unique_constraint("uq_buddy_assignments_public_id", ["public_id"])
    with op.batch_alter_table("buddy_logs") as batch:
        batch.add_column(sa.Column("public_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("concern_level", sa.String(30)))
        batch.add_column(sa.Column("escalation_owner_id", sa.Integer()))
        batch.add_column(sa.Column("escalation_status", sa.String(30)))
        batch.add_column(sa.Column("resolution", sa.Text()))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.create_foreign_key("fk_buddy_log_escalation_owner", "users", ["escalation_owner_id"], ["id"], ondelete="SET NULL")
    _backfill_public_ids("buddy_logs")
    with op.batch_alter_table("buddy_logs") as batch:
        batch.alter_column("public_id", existing_type=sa.String(36), nullable=False)
        batch.create_unique_constraint("uq_buddy_logs_public_id", ["public_id"])
    _add_completion_columns()


def _add_completion_columns():
    columns = {
        "work_tasks": [
            sa.Column("reminder_at", sa.DateTime(timezone=True)),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        ],
        "checklist_item_statuses": [
            sa.Column("waived_by_id", sa.Integer()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        ],
        "team_assignments": [sa.Column("version", sa.Integer(), nullable=False, server_default="1")],
        "session_attendance": [sa.Column("version", sa.Integer(), nullable=False, server_default="1")],
        "document_records": [
            sa.Column("drive_name", sa.String(255)),
            sa.Column("drive_mime_type", sa.String(150)),
            sa.Column("drive_visibility", sa.String(40)),
            sa.Column("drive_permission_metadata", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("drive_modified_at", sa.DateTime(timezone=True)),
            sa.Column("drive_validated_at", sa.DateTime(timezone=True)),
            sa.Column("drive_validation_status", sa.String(30), nullable=False, server_default="Unverified"),
            sa.Column("waiver_reason", sa.Text()),
            sa.Column("waived_by_id", sa.Integer()),
            sa.Column("rejection_reason", sa.Text()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        ],
        "budget_lines": [
            sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        ],
        "operational_requests": [
            sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
            sa.Column("decision_comment", sa.Text()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        ],
        "feedback_forms": [
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("opens_at", sa.DateTime(timezone=True)),
            sa.Column("closes_at", sa.DateTime(timezone=True)),
        ],
        "import_batches": [
            sa.Column("importer_version", sa.String(30), nullable=False, server_default="2"),
            sa.Column("mapping_version", sa.String(30), nullable=False, server_default="1"),
        ],
        "report_snapshots": [
            sa.Column("publication_status", sa.String(30), nullable=False, server_default="Unpublished"),
            sa.Column("published_at", sa.DateTime(timezone=True)),
        ],
    }
    for table_name, table_columns in columns.items():
        with op.batch_alter_table(table_name) as batch:
            for column in table_columns:
                batch.add_column(column)
            if table_name == "checklist_item_statuses":
                batch.create_foreign_key("fk_checklist_waiver_user", "users", ["waived_by_id"], ["id"], ondelete="SET NULL")
            if table_name == "document_records":
                batch.create_foreign_key("fk_document_waiver_user", "users", ["waived_by_id"], ["id"], ondelete="SET NULL")


def _backfill_public_ids(table_name):
    table = sa.table(table_name, sa.column("id", sa.Integer()), sa.column("public_id", sa.String(36)))
    connection = op.get_bind()
    for item_id in connection.execute(sa.select(table.c.id)).scalars():
        connection.execute(table.update().where(table.c.id == item_id).values(public_id=str(uuid.uuid4())))


def downgrade():
    completion_columns = {
        "report_snapshots": ["published_at", "publication_status"],
        "import_batches": ["mapping_version", "importer_version"],
        "feedback_forms": ["closes_at", "opens_at", "version"],
        "operational_requests": ["version", "decision_comment", "currency"],
        "budget_lines": ["version", "currency"],
        "document_records": ["version", "rejection_reason", "waived_by_id", "waiver_reason", "drive_validation_status", "drive_validated_at", "drive_modified_at", "drive_permission_metadata", "drive_visibility", "drive_mime_type", "drive_name"],
        "session_attendance": ["version"],
        "team_assignments": ["version"],
        "checklist_item_statuses": ["version", "waived_by_id"],
        "work_tasks": ["version", "reminder_at"],
    }
    for table_name, column_names in completion_columns.items():
        with op.batch_alter_table(table_name) as batch:
            if table_name == "document_records":
                batch.drop_constraint("fk_document_waiver_user", type_="foreignkey")
            if table_name == "checklist_item_statuses":
                batch.drop_constraint("fk_checklist_waiver_user", type_="foreignkey")
            for column_name in column_names:
                batch.drop_column(column_name)
    with op.batch_alter_table("role_assignments") as batch:
        batch.drop_constraint("fk_role_governance_term", type_="foreignkey")
        batch.drop_constraint("fk_role_position", type_="foreignkey")
        batch.drop_column("assignment_reason")
        batch.drop_column("governance_term_id")
        batch.drop_column("position_id")
    with op.batch_alter_table("feedback_responses") as batch:
        batch.drop_constraint("uq_feedback_response_key", type_="unique")
        batch.drop_column("response_key_hash")
    with op.batch_alter_table("buddy_logs") as batch:
        batch.drop_constraint("uq_buddy_logs_public_id", type_="unique")
        batch.drop_constraint("fk_buddy_log_escalation_owner", type_="foreignkey")
        for name in ["version", "resolution", "escalation_status", "escalation_owner_id", "concern_level", "public_id"]:
            batch.drop_column(name)
    with op.batch_alter_table("buddy_assignments") as batch:
        batch.drop_constraint("uq_buddy_assignments_public_id", type_="unique")
        batch.drop_column("version")
        batch.drop_column("public_id")
    with op.batch_alter_table("project_participants") as batch:
        batch.drop_constraint("ck_participant_identity", type_="check")
        batch.drop_constraint("uq_project_participants_public_id", type_="unique")
        batch.drop_constraint("uq_project_person_participant", type_="unique")
        batch.drop_constraint("fk_participant_cohort", type_="foreignkey")
        batch.drop_constraint("fk_participant_person", type_="foreignkey")
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        for name in ["version", "cohort_id", "person_id", "public_id"]:
            batch.drop_column(name)
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_public_id", type_="unique")
        for name in ["version", "is_archived", "session_version", "password_reset_expires_at", "password_reset_token_hash", "password_changed_at", "public_id"]:
            batch.drop_column(name)
    with op.batch_alter_table("people") as batch:
        for name in ["contact_visibility", "emergency_contact_phone", "emergency_contact_name", "privacy_classification", "consent_recorded_at"]:
            batch.drop_column(name)

    for table_name in [
        "import_mapping_decisions", "sensitive_access_events", "report_jobs", "report_definitions",
        "notification_delivery_attempts", "notifications", "notification_preferences", "approval_events",
        "document_requirements", "contribution_records", "aggregate_attendance", "attendance_change_events",
        "task_status_events", "project_risks", "recruitment_applications", "cohorts", "identity_links",
        "governance_terms", "positions", "controlled_vocabularies",
    ]:
        op.drop_table(table_name)
