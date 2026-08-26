import io
import os
import unittest
from datetime import date
from pathlib import Path

os.environ["TESTING"] = "true"

from werkzeug.datastructures import FileStorage

from app import create_app
from app.database import db
from app.models.erp import ItineraryRevision, OperatingUnit, Person, ProjectSession, SessionAttendance
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.itinerary import (
    ItineraryParseError,
    commit_itinerary_batch,
    parse_itinerary,
    sniff_itinerary_format,
    stage_itinerary_import,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "summer_school_itinerary"


class ItineraryParserTestCase(unittest.TestCase):
    """Pure-parsing tests against the supplied wide-layout itinerary. See
    PLAN.md 'IGP itinerary' acceptance criteria."""

    @classmethod
    def setUpClass(cls):
        cls.content = FIXTURE_PATH.read_bytes()
        cls.parsed = parse_itinerary("Summer School Itinerary", cls.content)

    def test_extensionless_file_is_recognized_as_csv(self):
        self.assertEqual(sniff_itinerary_format("Summer School Itinerary", self.content), "csv")

    def test_all_29_dated_days_are_represented(self):
        self.assertEqual(len(self.parsed["days"]), 29)
        self.assertEqual(self.parsed["start_date"], date(2026, 6, 27))
        self.assertEqual(self.parsed["end_date"], date(2026, 7, 25))

    def test_title_is_inferred_from_title_row(self):
        self.assertEqual(self.parsed["title"], "International Summer School 2026")

    def test_adjacent_repeated_activity_cells_merge(self):
        tuesday = next(day for day in self.parsed["days"] if day["date"] == date(2026, 6, 30))
        # Columns 1 and 2 both read "Dr Sharon Valarmathi..." and should merge
        # into a single 9:30-12:00 session rather than two separate ones.
        matching = [s for s in tuesday["sessions"] if "Sharon Valarmathi" in s["title"]]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["start_time"].strftime("%H:%M"), "09:30")
        self.assertEqual(matching[0]["end_time"].strftime("%H:%M"), "12:00")

    def test_embedded_time_overrides_column_time(self):
        valedictory_day = next(day for day in self.parsed["days"] if day["date"] == date(2026, 7, 24))
        session = next(s for s in valedictory_day["sessions"] if "Valedictory" in s["title"])
        # Column time for this slot is 9:30-10:30; the cell text embeds
        # "11:00 AM- 12:00 Noon" which must win.
        self.assertEqual(session["start_time"].strftime("%H:%M"), "11:00")
        self.assertEqual(session["end_time"].strftime("%H:%M"), "12:00")
        self.assertFalse(session["is_all_day"])

    def test_arrivals_are_all_day_with_no_fake_time(self):
        arrival_day = next(day for day in self.parsed["days"] if day["date"] == date(2026, 6, 27))
        self.assertEqual(len(arrival_day["sessions"]), 1)
        session = arrival_day["sessions"][0]
        self.assertTrue(session["is_all_day"])
        self.assertIsNone(session["start_time"])
        self.assertIsNone(session["end_time"])
        self.assertEqual(session["session_type"], "Arrival")

    def test_holidays_are_all_day(self):
        holiday_day = next(day for day in self.parsed["days"] if day["date"] == date(2026, 7, 5))
        self.assertTrue(holiday_day["sessions"][0]["is_all_day"])
        self.assertEqual(holiday_day["sessions"][0]["session_type"], "Holiday")

    def test_excursions_and_departures_are_all_day(self):
        excursion_day = next(day for day in self.parsed["days"] if day["date"] == date(2026, 7, 1))
        self.assertTrue(excursion_day["sessions"][0]["is_all_day"])
        self.assertEqual(excursion_day["sessions"][0]["session_type"], "Excursion")

    def test_meal_availability_is_preserved(self):
        monday = next(day for day in self.parsed["days"] if day["date"] == date(2026, 6, 29))
        self.assertEqual(monday["meals"]["breakfast"], "✓")
        self.assertEqual(monday["meals"]["lunch"], "✓")
        self.assertEqual(monday["meals"]["dinner"], "✓")
        wednesday = next(day for day in self.parsed["days"] if day["date"] == date(2026, 7, 1))
        self.assertEqual(wednesday["meals"]["dinner"], "On own")

    def test_blank_and_dash_cells_are_ignored(self):
        for day in self.parsed["days"]:
            for session in day["sessions"]:
                self.assertNotEqual(session["title"], "-")
                self.assertNotEqual(session["title"], "")

    def test_footer_notes_and_default_venue_are_captured(self):
        self.assertTrue(self.parsed["footer_notes"])
        self.assertEqual(self.parsed["default_venue"], "803")

    def test_unsupported_suffix_is_rejected(self):
        with self.assertRaises(ItineraryParseError):
            sniff_itinerary_format("itinerary.pdf", b"%PDF-1.4")


