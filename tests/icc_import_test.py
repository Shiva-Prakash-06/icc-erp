import io
import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from openpyxl import Workbook
from werkzeug.datastructures import FileStorage

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, OperatingUnit, Person, ProjectSession, SessionAttendance, TeamAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.documents import classify_filename
from app.services.icc_import import (
    commit_icc_attendance_batch,
    infer_actual_reach,
    map_attendance,
    stage_icc_attendance_import,
    stage_icc_event_folder_import,
)


def _build_workbook(volunteer_rows, guest_rows=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "STU LIST"
    ws.append(["ICC VOLUNTEERS"])
    ws.append(["S.no.", "Primary role", "Name", "Class", "Reg Number", "Student type", "ATTENDANCE"])
    for row in volunteer_rows:
        ws.append(row)
    if guest_rows is not None:
        gs = wb.create_sheet("GUEST LIST")
        gs.append(["KENGERI CAMPUS"])
        gs.append([None])
        gs.append(["No.", "NAME", "REG NO.", "CATEGORY", "PROGRAM", "PARENTS NAME"])
        for row in guest_rows:
            gs.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


class AttendanceMappingTestCase(unittest.TestCase):
    def test_present_variants(self):
        for value in ["Present", "p", "P", "Yes", "YES", "1", "✓"]:
            self.assertEqual(map_attendance(value), "Present", value)

    def test_absent_variants(self):
        for value in ["Absent", "a", "A", "No", "no", "0"]:
            self.assertEqual(map_attendance(value), "Absent", value)

    def test_blank_maps_to_none(self):
        for value in [None, "", "   "]:
            self.assertIsNone(map_attendance(value))

    def test_unrecognized_value_maps_to_none(self):
        self.assertIsNone(map_attendance("Maybe"))


class DocumentClassificationTestCase(unittest.TestCase):
    def test_every_named_igp_reference_classifies_correctly(self):
        expected = {
            "UC Screen Flyer.pdf": "Screen Banner",
            "Lamppost.pdf": "Lamppost",
            "Copy of Welcome notes .pdf": "Welcome Notes",
            "UC students Certs.pdf": "Participant Certificates",
            "UC Buddies Certs.pdf": "Buddy Certificates",
            "Daywise Buddies - Summer School.csv": "Daywise Buddy Allocation",
            "UC Inaug Schedule.pdf": "Inauguration Schedule",
            "UC Valedictory Schedule.pdf": "Valedictory Schedule",
            "Summer School Claimsheet.pdf": "Attendance Claim",
            "Summer School Buddies Allocation.csv": "Buddy Allocation Source",
            "_Summer School- Check List.xlsx": "Operational Checklist",
        }
        for filename, category in expected.items():
            self.assertEqual(classify_filename(filename)[0], category, filename)

    def test_restricted_defaults(self):
        for filename in ["Copy of Welcome notes .pdf", "Daywise Buddies - Summer School.csv", "Summer School Claimsheet.pdf", "Summer School Buddies Allocation.csv"]:
            self.assertEqual(classify_filename(filename)[1], "Restricted", filename)

    def test_public_defaults(self):
        for filename in ["UC Screen Flyer.pdf", "Lamppost.pdf"]:
            self.assertEqual(classify_filename(filename)[1], "Public", filename)


class IccAttendanceImportTestCase(unittest.TestCase):
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
            code="ICC-2026-CEN-960", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Coffee Meet",
            category="Event", status="Active", start_date=date(2026, 8, 20), end_date=date(2026, 8, 20),
        )
        self.user = User(username="events_head", email="events_head@example.com", role="ICC Core Committee", status="Approved")
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _upload(self, content, filename="v.xlsx"):
        return FileStorage(stream=io.BytesIO(content), filename=filename)

    def test_volunteer_roster_creates_one_main_session_and_team_assignments(self):
        content = _build_workbook([
            [1, "Events Core", "Alice A", "3 BBA", 1001, "International", "Present"],
            [2, None, "Bob B", "3 BCA", 1002, "International", None],
        ])
        batch = stage_icc_attendance_import(self.project, self._upload(content), "op")
        commit_icc_attendance_batch(batch, self.user)
        self.assertEqual(ProjectSession.query.filter_by(project_id=self.project.id, code="MAIN").count(), 1)
        self.assertEqual(TeamAssignment.query.filter_by(project_id=self.project.id).count(), 2)
        self.assertEqual(SessionAttendance.query.count(), 1)  # Bob's blank attendance creates no record

    def test_attendance_is_unverified_on_import(self):
        content = _build_workbook([[1, None, "Alice A", "3 BBA", 1001, "International", "Present"]])
        batch = stage_icc_attendance_import(self.project, self._upload(content), "op")
        commit_icc_attendance_batch(batch, self.user)
        attendance = SessionAttendance.query.one()
        self.assertIsNone(attendance.verified_by_id)
        self.assertIsNone(attendance.verified_at)

    def test_empty_guest_sheet_creates_no_guests(self):
        content = _build_workbook([[1, None, "Alice A", "3 BBA", 1001, "International", None]], guest_rows=[])
        batch = stage_icc_attendance_import(self.project, self._upload(content), "op")
        self.assertEqual(batch.reconciliation_json["guest_rows"], 0)
        commit_icc_attendance_batch(batch, self.user)
        self.assertEqual(Person.query.filter_by(person_type="Guest").count(), 0)

    def test_guest_sheet_with_rows_is_imported_without_login_accounts(self):
        content = _build_workbook(
            [[1, None, "Alice A", "3 BBA", 1001, "International", None]],
            guest_rows=[[1, "Guest One", None, "Parent", None, None], [2, "Guest Two", None, "Parent", None, None]],
        )
        batch = stage_icc_attendance_import(self.project, self._upload(content), "op")
        self.assertEqual(batch.reconciliation_json["guest_rows"], 2)
        commit_icc_attendance_batch(batch, self.user)
        guests = Person.query.filter_by(person_type="Guest").all()
        self.assertEqual(len(guests), 2)
        for guest in guests:
            self.assertIsNone(guest.user_account)

    def test_reach_prefers_guest_roster_over_volunteer_present_count(self):
        content = _build_workbook(
            [[1, None, "Alice A", "3 BBA", 1001, "International", "Present"], [2, None, "Bob B", "3 BCA", 1002, "International", "Present"]],
            guest_rows=[[1, "Guest One", None, "Parent", None, None]],
        )
        batch = stage_icc_attendance_import(self.project, self._upload(content), "op")
        commit_icc_attendance_batch(batch, self.user)
        self.assertEqual(self.project.actual_reach, 1)

    def test_reach_is_blank_for_volunteer_only_roster(self):
        content = _build_workbook([[1, None, "Alice A", "3 BBA", 1001, "International", "Present"]])
        batch = stage_icc_attendance_import(self.project, self._upload(content), "op")
        commit_icc_attendance_batch(batch, self.user)
        self.assertIsNone(self.project.actual_reach)

    def test_reach_is_untouched_when_already_explicitly_set(self):
        self.project.actual_reach = 200
        db.session.commit()
        content = _build_workbook(
            [[1, None, "Alice A", "3 BBA", 1001, "International", "Present"]],
            guest_rows=[[1, "Guest One", None, "Parent", None, None]],
        )
        batch = stage_icc_attendance_import(self.project, self._upload(content), "op")
        commit_icc_attendance_batch(batch, self.user)
        self.assertEqual(self.project.actual_reach, 200)

    def test_reimport_of_identical_file_is_idempotent(self):
        content = _build_workbook([[1, None, "Alice A", "3 BBA", 1001, "International", "Present"]])
        first = stage_icc_attendance_import(self.project, self._upload(content), "op")
        commit_icc_attendance_batch(first, self.user)
        replay = stage_icc_attendance_import(self.project, self._upload(content), "op")
        self.assertEqual(first.id, replay.id)


