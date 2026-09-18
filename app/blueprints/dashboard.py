from flask import Blueprint, render_template, redirect, url_for, request, flash, g, abort
from app.database import db
from app.models.user import User
from app.models.project import AcademicYear, Campus, Project
from app.models.erp import Person, RoleAssignment, Wing
from app.services.audit import record_audit
from app.services.account import build_account_activity
from app.services.authorization import has_any_permission, has_permission, invalidate_assignment_cache
from app.services.home import build_campus_home, build_home
from app.services.hierarchy import campus_tiles
from app.services.roles import replace_scoped_assignment
from app.blueprints.auth import login_required
from datetime import datetime, timezone


dashboard_bp = Blueprint('dashboard', __name__)

ACCOUNT_ROLE_OPTIONS = [
    "Volunteer",
    "Buddy",
    "Participant / Exchange Student",
    "ICC Associate",
    "IGP Program Lead",
    "ICC Events Head",
    "ICC Media Head",
    "ICC Culturals Head",
    "ICC Secretary / USC",
    "IGP Head",
    "Faculty Coordinator",
    "Auditor / Read-only",
    "OIA Faculty Administrator",
    "System Administrator",
]


@dashboard_bp.route('/')
@login_required
def index():
    """The first screen after sign-in: one tile per campus.

    Central is open and is the only tile with an href; the other three are
    plain content. Everything the old home page carried -- the decision
    queue, the user's own open work, the sessions coming up -- moved to
    ``dashboard.queue``, which is reachable from this screen's head and is
    the same data in one-line rows. Splitting them is what lets both fit a
    viewport: the old page had six regions and ran three screens deep.
    """
    hour = datetime.now(timezone.utc).astimezone().hour
    day_part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    return render_template(
        'dashboard/home.html',
        campus_tiles=campus_tiles(g.user),
        day_part=day_part,
        **build_campus_home(g.user),
    )


@dashboard_bp.route('/queue')
@login_required
def queue():
    """Everything waiting on you, as one list of one-line rows.

    ``?queue=all`` is kept as an accepted argument so the links the old home
    page emitted (and the onboarding checklist's first task) still resolve;
    this screen always shows the full queue, so it is a no-op rather than a
    mode switch.
    """
    context = build_home(g.user, show_all_queue=True)

    # Audit, Decision queue: "Twenty-three unrelated decision types are
    # placed in one ungrouped table. Users must scan the Kind column to
    # understand each action." `kind` is a query argument on the existing
    # route -- the URL map is untouched -- and the all-items view stays the
    # default, so nothing is hidden by a filter nobody chose.
    queue = context.get("action_queue") or []
    counts = {}
    for item in queue:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    kind_filter = (request.args.get("kind") or "").strip()
    if kind_filter and kind_filter in counts:
        context["action_queue"] = [item for item in queue if item["kind"] == kind_filter]
    else:
        kind_filter = ""
    context["queue_kind_filter"] = kind_filter
    # Busiest first: the filter exists to make a long list tractable, so the
    # segments that would shorten it most are offered first.
    context["queue_kinds"] = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    context["queue_total"] = len(queue)
    return render_template('dashboard/queue.html', **context)


@dashboard_bp.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    if not has_permission(g.user, "manage_users"):
        abort(403)
    pending_users = User.query.filter_by(status='Pending').order_by(User.created_at.desc()).all()
    approved_users = User.query.filter(User.status == 'Approved', User.id != g.user.id).order_by(User.username).all()
    campuses = Campus.query.all()
    academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    scope_projects = Project.query.order_by(Project.start_date.desc(), Project.title).all()

    return render_template(
        'dashboard/users.html',
        pending_users=pending_users,
        approved_users=approved_users,
        campuses=campuses,
        academic_years=academic_years,
        wings=Wing.query.order_by(Wing.name).all(),
        scope_projects=scope_projects,
        role_options=ACCOUNT_ROLE_OPTIONS,
    )

@dashboard_bp.route('/admin/users/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    if not has_permission(g.user, "manage_users"):
        abort(403)
    user = User.query.get_or_404(user_id)
    assigned_role = request.form.get('role')

    if not assigned_role or assigned_role == 'Pending':
        flash("Please assign a valid role for approval.", "warning")
        return redirect(url_for('dashboard.admin_users'))

    try:
        user.role = assigned_role
        user.status = 'Approved'
        user.approved_by_id = g.user.id
        user.approved_at = datetime.now(timezone.utc)
        if not user.person:
            person = Person.query.filter(db.func.lower(Person.primary_email) == user.email.lower()).first()
            if not person:
                person = Person(first_name=user.username, primary_email=user.email, campus_id=user.campus_id, person_type="Platform User")
                db.session.add(person)
                db.session.flush()
            user.person_id = person.id
        assignment = replace_scoped_assignment(user, assigned_role, request.form, g.user)
        user.session_version += 1
        record_audit("account.approve", user, after={"status": "Approved", "role": assigned_role, "assignment": assignment.public_id}, actor=g.user)
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
        return redirect(url_for('dashboard.admin_users'))

    flash(f"User {user.username} has been approved as {assigned_role}.", "success")
    return redirect(url_for('dashboard.admin_users'))

@dashboard_bp.route('/admin/users/reject/<int:user_id>', methods=['POST'])
@login_required
def reject_user(user_id):
    if not has_permission(g.user, "manage_users"):
        abort(403)
    user = User.query.get_or_404(user_id)
    user.status = 'Rejected'
    user.session_version += 1
    for assignment in RoleAssignment.query.filter_by(user_id=user.id, is_active=True):
        assignment.is_active = False
    invalidate_assignment_cache(user)
    record_audit("account.reject", user, after={"status": "Rejected", "reason": request.form.get("reason") or "Rejected by faculty administrator"}, actor=g.user)
    db.session.commit()

    flash(f"User {user.username} registration has been rejected.", "info")
    return redirect(url_for('dashboard.admin_users'))

@dashboard_bp.route('/admin/users/modify-role/<int:user_id>', methods=['POST'])
@login_required
def modify_user_role(user_id):
    if not has_permission(g.user, "manage_users"):
        abort(403)
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')

    if user.id == g.user.id:
        flash("You cannot modify your own role.", "danger")
        return redirect(url_for('dashboard.admin_users'))

    if new_role:
        try:
            before = {"role": user.role}
            user.role = new_role
            assignment = replace_scoped_assignment(user, new_role, request.form, g.user)
            user.session_version += 1
            record_audit("account.role_change", user, before=before, after={"role": new_role, "assignment": assignment.public_id}, actor=g.user)
            db.session.commit()
            flash(f"Role for {user.username} updated to {new_role}.", "success")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "danger")

    return redirect(url_for('dashboard.admin_users'))


@dashboard_bp.route('/profile')
@login_required
def profile():
    """My Account & Activity: role assignments with human-readable scope,
    assigned projects, recent requests/contributions, notifications, and
    password-security actions -- replaces the volunteer-oriented, commonly-
    empty "My Profile" page. See PLAN.md "USC My Profile" finding."""
    return render_template('dashboard/profile.html', person=g.user.person, **build_account_activity(g.user))
