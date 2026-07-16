from app.database import db

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)  # User whose attendance is marked
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'Present', 'Absent'
    verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='attendance_records')

    def __repr__(self):
        return f"<AttendanceRecord project_id={self.project_id} user={self.user_id} date={self.date} status={self.status}>"


class Contribution(db.Model):
    __tablename__ = 'contributions'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # 'Media support', 'Event support', 'Logistics support', 'Administrative'
    description = db.Column(db.Text, nullable=True)
    division = db.Column(db.String(50), nullable=True)  # 'Graphic design', 'Photography', 'Operations', 'Translation'
    duration_hours = db.Column(db.Float, default=1.0, nullable=False)
    approval_status = db.Column(db.String(20), default='Pending', nullable=False)  # 'Pending', 'Approved', 'Rejected'
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='contributions')
    project = db.relationship('Project', backref='contributions')

    def __repr__(self):
        return f"<Contribution user={self.user_id} type={self.activity_type} status={self.approval_status}>"


class Feedback(db.Model):
    __tablename__ = 'feedback'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1 to 5
    comments = db.Column(db.Text, nullable=True)
    suggestions = db.Column(db.Text, nullable=True)
    submission_type = db.Column(db.String(50), nullable=False)  # 'Event feedback', 'IGP feedback', 'Buddy feedback', 'Experience sharing'
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationships
    user = db.relationship('User', backref='feedback_submissions')
    project = db.relationship('Project', backref='feedbacks')

    def __repr__(self):
        return f"<Feedback project_id={self.project_id} user={self.user_id} rating={self.rating}>"


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)  # 'Poster', 'Report', 'Presentation', 'Photo', 'Video', 'Other'
    google_drive_link = db.Column(db.String(500), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationships
    uploaded_by = db.relationship('User', backref='uploaded_documents')
    project = db.relationship('Project', backref='documents')

    def __repr__(self):
        return f"<Document title={self.title} type={self.document_type}>"


class Report(db.Model):
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(50), nullable=False)  # 'Project Report', 'Monthly Report', 'Academic Year Report'
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='SET NULL'), nullable=True)
    program_type_id = db.Column(db.Integer, db.ForeignKey('program_types.id', ondelete='SET NULL'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    generated_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relationships
    campus = db.relationship('Campus', backref='reports')
    program_type = db.relationship('ProgramType', backref='reports')
    project = db.relationship('Project', backref='reports')
    generated_by = db.relationship('User', backref='generated_reports')

    def __repr__(self):
        return f"<Report title={self.title} type={self.report_type}>"
