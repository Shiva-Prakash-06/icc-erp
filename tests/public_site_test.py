import os
import unittest
from datetime import date, datetime

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, Person, ReportSnapshot, RoleAssignment, TeamAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User


class PublicSiteTestCase(unittest.TestCase):
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
            code="ICC-2026-CEN-500", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Public Test Event", description="A test event.",
            category="Operational", status="Completed", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
            actual_reach=175, publication_status="Published",
        )
        self.draft_project = Project(
            code="ICC-2026-CEN-501", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Draft Hidden Event", category="Operational", status="Draft",
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
        )
        db.session.add_all([self.project, self.draft_project])
        db.session.flush()
        self.person = Person(first_name="ShouldNotLeak", last_name="Person", primary_email="shouldnotleak@example.com", person_type="Student")
        db.session.add(self.person)
        db.session.flush()
        db.session.add(TeamAssignment(project_id=self.project.id, person_id=self.person.id, assignment_type="Project Team"))
        self.published_snapshot = ReportSnapshot(
            project_id=self.project.id, report_type="Project Operational Report", title="Public Test Event Report",
            version=1, snapshot_json={"reach": {"actual": 175}, "budget": {"estimated": "9999"}},
            source_references=[self.project.public_id], approval_status="Approved", publication_status="Published",
        )
        self.draft_snapshot = ReportSnapshot(
            project_id=self.project.id, report_type="Project Operational Report", title="Unpublished Report",
            version=2, snapshot_json={}, source_references=[self.project.public_id],
            approval_status="Draft", publication_status="Unpublished",
        )
        db.session.add_all([self.published_snapshot, self.draft_snapshot])
        db.session.add(DocumentRecord(project_id=self.project.id, title="Event Poster", category="Poster", status="Approved", drive_url="https://drive.google.com/file/d/abc/view", permission_classification="Public"))
        db.session.add(DocumentRecord(project_id=self.project.id, title="Secret Buddy List", category="Report", status="Approved", drive_url="https://drive.google.com/file/d/secret/view", permission_classification="Restricted"))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_public_routes_do_not_require_login(self):
        for path in ("/public/", "/public/events", "/public/reports", "/public/analytics-data"):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_landing_loads_lightweight_charts_only_when_data_is_published(self):
        response = self.client.get("/public/")
        self.assertIn(b"public-charts.js", response.data)
        self.assertIn(b"campusChart", response.data)
        self.assertIn(b"View analytics as data tables", response.data)
        self.assertIn(b"Published events by campus", response.data)
        self.assertIn(b"Central", response.data)
        self.assertIn(b"2026-2027", response.data)
        self.assertNotIn(b"chart.umd.min.js", response.data)

        analytics = self.client.get("/public/analytics-data").get_json()
        self.assertIn({"label": "2026-2027", "value": 175}, analytics["participation_trend"])

        self.project.publication_status = "Private"
        db.session.commit()
        response = self.client.get("/public/")
        self.assertIn(b"No published analytics yet", response.data)
        self.assertNotIn(b"public-charts.js", response.data)
        self.assertNotIn(b"campusChart", response.data)

    def test_draft_project_is_not_publicly_visible(self):
        response = self.client.get("/public/events")
        self.assertNotIn(b"Draft Hidden Event", response.data)
        self.assertEqual(self.client.get(f"/public/events/{self.draft_project.code}").status_code, 404)

    def test_completed_but_unpublished_project_is_not_publicly_visible(self):
        # Publication is an explicit, separate gate from workflow status --
        # a Completed project must stay private until it is Published.
        # See PLAN.md "Additional release blockers" finding.
        unpublished = Project(
            code="ICC-2026-CEN-777", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Completed But Never Reviewed", category="Operational",
            status="Completed", start_date=date(2026, 7, 1), end_date=date(2026, 7, 2),
        )
        db.session.add(unpublished)
        db.session.commit()
        self.assertEqual(unpublished.publication_status, "Private")
        response = self.client.get("/public/events")
        self.assertNotIn(b"Completed But Never Reviewed", response.data)
        self.assertEqual(self.client.get(f"/public/events/{unpublished.code}").status_code, 404)

    def test_event_detail_never_leaks_person_names_or_budget(self):
        response = self.client.get(f"/public/events/{self.project.code}")
        html = response.get_data(as_text=True)
        self.assertNotIn("ShouldNotLeak", html)
        self.assertNotIn("9999", html)

    def test_restricted_document_never_shown_public_only_poster_is(self):
        response = self.client.get(f"/public/events/{self.project.code}")
        html = response.get_data(as_text=True)
        self.assertIn("Event Poster", html)
        self.assertNotIn("Secret Buddy List", html)

    def test_only_published_approved_reports_are_shown(self):
        response = self.client.get(f"/public/events/{self.project.code}")
        html = response.get_data(as_text=True)
        self.assertIn("Public Test Event Report", html)
        self.assertNotIn("Unpublished Report", html)

    def test_report_for_cancelled_project_is_not_publicly_visible(self):
        cancelled_project = Project(
            code="ICC-2026-CEN-778", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Cancelled Published Event", category="Operational",
            status="Cancelled", publication_status="Published",
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 2),
        )
        db.session.add(cancelled_project)
        db.session.flush()
        db.session.add(ReportSnapshot(
            project_id=cancelled_project.id, report_type="Project Operational Report",
            title="Cancelled Project Report", version=1, snapshot_json={},
            source_references=[cancelled_project.public_id], approval_status="Approved",
            publication_status="Published",
        ))
        db.session.commit()

        response = self.client.get("/public/reports")
        self.assertNotIn(b"Cancelled Project Report", response.data)
        self.assertEqual(self.client.get(f"/public/events/{cancelled_project.code}").status_code, 404)


    def test_demo_banner_and_return_to_erp_shown_for_authenticated_users(self):
        # See PLAN.md "USC demo warning" and "Published reports back
        # navigation" findings: the demo banner was missing from the public
        # shell, and authenticated users had no reliable route back to ERP.
        user = User(username="public_nav", email="public_nav@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        user.set_password("A-secure-test-password-2026")
        db.session.add(user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=user.id, role_code="VOLUNTEER", is_active=True))
        db.session.commit()
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version
        response = self.client.get("/public/events")
        html = response.get_data(as_text=True)
        self.assertIn("do not enter sensitive or personal data", html)
        self.assertIn("Return to ERP", html)
        self.assertNotIn(">Sign in<", html)

    def test_anonymous_public_visitor_sees_sign_in_not_return_to_erp(self):
        response = self.client.get("/public/events")
        html = response.get_data(as_text=True)
        self.assertIn("Sign in", html)
        self.assertNotIn("Return to ERP", html)


if __name__ == "__main__":
    unittest.main()
