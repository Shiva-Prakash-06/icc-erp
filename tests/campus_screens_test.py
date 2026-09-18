import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User


class CampusScreensTestCase(unittest.TestCase):
    """Project Basics previously omitted campus/program/year/wing, and the
    legacy campus-hierarchy screen was removed while docs still referenced
    it. See PLAN.md "ICC campus definition" finding. The new /erp/campuses
    screens are read-only and scoped to the caller's visible projects, not a
    restoration of the deleted analytics module."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.other_campus = Campus(name="Other", code="OTH")
        self.icc = ProgramType(name="ICC")
        db.session.add_all([self.year, self.campus, self.other_campus, self.icc])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-950", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Basics scoped project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        self.other_project = Project(
            code="ICC-2026-OTH-950", campus_id=self.other_campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Other campus project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add_all([self.project, self.other_project])
        db.session.flush()
        self.user = User(username="wing_head", email="wing_head@example.com", role="ICC Events Head", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="ICC_EVENTS_HEAD", project_id=self.project.id, is_active=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version

    def test_project_basics_card_shows_campus_program_year_wing(self):
        # The two "Project Basics" / "Project record" definition lists were
        # merged into one "Record" facts panel in the blueprint redesign,
        # and the Tile System moved that panel to the Logistics tab when it
        # deleted Overview. The facts it must carry are unchanged.
        self.login()
        response = self.client.get(f"/erp/projects/{self.project.public_id}?tab=logistics")
        html = response.get_data(as_text=True)
        self.assertIn("Academic year", html)
        self.assertIn("Central", html)
        self.assertIn("ICC", html)
        self.assertIn("2026-2027", html)
        self.assertIn("Not set", html)  # no wing assigned

    def test_campuses_list_only_shows_scoped_campus(self):
        self.login()
        response = self.client.get("/erp/campuses")
        html = response.get_data(as_text=True)
        self.assertIn("Central", html)
        self.assertNotIn("Other", html)

    def test_campus_detail_denies_out_of_scope_campus(self):
        self.login()
        response = self.client.get(f"/erp/campuses/{self.other_campus.public_id}")
        self.assertEqual(response.status_code, 404)

    def test_campus_detail_offers_both_divisions(self):
        """Level two of the drill-down is divisions, not a project list.

        The campus screen used to be a flat list of every project on the
        campus; the Tile System puts IGP and ICC between the campus and its
        events, so what this screen must show is the two divisions and a
        live count for each.
        """
        self.login()
        response = self.client.get(f"/erp/campuses/{self.campus.public_id}")
        html = response.get_data(as_text=True)
        self.assertIn("India Gateway Program", html)
        self.assertIn("International Christite Community", html)
        self.assertIn(f"/erp/campuses/{self.campus.public_id}/icc", html)
        self.assertIn(f"/erp/campuses/{self.campus.public_id}/igp", html)

    def test_division_screen_lists_that_divisions_events_only(self):
        self.login()
        response = self.client.get(f"/erp/campuses/{self.campus.public_id}/icc")
        html = response.get_data(as_text=True)
        self.assertIn("Basics scoped project", html)
        self.assertNotIn("Other campus project", html)

    def test_division_screen_rejects_an_unknown_division(self):
        self.login()
        self.assertEqual(self.client.get(f"/erp/campuses/{self.campus.public_id}/xyz").status_code, 404)

    def test_division_screen_denies_out_of_scope_campus(self):
        self.login()
        self.assertEqual(self.client.get(f"/erp/campuses/{self.other_campus.public_id}/icc").status_code, 404)


if __name__ == "__main__":
    unittest.main()
