import os
os.environ['TESTING'] = 'True'

import unittest
from datetime import date
from app import create_app, db
from app.models.user import User
from app.models.erp import Person, RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project

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

        self.assertIn(b"You're all set", response.data)

        # Verify database flag is cleared
        with self.app.app_context():
            user = db.session.get(User, self.faculty_id)
            self.assertFalse(user.needs_password_reset)

    def test_sign_up_is_instantly_a_volunteer(self):
        """Signing up needs no approval: the account is a volunteer straight
        away and lands on the home screen."""
        response = self.client.post('/register', data={
            'first_name': 'Asha',
            'last_name': 'Rao',
            'email': 'asha.rao@christuniversity.in',
            'password': 'Volunteer-Test-2026!',
            'campus_id': self.campus_id,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/'))

        with self.app.app_context():
            new_user = User.query.filter_by(email='asha.rao@christuniversity.in').one()
            self.assertEqual(new_user.status, 'Approved')
            self.assertEqual(new_user.username, 'asha.rao')
            self.assertEqual(new_user.person.first_name, 'Asha')
            self.assertEqual(new_user.person.last_name, 'Rao')
            codes = {a.role_code for a in RoleAssignment.query.filter_by(user_id=new_user.id, is_active=True)}
            self.assertEqual(codes, {'VOLUNTEER'})

    def test_sign_up_refuses_a_non_university_email(self):
        response = self.client.post('/register', data={
            'first_name': 'Out', 'email': 'someone@gmail.com',
            'password': 'Volunteer-Test-2026!', 'campus_id': self.campus_id,
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn(b"Use your university email", response.data)
        with self.app.app_context():
            self.assertIsNone(User.query.filter_by(email='someone@gmail.com').first())

    def test_sign_up_joins_an_existing_person_record(self):
        """A volunteer a head already listed on an event keeps those events."""
        with self.app.app_context():
            person = Person(first_name='Listed', primary_email='listed@christuniversity.in', person_type='Student')
            db.session.add(person)
            db.session.commit()
            person_id = person.id
        self.client.post('/register', data={
            'first_name': 'Listed', 'email': 'listed@christuniversity.in',
            'password': 'Volunteer-Test-2026!', 'campus_id': self.campus_id,
        })
        with self.app.app_context():
            user = User.query.filter_by(email='listed@christuniversity.in').one()
            self.assertEqual(user.person_id, person_id)

if __name__ == '__main__':
    unittest.main()
