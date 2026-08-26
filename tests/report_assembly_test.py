import io
import os
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

os.environ["TESTING"] = "true"

from pypdf import PdfReader

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, OperatingUnit, ProjectSession, ReportSnapshot, RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.report_assembly import (
    ReportIncompleteError,
    assemble_complete_report,
    preflight_report,
    select_authoritative_report,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EVENT_REPORT_DOCX = FIXTURES / "event_report_coffee_meet.docx"
TESTIMONIAL_PDF = FIXTURES / "testimonial_advaithya.pdf"


class ReportAssemblyTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
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
            code="ICC-2026-CEN-995", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Coffee Meet & Greet 2026",
            category="Event", status="Active", start_date=date(2026, 8, 20), end_date=date(2026, 8, 20),
        )
        self.user = User(username="events_head4", email="events_head4@example.com", role="ICC Core Committee", status="Approved")
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True, can_view_sensitive_links=True))
        db.session.commit()
        self.fixture_bytes = {}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _add_document(self, category, filename, file_id, mime_type, *, classification="Internal"):
        content = (FIXTURES / filename).read_bytes() if (FIXTURES / filename).exists() else b"placeholder"
        self.fixture_bytes[file_id] = content
        document = DocumentRecord(
            project_id=self.project.id, category=category, title=filename.rsplit(".", 1)[0], status="Indexed",
            permission_classification=classification, drive_file_id=file_id,
            drive_url=f"https://drive.google.com/file/d/{file_id}/view", drive_name=filename,
            drive_mime_type=mime_type, drive_validation_status="Valid",
        )
        db.session.add(document)
        db.session.commit()
        return document

    def _fetch_override(self, document):
        return self.fixture_bytes[document.drive_file_id]

    def test_authoritative_report_docx_body_and_five_images_survive_assembly(self):
        self._add_document("Event Report", "event_report_coffee_meet.docx", "doc1", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        pdf_bytes, snapshot = assemble_complete_report(self.project, self.user, fetch_override=self._fetch_override)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        self.assertGreater(len(reader.pages), 0)
        image_count = 0
        for page in reader.pages:
            resources = page.get("/Resources") or {}
            xobjects = resources.get("/XObject")
            if xobjects:
                for obj in xobjects.values():
                    if obj.get_object().get("/Subtype") == "/Image":
                        image_count += 1
        self.assertEqual(image_count, 5)
        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("COFFEE MEET", full_text.upper())

    def test_testimonial_can_be_appended(self):
        self._add_document("Event Report", "event_report_coffee_meet.docx", "doc1", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        report_only_bytes, _ = assemble_complete_report(self.project, self.user, fetch_override=self._fetch_override)
        report_only_pages = len(PdfReader(io.BytesIO(report_only_bytes)).pages)

        self._add_document("Testimonial", "testimonial_advaithya.pdf", "doc2", "application/pdf")
        testimonial_only_pages = len(PdfReader(io.BytesIO(TESTIMONIAL_PDF.read_bytes())).pages)
        combined_bytes, snapshot = assemble_complete_report(self.project, self.user, fetch_override=self._fetch_override)
        combined_pages = len(PdfReader(io.BytesIO(combined_bytes)).pages)

        self.assertEqual(len(snapshot.snapshot_json["included_documents"]), 2)
        self.assertEqual(combined_pages, report_only_pages + testimonial_only_pages)

    def test_preflight_reports_missing_authoritative_report(self):
        preflight = preflight_report(self.project)
        self.assertFalse(preflight["has_authoritative_report"])
        self.assertTrue(preflight["complete"])  # nothing to be missing yet -- no dependency rows at all

    def test_preflight_reports_missing_document_status(self):
        document = self._add_document("Testimonial", "testimonial_advaithya.pdf", "doc2", "application/pdf")
        document.drive_file_id = None
        document.drive_url = None
        db.session.commit()
        preflight = preflight_report(self.project)
        self.assertEqual(len(preflight["missing"]), 1)
        self.assertFalse(preflight["complete"])

    def test_preflight_reports_inaccessible_document(self):
        document = self._add_document("Testimonial", "testimonial_advaithya.pdf", "doc2", "application/pdf")
        document.drive_validation_status = "Invalid"
        db.session.commit()
        preflight = preflight_report(self.project)
        self.assertEqual(len(preflight["inaccessible"]), 1)

    def test_preflight_reports_unsupported_extension(self):
        document = self._add_document("Testimonial", "weird.xyz", "doc3", "application/octet-stream")
        preflight = preflight_report(self.project)
        self.assertEqual(len(preflight["unsupported"]), 1)

    def test_incomplete_download_requires_acknowledgement(self):
        self._add_document("Testimonial", "weird.xyz", "doc3", "application/octet-stream")
        with self.assertRaises(ReportIncompleteError):
            assemble_complete_report(self.project, self.user, fetch_override=self._fetch_override)
        # with allow_incomplete it proceeds, skipping the unsupported dependency
        pdf_bytes, snapshot = assemble_complete_report(self.project, self.user, allow_incomplete=True, fetch_override=self._fetch_override)
        self.assertTrue(snapshot.snapshot_json["acknowledged_incomplete"])
        self.assertEqual(snapshot.snapshot_json["included_documents"], [])

    def test_no_authoritative_report_generates_summary(self):
        session = ProjectSession(
            project_id=self.project.id, code="MAIN", title="Coffee Meet", session_type="Event",
            starts_at=datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc), ends_at=datetime(2026, 8, 20, 17, 0, tzinfo=timezone.utc),
        )
        db.session.add(session)
        db.session.commit()
        pdf_bytes, snapshot = assemble_complete_report(self.project, self.user, fetch_override=self._fetch_override)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("generated summary", text.lower())
        self.assertEqual(snapshot.snapshot_json["included_documents"], [])

    def test_restricted_document_not_embedded_without_sensitive_permission(self):
        self._add_document("Event Report", "event_report_coffee_meet.docx", "doc1", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        restricted = self._add_document("Testimonial", "testimonial_advaithya.pdf", "doc2", "application/pdf", classification="Restricted")
        limited_user = User(username="limited", email="limited@example.com", role="Volunteer", status="Approved")
        limited_user.set_password("A-secure-test-password-2026")
        db.session.add(limited_user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=limited_user.id, role_code="VOLUNTEER", project_id=self.project.id, is_active=True))
        db.session.commit()
        pdf_bytes, snapshot = assemble_complete_report(self.project, limited_user, fetch_override=self._fetch_override)
        included_ids = {doc["document_public_id"] for doc in snapshot.snapshot_json["included_documents"]}
        self.assertNotIn(restricted.public_id, included_ids)

    def test_snapshot_is_reproducible_with_source_metadata(self):
        self._add_document("Event Report", "event_report_coffee_meet.docx", "doc1", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        _, snapshot = assemble_complete_report(self.project, self.user, fetch_override=self._fetch_override)
        self.assertEqual(len(snapshot.source_references), 1)
        self.assertIn("checksum_sha256", snapshot.snapshot_json["included_documents"][0])
        self.assertEqual(ReportSnapshot.query.filter_by(project_id=self.project.id, report_type="complete_pdf").count(), 1)

    def test_select_authoritative_report_prefers_latest(self):
        first = self._add_document("Event Report", "event_report_coffee_meet.docx", "doc1", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        second = self._add_document("Event Report", "testimonial_advaithya.pdf", "doc2", "application/pdf")
        second.drive_modified_at = datetime(2026, 8, 21, tzinfo=timezone.utc)
        db.session.commit()
        self.assertEqual(select_authoritative_report(self.project).id, second.id)


if __name__ == "__main__":
    unittest.main()
