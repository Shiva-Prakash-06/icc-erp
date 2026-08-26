import io
import os
import unittest
from datetime import date, timedelta

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, OperatingUnit, RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.project_quickcreate import create_minimal_project, infer_status_from_dates


class InferStatusFromDatesTestCase(unittest.TestCase):
    def test_future_dates_are_planned(self):
        today = date(2026, 8, 12)
        self.assertEqual(infer_status_from_dates(date(2026, 9, 1), date(2026, 9, 2), today), "Planned")

    def test_current_window_is_active(self):
        today = date(2026, 8, 12)
        self.assertEqual(infer_status_from_dates(date(2026, 8, 1), date(2026, 8, 20), today), "Active")

    def test_past_dates_are_completed(self):
        today = date(2026, 8, 12)
        self.assertEqual(infer_status_from_dates(date(2026, 7, 1), date(2026, 7, 2), today), "Completed")


class CreateMinimalProjectTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.igp = ProgramType(name="IGP")
        self.icc = ProgramType(name="ICC")
        self.unit_igp = OperatingUnit(code="IGP", name="IGP unit")
        self.unit_icc = OperatingUnit(code="ICC", name="ICC unit")
        db.session.add_all([self.year, self.campus, self.igp, self.icc, self.unit_igp, self.unit_icc])
        db.session.flush()
        self.user = User(username="admin", email="admin@example.com", role="Faculty", status="Approved", campus_id=self.campus.id)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True, can_view_sensitive_links=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _login(self):
        return self.client.post("/login", data={"username": "admin", "password": "A-secure-test-password-2026"}, follow_redirects=True)

    def test_only_title_and_dates_are_required(self):
        project = create_minimal_project(
            program_type_name="IGP", title="Minimal IGP", start_date=date(2026, 9, 1), end_date=date(2026, 9, 2), actor=self.user,
        )
        self.assertEqual(project.title, "Minimal IGP")
        self.assertEqual(project.campus_id, self.campus.id)
        self.assertEqual(project.academic_year_id, self.year.id)
        self.assertEqual(project.category, "Operational")
        self.assertIsNotNone(project.code)
        self.assertEqual(project.status, "Planned")
        self.assertIsNone(project.venue)
        self.assertIsNone(project.target_audience)

    def test_venue_and_audience_are_optional_more_details(self):
        project = create_minimal_project(
            program_type_name="ICC", title="With details", start_date=date(2026, 9, 1), end_date=date(2026, 9, 1),
            actor=self.user, venue="Auditorium", target_audience="Students",
        )
        self.assertEqual(project.venue, "Auditorium")
        self.assertEqual(project.target_audience, "Students")

    def test_blank_title_is_rejected(self):
        with self.assertRaises(ValueError):
            create_minimal_project(program_type_name="IGP", title="  ", start_date=date(2026, 9, 1), end_date=date(2026, 9, 2), actor=self.user)

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(ValueError):
            create_minimal_project(program_type_name="IGP", title="Bad dates", start_date=date(2026, 9, 2), end_date=date(2026, 9, 1), actor=self.user)

    def test_unknown_program_type_is_rejected(self):
        with self.assertRaises(ValueError):
            create_minimal_project(program_type_name="NOPE", title="X", start_date=date(2026, 9, 1), end_date=date(2026, 9, 2), actor=self.user)

    def test_landing_page_renders(self):
        self._login()
        response = self.client.get("/erp/projects/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create IGP from itinerary", response.data)
        self.assertIn(b"Import ICC event summary", response.data)

    def test_quick_create_route_creates_project_and_redirects(self):
        self._login()
        response = self.client.post("/erp/projects/quick-create", data={
            "program_type_name": "ICC", "title": "Route Created", "start_date": "2026-09-01", "end_date": "2026-09-01",
        })
        self.assertEqual(response.status_code, 302)
        project = Project.query.filter_by(title="Route Created").one()
        self.assertEqual(project.program_type.name, "ICC")

    def test_quick_create_from_itinerary_route(self):
        self._login()
        content = open("tests/fixtures/summer_school_itinerary", "rb").read()
        response = self.client.post(
            "/erp/projects/quick-create-from-itinerary",
            data={"source_file": (io.BytesIO(content), "Summer School Itinerary")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        project = Project.query.filter_by(program_type_id=self.igp.id).one()
        self.assertEqual(project.title, "International Summer School 2026")
        self.assertEqual(len(project.sessions), 71)

    def test_quick_create_with_documents_route(self):
        self._login()
        response = self.client.post(
            "/erp/projects/quick-create-with-documents",
            data={
                "program_type_name": "ICC", "title": "Doc Route", "start_date": "2026-09-05", "end_date": "2026-09-05",
                "source_files": (io.BytesIO(b"poster-bytes"), "UC Screen Flyer.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        project = Project.query.filter_by(title="Doc Route").one()
        self.assertEqual(DocumentRecord.query.filter_by(project_id=project.id).count(), 1)

    def test_quick_create_rejects_missing_title(self):
        self._login()
        response = self.client.post("/erp/projects/quick-create", data={
            "program_type_name": "ICC", "title": "", "start_date": "2026-09-01", "end_date": "2026-09-01",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Project.query.filter_by(title="").count(), 0)


if __name__ == "__main__":
    unittest.main()
