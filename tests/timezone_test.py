"""Audit finding B09: one timezone convention across every entry path.

Imported itinerary sessions displayed 03:30 for a 09:00 activity in
production while a manually created 09:00 session displayed 09:00. Import
attached `Asia/Kolkata` and templates formatted the stored value without
converting it, so on PostgreSQL (`timestamptz`, normalised to UTC) the two
paths disagreed by 5 1/2 hours. SQLite keeps naive values, which is why the
audit's local run did not reproduce the shift.

These tests assert the convention directly -- stored UTC, rendered campus
local -- so they hold on either backend. Run them against PostgreSQL too:

    DATABASE_URL=postgresql+psycopg://icc_erp:local-development-only@127.0.0.1:5432/icc_erp \\
      uv run --frozen python -m unittest discover -s tests -p 'timezone_test.py'
"""

import io
import os
import unittest
from pathlib import Path
from datetime import date, datetime, time, timezone

os.environ["TESTING"] = "true"

from werkzeug.datastructures import FileStorage

from app import create_app
from app.database import db
from app.models.erp import OperatingUnit, ProjectSession, RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project

from app.models.user import User
from app.services.itinerary import commit_itinerary_batch, stage_itinerary_import
from app.services.timeutil import to_campus, to_utc

IST_OFFSET_MINUTES = 330


