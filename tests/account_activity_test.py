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

    def test_usc_sees_role_scope_and_own_request(self):
        self.login(self.usc)
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("My Account", html)
        self.assertIn("Icc Secretary Usc", html)
        self.assertIn("Account activity project", html)
        self.assertIn("Campus shuttle", html)

    def test_user_with_no_activity_sees_empty_state_not_an_error(self):
        self.login(self.empty_user)
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        self.assertIn("No activity recorded yet", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
