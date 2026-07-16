from flask import Blueprint, render_template, redirect, url_for, request, flash, session, g, jsonify, send_file, abort
from app.database import db
from app.models.user import User, Volunteer
from app.models.project import AcademicYear, Campus, ProgramType, Project, ProjectParticipant, BuddyLog, BuddyAssignment
from app.models.operational import AttendanceRecord, Contribution, Feedback, Document, Report
from app.services.analytics import AnalyticsService
from app.blueprints.auth import login_required, role_required
from datetime import datetime
from sqlalchemy import func
import io
import pandas as pd


dashboard_bp = Blueprint('dashboard', __name__)

def has_contributed_to_project(user, project_id):
    if user.role not in ['Volunteer', 'Buddy', 'ICC Event Volunteer', 'IGP Buddy']:
        return True
    is_participant = ProjectParticipant.query.filter_by(project_id=project_id, user_id=user.id).first() is not None
    has_contrib = Contribution.query.filter_by(project_id=project_id, user_id=user.id).first() is not None
    has_att = AttendanceRecord.query.filter_by(project_id=project_id, user_id=user.id).first() is not None
    return is_participant or has_contrib or has_att

def has_contributed_to_report(user, report):
    if user.role not in ['Volunteer', 'Buddy', 'ICC Event Volunteer', 'IGP Buddy']:
        return True
    
    # Get projects in scope for this report
    project_filter = []
    if report.campus_id:
        project_filter.append(Project.campus_id == report.campus_id)
    if report.program_type_id:
        project_filter.append(Project.program_type_id == report.program_type_id)
    if report.project_id:
        project_filter.append(Project.id == report.project_id)

    projects_query = Project.query
    if project_filter:
        projects_query = projects_query.filter(*project_filter)
    
    if report.start_date:
        projects_query = projects_query.filter(Project.end_date >= report.start_date)
    if report.end_date:
        projects_query = projects_query.filter(Project.start_date <= report.end_date)
        
    projects = projects_query.all()
    project_ids = [p.id for p in projects]
    
    if not project_ids:
        return False
        
    # Check if the user has contributed to any of these projects
    is_participant = ProjectParticipant.query.filter(
        ProjectParticipant.project_id.in_(project_ids),
        ProjectParticipant.user_id == user.id
    ).first() is not None
    if is_participant:
        return True
        
    has_contrib = Contribution.query.filter(
        Contribution.project_id.in_(project_ids),
        Contribution.user_id == user.id
    ).first() is not None
    if has_contrib:
        return True
        
    has_att = AttendanceRecord.query.filter(
        AttendanceRecord.project_id.in_(project_ids),
        AttendanceRecord.user_id == user.id
    ).first() is not None
    return has_att

def _get_report_data(report):
    project_filter = []
    if report.campus_id:
        project_filter.append(Project.campus_id == report.campus_id)
    if report.program_type_id:
        project_filter.append(Project.program_type_id == report.program_type_id)
    if report.project_id:
        project_filter.append(Project.id == report.project_id)

    projects_query = Project.query
    if project_filter:
        projects_query = projects_query.filter(*project_filter)
    
    if report.start_date:
        projects_query = projects_query.filter(Project.end_date >= report.start_date)
    if report.end_date:
        projects_query = projects_query.filter(Project.start_date <= report.end_date)
        
    projects = projects_query.all()
    project_ids = [p.id for p in projects]

    summary = {
        'project_count': len(projects),
        'total_participants': 0,
        'attendance_rate': 100.0,
        'contribution_hours': 0.0,
        'average_feedback': 0.0,
        'feedback_count': 0
    }

    if project_ids:
        summary['total_participants'] = db.session.query(func.count(func.distinct(ProjectParticipant.user_id))).filter(
            ProjectParticipant.project_id.in_(project_ids),
            ProjectParticipant.status == 'Active'
        ).scalar() or 0

        att_query = db.session.query(
            func.count(AttendanceRecord.id),
            func.sum(db.case((AttendanceRecord.status == 'Present', 1), else_=0))
        ).filter(AttendanceRecord.project_id.in_(project_ids))
        if report.start_date:
            att_query = att_query.filter(AttendanceRecord.date >= report.start_date)
        if report.end_date:
            att_query = att_query.filter(AttendanceRecord.date <= report.end_date)
            
        total_att, present_att = att_query.first()
        summary['attendance_rate'] = round((present_att / total_att) * 100, 1) if (total_att and total_att > 0) else 100.0

        contrib_query = db.session.query(func.sum(Contribution.duration_hours)).filter(
            Contribution.project_id.in_(project_ids),
            Contribution.approval_status == 'Approved'
        )
        summary['contribution_hours'] = round(contrib_query.scalar() or 0.0, 1)

        feedback_query = db.session.query(
            func.avg(Feedback.rating),
            func.count(Feedback.id)
        ).filter(Feedback.project_id.in_(project_ids))
        avg_f, count_f = feedback_query.first()
        summary['average_feedback'] = round(avg_f, 2) if avg_f is not None else 0.0
        summary['feedback_count'] = count_f or 0

    return projects, summary