def _as_utc(value):
    """Read a stored datetime back as UTC regardless of backend: PostgreSQL
    returns it tz-aware, SQLite naive."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class TimezoneConventionTestCase(unittest.TestCase):
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
            code="IGP-2026-CEN-901", campus_id=self.campus.id, program_type_id=self.igp.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Timezone check",
            category="Exchange", status="Active", start_date=date(2026, 9, 13), end_date=date(2026, 9, 14),
        )
        self.user = User(
            username="igp_tz", email="igp_tz@example.com", role="IGP Head",
            status="Approved", needs_password_reset=False,
        )
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="IGP_HEAD", is_active=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    # --- conversion helpers -------------------------------------------------

    def test_naive_input_is_read_as_campus_local_and_stored_as_utc(self):
        self.assertEqual(
            to_utc(datetime(2026, 9, 13, 9, 0)),
            datetime(2026, 9, 13, 3, 30, tzinfo=timezone.utc),
        )

    def test_naive_stored_value_is_read_back_as_utc_and_rendered_local(self):
        self.assertEqual(to_campus(datetime(2026, 9, 13, 3, 30)).strftime("%H:%M"), "09:00")

    def test_round_trip_is_lossless(self):
        original = datetime(2026, 9, 13, 9, 0)
        self.assertEqual(to_campus(to_utc(original)).replace(tzinfo=None), original)

    # --- the two entry paths must agree -------------------------------------

    def _import_audit_itinerary(self):
        content = (
            "Date,Start Time,End Time,Activity,Venue,Type\n"
            "2026-09-13,09:00 AM,10:00 AM,Day one activity,Auditorium,Session\n"
            "2026-09-14,10:00 AM,11:00 AM,Day two activity,Auditorium,Session\n"
        ).encode()
        batch = stage_itinerary_import(
            self.project, FileStorage(stream=io.BytesIO(content), filename="plan.csv"), "tz-key"
        )
        commit_itinerary_batch(batch, self.user)

    def test_imported_itinerary_stores_utc_for_the_audit_fixture_times(self):
        self._import_audit_itinerary()
        sessions = ProjectSession.query.order_by(ProjectSession.starts_at).all()
        self.assertEqual(len(sessions), 2)
        # 13 September 09:00 IST and 14 September 10:00 IST, per the audit's
        # stated expectation for BETA-AUDIT-itinerary.csv.
        self.assertEqual(_as_utc(sessions[0].starts_at), datetime(2026, 9, 13, 3, 30, tzinfo=timezone.utc))
        self.assertEqual(_as_utc(sessions[1].starts_at), datetime(2026, 9, 14, 4, 30, tzinfo=timezone.utc))

    def test_imported_itinerary_renders_the_times_the_user_typed(self):
        self._import_audit_itinerary()
        sessions = ProjectSession.query.order_by(ProjectSession.starts_at).all()
        rendered = [
            (to_campus(s.starts_at).strftime("%d %b %H:%M"), to_campus(s.ends_at).strftime("%H:%M"))
            for s in sessions
        ]
        self.assertEqual(rendered, [("13 Sep 09:00", "10:00"), ("14 Sep 10:00", "11:00")])

    def test_manual_entry_and_import_agree_on_the_same_wall_clock_time(self):
        self._import_audit_itinerary()
        imported = ProjectSession.query.order_by(ProjectSession.starts_at).first()
        manual = ProjectSession(
            project_id=self.project.id, code="MANUAL-1", title="Manually created", session_type="Session",
            starts_at=to_utc(datetime.strptime("2026-09-13T09:00", "%Y-%m-%dT%H:%M")),
            ends_at=to_utc(datetime.strptime("2026-09-13T10:00", "%Y-%m-%dT%H:%M")),
        )
        db.session.add(manual)
        db.session.commit()
        self.assertEqual(_as_utc(manual.starts_at), _as_utc(imported.starts_at))

    # --- date boundaries ----------------------------------------------------

    def test_late_evening_session_does_not_slide_onto_the_next_day(self):
        session = ProjectSession(
            project_id=self.project.id, code="LATE", title="Late", session_type="Session",
            starts_at=to_utc(datetime.combine(date(2026, 9, 13), time(23, 30))),
            ends_at=to_utc(datetime.combine(date(2026, 9, 13), time(23, 59))),
        )
        db.session.add(session)
        db.session.commit()
        # 23:30 IST is 18:00Z the same day; the rendered date must stay the 13th.
        self.assertEqual(_as_utc(session.starts_at).strftime("%d"), "13")
        self.assertEqual(to_campus(session.starts_at).strftime("%d %b %H:%M"), "13 Sep 23:30")

    def test_early_morning_session_does_not_slide_onto_the_previous_day(self):
        session = ProjectSession(
            project_id=self.project.id, code="EARLY", title="Early", session_type="Session",
            starts_at=to_utc(datetime.combine(date(2026, 9, 14), time(0, 30))),
            ends_at=to_utc(datetime.combine(date(2026, 9, 14), time(1, 30))),
        )
        db.session.add(session)
        db.session.commit()
        # 00:30 IST is 19:00Z on the 13th; rendering must put it back on the 14th.
        self.assertEqual(_as_utc(session.starts_at), datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(to_campus(session.starts_at).strftime("%d %b %H:%M"), "14 Sep 00:30")

    # --- the real routes and templates, not just the helpers ----------------

    def test_add_session_route_stores_the_typed_time_as_utc(self):
        """The manual path was the one storing a wrong instant on PostgreSQL:
        it wrote 09:00 as 09:00Z and then displayed it unconverted, so the two
        errors cancelled out and only the imported sessions looked wrong."""
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version
        response = client.post(
            f"/erp/projects/{self.project.public_id}/sessions",
            data={
                "title": "Typed by hand", "starts_at": "2026-09-13T09:00",
                "ends_at": "2026-09-13T10:00", "session_type": "Session",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        created = ProjectSession.query.filter_by(title="Typed by hand").one()
        self.assertEqual(_as_utc(created.starts_at), datetime(2026, 9, 13, 3, 30, tzinfo=timezone.utc))

    def test_no_template_formats_a_session_datetime_without_converting_it(self):
        """The display half of B09: templates called `.strftime()` straight on
        the stored value, so a correctly stored UTC instant still rendered as
        03:30. Storage tests alone cannot catch that -- this guards the
        convention across every template at once."""
        offenders = []
        for template in Path("app/templates").rglob("*.html"):
            for line_number, line in enumerate(template.read_text().splitlines(), 1):
                for field in ("starts_at", "ends_at", "occurred_at", "last_login_at"):
                    if f"{field}.strftime" in line:
                        offenders.append(f"{template}:{line_number} renders {field} with .strftime")
        self.assertEqual(
            offenders, [],
            "Render datetimes through the localdate/localtime/localdatetime filters:\n" + "\n".join(offenders),
        )

    # --- rendering ----------------------------------------------------------

    def test_filters_render_campus_local_and_label_times(self):
        stored = datetime(2026, 9, 13, 3, 30, tzinfo=timezone.utc)
        rendered = self.app.jinja_env.from_string(
            "{{ value|localdate }}|{{ value|localtime }}|{{ value|localtime(label=False) }}"
        ).render(value=stored)
        local_date, labelled_time, bare_time = rendered.split("|")
        self.assertEqual(local_date, "Sun, 13 Sep 2026")
        self.assertEqual(bare_time, "09:00 AM")
        self.assertTrue(labelled_time.startswith("09:00 AM "), labelled_time)
        self.assertIn("IST", labelled_time)

    def test_filters_render_a_missing_datetime_without_raising(self):
        self.assertEqual(
            self.app.jinja_env.from_string("{{ value|localdatetime }}").render(value=None), "—"
        )

    def test_offset_matches_the_configured_zone(self):
        offset = to_campus(datetime(2026, 9, 13, 3, 30, tzinfo=timezone.utc)).utcoffset()
        self.assertEqual(offset.total_seconds() / 60, IST_OFFSET_MINUTES)


if __name__ == "__main__":
    unittest.main()
