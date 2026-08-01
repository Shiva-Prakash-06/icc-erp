import uuid

from app.database import db

class AcademicYear(db.Model):
    __tablename__ = 'academic_years'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)  # e.g., '2026-2027'
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False, nullable=False)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    def __repr__(self):
        return f"<AcademicYear {self.name}>"

class Campus(db.Model):
    __tablename__ = 'campuses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    def __repr__(self):
        return f"<Campus {self.name}>"

class ProgramType(db.Model):
    __tablename__ = 'program_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)  # 'ICC' or 'IGP'
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    def __repr__(self):
        return f"<ProgramType {self.name}>"

class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    code = db.Column(db.String(40), unique=True, nullable=True)
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='CASCADE'), nullable=False)
    program_type_id = db.Column(db.Integer, db.ForeignKey('program_types.id', ondelete='CASCADE'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    project_type = db.Column(db.String(50), nullable=True)
    objectives = db.Column(db.Text, nullable=True)
    target_audience = db.Column(db.String(255), nullable=True)
    venue = db.Column(db.String(255), nullable=True)
    capacity = db.Column(db.Integer, nullable=True)
    expected_reach = db.Column(db.Integer, nullable=True)
    actual_reach = db.Column(db.Integer, nullable=True)
    owner_person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='SET NULL'), nullable=True)
    operating_unit_id = db.Column(db.Integer, db.ForeignKey('operating_units.id', ondelete='SET NULL'), nullable=True)
    wing_id = db.Column(db.Integer, db.ForeignKey('wings.id', ondelete='SET NULL'), nullable=True)
    partner_institution_id = db.Column(db.Integer, db.ForeignKey('partner_institutions.id', ondelete='SET NULL'), nullable=True)
    category = db.Column(db.String(50), nullable=False)  # 'Sports', 'Cultural', 'Leadership', 'Exchange', 'Academic', 'Social Work'
    status = db.Column(db.String(30), default='Draft', nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    cancellation_reason = db.Column(db.Text, nullable=True)
    closure_summary = db.Column(db.Text, nullable=True)
    archived_at = db.Column(db.DateTime(timezone=True), nullable=True)
    version = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    __table_args__ = (
        db.CheckConstraint('end_date >= start_date', name='ck_project_date_order'),
        db.CheckConstraint('capacity IS NULL OR capacity >= 0', name='ck_project_capacity_nonnegative'),
        db.CheckConstraint('expected_reach IS NULL OR expected_reach >= 0', name='ck_project_expected_reach_nonnegative'),
        db.CheckConstraint('actual_reach IS NULL OR actual_reach >= 0', name='ck_project_actual_reach_nonnegative'),
    )

    # Relationships
    campus = db.relationship('Campus', back_populates='projects')
    program_type = db.relationship('ProgramType', back_populates='projects')
    academic_year = db.relationship('AcademicYear', back_populates='projects')
    buddy_assignments = db.relationship('BuddyAssignment', back_populates='project', cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project {self.title}>"

# Back-populate relationships on parent models
Campus.projects = db.relationship('Project', order_by=Project.id, back_populates='campus', cascade="all, delete-orphan")
ProgramType.projects = db.relationship('Project', order_by=Project.id, back_populates='program_type', cascade="all, delete-orphan")
AcademicYear.projects = db.relationship('Project', order_by=Project.id, back_populates='academic_year', cascade="all, delete-orphan")




class BuddyAssignment(db.Model):
    __tablename__ = 'buddy_assignments'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    # Nullable: a buddy or exchange student may be represented by a bare
    # Person (no login account). Exactly one of the *_user_id/*_person_id
    # pair must be set per side -- enforced by ck_buddy_identity below.
    buddy_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    exchange_student_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    buddy_person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='SET NULL'), nullable=True)
    exchange_student_person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='SET NULL'), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Active', nullable=False)  # 'Active', 'Completed', 'Inactive'
    assignment_type = db.Column(db.String(30), default='One-to-one', nullable=False)
    overlap_override_reason = db.Column(db.Text, nullable=True)
    overlap_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL', name='fk_buddy_overlap_approver'), nullable=True)
    version = db.Column(db.Integer, default=1, nullable=False)

    __table_args__ = (
        db.CheckConstraint('end_date >= start_date', name='ck_buddy_assignment_dates'),
        db.CheckConstraint(
            '(buddy_user_id IS NOT NULL OR buddy_person_id IS NOT NULL) '
            'AND (exchange_student_id IS NOT NULL OR exchange_student_person_id IS NOT NULL)',
            name='ck_buddy_identity',
        ),
        db.UniqueConstraint('project_id', 'buddy_user_id', 'exchange_student_id', 'start_date', name='uq_buddy_assignment_exact'),
    )

    # Relationships
    project = db.relationship('Project', back_populates='buddy_assignments')
    buddy = db.relationship('User', foreign_keys=[buddy_user_id], backref='buddy_assignments')
    exchange_student = db.relationship('User', foreign_keys=[exchange_student_id], backref='exchange_buddy_assignments')
    buddy_person = db.relationship('Person', foreign_keys=[buddy_person_id])
    exchange_student_person = db.relationship('Person', foreign_keys=[exchange_student_person_id])
    logs = db.relationship('BuddyLog', back_populates='assignment', cascade="all, delete-orphan")

    @property
    def buddy_identity_person_id(self):
        """Resolve the buddy side to a person_id regardless of which
        identity column is populated -- every User is expected to have a
        linked Person (see the person-link backfill), so this collapses the
        two representations to a single axis for overlap-checking."""
        if self.buddy_person_id:
            return self.buddy_person_id
        return getattr(self.buddy, "person_id", None)

    @property
    def exchange_student_identity_person_id(self):
        if self.exchange_student_person_id:
            return self.exchange_student_person_id
        return getattr(self.exchange_student, "person_id", None)

    def __repr__(self):
        return f"<BuddyAssignment project_id={self.project_id} buddy={self.buddy_user_id} student={self.exchange_student_id}>"


class BuddyLog(db.Model):
    __tablename__ = 'buddy_logs'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    buddy_assignment_id = db.Column(db.Integer, db.ForeignKey('buddy_assignments.id', ondelete='CASCADE'), nullable=False)
    activity_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    duration_hours = db.Column(db.Float, default=1.0, nullable=False)
    status = db.Column(db.String(20), default='Pending', nullable=False)  # 'Pending', 'Approved', 'Rejected'
    verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    concern_level = db.Column(db.String(30), nullable=True)
    escalation_owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    escalation_status = db.Column(db.String(30), nullable=True)
    resolution = db.Column(db.Text, nullable=True)
    version = db.Column(db.Integer, default=1, nullable=False)

    # Relationships
    assignment = db.relationship('BuddyAssignment', back_populates='logs')

    def __repr__(self):
        return f"<BuddyLog id={self.id} status={self.status}>"
