import secrets
import smtplib
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, current_app, render_template, redirect, url_for, request, flash, session, g
from app.database import db
from app.database import limiter
from app.models.user import User
from app.models.erp import Person, RoleAssignment
from app.models.project import Campus
from app.services.audit import record_audit
from app.services.identity import InternalPasswordIdentityProvider
from app.services.passwords import enqueue_reset_email, find_user_for_reset, issue_reset_token, validate_password

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash("Sign in first.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"], methods=["POST"])
def login():
    if g.user:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username_or_email = (request.form.get('username') or "").strip()
        password = request.form.get('password')

        normalized_identifier = username_or_email.lower()
        user = User.query.filter((db.func.lower(User.username) == normalized_identifier) | (db.func.lower(User.email) == normalized_identifier)).first()

        now = datetime.now(timezone.utc)
        if user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
            flash("Too many tries. Wait a few minutes, then try again, or ask Faculty for help.", "danger")
            return render_template('auth/login.html'), 429

        identity = InternalPasswordIdentityProvider().authenticate(username_or_email, password)
        if user and identity and not user.is_archived:
            if user.status == 'Rejected':
                flash("Faculty did not let this account in. Ask them if you think that is wrong.", "danger")
                return redirect(url_for('auth.login'))

            session.clear()
            session['user_id'] = user.id
            session['session_version'] = user.session_version
            session.permanent = True  # session persistent
            user.failed_login_count = 0
            user.locked_until = None
            user.last_login_at = now
            db.session.commit()
            
            if user.needs_password_reset:
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
            flash("That username or password is not right. Try again.", "danger")

    return render_template('auth/login.html')

def _signup_email_allowed(email):
    domains = current_app.config.get("SIGNUP_EMAIL_DOMAINS") or []
    if not domains:
        return True
    host = email.rpartition("@")[2]
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _username_from_email(email):
    """Usernames are not asked for any more: the part before the @ is used,
    with a number added if someone already has it."""
    base = "".join(ch for ch in email.partition("@")[0] if ch.isalnum() or ch in "._-")[:70] or "user"
    candidate, suffix = base, 1
    while User.query.filter(db.func.lower(User.username) == candidate.lower()).first():
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=["POST"])
def register():
    """Sign up: name, university email, password -- and you are in.

    Every new account is a volunteer straight away, with nothing to approve:
    a volunteer only sees the events they are listed on, so there is nothing
    to protect by making them wait. Faculty gives anyone a bigger role from
    the People page.
    """
    if g.user:
        return redirect(url_for('dashboard.index'))

    campuses = Campus.query.order_by(Campus.id).all()

    if request.method == 'POST':
        first_name = (request.form.get('first_name') or "").strip()
        last_name = (request.form.get('last_name') or "").strip()
        email = (request.form.get('email') or "").strip().lower()
        password = request.form.get('password') or ""
        campus_id = request.form.get('campus_id')
        campus = db.session.get(Campus, int(campus_id)) if (campus_id or "").isdigit() else None
        if campus is None and len(campuses) == 1:
            campus = campuses[0]

        errors = {}
        if not first_name:
            errors["first_name"] = "Type your first name."
        if not email or "@" not in email:
            errors["email"] = "Type your university email."
        elif not _signup_email_allowed(email):
            errors["email"] = "Use your university email address."
        if campus is None:
            errors["campus_id"] = "Pick your campus."
        if not errors:
            try:
                validate_password(password)
            except (ValueError, requests.RequestException) as error:
                errors["password"] = str(error)
        if not errors and User.query.filter(db.func.lower(User.email) == email).first():
            errors["email"] = "This email already has an account. Sign in instead."
        if errors:
            return render_template('auth/register.html', campuses=campuses, field_errors=errors, form=request.form), 422

        now = datetime.now(timezone.utc)
        new_user = User(
            username=_username_from_email(email),
            email=email,
            preferred_role="Volunteer",
            role="Volunteer",
            status="Approved",
            approved_at=now,
            campus_id=campus.id,
            # Signing up is the first visit: show the welcome, not skip it.
            onboarding_seen=False,
        )
        new_user.set_password(password)
        new_user.password_changed_at = now
        db.session.add(new_user)
        db.session.flush()

        # Someone already listed on an event (by a head pasting a volunteer
        # list) is the same person: their account picks up those events.
        person = Person.query.filter(db.func.lower(Person.primary_email) == email).first()
        if person is None:
            person = Person(first_name=first_name, last_name=last_name or None, primary_email=email,
                            campus_id=campus.id, person_type="Platform User")
            db.session.add(person)
            db.session.flush()
        elif person.user_account is not None:
            db.session.rollback()
            errors = {"email": "This email already has an account. Sign in instead."}
            return render_template('auth/register.html', campuses=campuses, field_errors=errors, form=request.form), 422
        new_user.person_id = person.id
        db.session.add(RoleAssignment(
            user_id=new_user.id, role_code="VOLUNTEER", campus_id=campus.id,
            assignment_reason="Signed up", is_active=True,
        ))
        record_audit("account.signup", new_user, after={"role": "Volunteer", "campus": campus.public_id}, actor=new_user)
        db.session.commit()

        session.clear()
        session['user_id'] = new_user.id
        session['session_version'] = new_user.session_version
        session.permanent = True
        flash(f"Welcome, {first_name}!", "success")
        return redirect(url_for('dashboard.index'))

    return render_template('auth/register.html', campuses=campuses, field_errors={}, form={})

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

        try:
            validate_password(new_password)
        except Exception as error:
            return render_template(
                'auth/reset_password.html',
                field_errors={"new_password": str(error)},
            ), 422

        if new_password != confirm_password:
            return render_template(
                'auth/reset_password.html',
                field_errors={"confirm_password": "Passwords do not match."},
            ), 422

        g.user.set_password(new_password)
        g.user.needs_password_reset = False
        g.user.password_changed_at = datetime.now(timezone.utc)
        g.user.session_version += 1
        session['session_version'] = g.user.session_version
        record_audit("account.password_changed", g.user, actor=g.user)
        db.session.commit()

        if g.user.status == 'Pending':
            flash("Your password has been saved.", "success")
            return redirect(url_for('auth.pending_approval'))

        return redirect(url_for('auth.reset_password_success'))

    return render_template('auth/reset_password.html')


