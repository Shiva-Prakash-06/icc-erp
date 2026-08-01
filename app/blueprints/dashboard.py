from flask import Blueprint, render_template, redirect, url_for, request, flash, g, abort
from app.database import db
from app.models.user import User
from app.models.project import AcademicYear, Campus, Project
from app.models.erp import ContributionRecord, Person, ProjectSession, RoleAssignment, SessionAttendance, TeamAssignment, Wing
from app.services.audit import record_audit
from app.services.authorization import has_permission
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
    """The personalized per-role home dashboard has been retired in favor
    of the production-schema ERP surface: Faculty/approvers land on the
    oversight dashboard (cross-project KPIs and a pending-approval action
    queue); everyone else lands on the ERP hub (their in-scope projects).
    Both replacements cover everything the legacy dashboard showed, backed
    by the scoped RoleAssignment model rather than free-text role strings.
    """
    if has_permission(g.user, "approve"):
        return redirect(url_for('erp.oversight'))
    return redirect(url_for('erp.hub'))


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
    person = g.user.person
    contribution_hours = {}
    contributed_project_ids = set()

    if person:
        for contribution in ContributionRecord.query.filter_by(person_id=person.id, approval_status='Approved').all():
            contribution_hours[contribution.activity_type] = contribution_hours.get(contribution.activity_type, 0) + float(contribution.duration_hours)
        contributed_project_ids.update(
            t.project_id for t in TeamAssignment.query.filter_by(person_id=person.id).all() if t.project_id
        )
        contributed_project_ids.update(
            c.project_id for c in ContributionRecord.query.filter_by(person_id=person.id).all()
        )
        session_ids = [a.session_id for a in SessionAttendance.query.filter_by(person_id=person.id).all()]
        if session_ids:
            contributed_project_ids.update(
                s.project_id for s in ProjectSession.query.filter(ProjectSession.id.in_(session_ids)).all()
            )

    contributed_projects = []
    if contributed_project_ids:
        contributed_projects = Project.query.filter(Project.id.in_(contributed_project_ids)).order_by(Project.start_date.desc()).all()

    return render_template(
        'dashboard/profile.html',
        volunteer_profile=person,
        skills_hours=contribution_hours,
        contributed_projects=contributed_projects,
    )
