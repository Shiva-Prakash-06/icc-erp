import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import OperationalRequest, RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User


class AccountActivityTestCase(unittest.TestCase):
    """"My Profile" was volunteer-oriented and commonly empty for USC users
    -- see PLAN.md "USC My Profile" finding. /profile must now show role
    assignments (with human-readable scope) and recent activity for any
    role, and degrade gracefully with an empty state."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc = ProgramType(name="ICC")
        db.session.add_all([self.year, self.campus, self.icc])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-900", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Account activity project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()
        self.usc = User(username="usc_acct", email="usc_acct@example.com", role="ICC Secretary / USC", status="Approved", needs_password_reset=False)
        self.usc.set_password("A-secure-test-password-2026")
        self.empty_user = User(username="lonely", email="lonely@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        self.empty_user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.usc, self.empty_user])
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.usc.id, role_code="ICC_SECRETARY_USC", project_id=self.project.id, is_active=True))
        db.session.add(RoleAssignment(user_id=self.empty_user.id, role_code="VOLUNTEER", is_active=True))
        db.session.add(OperationalRequest(project_id=self.project.id, request_type="Vehicle", title="Campus shuttle", created_by_id=self.usc.id))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    def test_usc_sees_role_and_events(self):
        self.login(self.usc)
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("<h1 class=\"ds-screen__title\">Account</h1>", html)
        self.assertIn("ICC Secretary / USC", html)
        self.assertIn("Account activity project", html)

    def test_user_with_no_activity_sees_empty_state_not_an_error(self):
        self.login(self.empty_user)
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nothing here yet", response.get_data(as_text=True))

    def test_anyone_can_fix_their_own_details(self):
        self.login(self.empty_user)
        self.assertIn('name="registration_number"', self.client.get("/profile").get_data(as_text=True))
        response = self.client.post("/profile/details", data={
            "first_name": " Lonely ", "last_name": "Learner", "phone": "+91 98450 12345", "registration_number": "2441234",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/profile#details"))
        person = db.session.get(User, self.empty_user.id).person
        self.assertEqual((person.first_name, person.last_name, person.phone, person.registration_number),
                         ("Lonely", "Learner", "+91 98450 12345", "2441234"))
        self.assertEqual(person.primary_email, "lonely@example.com")

        # Clearing an optional box clears it; the same Person is kept.
        self.client.post("/profile/details", data={"first_name": "Lonely", "last_name": "", "phone": "", "registration_number": "2441234"})
        db.session.expire_all()
        again = db.session.get(User, self.empty_user.id).person
        self.assertEqual(again.id, person.id)
        self.assertIsNone(again.phone)
        self.assertIsNone(again.last_name)

    def test_details_need_a_first_name_and_a_free_register_number(self):
        from app.models.erp import Person

        db.session.add(Person(first_name="Someone", registration_number="TAKEN-1"))
        db.session.commit()
        self.login(self.usc)
        page = self.client.post("/profile/details", data={"first_name": "USC", "registration_number": "TAKEN-1"}, follow_redirects=True)
        self.assertIn("already someone else", page.get_data(as_text=True))
        page = self.client.post("/profile/details", data={"first_name": "  "}, follow_redirects=True)
        self.assertIn("Type your first name", page.get_data(as_text=True))
        self.assertIsNone(db.session.get(User, self.usc.id).person)

    def test_details_attach_an_existing_unclaimed_person_by_email(self):
        from app.models.erp import Person

        listed = Person(first_name="Listed", primary_email="LONELY@example.com")
        db.session.add(listed)
        db.session.commit()
        self.login(self.empty_user)
        self.client.post("/profile/details", data={"first_name": "Lonely"})
        self.assertEqual(db.session.get(User, self.empty_user.id).person_id, listed.id)


if __name__ == "__main__":
    unittest.main()
