from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, redirect, url_for, request, flash, session, g
from app.database import db
from app.database import limiter
from app.models.user import User, Volunteer
from app.models.project import Campus

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash("You must be logged in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if g.user is None:
                flash("You must be logged in to access this page.", "warning")
                return redirect(url_for('auth.login'))
            if g.user.role not in roles:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if g.user:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username_or_email = request.form.get('username')
        password = request.form.get('password')

        # Check if username or email
        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()

        now = datetime.now(timezone.utc)
        if user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
            flash("This account is temporarily locked. Try again later or contact an administrator.", "danger")
            return render_template('auth/login.html'), 429

        if user and user.check_password(password):
            if user.status == 'Rejected':
                flash("Your access registration has been rejected by administration.", "danger")
                return redirect(url_for('auth.login'))

            session.clear()
            session['user_id'] = user.id
            session.permanent = True  # session persistent
            user.failed_login_count = 0
            user.locked_until = None
            user.last_login_at = now
            db.session.commit()
            
            if user.needs_password_reset:
                flash("Please reset your password before continuing.", "warning")
                return redirect(url_for('auth.reset_password'))

            if user.status == 'Pending':
                return redirect(url_for('auth.pending_approval'))

            flash(f"Welcome back, {user.username}!", "success")
            return redirect(url_for('dashboard.index'))
        else:
            if user:
                user.failed_login_count += 1
                if user.failed_login_count >= 5:
                    user.locked_until = now + timedelta(minutes=15)
                db.session.commit()
            flash("Invalid username/email or password.", "danger")

    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=["POST"])
def register():
    if g.user:
        return redirect(url_for('dashboard.index'))

    campuses = Campus.query.all()

    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        preferred_role = request.form.get('preferred_role')
        campus_id = request.form.get('campus_id')

        # Simple validations
        if not username or not email or not password or not preferred_role:
            flash("All fields are required.", "danger")
            return render_template('auth/register.html', campuses=campuses)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('auth/register.html', campuses=campuses)

        common_passwords = {"password", "password123", "12345678", "christ123", "qwerty123"}
        if len(password) < 12 or password.lower() in common_passwords:
            flash("Use at least 12 characters and avoid common passwords.", "danger")
            return render_template('auth/register.html', campuses=campuses)

        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash("Username or Email already registered.", "danger")
            return render_template('auth/register.html', campuses=campuses)

        # Create user in Pending status
        new_user = User(
            username=username,
            email=email,
            preferred_role=preferred_role,
            role='Pending',  # Force Role as Pending initially
            status='Pending',
            campus_id=int(campus_id) if campus_id else None
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        # If they registered as a Volunteer, we can create their Volunteer profile
        if preferred_role == 'Volunteer' or preferred_role == 'Buddy':
            skills = request.form.get('skills', '')
            interests = request.form.get('interests', '')
            vol_profile = Volunteer(user_id=new_user.id, skills=skills, interests=interests)
            db.session.add(vol_profile)
            db.session.commit()

        session['user_id'] = new_user.id
        return redirect(url_for('auth.pending_approval'))

    return render_template('auth/register.html', campuses=campuses)

@auth_bp.route('/pending-approval')
def pending_approval():
    if g.user is None:
        return redirect(url_for('auth.login'))
    if g.user.status != 'Pending':
        return redirect(url_for('dashboard.index'))
    return render_template('auth/pending.html')

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
@login_required
def reset_password():
    if not g.user.needs_password_reset:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or len(new_password) < 12:
            flash("Password must be at least 12 characters long.", "danger")
            return render_template('auth/reset_password.html')

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('auth/reset_password.html')

        g.user.set_password(new_password)
        g.user.needs_password_reset = False
        db.session.commit()

        flash("Your password has been reset successfully. Access granted.", "success")
        
        if g.user.status == 'Pending':
            return redirect(url_for('auth.pending_approval'))
            
        return redirect(url_for('dashboard.index'))

    return render_template('auth/reset_password.html')

@auth_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))