@auth_bp.route('/reset-password/success')
@login_required
def reset_password_success():
    """Dedicated confirmation screen after a forced reset, replacing a bare
    redirect straight into the product with no acknowledgement. See
    PLAN.md "ICC password reset" finding."""
    return render_template('auth/reset_password_success.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    if request.method == "POST":
        started_at = time.monotonic()
        identifier = (request.form.get("identifier") or "").strip().lower()
        user = User.query.filter((db.func.lower(User.username) == identifier) | (db.func.lower(User.email) == identifier)).first()
        eligible = bool(user and user.status == "Approved" and not user.is_archived and user.identity_provider == "internal")
        # Both branches below must do equivalent-cost work (token generation, a
        # DB round-trip, and an email-send attempt) so the response timing
        # can't be used to enumerate which identifiers have an eligible
        # account -- only the ineligible branch's work is a no-op discard.
        if eligible:
            token = issue_reset_token(user)
            record_audit("account.password_reset_requested", user, actor=user)
            db.session.commit()
        else:
            decoy_token = secrets.token_urlsafe(32)
            digest = __import__("hashlib").sha256(decoy_token.encode("utf-8")).hexdigest()
            User.query.filter_by(password_reset_token_hash=digest).first()
            db.session.commit()
        reset_url = url_for(
            "auth.recover_password", token=token if eligible else decoy_token,
            _external=True, _scheme="https" if request.is_secure else "http",
        )
        enqueue_reset_email(user if eligible else None, reset_url)
        minimum_seconds = current_app.config.get("PASSWORD_RESET_MIN_RESPONSE_MS", 150) / 1000
        remaining = minimum_seconds - (time.monotonic() - started_at)
        if remaining > 0:
            time.sleep(remaining)
        return redirect(url_for("auth.forgot_password_sent"))
    return render_template("auth/forgot_password.html")


@auth_bp.route('/forgot-password/sent')
def forgot_password_sent():
    """Identical confirmation screen regardless of whether the submitted
    identifier matched an eligible account -- preserves anti-enumeration
    while giving a real dedicated screen instead of a login-page flash. See
    PLAN.md "ICC password reset" finding."""
    return render_template("auth/forgot_password_sent.html")


@auth_bp.route('/recover-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per hour", methods=["POST"])
def recover_password(token):
    user = find_user_for_reset(token)
    if not user:
        flash("That link has run out. Ask for a new one.", "danger")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("new_password")
        confirmation = request.form.get("confirm_password")
        if password != confirmation:
            flash("Passwords do not match.", "danger")
            return render_template("auth/recover_password.html")
        try:
            validate_password(password)
        except Exception as error:
            flash(str(error), "danger")
            return render_template("auth/recover_password.html")
        user.set_password(password)
        user.password_changed_at = datetime.now(timezone.utc)
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        user.failed_login_count = 0
        user.locked_until = None
        user.session_version += 1
        record_audit("account.password_recovered", user, actor=user)
        db.session.commit()
        flash("Your new password is saved. Sign in with it.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/recover_password.html")

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))
