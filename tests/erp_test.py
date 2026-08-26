import os
import unittest
from datetime import date, datetime, timezone

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import (
    ChecklistInstance,
    ChecklistItemStatus,
    ChecklistTemplate,
    ChecklistTemplateItem,
    DocumentRecord,
    FeedbackForm,
    FeedbackResponse,
    ImportBatch,
    OperatingUnit,
    Person,
    ProjectSession,
    RoleAssignment,
    SessionAttendance,
    Wing,
    WorkTask,
)
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.project import BuddyAssignment
from app.models.user import User
from app.services.authorization import has_permission
from app.services.imports import commit_batch, stage_supplied_source
from app.services.lifecycle import closure_blockers, transition_project
from app.services.buddy import validate_buddy_assignment


class ERPProductionShapeTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.central = Campus(name="Bangalore Central Campus", code="CEN")
        self.kengeri = Campus(name="Kengeri Campus", code="KEN")
        self.icc_type = ProgramType(name="ICC")
        self.igp_type = ProgramType(name="IGP")
        self.icc = OperatingUnit(code="ICC", name="International Christite Community")
        self.igp = OperatingUnit(code="IGP", name="India Gateway Program")
        db.session.add_all([self.year, self.central, self.kengeri, self.icc_type, self.igp_type, self.icc, self.igp])
        db.session.flush()
        self.events = Wing(operating_unit_id=self.icc.id, code="EVENTS", name="Events")
        db.session.add(self.events)
        db.session.flush()

        self.icc_project = self._project("ICC-2026-CEN-001", self.icc_type, self.icc, self.events)
        self.igp_project = self._project("IGP-2026-CEN-001", self.igp_type, self.igp, None)
        self.user = User(username="scoped.head", email="head@example.com", role="Scoped", preferred_role="ICC Head", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="ICC_EVENTS_HEAD", operating_unit_id=self.icc.id, wing_id=self.events.id, academic_year_id=self.year.id))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _project(self, code, program_type, unit, wing):
        project = Project(
            code=code,
            title=code,
            campus_id=self.central.id,
            program_type_id=program_type.id,
            academic_year_id=self.year.id,
            operating_unit_id=unit.id,
            wing_id=wing.id if wing else None,
            category="Event",
            status="Draft",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
        )
        db.session.add(project)
        db.session.flush()
        return project

    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.id

    def test_scoped_icc_head_cannot_approve_igp(self):
        self.assertTrue(has_permission(self.user, "approve", self.icc_project))
        self.assertFalse(has_permission(self.user, "approve", self.igp_project))

    def test_person_can_attend_without_account(self):
        person = Person(first_name="Visitor", primary_email="visitor@example.com", person_type="Participant")
        session = ProjectSession(
            project_id=self.icc_project.id,
            code="MAIN",
            title="Main session",
            starts_at=datetime(2026, 7, 1, 9, tzinfo=timezone.utc),
            ends_at=datetime(2026, 7, 1, 10, tzinfo=timezone.utc),
        )
        db.session.add_all([person, session])
        db.session.flush()
        db.session.add(SessionAttendance(session_id=session.id, person_id=person.id, status="Present", verified_by_id=self.user.id))
        db.session.commit()
        self.assertIsNone(person.user_account)
        self.assertEqual(SessionAttendance.query.count(), 1)

    def test_closure_is_blocked_until_requirements_are_resolved(self):
        self.icc_project.status = "Closing"
        self.icc_project.closure_summary = "Reviewed closure narrative."
        task = WorkTask(project_id=self.icc_project.id, title="Final approvals", status="In Progress", mandatory_for_closure=True)
        document = DocumentRecord(project_id=self.icc_project.id, category="Report", title="Final report", status="Missing", mandatory_for_closure=True)
        db.session.add_all([task, document])
        db.session.commit()
        self.assertEqual(len(closure_blockers(self.icc_project)), 2)
        with self.assertRaises(ValueError):
            transition_project(self.icc_project, "Completed", self.user)
        task.waived = True
        task.waiver_reason = "Faculty-approved exception"
        document.status = "Approved"
        db.session.commit()
        transition_project(self.icc_project, "Completed", self.user)
        self.assertEqual(self.icc_project.status, "Completed")

    def test_concurrent_project_update_returns_conflict(self):
        self.login()
        response = self.client.patch(
            f"/api/v1/projects/{self.icc_project.public_id}",
            json={"title": "Changed", "version": self.icc_project.version - 1},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.content_type, "application/problem+json")

    def test_sensitive_drive_reference_is_hidden_without_named_permission(self):
        document = DocumentRecord(
            project_id=self.icc_project.id,
            category="Sensitive requirement",
            title="Visa verification status",
            status="Submitted",
            drive_file_id="restricted-file-id",
            drive_url="https://drive.google.com/file/d/restricted-file-id/view",
            permission_classification="Restricted",
        )
        db.session.add(document)
        db.session.commit()
        self.login()
        response = self.client.get("/api/v1/documents")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json["data"][0]["drive_file_id"])
        self.assertNotIn("drive_url", response.json["data"][0])

    def test_public_feedback_token_accepts_moderated_anonymous_response(self):
        form = FeedbackForm(
            project_id=self.icc_project.id,
            title="Coffee Meet feedback",
            public_token="public-test-token",
            is_open=True,
            is_anonymous=True,
            questions_json=[{"id": "rating", "type": "rating", "label": "Rating"}],
        )
        db.session.add(form)
        db.session.commit()
        response = self.client.post(
            "/api/v1/public/feedback/public-test-token",
            json={"answers": {"rating": 5}, "publication_consent": False},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(FeedbackResponse.query.one().moderation_status, "Pending")

    def test_buddy_overlap_is_rejected(self):
        buddy = User(username="buddy", email="buddy@example.com", role="Buddy", preferred_role="Buddy", status="Approved", needs_password_reset=False)
        student_one = User(username="student1", email="student1@example.com", role="Exchange Student", preferred_role="Exchange Student", status="Approved", needs_password_reset=False)
        student_two = User(username="student2", email="student2@example.com", role="Exchange Student", preferred_role="Exchange Student", status="Approved", needs_password_reset=False)
        for account in (buddy, student_one, student_two):
            account.set_password("A-secure-test-password-2026")
        db.session.add_all([buddy, student_one, student_two])
        db.session.flush()
        db.session.add(BuddyAssignment(project_id=self.igp_project.id, buddy_user_id=buddy.id, exchange_student_id=student_one.id, start_date=date(2026, 7, 1), end_date=date(2026, 7, 10)))
        db.session.commit()
        with self.assertRaises(ValueError):
            validate_buddy_assignment(self.igp_project, buddy.id, student_two.id, date(2026, 7, 5), date(2026, 7, 12))

    def test_every_new_project_tab_renders(self):
        # See in-the-operation-checklists-crystalline-dongarra.md Step 8:
        # the old single "operations" tab was split into delivery/
        # contributions/finance.
        self.login()
        for tab in ("overview", "people", "delivery", "contributions", "finance", "insights", "resources"):
            response = self.client.get(f"/erp/projects/{self.icc_project.public_id}?tab={tab}")
            self.assertEqual(response.status_code, 200, tab)

    def test_operations_tab_alias_renders_delivery_panel(self):
        self.login()
        response = self.client.get(f"/erp/projects/{self.icc_project.public_id}?tab=operations")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="panel-delivery"', html)
        self.assertIn('class="aurora-tab active"', html)

    def test_saving_task_or_checklist_status_returns_to_delivery_not_overview(self):
        # Pre-existing bug: these three handlers used to redirect to the
        # bare project URL with no `tab`, throwing the user back to
        # Overview after every save.
        task = WorkTask(project_id=self.icc_project.id, title="Book venue", status="Not Started", version=1)
        db.session.add(task)
        db.session.commit()
        self.login()
        response = self.client.post(
            f"/erp/projects/{self.icc_project.public_id}/tasks/{task.public_id}/status",
            data={"version": 1, "status": "In Progress"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=delivery", response.headers["Location"])


class SuppliedImportTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_supplied_sources_stage_idempotently_and_reconcile(self):
        events = stage_supplied_source("events_summary")
        same_events = stage_supplied_source("events_summary")
        self.assertEqual(events.id, same_events.id)
        commit_batch(events)
        coffee = stage_supplied_source("coffee_meet")
        commit_batch(coffee)
        summer = stage_supplied_source("summer_school")
        commit_batch(summer)

        self.assertEqual(events.reconciliation_json["difference"], 0)
        self.assertEqual(coffee.reconciliation_json["difference"], 0)
        self.assertEqual(summer.reconciliation_json["difference"], 0)
        self.assertEqual(coffee.committed_count, 58)
        coffee_project = Project.query.filter_by(code="ICC-2026-CEN-001").one()
        self.assertEqual(ProjectSession.query.filter_by(project_id=coffee_project.id).count(), 9)
        self.assertEqual(coffee_project.actual_reach, 175)
        self.assertIn("approximately 175 guests", coffee_project.closure_summary)
        self.assertEqual(ChecklistTemplateItem.query.count(), 50)
        self.assertEqual(ChecklistItemStatus.query.count(), 50)
        self.assertEqual(ChecklistTemplateItem.query.filter_by(sensitive=True).count(), 1)
        self.assertEqual(ImportBatch.query.count(), 3)


if __name__ == "__main__":
    unittest.main()
