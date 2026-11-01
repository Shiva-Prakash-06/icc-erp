from flask import Blueprint, render_template, redirect, url_for, request, flash, g, abort
from app.database import db
from app.models.user import User
from app.models.project import Campus, Project
from app.models.erp import Person, RoleAssignment
from app.services.audit import record_audit
from app.services.account import build_account_activity
from app.services.authorization import can_view_project, has_permission, invalidate_assignment_cache
from app.services.action_queue import build_action_queue
from app.services.home import build_my_activities, build_my_work, is_faculty, is_view_only
from app.services.navigation import REPORT_TEAMS
from app.services.overview import build_campus_programs, build_campus_tiles, build_program_actions
from app.services.roles import ASSIGNABLE_ROLES, replace_scoped_assignment, role_context
from app.services.scope import approvable_projects
from app.services.teams import user_teams
from app.services.year_report import build_year_report, pick_year
from app.blueprints.auth import login_required
from datetime import datetime, timezone


dashboard_bp = Blueprint('dashboard', __name__)

# "System Administrator" stays assignable for technical operations only; it
# approves nothing (see ROLE_PERMISSIONS).
ACCOUNT_ROLE_OPTIONS = [*ASSIGNABLE_ROLES, "System Administrator"]


@dashboard_bp.route('/')
@login_required
def index():
    """My work: what is waiting on you, today first. Volunteers see the
    events they are on instead -- see app/services/home.py."""
    if is_view_only(g.user):
        return render_template('dashboard/activities.html', **build_my_activities(g.user))
    show = (request.args.get('show') or '').strip() or None
    return render_template('dashboard/home.html', **build_my_work(g.user, show=show))


def landing_endpoint(user):
    """Where someone lands after signing in. Faculty, the USC and the heads
    open on the campus overview; a volunteer opens on their own events."""
    return 'dashboard.index' if is_view_only(user) else 'dashboard.overview'


def _overview_allowed():
    if is_view_only(g.user):
        abort(403)


@dashboard_bp.route('/overview')
@login_required
def overview():
    """The landing page: the four campuses, each a tile. Information only --
    see app/services/overview.py."""
    _overview_allowed()
    return render_template('dashboard/overview.html', **build_campus_tiles())


@dashboard_bp.route('/overview/campus/<string:public_id>')
@login_required
def overview_campus(public_id):
    """One campus: its ICC events and IGP programmes."""
    _overview_allowed()
    campus = Campus.query.filter_by(public_id=public_id).first_or_404()
    return render_template('dashboard/overview_campus.html', **build_campus_programs(campus))


@dashboard_bp.route('/overview/program/<string:public_id>')
@login_required
def overview_program(public_id):
    """One program: every action on it and who owns it."""
    _overview_allowed()
    project = Project.query.filter_by(public_id=public_id).first_or_404()
    return render_template(
        'dashboard/overview_program.html',
        can_open=can_view_project(g.user, project),
        **build_program_actions(project),
    )


@dashboard_bp.route('/queue')
@login_required
def queue():
    """Everything that needs Faculty's OK, in one list. Home shows the first
    five; this is "Show all". Anyone else has nothing to approve, so they go
    back to their own list."""
    if not is_faculty(g.user):
        return redirect(url_for('dashboard.index'))
    return render_template('dashboard/queue.html', needs_ok=build_action_queue(g.user, projects=approvable_projects(g.user)))


@dashboard_bp.route('/reports')
@login_required
def reports():
    """One year at a glance, then the finished events and their reports.
    Faculty and the USC only."""
    if not (user_teams(g.user) & REPORT_TEAMS):
        abort(403)
    year = pick_year(request.args.get('year'))
    return render_template('dashboard/reports.html', **build_year_report(g.user, year, show_all=bool(request.args.get('all'))))


#: Shown on the People page before "Show all".
PEOPLE_SHOWN = 10