def calculate_project_progress(projects):
    today = datetime.utcnow().date()
    for p in projects:
        if p.end_date <= p.start_date:
            p.progress_percent = 100
        elif today < p.start_date:
            p.progress_percent = 0
        elif today > p.end_date:
            p.progress_percent = 100
        else:
            total_days = (p.end_date - p.start_date).days
            elapsed_days = (today - p.start_date).days
            p.progress_percent = min(100, max(0, int((elapsed_days / total_days) * 100)))

def get_combined_activities(recent_contributions, recent_buddy_logs):
    recent_activities = []
    for c in recent_contributions:
        recent_activities.append({
            'type': 'contribution',
            'user': c.user.username,
            'project': c.project.title,
            'desc': f"logged {c.duration_hours} hours for {c.activity_type}",
            'status': c.approval_status,
            'id': c.id,
            'project_id': c.project_id,
            'campus_id': c.project.campus_id
        })
    for b in recent_buddy_logs:
        recent_activities.append({
            'type': 'buddy_log',
            'user': b.assignment.buddy.username if b.assignment and b.assignment.buddy else 'Unknown',
            'project': b.assignment.project.title if b.assignment and b.assignment.project else 'Unknown',
            'desc': f"logged interaction with {b.assignment.exchange_student.username if b.assignment and b.assignment.exchange_student else 'student'}",
            'status': b.status,
            'id': b.id,
            'project_id': b.assignment.project_id if b.assignment else None,
            'campus_id': b.assignment.project.campus_id if b.assignment and b.assignment.project else None
        })
    recent_activities.sort(key=lambda x: x['id'], reverse=True)
    return recent_activities[:10]

