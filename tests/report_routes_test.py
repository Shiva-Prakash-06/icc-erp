import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, OperatingUnit, RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User


class ReportRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc = ProgramType(name="ICC")
        self.unit = OperatingUnit(code="ICC", name="ICC unit")
        db.session.add_all([self.year, self.campus, self.icc, self.unit])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-996", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Route Test Event",
            category="Event", status="Active", start_date=date(2026, 8, 20), end_date=date(2026, 8, 20),
        )
        self.user = User(username="events_head5", email="events_head5@example.com", role="ICC Core Committee", status="Approved")
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True, can_view_sensitive_links=True))
        db.session.commit()
        self.client.post("/login", data={"username": "events_head5", "password": "A-secure-test-password-2026"}, follow_redirects=True)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_preflight_route_returns_json(self):
        response = self.client.get(f"/erp/projects/{self.project.public_id}/report/preflight")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("complete", data)
        self.assertIn("dependencies", data)

    def test_preview_page_renders(self):
        response = self.client.get(f"/erp/projects/{self.project.public_id}/report/complete")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Complete PDF report", response.data)

    def test_download_without_dependencies_returns_generated_summary_pdf(self):
        response = self.client.get(f"/erp/projects/{self.project.public_id}/report/complete.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF"))

    def test_download_redirects_to_preview_when_incomplete_and_not_acknowledged(self):
        document = DocumentRecord(
            project_id=self.project.id, category="Testimonial", title="Weird", status="Indexed",
            permission_classification="Internal", drive_file_id="x", drive_url="https://drive.google.com/file/d/x/view",
            drive_name="weird.xyz", drive_mime_type="application/octet-stream", drive_validation_status="Valid",
        )
        db.session.add(document)
        db.session.commit()
        response = self.client.get(f"/erp/projects/{self.project.public_id}/report/complete.pdf", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/report/complete", response.location)

    def test_download_with_allow_incomplete_succeeds(self):
        document = DocumentRecord(
            project_id=self.project.id, category="Testimonial", title="Weird", status="Indexed",
            permission_classification="Internal", drive_file_id="x", drive_url="https://drive.google.com/file/d/x/view",
            drive_name="weird.xyz", drive_mime_type="application/octet-stream", drive_validation_status="Valid",
        )
        db.session.add(document)
        db.session.commit()
        response = self.client.get(f"/erp/projects/{self.project.public_id}/report/complete.pdf?allow_incomplete=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/pdf")

    def test_unauthorized_user_is_forbidden(self):
        other = User(username="stranger", email="stranger@example.com", role="Volunteer", status="Approved")
        other.set_password("A-secure-test-password-2026")
        db.session.add(other)
        db.session.commit()
        client = self.app.test_client()
        client.post("/login", data={"username": "stranger", "password": "A-secure-test-password-2026"}, follow_redirects=True)
        response = client.get(f"/erp/projects/{self.project.public_id}/report/preflight")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
