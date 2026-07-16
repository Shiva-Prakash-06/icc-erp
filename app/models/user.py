from app.database import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default='Pending', nullable=False)  # 'Faculty', 'ICC Core Committee', 'Volunteer', 'Buddy', 'Exchange Student', 'Pending'
    preferred_role = db.Column(db.String(50), nullable=True)            # Role requested during signup
    status = db.Column(db.String(20), default='Pending', nullable=False) # 'Pending', 'Approved', 'Rejected'
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    needs_password_reset = db.Column(db.Boolean, default=False, nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='SET NULL'), unique=True, nullable=True)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    identity_provider = db.Column(db.String(30), default='internal', nullable=False)
    external_subject = db.Column(db.String(255), nullable=True)

    # Relationships
    campus = db.relationship('Campus', backref='users', lazy=True)
    volunteer_profile = db.relationship('Volunteer', back_populates='user', uselist=False, cascade="all, delete-orphan")
    participants = db.relationship('ProjectParticipant', back_populates='user', cascade="all, delete-orphan")
    buddy_logs_verified = db.relationship('BuddyLog', foreign_keys='BuddyLog.verified_by_id', backref='verifier', lazy=True)
    attendance_records_verified = db.relationship('AttendanceRecord', foreign_keys='AttendanceRecord.verified_by_id', backref='verifier', lazy=True)
    contributions_approved = db.relationship('Contribution', foreign_keys='Contribution.approved_by_id', backref='approver', lazy=True)
    person = db.relationship('Person', back_populates='user_account', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"

class Volunteer(db.Model):
    __tablename__ = 'volunteers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    skills = db.Column(db.Text, nullable=True)
    interests = db.Column(db.Text, nullable=True)
    current_status = db.Column(db.String(50), default='Active', nullable=False)  # 'Active', 'Inactive'

    # Relationships
    user = db.relationship('User', back_populates='volunteer_profile')

    def __repr__(self):
        return f"<Volunteer user_id={self.user_id}>"