@dashboard_bp.route('/')
@login_required
def index():
    # Load all academic years and select the current one
    academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    
    current_year_id = request.args.get('academic_year_id', type=int)
    if not current_year_id:
        current_year = AcademicYear.query.filter_by(is_current=True).first()
        current_year_id = current_year.id if current_year else (academic_years[0].id if academic_years else None)

    # Branch based on user roles
    role = g.user.role

    # Check if core roles or faculty
    is_faculty = (role == 'Faculty')
    is_igp_core = (role == 'IGP Core')
    is_icc_core = (role in ['ICC Events Core', 'ICC Cultural Core', 'ICC Media Core', 'ICC Core Committee'])
    is_volunteer = (role in ['Volunteer', 'Buddy', 'ICC Event Volunteer', 'IGP Buddy'])

    if is_faculty:
        # ----------------- FACULTY DASHBOARD (No change) -----------------
        stats = AnalyticsService.get_global_overview(academic_year_id=current_year_id)
        
        # Fetch active projects list for preview
        active_projects = Project.query.filter_by(status='Active')
        if current_year_id:
            active_projects = active_projects.filter_by(academic_year_id=current_year_id)
        active_projects = active_projects.order_by(Project.start_date).limit(5).all()
        calculate_project_progress(active_projects)

        # Campuses list for the drill-down selector
        campuses = Campus.query.all()
        
        # Fetch pending items for admin/faculty review
        pending_registrations = User.query.filter_by(status='Pending').order_by(User.created_at.desc()).all()
        pending_contributions = Contribution.query.filter_by(approval_status='Pending').order_by(Contribution.id.desc()).all()
        pending_buddy_logs = BuddyLog.query.filter_by(status='Pending').order_by(BuddyLog.id.desc()).all()

        # Fetch recent activity
        recent_contributions = Contribution.query.order_by(Contribution.id.desc()).limit(5).all()
        recent_buddy_logs = BuddyLog.query.order_by(BuddyLog.id.desc()).limit(5).all()
        recent_activities = get_combined_activities(recent_contributions, recent_buddy_logs)

        # Timeline of upcoming events (planned or active projects)
        upcoming_events = Project.query.filter(Project.status.in_(['Planned', 'Active']))
        if current_year_id:
            upcoming_events = upcoming_events.filter_by(academic_year_id=current_year_id)
        upcoming_events = upcoming_events.order_by(Project.start_date.asc()).limit(5).all()

        return render_template(
            'dashboard/index.html',
            stats=stats,
            academic_years=academic_years,
            selected_year_id=current_year_id,
            active_projects=active_projects,
            campuses=campuses,
            pending_registrations=pending_registrations,
            pending_contributions=pending_contributions,
            pending_buddy_logs=pending_buddy_logs,
            recent_activities=recent_activities,
            upcoming_events=upcoming_events
        )

    elif is_igp_core or is_icc_core:
        # ----------------- CAMPUS & PROGRAM SPECIFIC CORE DASHBOARD -----------------
        campus_id = g.user.campus_id
        if not campus_id:
            campus_id = Campus.query.first().id if Campus.query.first() else None

        program_name = 'IGP' if is_igp_core else 'ICC'
        program_type = ProgramType.query.filter_by(name=program_name).first()
        program_type_id = program_type.id if program_type else None

        # Fetch filtered stats
        stats = AnalyticsService.get_program_campus_overview(program_name, campus_id, academic_year_id=current_year_id)

        # Active projects for this campus & program
        active_projects_query = Project.query.filter_by(status='Active', campus_id=campus_id)
        if program_type_id:
            active_projects_query = active_projects_query.filter_by(program_type_id=program_type_id)
        if current_year_id:
            active_projects_query = active_projects_query.filter_by(academic_year_id=current_year_id)
        active_projects = active_projects_query.order_by(Project.start_date).limit(5).all()
        calculate_project_progress(active_projects)

        # Upcoming events for this campus & program
        upcoming_query = Project.query.filter(Project.status.in_(['Planned', 'Active']), Project.campus_id == campus_id)
        if program_type_id:
            upcoming_query = upcoming_query.filter_by(program_type_id=program_type_id)
        if current_year_id:
            upcoming_query = upcoming_query.filter_by(academic_year_id=current_year_id)
        upcoming_events = upcoming_query.order_by(Project.start_date.asc()).limit(5).all()

        # Pending approvals (only for this campus & program)
        pending_registrations = User.query.filter_by(status='Pending', campus_id=campus_id).order_by(User.created_at.desc()).all()
        
        pending_contribs_query = Contribution.query.filter_by(approval_status='Pending').join(Project).filter(Project.campus_id == campus_id)
        if program_type_id:
            pending_contribs_query = pending_contribs_query.filter(Project.program_type_id == program_type_id)
        pending_contributions = pending_contribs_query.order_by(Contribution.id.desc()).all()

        pending_buddy_logs = []
        if is_igp_core:
            pending_buddy_logs_query = BuddyLog.query.filter_by(status='Pending').join(BuddyAssignment).join(Project).filter(Project.campus_id == campus_id)
            if program_type_id:
                pending_buddy_logs_query = pending_buddy_logs_query.filter(Project.program_type_id == program_type_id)
            pending_buddy_logs = pending_buddy_logs_query.order_by(BuddyLog.id.desc()).all()

        # Recent activities (filtered by campus and program)
        recent_contribs_query = Contribution.query.join(Project).filter(Project.campus_id == campus_id)
        if program_type_id:
            recent_contribs_query = recent_contribs_query.filter(Project.program_type_id == program_type_id)
        recent_contributions = recent_contribs_query.order_by(Contribution.id.desc()).limit(5).all()

        recent_buddy_logs = []
        if is_igp_core:
            recent_buddy_logs_query = BuddyLog.query.join(BuddyAssignment).join(Project).filter(Project.campus_id == campus_id)
            if program_type_id:
                recent_buddy_logs_query = recent_buddy_logs_query.filter(Project.program_type_id == program_type_id)
            recent_buddy_logs = recent_buddy_logs_query.order_by(BuddyLog.id.desc()).limit(5).all()

        recent_activities = get_combined_activities(recent_contributions, recent_buddy_logs)

        # Get campus details
        campus = Campus.query.get(campus_id)

        template_name = 'dashboard/igp_core.html' if is_igp_core else 'dashboard/icc_core.html'
        return render_template(
            template_name,
            stats=stats,
            academic_years=academic_years,
            selected_year_id=current_year_id,
            active_projects=active_projects,
            pending_registrations=pending_registrations,
            pending_contributions=pending_contributions,
            pending_buddy_logs=pending_buddy_logs,
            recent_activities=recent_activities,
            upcoming_events=upcoming_events,
            campus=campus
        )

    else:
        # ----------------- VOLUNTEER & BUDDY PERSONALIZED DASHBOARD -----------------
        user_id = g.user.id
        stats = AnalyticsService.get_volunteer_overview(user_id, academic_year_id=current_year_id)

        # Approved contributions
        approved_contributions = Contribution.query.filter_by(user_id=user_id, approval_status='Approved').order_by(Contribution.id.desc()).limit(10).all()
        
        # Approved buddy logs
        approved_buddy_logs = BuddyLog.query.join(BuddyAssignment).filter(
            BuddyAssignment.buddy_user_id == user_id,
            BuddyLog.status == 'Approved'
        ).order_by(BuddyLog.id.desc()).limit(10).all()

        # Pending items
        pending_contributions = Contribution.query.filter_by(user_id=user_id, approval_status='Pending').order_by(Contribution.id.desc()).all()
        pending_buddy_logs = BuddyLog.query.join(BuddyAssignment).filter(
            BuddyAssignment.buddy_user_id == user_id,
            BuddyLog.status == 'Pending'
        ).order_by(BuddyLog.id.desc()).all()

        # Attendance records
        attendance_records = AttendanceRecord.query.filter_by(user_id=user_id).order_by(AttendanceRecord.date.desc()).limit(10).all()

        # Enrolled active projects for shortcuts
        enrolled_participants = ProjectParticipant.query.filter_by(user_id=user_id, status='Active').all()
        enrolled_projects = [ep.project for ep in enrolled_participants if ep.project.status == 'Active']
        calculate_project_progress(enrolled_projects)

        # All buddy assignments (active)
        buddy_assignments = BuddyAssignment.query.filter_by(buddy_user_id=user_id, status='Active').all()

        return render_template(
            'dashboard/volunteer.html',
            stats=stats,
            academic_years=academic_years,
            selected_year_id=current_year_id,
            approved_contributions=approved_contributions,
            approved_buddy_logs=approved_buddy_logs,
            pending_contributions=pending_contributions,
            pending_buddy_logs=pending_buddy_logs,
            attendance_records=attendance_records,
            enrolled_projects=enrolled_projects,
            buddy_assignments=buddy_assignments
        )


