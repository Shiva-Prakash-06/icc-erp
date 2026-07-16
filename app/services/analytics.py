from sqlalchemy import func
from app.database import db
from app.models.user import User, Volunteer
from app.models.project import AcademicYear, Campus, ProgramType, Project, ProjectParticipant, BuddyAssignment, BuddyLog
from app.models.operational import AttendanceRecord, Contribution, Feedback, Document, Report
from datetime import datetime

class AnalyticsService:
    @staticmethod
    def get_project_summary(project_id):
        """
        Dynamically computes the statistics for a single project.
        """
        project = Project.query.get(project_id)
        if not project:
            return None

        # 1. Participants count & type breakdown
        participants_query = db.session.query(
            ProjectParticipant.participant_type, 
            func.count(ProjectParticipant.id)
        ).filter(ProjectParticipant.project_id == project_id, ProjectParticipant.status == 'Active').group_by(ProjectParticipant.participant_type).all()
        
        participant_breakdown = {t: count for t, count in participants_query}
        total_participants = sum(participant_breakdown.values())

        # 2. Attendance rates
        total_attendance = AttendanceRecord.query.filter_by(project_id=project_id).count()
        present_attendance = AttendanceRecord.query.filter_by(project_id=project_id, status='Present').count()
        attendance_rate = round((present_attendance / total_attendance) * 100, 1) if total_attendance > 0 else 100.0

        # 3. Contributions hours
        total_hours = db.session.query(func.sum(Contribution.duration_hours)).filter(
            Contribution.project_id == project_id,
            Contribution.approval_status == 'Approved'
        ).scalar() or 0.0
        total_hours = round(total_hours, 1)

        # 4. Feedback ratings
        feedback_stats = db.session.query(
            func.avg(Feedback.rating),
            func.count(Feedback.id)
        ).filter(Feedback.project_id == project_id).first()
        
        avg_rating = round(feedback_stats[0], 2) if feedback_stats[0] is not None else None
        feedback_count = feedback_stats[1] or 0

        # 5. Documents count
        doc_count = Document.query.filter_by(project_id=project_id).count()

        # 6. Buddy assignments
        buddy_count = BuddyAssignment.query.filter_by(project_id=project_id, status='Active').count()
        
        # 7. Buddy log hours (Approved)
        buddy_hours = db.session.query(func.sum(BuddyLog.duration_hours)).join(BuddyAssignment).filter(
            BuddyAssignment.project_id == project_id,
            BuddyLog.status == 'Approved'
        ).scalar() or 0.0
        buddy_hours = round(buddy_hours, 1)

        return {
            'project': project,
            'total_participants': total_participants,
            'participant_breakdown': participant_breakdown,
            'attendance_rate': attendance_rate,
            'total_attendance_records': total_attendance,
            'present_records': present_attendance,
            'total_contribution_hours': total_hours,
            'avg_feedback_rating': avg_rating,
            'feedback_count': feedback_count,
            'document_count': doc_count,
            'buddy_count': buddy_count,
            'buddy_hours': buddy_hours
        }

    @staticmethod
    def get_campus_summary(campus_id, academic_year_id=None):
        """
        Dynamically computes campus-level metrics.
        """
        campus = Campus.query.get(campus_id)
        if not campus:
            return None

        # Filter base
        project_filter = [Project.campus_id == campus_id]
        if academic_year_id:
            project_filter.append(Project.academic_year_id == academic_year_id)

        # 1. Projects count by status
        status_query = db.session.query(
            Project.status,
            func.count(Project.id)
        ).filter(*project_filter).group_by(Project.status).all()
        status_counts = {status: count for status, count in status_query}
        total_projects = sum(status_counts.values())

        # 2. Total active participants
        active_participants = db.session.query(func.count(func.distinct(ProjectParticipant.user_id))).join(Project).filter(
            Project.campus_id == campus_id,
            ProjectParticipant.status == 'Active'
        )
        if academic_year_id:
            active_participants = active_participants.filter(Project.academic_year_id == academic_year_id)
        active_participants = active_participants.scalar() or 0

        # 3. Overall attendance rate
        att_query = db.session.query(
            func.count(AttendanceRecord.id),
            func.sum(db.case((AttendanceRecord.status == 'Present', 1), else_=0))
        ).join(Project).filter(Project.campus_id == campus_id)
        if academic_year_id:
            att_query = att_query.filter(Project.academic_year_id == academic_year_id)
        total_att, present_att = att_query.first()
        attendance_rate = round((present_att / total_att) * 100, 1) if (total_att and total_att > 0) else 100.0

        # 4. Total contribution hours
        hours_query = db.session.query(func.sum(Contribution.duration_hours)).join(Project).filter(
            Project.campus_id == campus_id,
            Contribution.approval_status == 'Approved'
        )
        if academic_year_id:
            hours_query = hours_query.filter(Project.academic_year_id == academic_year_id)
        contribution_hours = round(hours_query.scalar() or 0.0, 1)

        # 5. Program type distribution
        prog_query = db.session.query(
            ProgramType.name,
            func.count(Project.id)
        ).join(ProgramType).filter(*project_filter).group_by(ProgramType.name).all()
        program_distribution = {name: count for name, count in prog_query}

        return {
            'campus': campus,
            'total_projects': total_projects,
            'projects_by_status': status_counts,
            'active_participants': active_participants,
            'attendance_rate': attendance_rate,
            'contribution_hours': contribution_hours,
            'program_distribution': program_distribution
        }

    @staticmethod
    def get_global_overview(academic_year_id=None):
        """
        Computes high-level strategic intelligence metrics for the main Mission Control dashboard.
        """
        # Filter projects
        project_filter = []
        if academic_year_id:
            project_filter.append(Project.academic_year_id == academic_year_id)

        # 1. Active, Completed, Planned counts
        status_query = db.session.query(
            Project.status,
            func.count(Project.id)
        )
        if project_filter:
            status_query = status_query.filter(*project_filter)
        status_query = status_query.group_by(Project.status).all()
        status_counts = {status: count for status, count in status_query}
        total_projects = sum(status_counts.values())

        # 2. Campus project counts
        campus_query = db.session.query(
            Campus.name,
            func.count(Project.id)
        ).join(Project, Campus.id == Project.campus_id)
        if project_filter:
            campus_query = campus_query.filter(*project_filter)
        campus_projects = {name: count for name, count in campus_query.group_by(Campus.name).all()}

        # 3. Overall volunteers active count
        volunteers_count = db.session.query(func.count(func.distinct(ProjectParticipant.user_id))).join(Project).filter(
            ProjectParticipant.participant_type == 'Volunteer',
            ProjectParticipant.status == 'Active'
        )
        if academic_year_id:
            volunteers_count = volunteers_count.filter(Project.academic_year_id == academic_year_id)
        volunteers_count = volunteers_count.scalar() or 0

        # 4. Buddy assignments active count
        buddy_count = db.session.query(func.count(BuddyAssignment.id)).join(Project).filter(
            BuddyAssignment.status == 'Active'
        )
        if academic_year_id:
            buddy_count = buddy_count.filter(Project.academic_year_id == academic_year_id)
        buddy_count = buddy_count.scalar() or 0

        # 5. Total contribution hours
        hours_query = db.session.query(func.sum(Contribution.duration_hours)).join(Project).filter(
            Contribution.approval_status == 'Approved'
        )
        if academic_year_id:
            hours_query = hours_query.filter(Project.academic_year_id == academic_year_id)
        contribution_hours = round(hours_query.scalar() or 0.0, 1)

        # 6. Overall average attendance
        att_query = db.session.query(
            func.count(AttendanceRecord.id),
            func.sum(db.case((AttendanceRecord.status == 'Present', 1), else_=0))
        ).join(Project)
        if academic_year_id:
            att_query = att_query.filter(Project.academic_year_id == academic_year_id)
        total_att, present_att = att_query.first()
        attendance_rate = round((present_att / total_att) * 100, 1) if (total_att and total_att > 0) else 100.0

        # 7. IGP vs ICC breakdown
        prog_query = db.session.query(
            ProgramType.name,
            func.count(Project.id)
        ).join(Project, ProgramType.id == Project.program_type_id)
        if project_filter:
            prog_query = prog_query.filter(*project_filter)
        program_counts = {name: count for name, count in prog_query.group_by(ProgramType.name).all()}

        return {
            'total_projects': total_projects,
            'projects_by_status': status_counts,
            'campus_distribution': campus_projects,
            'active_volunteers': volunteers_count,
            'active_buddies': buddy_count,
            'total_contribution_hours': contribution_hours,
            'overall_attendance_rate': attendance_rate,
            'program_breakdown': program_counts
        }

    @staticmethod
    def get_attendance_analytics(campus_id=None, program_type_id=None, academic_year_id=None, project_id=None, start_date=None, end_date=None):
        """
        Retrieves detailed attendance logs grouped by date or project.
        """
        query = db.session.query(
            AttendanceRecord.date,
            func.count(AttendanceRecord.id).label('total'),
            func.sum(db.case((AttendanceRecord.status == 'Present', 1), else_=0)).label('present')
        ).join(Project)

        if campus_id:
            query = query.filter(Project.campus_id == campus_id)
        if program_type_id:
            query = query.filter(Project.program_type_id == program_type_id)
        if academic_year_id:
            query = query.filter(Project.academic_year_id == academic_year_id)
        if project_id:
            query = query.filter(AttendanceRecord.project_id == project_id)
        if start_date:
            query = query.filter(AttendanceRecord.date >= start_date)
        if end_date:
            query = query.filter(AttendanceRecord.date <= end_date)

        results = query.group_by(AttendanceRecord.date).order_by(AttendanceRecord.date).all()
        
        analytics_data = []
        for row in results:
            total = row.total
            present = row.present or 0
            rate = round((present / total) * 100, 1) if total > 0 else 100.0
            analytics_data.append({
                'date': row.date.strftime('%Y-%m-%d'),
                'total': total,
                'present': present,
                'absent': total - present,
                'rate': rate
            })
        return analytics_data

    @staticmethod
    def get_volunteer_analytics(campus_id=None, program_type_id=None, academic_year_id=None, project_id=None, division=None):
        """
        Retrieves volunteer logging and contribution metrics.
        """
        # Hours by activity type
        act_query = db.session.query(
            Contribution.activity_type,
            func.sum(Contribution.duration_hours)
        ).join(Project).filter(Contribution.approval_status == 'Approved')

        # Hours by division
        div_query = db.session.query(
            Contribution.division,
            func.sum(Contribution.duration_hours)
        ).join(Project).filter(Contribution.approval_status == 'Approved')

        # Top contributors
        top_query = db.session.query(
            User.username,
            func.sum(Contribution.duration_hours).label('total_hours')
        ).join(Contribution, User.id == Contribution.user_id).join(Project).filter(Contribution.approval_status == 'Approved')

        filters = []
        if campus_id:
            filters.append(Project.campus_id == campus_id)
        if program_type_id:
            filters.append(Project.program_type_id == program_type_id)
        if academic_year_id:
            filters.append(Project.academic_year_id == academic_year_id)
        if project_id:
            filters.append(Contribution.project_id == project_id)
        if division:
            filters.append(Contribution.division == division)

        if filters:
            act_query = act_query.filter(*filters)
            div_query = div_query.filter(*filters)
            top_query = top_query.filter(*filters)

        activity_hours = {act: round(hours or 0.0, 1) for act, hours in act_query.group_by(Contribution.activity_type).all()}
        division_hours = {div or 'General': round(hours or 0.0, 1) for div, hours in div_query.group_by(Contribution.division).all()}
        top_volunteers = [{'username': name, 'hours': round(hours or 0.0, 1)} for name, hours in top_query.group_by(User.id).order_by(db.desc('total_hours')).limit(10).all()]

        return {
            'activity_hours': activity_hours,
            'division_hours': division_hours,
            'top_volunteers': top_volunteers
        }

    @staticmethod
    def get_feedback_analytics(project_id=None, campus_id=None, program_type_id=None, academic_year_id=None):
        """
        Gathers feedback analytics: ratings count, average, and star distributions.
        """
        query = db.session.query(Feedback).join(Project)
        if project_id:
            query = query.filter(Feedback.project_id == project_id)
        if campus_id:
            query = query.filter(Project.campus_id == campus_id)
        if program_type_id:
            query = query.filter(Project.program_type_id == program_type_id)
        if academic_year_id:
            query = query.filter(Project.academic_year_id == academic_year_id)

        feedback_records = query.all()
        total = len(feedback_records)
        
        ratings = [f.rating for f in feedback_records]
        avg_rating = round(sum(ratings) / total, 2) if total > 0 else 0.0
        
        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in ratings:
            if r in distribution:
                distribution[r] += 1

        return {
            'total_feedback': total,
            'average_rating': avg_rating,
            'distribution': distribution,
            'feedbacks': feedback_records[-20:] # Return last 20 feedback entries
        }

    @staticmethod
    def get_program_campus_overview(program_name, campus_id, academic_year_id=None):
        """
        Computes campus and program specific metrics (e.g. for IGP Core or ICC Core dashboards).
        """
        program_type = ProgramType.query.filter_by(name=program_name).first()
        program_type_id = program_type.id if program_type else None

        # Filter projects
        project_filter = [Project.campus_id == campus_id]
        if program_type_id:
            project_filter.append(Project.program_type_id == program_type_id)
        if academic_year_id:
            project_filter.append(Project.academic_year_id == academic_year_id)

        # 1. Projects count by status
        status_query = db.session.query(
            Project.status,
            func.count(Project.id)
        ).filter(*project_filter).group_by(Project.status).all()
        status_counts = {status: count for status, count in status_query}
        total_projects = sum(status_counts.values())

        # 2. Total active participants
        active_participants = db.session.query(func.count(func.distinct(ProjectParticipant.user_id))).join(Project).filter(
            Project.campus_id == campus_id,
            ProjectParticipant.status == 'Active'
        )
        if program_type_id:
            active_participants = active_participants.filter(Project.program_type_id == program_type_id)
        if academic_year_id:
            active_participants = active_participants.filter(Project.academic_year_id == academic_year_id)
        active_participants = active_participants.scalar() or 0

        # 3. Active buddies (only relevant for IGP)
        buddy_count = 0
        if program_name == 'IGP':
            buddy_count = db.session.query(func.count(BuddyAssignment.id)).join(Project).filter(
                Project.campus_id == campus_id,
                BuddyAssignment.status == 'Active'
            )
            if academic_year_id:
                buddy_count = buddy_count.filter(Project.academic_year_id == academic_year_id)
            buddy_count = buddy_count.scalar() or 0

        # 4. Total contribution hours (approved)
        hours_query = db.session.query(func.sum(Contribution.duration_hours)).join(Project).filter(
            Project.campus_id == campus_id,
            Contribution.approval_status == 'Approved'
        )
        if program_type_id:
            hours_query = hours_query.filter(Project.program_type_id == program_type_id)
        if academic_year_id:
            hours_query = hours_query.filter(Project.academic_year_id == academic_year_id)
        contribution_hours = round(hours_query.scalar() or 0.0, 1)

        # 5. Overall attendance rate
        att_query = db.session.query(
            func.count(AttendanceRecord.id),
            func.sum(db.case((AttendanceRecord.status == 'Present', 1), else_=0))
        ).join(Project).filter(Project.campus_id == campus_id)
        if program_type_id:
            att_query = att_query.filter(Project.program_type_id == program_type_id)
        if academic_year_id:
            att_query = att_query.filter(Project.academic_year_id == academic_year_id)
        total_att, present_att = att_query.first()
        present_att = present_att or 0
        attendance_rate = round((present_att / total_att) * 100, 1) if (total_att and total_att > 0) else 100.0

        return {
            'total_projects': total_projects,
            'projects_by_status': status_counts,
            'active_volunteers': active_participants,
            'active_buddies': buddy_count,
            'total_contribution_hours': contribution_hours,
            'overall_attendance_rate': attendance_rate
        }

    @staticmethod
    def get_volunteer_overview(user_id, academic_year_id=None):
        """
        Computes personalized metrics and logs for a volunteer/buddy.
        """
        # 1. Total contribution hours (approved)
        hours_query = db.session.query(func.sum(Contribution.duration_hours)).filter(
            Contribution.user_id == user_id,
            Contribution.approval_status == 'Approved'
        )
        if academic_year_id:
            hours_query = hours_query.join(Project).filter(Project.academic_year_id == academic_year_id)
        contribution_hours = round(hours_query.scalar() or 0.0, 1)

        # 2. Pending contribution hours
        pending_hours_query = db.session.query(func.sum(Contribution.duration_hours)).filter(
            Contribution.user_id == user_id,
            Contribution.approval_status == 'Pending'
        )
        if academic_year_id:
            pending_hours_query = pending_hours_query.join(Project).filter(Project.academic_year_id == academic_year_id)
        pending_contribution_hours = round(pending_hours_query.scalar() or 0.0, 1)

        # 3. Attendance rate
        att_query = db.session.query(
            func.count(AttendanceRecord.id),
            func.sum(db.case((AttendanceRecord.status == 'Present', 1), else_=0))
        ).filter(AttendanceRecord.user_id == user_id)
        if academic_year_id:
            att_query = att_query.join(Project).filter(Project.academic_year_id == academic_year_id)
        total_att, present_att = att_query.first()
        present_att = present_att or 0
        attendance_rate = round((present_att / total_att) * 100, 1) if (total_att and total_att > 0) else 100.0

        # 4. Total enrolled projects
        proj_query = db.session.query(func.count(ProjectParticipant.id)).filter(
            ProjectParticipant.user_id == user_id,
            ProjectParticipant.status == 'Active'
        )
        if academic_year_id:
            proj_query = proj_query.join(Project).filter(Project.academic_year_id == academic_year_id)
        project_count = proj_query.scalar() or 0

        # 5. Buddy assignments & buddy hours
        assignments_query = db.session.query(BuddyAssignment.id).filter(
            BuddyAssignment.buddy_user_id == user_id
        )
        if academic_year_id:
            assignments_query = assignments_query.join(Project).filter(Project.academic_year_id == academic_year_id)
        assignment_ids = [r[0] for r in assignments_query.all()]
        buddy_assignments_count = len(assignment_ids)

        buddy_hours = 0.0
        pending_buddy_hours = 0.0
        if assignment_ids:
            buddy_hours_query = db.session.query(func.sum(BuddyLog.duration_hours)).filter(
                BuddyLog.buddy_assignment_id.in_(assignment_ids),
                BuddyLog.status == 'Approved'
            )
            buddy_hours = round(buddy_hours_query.scalar() or 0.0, 1)

            pending_buddy_hours_query = db.session.query(func.sum(BuddyLog.duration_hours)).filter(
                BuddyLog.buddy_assignment_id.in_(assignment_ids),
                BuddyLog.status == 'Pending'
            )
            pending_buddy_hours = round(pending_buddy_hours_query.scalar() or 0.0, 1)

        return {
            'contribution_hours': contribution_hours,
            'pending_contribution_hours': pending_contribution_hours,
            'attendance_rate': attendance_rate,
            'total_attendance_records': total_att or 0,
            'project_count': project_count,
            'buddy_assignments_count': buddy_assignments_count,
            'buddy_hours': buddy_hours,
            'pending_buddy_hours': pending_buddy_hours
        }

