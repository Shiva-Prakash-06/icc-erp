from app.database import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.models.erp import new_uuid

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=new_uuid)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
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
    password_changed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    password_reset_token_hash = db.Column(db.String(128), nullable=True)
    password_reset_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    session_version = db.Column(db.Integer, default=1, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    version = db.Column(db.Integer, default=1, nullable=False)
    identity_provider = db.Column(db.String(30), default='internal', nullable=False)
    external_subject = db.Column(db.String(255), nullable=True)

    # First-run onboarding. `onboarding_step` is the 1-based index of the tour
    # step the user is on (0 = not running), persisted server-side rather than
    # in sessionStorage because tour steps navigate between pages and the tour
    # has to survive a logout too. `onboarding_signals` records the handful of
    # getting-started tasks that leave no other trace in the database -- using
    # the command palette, opening a project, reading the audit trail; every
    # other checklist task is derived from real rows (see app/services/home.py).
    onboarding_seen = db.Column(db.Boolean, default=False, nullable=False)
    onboarding_step = db.Column(db.Integer, default=0, nullable=False)
    onboarding_dismissed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    onboarding_signals = db.Column(db.JSON, nullable=False, default=dict)

    # Relationships
    campus = db.relationship('Campus', backref='users', lazy=True)
    person = db.relationship('Person', back_populates='user_account', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