@dashboard_bp.route('/admin/users', methods=['GET', 'POST'])
@login_required
@role_required('Faculty')
def admin_users():
    pending_users = User.query.filter_by(status='Pending').order_by(User.created_at.desc()).all()
    approved_users = User.query.filter(User.status == 'Approved', User.id != g.user.id).order_by(User.username).all()
    campuses = Campus.query.all()

    return render_template(
        'dashboard/users.html',
        pending_users=pending_users,
        approved_users=approved_users,
        campuses=campuses
    )

@dashboard_bp.route('/admin/users/approve/<int:user_id>', methods=['POST'])
@login_required
@role_required('Faculty')
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    assigned_role = request.form.get('role')
    
    if not assigned_role or assigned_role == 'Pending':
        flash("Please assign a valid role for approval.", "warning")
        return redirect(url_for('dashboard.admin_users'))

    user.role = assigned_role
    user.status = 'Approved'
    user.approved_by_id = g.user.id
    user.approved_at = datetime.utcnow()
    db.session.commit()

    flash(f"User {user.username} has been approved as {assigned_role}.", "success")
    return redirect(url_for('dashboard.admin_users'))

@dashboard_bp.route('/admin/users/reject/<int:user_id>', methods=['POST'])
@login_required
@role_required('Faculty')
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = 'Rejected'
    db.session.commit()

    flash(f"User {user.username} registration has been rejected.", "info")
    return redirect(url_for('dashboard.admin_users'))

