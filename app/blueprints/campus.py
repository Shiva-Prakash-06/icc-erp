from flask import Blueprint, render_template, redirect, url_for, request, flash, g, jsonify, abort
from app.database import db
from app.models.user import User, Volunteer
from app.models.project import Campus, ProgramType, Project, ProjectParticipant, BuddyAssignment, BuddyLog
from app.models.operational import AttendanceRecord, Contribution, Feedback, Document, Report
from app.services.analytics import AnalyticsService
from app.blueprints.auth import login_required, role_required
from datetime import datetime, timezone

campus_bp = Blueprint('campus', __name__)

def check_project_access(project_id):
    from app.blueprints.dashboard import has_contributed_to_project
    if not has_contributed_to_project(g.user, project_id):
        abort(403)

# --- Core Hierarchy Routes ---

@campus_bp.route('/campuses')
@login_required
def list_campuses():
    if g.user.role in ['Volunteer', 'Buddy', 'ICC Event Volunteer', 'IGP Buddy']:
        abort(403)
    campuses = Campus.query.all()
    # Summarize project counts for each campus
    summaries = {}
    for c in campuses:
        summaries[c.id] = AnalyticsService.get_campus_summary(c.id)
    return render_template('campus/list.html', campuses=campuses, summaries=summaries)

@campus_bp.route('/campuses/<int:campus_id>')
@login_required
def campus_detail(campus_id):
    if g.user.role in ['Volunteer', 'Buddy', 'ICC Event Volunteer', 'IGP Buddy']:
        abort(403)
    campus = Campus.query.get_or_404(campus_id)
    summary = AnalyticsService.get_campus_summary(campus_id)
    
    # List program types (ICC / IGP)
    program_types = ProgramType.query.all()
    
    return render_template('campus/campus_detail.html', campus=campus, summary=summary, program_types=program_types)

@campus_bp.route('/campuses/<int:campus_id>/program/<string:program_name>')
@login_required
def program_detail(campus_id, program_name):
    if g.user.role in ['Volunteer', 'Buddy', 'ICC Event Volunteer', 'IGP Buddy']:
        abort(403)
    campus = Campus.query.get_or_404(campus_id)
    program_type = ProgramType.query.filter_by(name=program_name).first_or_404()
    
    # List projects of this program type on this campus
    projects = Project.query.filter_by(campus_id=campus_id, program_type_id=program_type.id).order_by(Project.start_date.desc()).all()
    
    # Summarize stats for each project
    project_summaries = {}
    for p in projects:
        project_summaries[p.id] = AnalyticsService.get_project_summary(p.id)
        
    return render_template(
        'campus/program_detail.html',
        campus=campus,
        program_type=program_type,
        projects=projects,
        project_summaries=project_summaries
    )

@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>')
@login_required
def project_detail(campus_id, project_id):
    check_project_access(project_id)
    campus = Campus.query.get_or_404(campus_id)
    project = Project.query.get_or_404(project_id)
    
    # Force context matching
    if project.campus_id != campus_id:
        return redirect(url_for('campus.project_detail', campus_id=project.campus_id, project_id=project.id))

    # Retrieve aggregations via Analytics Aggregation Layer
    summary = AnalyticsService.get_project_summary(project_id)
    feedback_analytics = AnalyticsService.get_feedback_analytics(project_id=project_id)
    volunteer_analytics = AnalyticsService.get_volunteer_analytics(project_id=project_id)

    # Load component records
    participants = ProjectParticipant.query.filter_by(project_id=project_id).all()
    attendance_records = AttendanceRecord.query.filter_by(project_id=project_id).order_by(AttendanceRecord.date.desc()).all()
    buddy_assignments = BuddyAssignment.query.filter_by(project_id=project_id).all()
    documents = Document.query.filter_by(project_id=project_id).order_by(Document.created_at.desc()).all()
    contributions = Contribution.query.filter_by(project_id=project_id).order_by(Contribution.approval_status.desc()).all()

    # Load users for selector options (excluding already added participants)
    added_user_ids = [pt.user_id for pt in participants]
    available_users = User.query.filter(User.status == 'Approved', ~User.id.in_(added_user_ids or [-1])).all()

    # Load buddies for assignment selector (users with role Buddy or Volunteer, who are participants)
    project_buddies = User.query.join(ProjectParticipant).filter(
        ProjectParticipant.project_id == project_id,
        ProjectParticipant.participant_type.in_(['Buddy', 'Volunteer'])
    ).all()
    
    project_exchange_students = User.query.join(ProjectParticipant).filter(
        ProjectParticipant.project_id == project_id,
        ProjectParticipant.participant_type == 'Exchange Student'
    ).all()

    # Determine default active tab
    active_tab = request.args.get('tab', 'overview')
    if active_tab not in ['overview', 'people', 'operations', 'insights', 'resources', 'attendance']:
        active_tab = 'overview'

    return render_template(
        'campus/project_detail.html',
        campus=campus,
        project=project,
        summary=summary,
        feedback_analytics=feedback_analytics,
        volunteer_analytics=volunteer_analytics,
        participants=participants,
        attendance_records=attendance_records,
        buddy_assignments=buddy_assignments,
        documents=documents,
        contributions=contributions,
        available_users=available_users,
        project_buddies=project_buddies,
        project_exchange_students=project_exchange_students,
        active_tab=active_tab
    )