@dashboard_bp.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    """People: find someone and make them a head, the USC or Faculty.

    Year and wing follow from the role, so the only other question is the
    campus, and that is asked only when there is more than one."""
    if not has_permission(g.user, "manage_users"):
        abort(403)
    search = (request.args.get('q') or '').strip()
    query = User.query.filter(User.status == 'Approved', User.id != g.user.id)
    if search:
        needle = f"%{search.lower()}%"
        query = query.filter(db.or_(db.func.lower(User.username).like(needle), db.func.lower(User.email).like(needle)))
    accounts = query.order_by(User.created_at.desc()).all()
    show_all = bool(search) or bool(request.args.get('all'))
    return render_template(
        'dashboard/users.html',
        pending_users=User.query.filter_by(status='Pending').order_by(User.created_at.desc()).all(),
        accounts=accounts if show_all else accounts[:PEOPLE_SHOWN],
        accounts_total=len(accounts),
        search=search,
        campuses=Campus.query.order_by(Campus.name).all(),
        role_options=ASSIGNABLE_ROLES,
        role_of={account.id: _role_label(account) for account in accounts},
    )


def _role_label(user):
    rows = role_context(user)
    return rows[0]["title"] if rows else "Volunteer"


@dashboard_bp.route('/admin/users/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    if not has_permission(g.user, "manage_users"):
        abort(403)
    user = User.query.get_or_404(user_id)
    assigned_role = request.form.get('role')

    if not assigned_role or assigned_role == 'Pending':
        flash("Pick what they should be.", "warning")
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

    flash(f"{user.username} is in ✓", "success")
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

    flash(f"{user.username} was turned away.", "info")
    return redirect(url_for('dashboard.admin_users'))

@dashboard_bp.route('/admin/users/modify-role/<int:user_id>', methods=['POST'])
@login_required
def modify_user_role(user_id):
    if not has_permission(g.user, "manage_users"):
        abort(403)
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')

    if user.id == g.user.id:
        flash("You cannot change what you are yourself. Ask another Faculty member.", "danger")
        return redirect(url_for('dashboard.admin_users'))

    if new_role:
        try:
            before = {"role": user.role}
            user.role = new_role
            assignment = replace_scoped_assignment(user, new_role, request.form, g.user)
            user.session_version += 1
            record_audit("account.role_change", user, before=before, after={"role": new_role, "assignment": assignment.public_id}, actor=g.user)
            db.session.commit()
            flash(f"Saved ✓ {user.username} is now {new_role}.", "success")
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


@dashboard_bp.route('/profile/details', methods=['POST'])
@login_required
def update_my_details():
    """Anyone can fix their own name, phone and register number. An account
    made before sign-up created a Person gets one here, matched by email."""
    first_name = (request.form.get('first_name') or "").strip()
    last_name = (request.form.get('last_name') or "").strip() or None
    phone = (request.form.get('phone') or "").strip() or None
    registration_number = (request.form.get('registration_number') or "").strip() or None
    if not first_name:
        flash("Type your first name.", "danger")
        return redirect(url_for('dashboard.profile') + '#details')
    if len(first_name) > 100 or (last_name and len(last_name) > 100) or (phone and len(phone) > 40) or (registration_number and len(registration_number) > 80):
        flash("That is too long. Make it shorter.", "danger")
        return redirect(url_for('dashboard.profile') + '#details')

    person = g.user.person
    if person is None and g.user.email:
        person = Person.query.filter(db.func.lower(Person.primary_email) == g.user.email.lower()).first()
        if person is not None and person.user_account is not None:
            person = None
    if registration_number:
        taken = Person.query.filter(Person.registration_number == registration_number).first()
        if taken is not None and taken is not person:
            flash("That register number is already someone else's. Check it, or ask Faculty.", "danger")
            return redirect(url_for('dashboard.profile') + '#details')
    if person is None:
        person = Person(first_name=first_name, primary_email=g.user.email, campus_id=g.user.campus_id, person_type="Platform User")
        db.session.add(person)
    g.user.person = person

    before = {"first_name": person.first_name, "last_name": person.last_name, "phone": person.phone, "registration_number": person.registration_number}
    person.first_name, person.last_name, person.phone, person.registration_number = first_name, last_name, phone, registration_number
    db.session.flush()
    record_audit("person.update_own", person, before=before, after={"first_name": first_name, "last_name": last_name, "phone": phone, "registration_number": registration_number}, actor=g.user)
    db.session.commit()
    flash("Saved ✓ Your details are up to date.", "success")
    return redirect(url_for('dashboard.profile') + '#details')