@dashboard_bp.route('/admin/users/modify-role/<int:user_id>', methods=['POST'])
@login_required
@role_required('Faculty')
def modify_user_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    
    if user.id == g.user.id:
        flash("You cannot modify your own role.", "danger")
        return redirect(url_for('dashboard.admin_users'))

    if new_role:
        user.role = new_role
        db.session.commit()
        flash(f"Role for {user.username} updated to {new_role}.", "success")
    
    return redirect(url_for('dashboard.admin_users'))


@dashboard_bp.route('/reports')
@login_required
def list_reports():
    all_reports = Report.query.order_by(Report.created_at.desc()).all()
    if g.user.role in ['Volunteer', 'Buddy', 'ICC Event Volunteer', 'IGP Buddy']:
        reports = [r for r in all_reports if has_contributed_to_report(g.user, r)]
    else:
        reports = all_reports
    return render_template('reports/list.html', reports=reports)


@dashboard_bp.route('/reports/generate', methods=['GET', 'POST'])
@login_required
@role_required('Faculty', 'ICC Core Committee', 'IGP Core', 'ICC Events Core', 'ICC Cultural Core', 'ICC Media Core')
def generate_report():
    campuses = Campus.query.all()
    program_types = ProgramType.query.all()
    projects = Project.query.order_by(Project.title).all()

    if request.method == 'POST':
        report_type = request.form.get('report_type')
        title = request.form.get('title').strip()
        description = request.form.get('description').strip()
        
        campus_id = request.form.get('campus_id')
        program_type_id = request.form.get('program_type_id')
        project_id = request.form.get('project_id')
        
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        if not title:
            flash("Report Title is required.", "danger")
            return render_template('reports/generate.html', campuses=campuses, program_types=program_types, projects=projects)

        # Create report configuration metadata
        report = Report(
            report_type=report_type,
            title=title,
            description=description,
            campus_id=int(campus_id) if campus_id else None,
            program_type_id=int(program_type_id) if program_type_id else None,
            project_id=int(project_id) if project_id else None,
            start_date=datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None,
            end_date=datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None,
            generated_by_id=g.user.id
        )
        db.session.add(report)
        db.session.commit()

        flash(f"Report '{title}' configuration saved. Stats compiled dynamically below.", "success")
        return redirect(url_for('dashboard.view_report', report_id=report.id))

    return render_template('reports/generate.html', campuses=campuses, program_types=program_types, projects=projects)

@dashboard_bp.route('/reports/view/<int:report_id>')
@login_required
def view_report(report_id):
    report = Report.query.get_or_404(report_id)
    if not has_contributed_to_report(g.user, report):
        abort(403)

    projects, summary = _get_report_data(report)
    return render_template('reports/view.html', report=report, projects=projects, summary=summary)