# --- Project Component CRUD Sub-routes ---

# 1. Add Participant
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/participants/add', methods=['POST'])
@login_required
@role_required('Faculty', 'ICC Core Committee', 'IGP Core', 'ICC Events Core', 'ICC Cultural Core', 'ICC Media Core')
def add_participant(campus_id, project_id):
    check_project_access(project_id)
    user_id = request.form.get('user_id', type=int)
    participant_type = request.form.get('participant_type')
    nationality = request.form.get('nationality', '').strip()

    if not user_id or not participant_type:
        flash("Invalid user or role selection.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='people'))

    # Check if already participant
    existing = ProjectParticipant.query.filter_by(project_id=project_id, user_id=user_id).first()
    if existing:
        flash("User is already registered as a participant.", "warning")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='people'))

    user = User.query.get(user_id)
    
    participant = ProjectParticipant(
        project_id=project_id,
        user_id=user_id,
        participant_type=participant_type,
        nationality=nationality if nationality else (user.campus.name if user.campus else "Indian"),
        status='Active'
    )
    db.session.add(participant)
    db.session.commit()

    flash(f"Added {user.username} as a {participant_type} to this project.", "success")
    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='people'))

# 2. Mark Attendance
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/attendance/mark', methods=['POST'])
@login_required
@role_required('Faculty', 'ICC Core Committee', 'IGP Core', 'ICC Events Core', 'ICC Cultural Core', 'ICC Media Core')
def mark_attendance(campus_id, project_id):
    check_project_access(project_id)
    date_str = request.form.get('date')
    user_ids = request.form.getlist('user_ids')
    status_dict = {}

    for uid in user_ids:
        status_dict[int(uid)] = request.form.get(f'status_{uid}', 'Absent')

    if not date_str:
        flash("Date is required.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

    mark_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    # Check and delete existing records for this date and project to overwrite
    AttendanceRecord.query.filter_by(project_id=project_id, date=mark_date).delete()

    # Add new records
    for uid, status in status_dict.items():
        record = AttendanceRecord(
            project_id=project_id,
            user_id=uid,
            date=mark_date,
            status=status,
            verified_by_id=g.user.id
        )
        db.session.add(record)
    
    db.session.commit()
    flash(f"Attendance recorded for {date_str}.", "success")
    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

# 3. Log Contribution
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/contributions/log', methods=['POST'])
@login_required
def log_contribution(campus_id, project_id):
    check_project_access(project_id)
    # Only allow Volunteers, Buddies, or Core Committee to log contributions
    activity_type = request.form.get('activity_type')
    description = request.form.get('description', '').strip()
    division = request.form.get('division')
    duration_hours = request.form.get('duration_hours', type=float)

    if not activity_type or not duration_hours:
        flash("Activity type and duration hours are required.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

    contrib = Contribution(
        project_id=project_id,
        user_id=g.user.id,
        activity_type=activity_type,
        description=description,
        division=division if division else 'General',
        duration_hours=duration_hours,
        approval_status='Pending'
    )
    db.session.add(contrib)
    db.session.commit()

    flash("Contribution logged successfully. Awaiting admin approval.", "success")
    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

# 4. Approve/Reject Contribution
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/contributions/action/<int:contrib_id>', methods=['POST'])
@login_required
@role_required('Faculty', 'ICC Core Committee', 'IGP Core', 'ICC Events Core', 'ICC Cultural Core', 'ICC Media Core')
def verify_contribution(campus_id, project_id, contrib_id):
    check_project_access(project_id)
    contrib = Contribution.query.get_or_404(contrib_id)
    action = request.form.get('action') # 'approve' or 'reject'

    if action == 'approve':
        contrib.approval_status = 'Approved'
        contrib.approved_by_id = g.user.id
        contrib.approved_at = datetime.now(timezone.utc)
        flash("Contribution approved.", "success")
    elif action == 'reject':
        contrib.approval_status = 'Rejected'
        flash("Contribution rejected.", "info")
    db.session.commit()

    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

# 5. Assign Buddy
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/buddies/assign', methods=['POST'])
@login_required
@role_required('Faculty', 'ICC Core Committee', 'IGP Core', 'ICC Events Core', 'ICC Cultural Core', 'ICC Media Core')
def assign_buddy(campus_id, project_id):
    check_project_access(project_id)
    buddy_user_id = request.form.get('buddy_user_id', type=int)
    exchange_student_id = request.form.get('exchange_student_id', type=int)
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')

    if not buddy_user_id or not exchange_student_id or not start_date_str or not end_date_str:
        flash("All fields are required for buddy assignment.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='people'))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    project = Project.query.get_or_404(project_id)
    from app.services.buddy import validate_buddy_assignment
    try:
        validate_buddy_assignment(project, buddy_user_id, exchange_student_id, start_date, end_date)
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='people'))

    assignment = BuddyAssignment(
        project_id=project_id,
        buddy_user_id=buddy_user_id,
        exchange_student_id=exchange_student_id,
        start_date=start_date,
        end_date=end_date,
        status='Active'
    )
    db.session.add(assignment)
    db.session.commit()

    flash("Buddy assigned successfully.", "success")
    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='people'))

