import os
import unittest
from datetime import date, datetime

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, FeedbackForm, FeedbackResponse, SessionAttendance, TeamAssignment, Wing
from app.models.operational import AttendanceRecord, Contribution, Document, Feedback
from app.models.production import ContributionRecord
from app.models.project import AcademicYear, Campus, ProgramType, Project, ProjectParticipant
from app.models.user import User
from app.services.legacy_migration import (
    migrate_attendance_to_sessions,
    migrate_contributions_to_records,
    migrate_documents_to_records,
    migrate_feedback_to_responses,
    migrate_participants_to_teams,
)


class LegacyMigrationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        campus = Campus(name="Central", code="CEN")
        program_type = ProgramType(name="ICC")
        db.session.add_all([year, campus, program_type])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-777", campus_id=campus.id, program_type_id=program_type.id,
            academic_year_id=year.id, title="Migration test project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()
        self.user = User(username="legacyuser", email="legacyuser@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_migrate_participants_to_teams_is_idempotent(self):
        db.session.add(ProjectParticipant(project_id=self.project.id, user_id=self.user.id, participant_type="Volunteer", nationality="Indian"))
        db.session.commit()
        result = migrate_participants_to_teams()
        self.assertEqual(result["migrated"], 1)
        self.assertEqual(TeamAssignment.query.count(), 1)
        again = migrate_participants_to_teams()
        self.assertEqual(again["migrated"], 0)
        self.assertEqual(TeamAssignment.query.count(), 1)

    def test_migrate_attendance_to_sessions_synthesizes_one_session_per_date(self):
        db.session.add(AttendanceRecord(project_id=self.project.id, user_id=self.user.id, date=date(2026, 8, 1), status="Present"))
        db.session.add(AttendanceRecord(project_id=self.project.id, user_id=self.user.id, date=date(2026, 8, 2), status="Absent"))
        db.session.commit()
        result = migrate_attendance_to_sessions()
        self.assertEqual(result["migrated"], 2)
        self.assertEqual(result["sessions_created"], 2)
        self.assertEqual(SessionAttendance.query.count(), 2)
        again = migrate_attendance_to_sessions()
        self.assertEqual(again["migrated"], 0)
        self.assertEqual(again["sessions_created"], 0)

    def test_migrate_contributions_preserves_unmappable_division(self):
        db.session.add(Contribution(project_id=self.project.id, user_id=self.user.id, activity_type="Media support", division="Translation", duration_hours=2.5))
        db.session.commit()
        result = migrate_contributions_to_records()
        self.assertEqual(result["migrated"], 1)
        record = ContributionRecord.query.first()
        self.assertIsNone(record.wing_id)
        self.assertIn("[Translation]", record.description)
        again = migrate_contributions_to_records()
        self.assertEqual(again["migrated"], 0)

    def test_migrate_contributions_maps_known_division_to_wing(self):
        # Wings require an operating unit in production; create one inline.
        from app.models.erp import OperatingUnit
        unit = OperatingUnit(code="ICC", name="ICC")
        db.session.add(unit)
        db.session.flush()
        wing = Wing(operating_unit_id=unit.id, code="MEDIA", name="Media")
        db.session.add(wing)
        db.session.add(Contribution(project_id=self.project.id, user_id=self.user.id, activity_type="Media support", division="Photography", duration_hours=1))
        db.session.commit()
        migrate_contributions_to_records()
        record = ContributionRecord.query.first()
        self.assertEqual(record.wing_id, wing.id)

    def test_migrate_documents_to_records(self):
        db.session.add(Document(project_id=self.project.id, title="Final report", document_type="Report", google_drive_link="https://drive.google.com/file/d/abc123/view", uploaded_by_id=self.user.id))
        db.session.commit()
        result = migrate_documents_to_records()
        self.assertEqual(result["migrated"], 1)
        record = DocumentRecord.query.first()
        self.assertEqual(record.status, "Submitted")
        self.assertEqual(record.category, "Report")
        again = migrate_documents_to_records()
        self.assertEqual(again["migrated"], 0)

    def test_migrate_feedback_to_responses_synthesizes_form_and_rating_convention(self):
        db.session.add(Feedback(project_id=self.project.id, user_id=self.user.id, rating=4, comments="Great event", submission_type="Event feedback"))
        db.session.commit()
        result = migrate_feedback_to_responses()
        self.assertEqual(result["migrated"], 1)
        self.assertEqual(result["forms_created"], 1)
        form = FeedbackForm.query.filter_by(project_id=self.project.id).first()
        self.assertIsNotNone(form)
        response = FeedbackResponse.query.filter_by(form_id=form.id).first()
        self.assertEqual(response.answers_json["rating"], 4)
        self.assertEqual(response.moderation_status, "Approved")
        self.assertFalse(response.publication_consent)
        again = migrate_feedback_to_responses()
        self.assertEqual(again["migrated"], 0)
        self.assertEqual(again["forms_created"], 0)


if __name__ == "__main__":
    unittest.main()