@dashboard_bp.route('/reports/export/<int:report_id>')
@login_required
def export_report(report_id):
    report = Report.query.get_or_404(report_id)
    if not has_contributed_to_report(g.user, report):
        abort(403)

    projects, summary = _get_report_data(report)

    # 1. Summary Sheet Data
    summary_data = {
        'Report Property': [
            'Report Title', 'Report Type', 'Description', 'Campus Boundary', 
            'Program Boundary', 'Start Date Limit', 'End Date Limit',
            'Projects Compiled', 'Total Active Participants', 'Overall Attendance Rate (%)',
            'Approved Contribution Hours', 'Average Feedback Score', 'Feedback Submissions Count',
            'Compiled By', 'Compiled At'
        ],
        'Value': [
            report.title,
            report.report_type,
            report.description or 'No description',
            get_campus_name(report.campus_id),
            report.program_type.name if report.program_type_id else 'All Programs',
            report.start_date.strftime('%Y-%m-%d') if report.start_date else 'All Time',
            report.end_date.strftime('%Y-%m-%d') if report.end_date else 'All Time',
            summary['project_count'],
            summary['total_participants'],
            summary['attendance_rate'],
            summary['contribution_hours'],
            summary['average_feedback'],
            summary['feedback_count'],
            report.generated_by.username if report.generated_by else 'System',
            report.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ]
    }
    df_summary = pd.DataFrame(summary_data)

    # 2. Projects Sheet Data
    proj_rows = []
    for p in projects:
        proj_rows.append({
            'Project ID': p.id,
            'Title': p.title,
            'Campus': p.campus.name,
            'Program Type': p.program_type.name,
            'Category': p.category,
            'Start Date': p.start_date.strftime('%Y-%m-%d'),
            'End Date': p.end_date.strftime('%Y-%m-%d'),
            'Status': p.status
        })
    df_projects = pd.DataFrame(proj_rows) if proj_rows else pd.DataFrame(columns=[
        'Project ID', 'Title', 'Campus', 'Program Type', 'Category', 'Start Date', 'End Date', 'Status'
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='Summary Metrics', index=False)
        df_projects.to_excel(writer, sheet_name='Projects List', index=False)
    
    output.seek(0)
    filename = f"report_{report_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#718096"))
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 54, 36, page_text)
        self.drawString(54, 36, "OIA Project Intelligence Platform | Confidential")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 48, letter[0] - 54, 48)
        self.restoreState()

