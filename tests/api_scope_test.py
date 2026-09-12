"""Every /api/v1 collection must be filtered to projects the caller can see.

list_resource scopes by `project_id` with an explicit fallback chain for models
that key on something else. AggregateAttendance (session_id) and
FeedbackResponse (form_id) fell through both branches, so no filter was applied
at all: any approved user could read every row on the platform, and
aggregate-attendance had no permission entry either, so there was no gate
whatsoever. These assertions fail on the pre-fix code.
"""

import os
import unittest
from datetime import date, datetime, timezone

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import FeedbackForm, FeedbackResponse, ProjectSession, RoleAssignment
from app.models.production import AggregateAttendance
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User


class ApiCollectionScopeTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        mine, theirs = Campus(name="Central", code="CEN"), Campus(name="Other", code="OTH")
        program = ProgramType(name="ICC")
        db.session.add_all([year, mine, theirs, program])
        db.session.flush()

        def project(code, campus):
            row = Project(code=code, campus_id=campus.id, program_type_id=program.id,
                          academic_year_id=year.id, title=code, category="Operational", status="Draft",
                          start_date=date(2026, 8, 1), end_date=date(2026, 8, 2))
            db.session.add(row)
            db.session.flush()
            return row

        self.visible = project("ICC-2026-CEN-001", mine)
        self.hidden = project("ICC-2026-OTH-001", theirs)

        for index, proj in enumerate((self.visible, self.hidden)):
            session_row = ProjectSession(
                project_id=proj.id, code=f"S{index}", title="Session", session_type="Event",
                starts_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc),
                ends_at=datetime(2026, 8, 1, 11, tzinfo=timezone.utc),
            )
            form = FeedbackForm(project_id=proj.id, title="Feedback", questions_json=[], is_open=True)
            db.session.add_all([session_row, form])
            db.session.flush()
            db.session.add(AggregateAttendance(session_id=session_row.id, category="Students", count=10 + index))
            db.session.add(FeedbackResponse(form_id=form.id, answers_json={"note": proj.code},
                                            moderation_status="Approved"))

        self.user = User(username="events_head", email="events_head@example.com",
                         role="ICC Events Head", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        # Scoped to one project only.
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="ICC_EVENTS_HEAD",
                                      project_id=self.visible.id, is_active=True))
        db.session.commit()

        with self.client.session_transaction() as flask_session:
            flask_session["user_id"] = self.user.id
            flask_session["session_version"] = self.user.session_version

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _rows(self, resource):
        response = self.client.get(f"/api/v1/{resource}")
        self.assertEqual(response.status_code, 200, response.data)
        return response.get_json()["data"]

    def test_aggregate_attendance_is_scoped_to_visible_projects(self):
        counts = {row["count"] for row in self._rows("aggregate-attendance")}
        self.assertEqual(counts, {10}, "row 11 belongs to a project this user cannot see")

    def test_feedback_responses_are_scoped_to_visible_projects(self):
        notes = {row["answers_json"]["note"] for row in self._rows("feedback-responses")}
        self.assertEqual(notes, {self.visible.code})

    def test_unscoped_user_is_refused_both_collections_outright(self):
        """With no active assignment the entry gate denies before any row is
        read. Previously aggregate-attendance had no permission entry at all,
        so this returned 200 with every row on the platform."""
        RoleAssignment.query.filter_by(user_id=self.user.id).update({"is_active": False})
        db.session.commit()
        for resource in ("aggregate-attendance", "feedback-responses"):
            self.assertEqual(self.client.get(f"/api/v1/{resource}").status_code, 403, resource)


if __name__ == "__main__":
    unittest.main()
