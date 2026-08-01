import os
import unittest
from datetime import date, datetime

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, Person, ReportSnapshot, TeamAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project


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
            actual_reach=175,
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
        db.session.add(DocumentRecord(project_id=self.project.id, title="Event Poster", category="Poster", drive_url="https://drive.google.com/file/d/abc/view", permission_classification="Internal"))
        db.session.add(DocumentRecord(project_id=self.project.id, title="Secret Buddy List", category="Report", drive_url="https://drive.google.com/file/d/secret/view", permission_classification="Restricted"))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_public_routes_do_not_require_login(self):
        for path in ("/public/", "/public/events", "/public/reports", "/public/analytics-data"):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_draft_project_is_not_publicly_visible(self):
        response = self.client.get("/public/events")
        self.assertNotIn(b"Draft Hidden Event", response.data)
        self.assertEqual(self.client.get(f"/public/events/{self.draft_project.code}").status_code, 404)

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


if __name__ == "__main__":
    unittest.main()
