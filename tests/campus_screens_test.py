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

    def test_event_details_card_holds_what_people_edit(self):
        # Campus, programme, year and wing are worked out from who created
        # the event and are no longer shown: the details card carries only
        # what a person might change -- name, days, place, audience.
        self.login()
        response = self.client.get(f"/erp/projects/{self.project.public_id}?card=details")
        html = response.get_data(as_text=True)
        self.assertRegex(html, r'id="card-details"\s+open')
        for label in ("Name", "First day", "Last day", "Where", "Who is it for?"):
            self.assertIn(label, html)
        self.assertIn(self.project.title, html)
        self.assertNotIn("Academic year", html)

    def test_old_campus_and_division_addresses_land_on_the_events_list(self):
        # The campus tiles and division screens are gone; a bookmark to one
        # still opens the Events list.
        self.login()
        for path in ("/erp/campuses", f"/erp/campuses/{self.campus.public_id}", f"/erp/campuses/{self.campus.public_id}/icc"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/erp/projects", response.headers["Location"])

    def test_events_list_shows_only_events_in_scope(self):
        self.login()
        html = self.client.get("/erp/projects").get_data(as_text=True)
        self.assertIn("Basics scoped project", html)
        self.assertNotIn("Other campus project", html)
        # One campus in reach: no campus picker.
        self.assertNotIn('name="campus"', html)

    def test_a_campus_filter_for_an_unreachable_campus_shows_nothing_extra(self):
        self.login()
        html = self.client.get("/erp/projects", query_string={"campus": self.other_campus.public_id}).get_data(as_text=True)
        self.assertNotIn("Other campus project", html)


if __name__ == "__main__":
    unittest.main()