@dashboard_bp.route('/reports/export-pdf/<int:report_id>')
@login_required
def export_report_pdf(report_id):
    report = Report.query.get_or_404(report_id)
    if not has_contributed_to_report(g.user, report):
        abort(403)

    projects, summary = _get_report_data(report)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=72
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=8
    )
    
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=15
    )
    
    h2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#2C5282"),
        spaceBefore=15,
        spaceAfter=8,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2D3748")
    )
    
    header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white
    )

    story = []

    story.append(Paragraph(report.title, title_style))
    story.append(Paragraph(report.description or "No description provided.", subtitle_style))
    
    meta_data = [
        [Paragraph("Report Type", body_style), Paragraph(report.report_type, body_style)],
        [Paragraph("Campus Scope", body_style), Paragraph(get_campus_name(report.campus_id), body_style)],
        [Paragraph("Program Scope", body_style), Paragraph(report.program_type.name if report.program_type_id else "All Programs", body_style)],
        [Paragraph("Timeline", body_style), Paragraph(f"{report.start_date.strftime('%b %d, %Y') if report.start_date else 'All time'} to {report.end_date.strftime('%b %d, %Y') if report.end_date else 'All time'}", body_style)],
        [Paragraph("Generated By", body_style), Paragraph(report.generated_by.username if report.generated_by else "System", body_style)],
        [Paragraph("Generated At", body_style), Paragraph(report.created_at.strftime('%b %d, %Y %I:%M %p'), body_style)]
    ]
    meta_table = Table(meta_data, colWidths=[2.0*inch, 4.0*inch])
    meta_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#EDF2F7")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Summary Performance Metrics", h2_style))
    metrics_data = [
        [
            Paragraph("Metric", header_style), 
            Paragraph("Value", header_style),
            Paragraph("Metric", header_style),
            Paragraph("Value", header_style)
        ],
        [
            Paragraph("Compiled Projects", body_style), 
            Paragraph(str(summary['project_count']), body_style),
            Paragraph("Active Participants", body_style),
            Paragraph(str(summary['total_participants']), body_style)
        ],
        [
            Paragraph("Approved Contribution Hours", body_style), 
            Paragraph(f"{summary['contribution_hours']} hrs", body_style),
            Paragraph("Overall Attendance Rate", body_style),
            Paragraph(f"{summary['attendance_rate']}%", body_style)
        ],
        [
            Paragraph("Feedback Submissions", body_style), 
            Paragraph(str(summary['feedback_count']), body_style),
            Paragraph("Average Feedback Score", body_style),
            Paragraph(f"{summary['average_feedback']} / 5.0", body_style)
        ]
    ]
    metrics_table = Table(metrics_data, colWidths=[2.0*inch, 1.25*inch, 1.75*inch, 1.0*inch])
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,1), (0,-1), colors.HexColor("#F7FAFC")),
        ('BACKGROUND', (2,1), (2,-1), colors.HexColor("#F7FAFC")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Compiled Projects Workspace", h2_style))
    
    headers = [
        Paragraph("Project Workspace", header_style),
        Paragraph("Campus", header_style),
        Paragraph("Program", header_style),
        Paragraph("Category", header_style),
        Paragraph("Date Range", header_style),
        Paragraph("Status", header_style)
    ]
    
    projects_table_data = [headers]
    for p in projects:
        timeline = p.start_date.strftime('%Y-%m-%d')
        if p.end_date and p.end_date != p.start_date:
            timeline += f" to {p.end_date.strftime('%Y-%m-%d')}"
            
        projects_table_data.append([
            Paragraph(p.title, body_style),
            Paragraph(p.campus.name.replace(" Campus", ""), body_style),
            Paragraph(p.program_type.name, body_style),
            Paragraph(p.category, body_style),
            Paragraph(timeline, body_style),
            Paragraph(p.status, body_style)
        ])
        
    col_widths = [1.8*inch, 1.1*inch, 0.7*inch, 1.0*inch, 1.5*inch, 0.9*inch]
    projects_table = Table(projects_table_data, colWidths=col_widths, repeatRows=1)
    
    ts = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2C5282")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]
    for r in range(1, len(projects_table_data)):
        if r % 2 == 0:
            ts.append(('BACKGROUND', (0,r), (-1,r), colors.HexColor("#F7FAFC")))
            
    projects_table.setStyle(TableStyle(ts))
    story.append(projects_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    
    buffer.seek(0)
    filename = f"report_{report_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@dashboard_bp.route('/profile')
@login_required
def profile():
    volunteer_profile = Volunteer.query.filter_by(user_id=g.user.id).first()
    
    approved_contribs = Contribution.query.filter_by(user_id=g.user.id, approval_status='Approved').all()
    skills_hours = {}
    for c in approved_contribs:
        skills_hours[c.activity_type] = skills_hours.get(c.activity_type, 0) + c.duration_hours
        
    participated_ids = [p.project_id for p in ProjectParticipant.query.filter_by(user_id=g.user.id).all()]
    contrib_ids = [c.project_id for c in Contribution.query.filter_by(user_id=g.user.id).all()]
    att_ids = [a.project_id for a in AttendanceRecord.query.filter_by(user_id=g.user.id).all()]
    all_project_ids = list(set(participated_ids + contrib_ids + att_ids))
    
    contributed_projects = []
    if all_project_ids:
        contributed_projects = Project.query.filter(Project.id.in_(all_project_ids)).order_by(Project.start_date.desc()).all()

    return render_template(
        'dashboard/profile.html',
        volunteer_profile=volunteer_profile,
        skills_hours=skills_hours,
        contributed_projects=contributed_projects
    )

@dashboard_bp.app_template_global()
def get_campus_name(campus_id):
    campus = Campus.query.get(campus_id)
    return campus.name if campus else "All Campuses"

@dashboard_bp.app_template_global()
def get_project_title(project_id):
    project = Project.query.get(project_id)
    return project.title if project else "Unknown Project"
