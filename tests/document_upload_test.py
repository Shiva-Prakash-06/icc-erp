import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, OperatingUnit
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.drive import ensure_project_folder, upload_file_to_drive
from app.services.upload_sessions import (
    UploadSessionError,
    append_chunk,
    complete_upload_session,
    start_upload_session,
    upload_file_single_shot,
)


class DocumentUploadTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.igp = ProgramType(name="IGP")
        self.unit = OperatingUnit(code="IGP", name="IGP unit")
        db.session.add_all([self.year, self.campus, self.igp, self.unit])
        db.session.flush()
        self.project = Project(
            code="IGP-2026-CEN-980", campus_id=self.campus.id, program_type_id=self.igp.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Doc upload test",
            category="Exchange", status="Active", start_date=date(2026, 6, 1), end_date=date(2026, 7, 1),
        )
        self.user = User(username="igp_head4", email="igp_head4@example.com", role="IGP Head", status="Approved")
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_mock_mode_upload_creates_indexed_document(self):
        doc = upload_file_single_shot(self.project, "UC Screen Flyer.pdf", b"poster-bytes", self.user)
        self.assertEqual(doc.category, "Screen Banner")
        self.assertEqual(doc.permission_classification, "Public")
        self.assertTrue(doc.drive_file_id.startswith("mock-"))
        self.assertEqual(doc.status, "Indexed")
        self.assertIsNotNone(doc.checksum_sha256)
        self.assertEqual(doc.uploaded_by_id, self.user.id)

    def test_identical_upload_is_deduplicated_by_checksum(self):
        first = upload_file_single_shot(self.project, "Lamppost.pdf", b"same-bytes", self.user)
        second = upload_file_single_shot(self.project, "Lamppost.pdf", b"same-bytes", self.user)
        self.assertEqual(first.id, second.id)
        self.assertEqual(DocumentRecord.query.filter_by(project_id=self.project.id).count(), 1)

    def test_changed_replacement_supersedes_without_asking_for_version(self):
        first = upload_file_single_shot(self.project, "Lamppost.pdf", b"v1", self.user)
        second = upload_file_single_shot(self.project, "Lamppost.pdf", b"v2-changed", self.user)
        self.assertEqual(second.supersedes_id, first.id)
        self.assertEqual(second.version_label, "2")

    def test_executable_file_is_rejected(self):
        with self.assertRaises(UploadSessionError):
            upload_file_single_shot(self.project, "installer.exe", b"MZ", self.user)
        self.assertEqual(DocumentRecord.query.count(), 0)

    def test_macro_enabled_workbook_is_rejected(self):
        with self.assertRaises(UploadSessionError):
            upload_file_single_shot(self.project, "budget.xlsm", b"PK...", self.user)

    def test_oversized_file_is_rejected_before_reading_content(self):
        with self.assertRaises(UploadSessionError):
            start_upload_session(self.project, "huge.pdf", 200 * 1024 * 1024, self.user)

    def test_chunked_upload_reassembles_full_content(self):
        session_id = start_upload_session(self.project, "Lamppost.pdf", 20, self.user)
        append_chunk(session_id, b"0123456789")
        append_chunk(session_id, b"9876543210")
        document = complete_upload_session(session_id, self.user)
        self.assertEqual(document.checksum_sha256, __import__("hashlib").sha256(b"01234567899876543210").hexdigest())

    def test_incomplete_chunked_upload_is_rejected_on_complete(self):
        session_id = start_upload_session(self.project, "Lamppost.pdf", 20, self.user)
        append_chunk(session_id, b"0123456789")
        with self.assertRaises(UploadSessionError):
            complete_upload_session(session_id, self.user)

    def test_restricted_classification_never_broadens_sharing(self):
        doc = upload_file_single_shot(self.project, "Daywise Buddies - Summer School.csv", b"data", self.user)
        self.assertEqual(doc.permission_classification, "Restricted")

    def test_ensure_project_folder_is_deterministic_in_mock_mode(self):
        folder_id_1 = ensure_project_folder(self.project)
        folder_id_2 = ensure_project_folder(self.project)
        self.assertEqual(folder_id_1, folder_id_2)

    def test_upload_file_to_drive_mock_never_calls_live_api(self):
        result = upload_file_to_drive(self.project, "test.pdf", b"content", "application/pdf")
        self.assertTrue(result["file_id"].startswith("mock-"))


if __name__ == "__main__":
    unittest.main()
