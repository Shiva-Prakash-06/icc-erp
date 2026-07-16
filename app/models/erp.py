"""Production-shaped ERP domain models added to the v2 modular monolith.

Legacy v2 integer identifiers remain as internal keys for upgrade compatibility;
all new public interfaces expose stable UUIDs and immutable human-readable codes.
The production migration program may promote UUIDs to physical primary keys after
the legacy screens have been retired.
"""

from __future__ import annotations

import uuid

from app.database import db


def new_uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now(), onupdate=db.func.now()
    )


class PublicIdMixin:
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=new_uuid)


class OperatingUnit(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "operating_units"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Wing(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "wings"

    id = db.Column(db.Integer, primary_key=True)
    operating_unit_id = db.Column(db.Integer, db.ForeignKey("operating_units.id"), nullable=False)
    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    operating_unit = db.relationship("OperatingUnit", backref="wings")
    __table_args__ = (db.UniqueConstraint("operating_unit_id", "code", name="uq_wing_unit_code"),)


class Person(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "people"

    id = db.Column(db.Integer, primary_key=True)
    registration_number = db.Column(db.String(80), unique=True, nullable=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=True)
    preferred_name = db.Column(db.String(100), nullable=True)
    primary_email = db.Column(db.String(255), unique=True, nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    campus_id = db.Column(db.Integer, db.ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True)
    person_type = db.Column(db.String(40), nullable=False, default="Student")
    nationality_country = db.Column(db.String(100), nullable=True)
    skills = db.Column(db.Text, nullable=True)
    interests = db.Column(db.Text, nullable=True)
    availability = db.Column(db.Text, nullable=True)
    consent_status = db.Column(db.String(30), nullable=False, default="Not Recorded")
    is_archived = db.Column(db.Boolean, nullable=False, default=False)

    campus = db.relationship("Campus", backref="people")
    user_account = db.relationship("User", back_populates="person", uselist=False)

    @property
    def display_name(self):
        return self.preferred_name or " ".join(filter(None, [self.first_name, self.last_name]))


class PartnerInstitution(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "partner_institutions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    country = db.Column(db.String(100), nullable=True)
    primary_contact_name = db.Column(db.String(150), nullable=True)
    primary_contact_email = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class RoleAssignment(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "role_assignments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_code = db.Column(db.String(60), nullable=False)
    operating_unit_id = db.Column(db.Integer, db.ForeignKey("operating_units.id"), nullable=True)
    campus_id = db.Column(db.Integer, db.ForeignKey("campuses.id"), nullable=True)
    wing_id = db.Column(db.Integer, db.ForeignKey("wings.id"), nullable=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_years.id"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    starts_on = db.Column(db.Date, nullable=True)
    ends_on = db.Column(db.Date, nullable=True)
    delegated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    can_view_sensitive_links = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship("User", foreign_keys=[user_id], backref="role_assignments")
    __table_args__ = (
        db.CheckConstraint("ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on", name="ck_role_dates"),
    )


class ProjectComponent(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "project_components"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    code = db.Column(db.String(60), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    component_type = db.Column(db.String(50), nullable=False, default="Workstream")
    description = db.Column(db.Text, nullable=True)
    sequence = db.Column(db.Integer, nullable=False, default=0)
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)

    project = db.relationship("Project", backref=db.backref("components", cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint("project_id", "code", name="uq_component_project_code"),)


class ProjectSession(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "project_sessions"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    component_id = db.Column(db.Integer, db.ForeignKey("project_components.id", ondelete="SET NULL"), nullable=True)
    code = db.Column(db.String(60), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    session_type = db.Column(db.String(50), nullable=False, default="Session")
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ends_at = db.Column(db.DateTime(timezone=True), nullable=False)
    venue = db.Column(db.String(255), nullable=True)
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)
    capacity = db.Column(db.Integer, nullable=True)
    programme_sequence = db.Column(db.Text, nullable=True)
    participant_group = db.Column(db.String(120), nullable=True)

    project = db.relationship("Project", backref=db.backref("sessions", cascade="all, delete-orphan"))
    __table_args__ = (
        db.UniqueConstraint("project_id", "code", name="uq_session_project_code"),
        db.CheckConstraint("ends_at >= starts_at", name="ck_session_date_order"),
        db.CheckConstraint("capacity IS NULL OR capacity >= 0", name="ck_session_capacity_nonnegative"),
    )


class WorkTask(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "work_tasks"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    component_id = db.Column(db.Integer, db.ForeignKey("project_components.id", ondelete="SET NULL"), nullable=True)
    title = db.Column(db.String(220), nullable=False)
    description = db.Column(db.Text, nullable=True)
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)
    accountable_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)
    external_contact = db.Column(db.String(255), nullable=True)
    due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    priority = db.Column(db.String(20), nullable=False, default="Medium")
    status = db.Column(db.String(30), nullable=False, default="Not Started")
    dependency_task_id = db.Column(db.Integer, db.ForeignKey("work_tasks.id"), nullable=True)
    evidence_reference = db.Column(db.String(500), nullable=True)
    decision_comment = db.Column(db.Text, nullable=True)
    mandatory_for_closure = db.Column(db.Boolean, nullable=False, default=False)
    waived = db.Column(db.Boolean, nullable=False, default=False)
    waiver_reason = db.Column(db.Text, nullable=True)
    waived_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    project = db.relationship("Project", backref=db.backref("work_tasks", cascade="all, delete-orphan"))


class ChecklistTemplate(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "checklist_templates"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    project_type = db.Column(db.String(60), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    source_reference = db.Column(db.String(500), nullable=True)

    __table_args__ = (db.UniqueConstraint("code", "version", name="uq_checklist_template_version"),)


class ChecklistTemplateItem(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "checklist_template_items"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    sequence = db.Column(db.Integer, nullable=False, default=0)
    mandatory = db.Column(db.Boolean, nullable=False, default=True)
    default_owner_label = db.Column(db.String(180), nullable=True)
    sensitive = db.Column(db.Boolean, nullable=False, default=False)

    template = db.relationship("ChecklistTemplate", backref=db.backref("items", cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint("template_id", "code", name="uq_checklist_item_code"),)


class ChecklistInstance(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "checklist_instances"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey("checklist_templates.id"), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="In Progress")

    project = db.relationship("Project", backref=db.backref("checklists", cascade="all, delete-orphan"))
    template = db.relationship("ChecklistTemplate")


class ChecklistItemStatus(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "checklist_item_statuses"

    id = db.Column(db.Integer, primary_key=True)
    checklist_instance_id = db.Column(db.Integer, db.ForeignKey("checklist_instances.id", ondelete="CASCADE"), nullable=False)
    template_item_id = db.Column(db.Integer, db.ForeignKey("checklist_template_items.id"), nullable=False)
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)
    external_owner = db.Column(db.String(255), nullable=True)
    due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Not Started")
    evidence_reference = db.Column(db.String(500), nullable=True)
    verifier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    decision_comment = db.Column(db.Text, nullable=True)
    waived = db.Column(db.Boolean, nullable=False, default=False)
    waiver_reason = db.Column(db.Text, nullable=True)
    source_file = db.Column(db.String(500), nullable=True)
    source_sheet = db.Column(db.String(200), nullable=True)
    source_row = db.Column(db.Integer, nullable=True)

    checklist = db.relationship("ChecklistInstance", backref=db.backref("item_statuses", cascade="all, delete-orphan"))
    template_item = db.relationship("ChecklistTemplateItem")
    __table_args__ = (
        db.UniqueConstraint("checklist_instance_id", "template_item_id", name="uq_checklist_status_item"),
    )


class TeamAssignment(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "team_assignments"

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    wing_id = db.Column(db.Integer, db.ForeignKey("wings.id"), nullable=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_years.id"), nullable=True)
    assignment_type = db.Column(db.String(50), nullable=False)
    role_label = db.Column(db.String(100), nullable=True)
    recruitment_status = db.Column(db.String(30), nullable=False, default="Selected")
    starts_on = db.Column(db.Date, nullable=True)
    ends_on = db.Column(db.Date, nullable=True)

    person = db.relationship("Person", backref="team_assignments")
    project = db.relationship("Project", backref=db.backref("team_assignments", cascade="all, delete-orphan"))


class SessionAttendance(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "session_attendance"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("project_sessions.id", ondelete="CASCADE"), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    source_import_row_id = db.Column(db.Integer, db.ForeignKey("import_rows.id"), nullable=True)

    __table_args__ = (db.UniqueConstraint("session_id", "person_id", name="uq_session_attendance_person"),)


class DocumentRecord(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "document_records"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    checklist_status_id = db.Column(db.Integer, db.ForeignKey("checklist_item_statuses.id"), nullable=True)
    category = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    version_label = db.Column(db.String(40), nullable=False, default="1")
    status = db.Column(db.String(30), nullable=False, default="Missing")
    drive_file_id = db.Column(db.String(255), nullable=True)
    drive_url = db.Column(db.String(500), nullable=True)
    permission_classification = db.Column(db.String(40), nullable=False, default="Internal")
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    expires_on = db.Column(db.Date, nullable=True)
    supersedes_id = db.Column(db.Integer, db.ForeignKey("document_records.id"), nullable=True)
    mandatory_for_closure = db.Column(db.Boolean, nullable=False, default=False)
    waived = db.Column(db.Boolean, nullable=False, default=False)

    project = db.relationship("Project", backref=db.backref("document_records", cascade="all, delete-orphan"))


class BudgetLine(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "budget_lines"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    estimated_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    approved_amount = db.Column(db.Numeric(12, 2), nullable=True)
    committed_amount = db.Column(db.Numeric(12, 2), nullable=True)
    actual_amount = db.Column(db.Numeric(12, 2), nullable=True)
    official_reference = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Draft")

    __table_args__ = (
        db.CheckConstraint("estimated_amount >= 0", name="ck_budget_estimate_nonnegative"),
        db.CheckConstraint("approved_amount IS NULL OR approved_amount >= 0", name="ck_budget_approved_nonnegative"),
        db.CheckConstraint("committed_amount IS NULL OR committed_amount >= 0", name="ck_budget_committed_nonnegative"),
        db.CheckConstraint("actual_amount IS NULL OR actual_amount >= 0", name="ck_budget_actual_nonnegative"),
    )


class OperationalRequest(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "operational_requests"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    request_type = db.Column(db.String(60), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    details = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Draft")
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)
    approver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    official_reference = db.Column(db.String(120), nullable=True)


class FeedbackForm(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "feedback_forms"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    public_token = db.Column(db.String(64), unique=True, nullable=True)
    response_policy = db.Column(db.String(30), nullable=False, default="One response")
    is_anonymous = db.Column(db.Boolean, nullable=False, default=False)
    questions_json = db.Column(db.JSON, nullable=False, default=list)
    is_open = db.Column(db.Boolean, nullable=False, default=False)


class FeedbackResponse(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "feedback_responses"

    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey("feedback_forms.id", ondelete="CASCADE"), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)
    answers_json = db.Column(db.JSON, nullable=False, default=dict)
    publication_consent = db.Column(db.Boolean, nullable=False, default=False)
    moderation_status = db.Column(db.String(30), nullable=False, default="Pending")


class ImportBatch(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "import_batches"

    id = db.Column(db.Integer, primary_key=True)
    idempotency_key = db.Column(db.String(120), unique=True, nullable=False)
    import_type = db.Column(db.String(60), nullable=False)
    source_file = db.Column(db.String(500), nullable=False)
    source_sha256 = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Staged")
    staged_count = db.Column(db.Integer, nullable=False, default=0)
    valid_count = db.Column(db.Integer, nullable=False, default=0)
    error_count = db.Column(db.Integer, nullable=False, default=0)
    committed_count = db.Column(db.Integer, nullable=False, default=0)
    reconciliation_json = db.Column(db.JSON, nullable=False, default=dict)
    committed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    committed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)


class ImportRow(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "import_rows"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False)
    sheet_name = db.Column(db.String(200), nullable=True)
    source_row = db.Column(db.Integer, nullable=False)
    source_json = db.Column(db.JSON, nullable=False)
    normalized_json = db.Column(db.JSON, nullable=False, default=dict)
    validation_status = db.Column(db.String(20), nullable=False, default="Pending")
    validation_messages = db.Column(db.JSON, nullable=False, default=list)
    target_entity = db.Column(db.String(80), nullable=True)
    target_public_id = db.Column(db.String(36), nullable=True)

    batch = db.relationship("ImportBatch", backref=db.backref("rows", cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint("batch_id", "sheet_name", "source_row", name="uq_import_source_row"),)


class AuditEvent(PublicIdMixin, db.Model):
    __tablename__ = "audit_events"

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_public_id = db.Column(db.String(36), nullable=True)
    before_summary = db.Column(db.JSON, nullable=True)
    after_summary = db.Column(db.JSON, nullable=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    request_id = db.Column(db.String(80), nullable=True)
    ip_address = db.Column(db.String(80), nullable=True)


class ReportSnapshot(PublicIdMixin, TimestampMixin, db.Model):
    __tablename__ = "report_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    report_type = db.Column(db.String(60), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    filters_json = db.Column(db.JSON, nullable=False, default=dict)
    snapshot_json = db.Column(db.JSON, nullable=False, default=dict)
    source_references = db.Column(db.JSON, nullable=False, default=list)
    approval_status = db.Column(db.String(30), nullable=False, default="Draft")
    generated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