class EventFolderImportTestCase(unittest.TestCase):
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
            code="ICC-2026-CEN-961", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Coffee Meet 2",
            category="Event", status="Active", start_date=date(2026, 8, 20), end_date=date(2026, 8, 20),
        )
        self.user = User(username="events_head2", email="events_head2@example.com", role="ICC Core Committee", status="Approved")
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_files_are_classified_and_attached(self):
        files = [
            FileStorage(stream=io.BytesIO(b"posterdata"), filename="UC Screen Flyer.pdf"),
            FileStorage(stream=io.BytesIO(b"reportdata"), filename="Event Report_ICC Test.docx"),
        ]
        results = stage_icc_event_folder_import(self.project, files, self.user)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["status"] == "attached" for r in results))
        self.assertEqual(DocumentRecord.query.filter_by(project_id=self.project.id).count(), 2)

    def test_executable_and_unsupported_files_are_rejected(self):
        files = [FileStorage(stream=io.BytesIO(b"MZ..."), filename="malware.exe")]
        results = stage_icc_event_folder_import(self.project, files, self.user)
        self.assertEqual(results[0]["status"], "rejected")
        self.assertEqual(DocumentRecord.query.filter_by(project_id=self.project.id).count(), 0)

    def test_identical_checksum_is_deduplicated(self):
        content = b"same-bytes"
        first = stage_icc_event_folder_import(
            self.project, [FileStorage(stream=io.BytesIO(content), filename="Lamppost.pdf")], self.user,
        )
        second = stage_icc_event_folder_import(
            self.project, [FileStorage(stream=io.BytesIO(content), filename="Lamppost.pdf")], self.user,
        )
        self.assertEqual(first[0]["status"], "attached")
        self.assertEqual(second[0]["status"], "duplicate")
        self.assertEqual(DocumentRecord.query.filter_by(project_id=self.project.id).count(), 1)

    def test_changed_replacement_supersedes_prior_version(self):
        stage_icc_event_folder_import(
            self.project, [FileStorage(stream=io.BytesIO(b"v1"), filename="Lamppost.pdf")], self.user,
        )
        stage_icc_event_folder_import(
            self.project, [FileStorage(stream=io.BytesIO(b"v2-different"), filename="Lamppost.pdf")], self.user,
        )
        documents = DocumentRecord.query.filter_by(project_id=self.project.id).order_by(DocumentRecord.id).all()
        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[1].supersedes_id, documents[0].id)
        self.assertEqual(documents[1].version_label, "2")


if __name__ == "__main__":
    unittest.main()
