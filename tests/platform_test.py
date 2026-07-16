import os
os.environ['TESTING'] = 'True'

import unittest
from datetime import date
from app import create_app, db
from app.models.user import User, Volunteer
from app.models.project import AcademicYear, Campus, ProgramType, Project, ProjectParticipant, BuddyAssignment, BuddyLog
from app.models.operational import AttendanceRecord, Contribution, Feedback, Document, Report

class OIAPlatformTestCase(unittest.TestCase):
    def setUp(self):
        # Create app and configure for testing
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False
        
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()
            
            # Clear all table contents to prevent connection-pool leaks
            db.session.rollback()
            db.session.query(Report).delete()
            db.session.query(Document).delete()
            db.session.query(Feedback).delete()
            db.session.query(Contribution).delete()
            db.session.query(AttendanceRecord).delete()
            db.session.query(BuddyLog).delete()
            db.session.query(BuddyAssignment).delete()
            db.session.query(ProjectParticipant).delete()
            db.session.query(Project).delete()
            db.session.query(Volunteer).delete()
            db.session.query(User).delete()
            db.session.query(Campus).delete()
            db.session.query(ProgramType).delete()
            db.session.query(AcademicYear).delete()
            db.session.commit()
            
            # Seed basic lookup data
            self.ay = AcademicYear(name="2026-2027", start_date=date(2026,6,1), end_date=date(2027,5,31), is_current=True)
            self.campus = Campus(name="Bannerghatta Road Campus")
            self.prog_icc = ProgramType(name="ICC")
            self.prog_igp = ProgramType(name="IGP")
            
            db.session.add_all([self.ay, self.campus, self.prog_icc, self.prog_igp])
            db.session.commit()
            
            # Seed faculty
            self.faculty = User(
                username="faculty.test",
                email="fac@test.com",
                role="Faculty",
                preferred_role="Faculty",
                status="Approved",
                campus_id=self.campus.id,
                needs_password_reset=True
            )
            self.faculty.set_password("temp123")
            
            # Seed project
            self.project = Project(
                title="Coffee Meet",
                description="Meet & greet event",
                campus_id=self.campus.id,
                program_type_id=self.prog_icc.id,
                academic_year_id=self.ay.id,
                category="Cultural",
                status="Planned",
                start_date=date(2026, 6, 5),
                end_date=date(2026, 6, 5)
            )
            
            db.session.add_all([self.faculty, self.project])
            db.session.commit()

            # Store IDs to reference in sessions
            self.faculty_id = self.faculty.id
            self.project_id = self.project.id
            self.campus_id = self.campus.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_login_redirection_for_unauthenticated_users(self):
        """Unauthenticated requests to protected routes should redirect to login."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/login'))

    def test_forced_password_reset_on_first_login(self):
        """Logged in users with needs_password_reset=True should be forced to change it."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.faculty_id
            
        # Any request to a dashboard view should redirect to /reset-password
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/reset-password'))

    def test_password_reset_success(self):
        """Resetting the password clears the force-reset flag and allows platform access."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.faculty_id
            
        # Perform password reset POST
        response = self.client.post('/reset-password', data={
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }, follow_redirects=True)
        
        self.assertIn(b"Your password has been reset successfully", response.data)
        
        # Verify database flag is cleared
        with self.app.app_context():
            user = User.query.get(self.faculty_id)
            self.assertFalse(user.needs_password_reset)

    def test_user_registration_pending_workflow(self):
        """New registrants are placed in pending state and restricted from dashboard views."""
        response = self.client.post('/register', data={
            'username': 'volunteer1',
            'email': 'vol@test.com',
            'password': 'Volunteer-Test-2026!',
            'confirm_password': 'Volunteer-Test-2026!',
            'preferred_role': 'Volunteer',
            'campus_id': self.campus_id
        }, follow_redirects=True)
        
        self.assertIn(b"Registration Pending", response.data)
        
        # Verify user is in pending state in db
        with self.app.app_context():
            new_user = User.query.filter_by(username='volunteer1').first()
            self.assertEqual(new_user.status, 'Pending')
            self.assertEqual(new_user.role, 'Pending')

    def test_report_compilation_metadata_storage(self):
        """Compiling a report creates a query definition rather than a static JSON snapshot."""
        # Log in as approved faculty who completed password reset
        with self.app.app_context():
            user = User.query.get(self.faculty_id)
            user.needs_password_reset = False
            db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.faculty_id

        # Generate a report definition
        response = self.client.post('/reports/generate', data={
            'report_type': 'Project Report',
            'title': 'Test Project Report',
            'description': 'Dynamic test definition',
            'campus_id': self.campus_id,
            'program_type_id': '',
            'project_id': self.project_id,
            'start_date': '2026-06-01',
            'end_date': '2026-06-30'
        }, follow_redirects=True)

        self.assertIn(b"Test Project Report", response.data)
        self.assertIn(b"configuration saved", response.data)
        
        # Confirm only report query parameters are stored
        with self.app.app_context():
            report = Report.query.filter_by(title='Test Project Report').first()
            self.assertIsNotNone(report)
            self.assertEqual(report.project_id, self.project_id)
            self.assertEqual(report.report_type, 'Project Report')

    def test_report_excel_export(self):
        """Exporting a compiled report should return an Excel file containing summary metrics and projects list."""
        # Log in as approved faculty who completed password reset
        with self.app.app_context():
            user = User.query.get(self.faculty_id)
            user.needs_password_reset = False
            
            campus = Campus.query.first()
            prog_icc = ProgramType.query.filter_by(name="ICC").first()
            project = Project.query.first()

            # Create a report definition first
            report = Report(
                report_type='Project Report',
                title='Export Test Report',
                description='Excel export test',
                campus_id=campus.id,
                program_type_id=prog_icc.id,
                project_id=project.id,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                generated_by_id=self.faculty_id
            )
            db.session.add(report)
            db.session.commit()
            report_id = report.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.faculty_id

        # Hit the export route
        response = self.client.get(f'/reports/export/{report_id}')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertTrue(response.headers['Content-Disposition'].startswith('attachment; filename=report_'))

    def test_report_pdf_export(self):
        """Exporting a compiled report as PDF should return a PDF file download."""
        with self.app.app_context():
            user = User.query.get(self.faculty_id)
            user.needs_password_reset = False
            
            campus = Campus.query.first()
            prog_icc = ProgramType.query.filter_by(name="ICC").first()
            project = Project.query.first()

            report = Report(
                report_type='Project Report',
                title='Export PDF Test Report',
                description='PDF export test',
                campus_id=campus.id,
                program_type_id=prog_icc.id,
                project_id=project.id,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                generated_by_id=self.faculty_id
            )
            db.session.add(report)
            db.session.commit()
            report_id = report.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.faculty_id

        # Hit the PDF export route
        response = self.client.get(f'/reports/export-pdf/{report_id}')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/pdf')
        self.assertTrue(response.headers['Content-Disposition'].startswith('attachment; filename=report_'))

    def test_volunteer_access_restrictions(self):
        """Volunteers should be restricted from projects and reports they haven't contributed to."""
        # Create a new volunteer student user in Central Campus
        with self.app.app_context():
            campus = Campus.query.first()
            campus_id = campus.id
            volunteer_user = User(
                username='restricted.volunteer',
                email='restricted.vol@christuniversity.in',
                role='Volunteer',
                preferred_role='Volunteer',
                status='Approved',
                campus_id=campus_id,
                needs_password_reset=False
            )
            volunteer_user.set_password('Restricted-Volunteer-2026!')
            db.session.add(volunteer_user)
            db.session.commit()
            volunteer_id = volunteer_user.id
            
            # Query an existing project (volunteer hasn't contributed to this)
            project = Project.query.first()
            project_id = project.id
            
            # Create a report for this project
            report = Report(
                report_type='Project Report',
                title='Restricted Access Report',
                description='Test restriction',
                campus_id=campus_id,
                program_type_id=project.program_type_id,
                project_id=project.id,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                generated_by_id=self.faculty_id
            )
            db.session.add(report)
            db.session.commit()
            report_id = report.id

        with self.client.session_transaction() as sess:
            sess['user_id'] = volunteer_id

        # Trying to access project detail should return 403 Forbidden
        response = self.client.get(f'/campuses/{campus_id}/projects/{project_id}')
        self.assertEqual(response.status_code, 403)
        
        # Trying to access report detail should return 403 Forbidden
        response = self.client.get(f'/reports/view/{report_id}')
        self.assertEqual(response.status_code, 403)
        
        # Trying to access campus list should return 403 Forbidden
        response = self.client.get('/campuses')
        self.assertEqual(response.status_code, 403)

    def test_project_detail_attendance_tab_parameter(self):
        """Verify that tab=attendance parameter is supported in project details."""
        with self.app.app_context():
            # Ensure faculty user does not reset password
            faculty = db.session.get(User, self.faculty_id)
            faculty.needs_password_reset = False
            db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.faculty_id

        # Access project detail with tab=attendance
        response = self.client.get(f'/campuses/{self.campus_id}/projects/{self.project_id}?tab=attendance')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Attendance Log History', response.data)

if __name__ == '__main__':
    unittest.main()
