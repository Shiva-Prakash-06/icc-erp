import os
import unittest
from datetime import date, datetime, timedelta, timezone

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import OperationalRequest, ProjectSession, RoleAssignment, WorkTask
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User


class MissionControlTestCase(unittest.TestCase):
    """`/` must render real, role-scoped content for every approved role
    instead of redirecting to Oversight -- see PLAN.md "USC dashboard/
    Mission Control" finding. `/` now also absorbs the former ERP hub and
    Oversight pages -- see
    in-the-operation-checklists-crystalline-dongarra.md Step 2."""

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
            code="ICC-2026-CEN-800", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Mission control project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()
        db.session.add(ProjectSession(
            project_id=self.project.id, code="S1", title="Kickoff", session_type="Meeting",
            starts_at=datetime.now(timezone.utc) + timedelta(days=1),
            ends_at=datetime.now(timezone.utc) + timedelta(days=1, hours=1),
        ))
        self.usc = User(username="usc", email="usc@example.com", role="ICC Secretary / USC", status="Approved", needs_password_reset=False)
        self.usc.set_password("A-secure-test-password-2026")
        db.session.add(self.usc)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.usc.id, role_code="ICC_SECRETARY_USC", project_id=self.project.id, is_active=True))
        db.session.add(OperationalRequest(project_id=self.project.id, request_type="Vehicle", title="Airport pickup", created_by_id=self.usc.id))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    def test_root_renders_home_instead_of_redirecting(self):
        self.login(self.usc)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Home", html)

    def test_mission_control_shows_scoped_project_session_and_own_request(self):
        self.login(self.usc)
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn("Mission control project", html)
        self.assertIn("Kickoff", html)
        self.assertIn("Airport pickup", html)

    def test_usc_does_not_receive_approval_queue_or_oversight_navigation(self):
        db.session.add(WorkTask(project_id=self.project.id, title="Awaiting review", status="Submitted"))
        db.session.commit()
        self.login(self.usc)
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("Needs your attention", html)
        self.assertNotIn(">Oversight<", html)

    def test_usc_queue_all_bypass_still_shows_no_queue(self):
        """?queue=all must never bypass the can_act/can_view_decision_queue gate."""
        db.session.add(WorkTask(project_id=self.project.id, title="Awaiting review", status="Submitted"))
        db.session.commit()
        self.login(self.usc)
        response = self.client.get("/?queue=all")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("Awaiting review", html)


if __name__ == "__main__":
    unittest.main()
