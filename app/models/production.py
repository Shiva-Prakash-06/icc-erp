"""Production completion entities for governance, history, jobs, and controls."""

from __future__ import annotations

from app.database import db
from app.models.erp import PublicIdMixin, TimestampMixin


class ControlledVocabulary(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "controlled_vocabularies"

    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(80), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    label = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("domain", "code", "version", name="uq_vocabulary_version"),
    )


class Position(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "positions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    operating_unit_id = db.Column(db.Integer, db.ForeignKey("operating_units.id", ondelete="CASCADE"), nullable=False)
    wing_id = db.Column(db.Integer, db.ForeignKey("wings.id", ondelete="SET NULL"), nullable=True)
    fixed_for_academic_year = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class GovernanceTerm(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "governance_terms"

    id = db.Column(db.Integer, primary_key=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_years.id", ondelete="CASCADE"), nullable=False)
    operating_unit_id = db.Column(db.Integer, db.ForeignKey("operating_units.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    starts_on = db.Column(db.Date, nullable=False)
    ends_on = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Planned")

    __table_args__ = (
        db.CheckConstraint("ends_on >= starts_on", name="ck_governance_term_dates"),
        db.UniqueConstraint("academic_year_id", "operating_unit_id", "name", name="uq_governance_term"),
    )


class IdentityLink(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "identity_links"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = db.Column(db.String(40), nullable=False)
    provider_subject = db.Column(db.String(255), nullable=False)
    email_at_link = db.Column(db.String(255), nullable=False)
    linked_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("provider", "provider_subject", name="uq_identity_provider_subject"),
    )


class Cohort(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "cohorts"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(180), nullable=False)
    partner_institution_id = db.Column(db.Integer, db.ForeignKey("partner_institutions.id", ondelete="SET NULL"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    starts_on = db.Column(db.Date, nullable=False)
    ends_on = db.Column(db.Date, nullable=False)
    expected_participants = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Planned")

    __table_args__ = (
        db.CheckConstraint("ends_on >= starts_on", name="ck_cohort_dates"),
        db.CheckConstraint("expected_participants IS NULL OR expected_participants >= 0", name="ck_cohort_size"),
    )


class RecruitmentApplication(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "recruitment_applications"

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    desired_role = db.Column(db.String(100), nullable=False)
    skills_snapshot = db.Column(db.Text, nullable=True)
    availability_snapshot = db.Column(db.Text, nullable=True)
    statement = db.Column(db.Text, nullable=True)
    interview_at = db.Column(db.DateTime(timezone=True), nullable=True)
    interview_notes = db.Column(db.Text, nullable=True)
    decision = db.Column(db.String(30), nullable=False, default="Submitted")
    decision_reason = db.Column(db.Text, nullable=True)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    consent_status = db.Column(db.String(30), nullable=False, default="Not Recorded")
    version = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (
        db.UniqueConstraint("person_id", "project_id", "desired_role", name="uq_recruitment_application"),
    )


class ProjectRisk(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "project_risks"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    likelihood = db.Column(db.String(20), nullable=False, default="Medium")
    impact = db.Column(db.String(20), nullable=False, default="Medium")
    mitigation = db.Column(db.Text, nullable=True)
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Open")
    is_critical = db.Column(db.Boolean, nullable=False, default=False)
    version = db.Column(db.Integer, nullable=False, default=1)


class TaskStatusEvent(PublicIdMixin, db.Model):
    __tablename__ = "task_status_events"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("work_tasks.id", ondelete="CASCADE"), nullable=False)
    previous_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    evidence_reference = db.Column(db.String(500), nullable=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())


class AttendanceChangeEvent(PublicIdMixin, db.Model):
    __tablename__ = "attendance_change_events"

    id = db.Column(db.Integer, primary_key=True)
    attendance_id = db.Column(db.Integer, db.ForeignKey("session_attendance.id", ondelete="CASCADE"), nullable=False)
    previous_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())


class AggregateAttendance(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "aggregate_attendance"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("project_sessions.id", ondelete="CASCADE"), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    count = db.Column(db.Integer, nullable=False)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    source_note = db.Column(db.Text, nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (
        db.CheckConstraint("count >= 0", name="ck_aggregate_attendance_nonnegative"),
        db.UniqueConstraint("session_id", "category", name="uq_aggregate_attendance_category"),
    )


class ContributionRecord(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "contribution_records"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    wing_id = db.Column(db.Integer, db.ForeignKey("wings.id", ondelete="SET NULL"), nullable=True)
    activity_type = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    duration_hours = db.Column(db.Numeric(7, 2), nullable=False)
    evidence_reference = db.Column(db.String(500), nullable=True)
    approval_status = db.Column(db.String(30), nullable=False, default="Pending")
    decision_reason = db.Column(db.Text, nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (db.CheckConstraint("duration_hours >= 0", name="ck_contribution_hours"),)


class DocumentRequirement(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "document_requirements"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    classification = db.Column(db.String(40), nullable=False, default="Internal")
    mandatory_for_closure = db.Column(db.Boolean, nullable=False, default=False)
    due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id", ondelete="SET NULL"), nullable=True)
    source_template_code = db.Column(db.String(80), nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)


class ApprovalEvent(PublicIdMixin, db.Model):
    __tablename__ = "approval_events"

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_public_id = db.Column(db.String(36), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())


class NotificationPreference(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "notification_preferences"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    email_enabled = db.Column(db.Boolean, nullable=False, default=True)
    in_app_enabled = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (db.UniqueConstraint("user_id", "event_type", name="uq_notification_preference"),)


class Notification(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    event_type = db.Column(db.String(80), nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="Info")
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.Text, nullable=False)
    action_url = db.Column(db.String(500), nullable=True)
    idempotency_key = db.Column(db.String(160), unique=True, nullable=False)
    is_critical = db.Column(db.Boolean, nullable=False, default=False)
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)
    delivery_status = db.Column(db.String(30), nullable=False, default="Pending")


class NotificationDeliveryAttempt(PublicIdMixin, db.Model):
    __tablename__ = "notification_delivery_attempts"

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False)
    channel = db.Column(db.String(30), nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False)
    provider_reference = db.Column(db.String(255), nullable=True)
    error_summary = db.Column(db.String(500), nullable=True)
    attempted_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("notification_id", "channel", "attempt_number", name="uq_notification_attempt"),
    )


class ReportDefinition(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "report_definitions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    report_type = db.Column(db.String(60), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    schema_json = db.Column(db.JSON, nullable=False, default=dict)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (db.UniqueConstraint("code", "version", name="uq_report_definition_version"),)


class ReportJob(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "report_jobs"

    id = db.Column(db.Integer, primary_key=True)
    definition_id = db.Column(db.Integer, db.ForeignKey("report_definitions.id", ondelete="RESTRICT"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = db.Column(db.String(160), unique=True, nullable=False)
    filters_json = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(30), nullable=False, default="Queued")
    output_format = db.Column(db.String(10), nullable=False, default="json")
    snapshot_id = db.Column(db.Integer, db.ForeignKey("report_snapshots.id", ondelete="SET NULL"), nullable=True)
    error_summary = db.Column(db.String(500), nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    snapshot = db.relationship("ReportSnapshot", foreign_keys=[snapshot_id])


class SensitiveAccessEvent(PublicIdMixin, db.Model):
    __tablename__ = "sensitive_access_events"

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_public_id = db.Column(db.String(36), nullable=False)
    project_public_id = db.Column(db.String(36), nullable=True)
    purpose = db.Column(db.String(180), nullable=False)
    request_id = db.Column(db.String(80), nullable=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())


class ImportMappingDecision(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "import_mapping_decisions"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False)
    row_id = db.Column(db.Integer, db.ForeignKey("import_rows.id", ondelete="CASCADE"), nullable=True)
    field_name = db.Column(db.String(100), nullable=False)
    source_value = db.Column(db.String(500), nullable=True)
    normalized_value = db.Column(db.String(500), nullable=True)
    decision = db.Column(db.String(30), nullable=False)
    rationale = db.Column(db.Text, nullable=True)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("batch_id", "row_id", "field_name", name="uq_import_mapping_decision"),
    )