# 6. Log Buddy Interaction
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/buddies/log', methods=['POST'])
@login_required
def log_buddy_interaction(campus_id, project_id):
    check_project_access(project_id)
    assignment_id = request.form.get('buddy_assignment_id', type=int)
    activity_date_str = request.form.get('activity_date')
    description = request.form.get('description', '').strip()
    duration_hours = request.form.get('duration_hours', type=float)

    if not assignment_id or not activity_date_str or not description or not duration_hours:
        flash("All fields are required to log buddy interaction.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

    assignment = BuddyAssignment.query.get(assignment_id)
    if not assignment or assignment.buddy_user_id != g.user.id:
        flash("Unauthorized log submission.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

    activity_date = datetime.strptime(activity_date_str, '%Y-%m-%d').date()

    blog = BuddyLog(
        buddy_assignment_id=assignment_id,
        activity_date=activity_date,
        description=description,
        duration_hours=duration_hours,
        status='Pending'
    )
    db.session.add(blog)
    db.session.commit()

    flash("Interaction log submitted. Awaiting verification.", "success")
    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

# 7. Verify Buddy Log
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/buddies/log/action/<int:log_id>', methods=['POST'])
@login_required
@role_required('Faculty', 'ICC Core Committee', 'IGP Core', 'ICC Events Core', 'ICC Cultural Core', 'ICC Media Core')
def verify_buddy_log(campus_id, project_id, log_id):
    check_project_access(project_id)
    log = BuddyLog.query.get_or_404(log_id)
    action = request.form.get('action') # 'approve' or 'reject'

    if action == 'approve':
        log.status = 'Approved'
        log.verified_by_id = g.user.id
        log.verified_at = datetime.now(timezone.utc)
        flash("Interaction log approved.", "success")
    elif action == 'reject':
        log.status = 'Rejected'
        flash("Interaction log rejected.", "info")
    db.session.commit()

    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='operations'))

# 8. Add Document
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/documents/add', methods=['POST'])
@login_required
def add_document(campus_id, project_id):
    check_project_access(project_id)
    title = request.form.get('title').strip()
    document_type = request.form.get('document_type')
    google_drive_link = request.form.get('google_drive_link').strip()

    if not title or not document_type or not google_drive_link:
        flash("All fields are required to add a document link.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='resources'))

    if not (google_drive_link.startswith('http://') or google_drive_link.startswith('https://')):
        flash("Please enter a valid URL link.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='resources'))

    doc = Document(
        project_id=project_id,
        title=title,
        document_type=document_type,
        google_drive_link=google_drive_link,
        uploaded_by_id=g.user.id
    )
    db.session.add(doc)
    db.session.commit()

    flash(f"Document '{title}' added to repository.", "success")
    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='resources'))

# 9. Submit Feedback
@campus_bp.route('/campuses/<int:campus_id>/projects/<int:project_id>/feedback/submit', methods=['POST'])
@login_required
def submit_feedback(campus_id, project_id):
    check_project_access(project_id)
    rating = request.form.get('rating', type=int)
    comments = request.form.get('comments', '').strip()
    suggestions = request.form.get('suggestions', '').strip()
    submission_type = request.form.get('submission_type')

    if not rating or not submission_type:
        flash("Rating and feedback type are required.", "danger")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='insights'))

    # User can only submit once per project to avoid duplicates
    existing = Feedback.query.filter_by(project_id=project_id, user_id=g.user.id).first()
    if existing:
        flash("You have already submitted feedback for this project.", "warning")
        return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='insights'))

    feedback = Feedback(
        project_id=project_id,
        user_id=g.user.id,
        rating=rating,
        comments=comments,
        suggestions=suggestions,
        submission_type=submission_type
    )
    db.session.add(feedback)
    db.session.commit()

    flash("Thank you! Your feedback has been recorded.", "success")
    return redirect(url_for('campus.project_detail', campus_id=campus_id, project_id=project_id, tab='insights'))