class ItineraryImportTestCase(unittest.TestCase):
    """Staging/commit/idempotency tests against a real project."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
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
            code="IGP-2026-CEN-900", campus_id=self.campus.id, program_type_id=self.igp.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Summer School",
            category="Exchange", status="Active", start_date=date(2026, 6, 27), end_date=date(2026, 7, 25),
        )
        self.user = User(username="igp_head", email="igp_head@example.com", role="IGP Head", status="Approved")
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.commit()
        self.content = FIXTURE_PATH.read_bytes()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _upload(self, content=None, filename="Summer School Itinerary"):
        return FileStorage(stream=io.BytesIO(content or self.content), filename=filename)

    def test_import_creates_one_session_per_activity_and_one_active_revision(self):
        batch = stage_itinerary_import(self.project, self._upload(), "op-key")
        commit_itinerary_batch(batch, self.user)
        self.assertEqual(batch.status, "Committed")
        sessions = ProjectSession.query.filter_by(project_id=self.project.id).all()
        self.assertEqual(len(sessions), batch.committed_count)
        self.assertTrue(all(session.is_active for session in sessions))
        self.assertEqual(ItineraryRevision.query.filter_by(project_id=self.project.id, is_active=True).count(), 1)

    def test_reimport_of_identical_file_is_idempotent(self):
        first = stage_itinerary_import(self.project, self._upload(), "op-key")
        commit_itinerary_batch(first, self.user)
        replay = stage_itinerary_import(self.project, self._upload(), "op-key")
        self.assertEqual(first.id, replay.id)

    def test_reimport_deactivates_removed_sessions_but_preserves_attendance(self):
        first = stage_itinerary_import(self.project, self._upload(), "op-key")
        commit_itinerary_batch(first, self.user)

        person = Person(first_name="Test", last_name="Student")
        db.session.add(person)
        db.session.flush()
        attended_session = ProjectSession.query.filter_by(project_id=self.project.id, is_active=True).first()
        db.session.add(SessionAttendance(session_id=attended_session.id, person_id=person.id, status="Present"))
        db.session.commit()
        attended_code = attended_session.code

        lines = self.content.decode("utf-8-sig").splitlines(keepends=True)
        modified = "".join(line for line in lines if "Arrivals" not in line).encode()
        second = stage_itinerary_import(self.project, self._upload(modified, "Summer School Itinerary v2"), "op-key")
        commit_itinerary_batch(second, self.user)

        self.assertEqual(ProjectSession.query.filter_by(project_id=self.project.id, is_active=False).count(), 2)
        kept = ProjectSession.query.filter_by(project_id=self.project.id, code=attended_code).first()
        self.assertIsNotNone(kept)
        self.assertEqual(SessionAttendance.query.filter_by(session_id=kept.id).count(), 1)

    def test_canonical_layout_is_supported(self):
        canonical_csv = (
            "Date,Start Time,End Time,Activity,Venue,Type,Breakfast,Lunch,Dinner\n"
            "2026-08-01,09:00 AM,10:00 AM,Orientation,Auditorium,Session,Yes,Yes,Yes\n"
        ).encode()
        batch = stage_itinerary_import(self.project, self._upload(canonical_csv, "plan.csv"), "op-key")
        commit_itinerary_batch(batch, self.user)
        session = ProjectSession.query.filter_by(project_id=self.project.id).one()
        self.assertEqual(session.title, "Orientation")
        self.assertEqual(session.venue, "Auditorium")


if __name__ == "__main__":
    unittest.main()
