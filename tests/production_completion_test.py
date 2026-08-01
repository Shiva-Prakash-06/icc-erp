import os
import unittest
import io
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from werkzeug.datastructures import FileStorage

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import ChecklistInstance, ChecklistItemStatus, ChecklistTemplate, ChecklistTemplateItem, DocumentRecord, FeedbackForm, FeedbackResponse, OperatingUnit, OperationalRequest, Person, ProjectSession, RoleAssignment, SessionAttendance, TeamAssignment, WorkTask
from app.models.production import (
    Notification,
    NotificationPreference,
    ContributionRecord,
    ProjectRisk,
    RecruitmentApplication,
    ReportDefinition,
    ReportJob,
    SensitiveAccessEvent,
    TaskStatusEvent,
)
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.drive import refresh_document_metadata, validate_drive_link
from app.services.authorization import can_view_project
from app.services.job_auth import verify_internal_job_request
from app.services.lifecycle import closure_blockers
from app.services.imports import _reference_data, commit_batch, stage_uploaded_source
from app.services.notifications import deliver_email, deliver_pending, generate_deadline_notifications, queue_notification
from app.services.operations import change_checklist_status, change_task_status, decide_budget_line, decide_buddy_log, decide_document, decide_recruitment, instantiate_checklist, mark_attendance
from app.models.erp import BudgetLine
from app.models.project import BuddyAssignment, BuddyLog
from app.services.passwords import find_user_for_reset, issue_reset_token, send_reset_email, validate_password
from app.services.reporting import compile_project_snapshot, enqueue_report_job, execute_report_job, render_snapshot


class ProductionCompletionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.program_type = ProgramType(name="ICC")
        self.unit = OperatingUnit(code="ICC", name="International Christite Community")
        db.session.add_all([self.year, self.campus, self.program_type, self.unit])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-999",
            campus_id=self.campus.id,
            program_type_id=self.program_type.id,
            academic_year_id=self.year.id,
            operating_unit_id=self.unit.id,
            title="Production completion test",
            category="Operational",
            status="Draft",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
        )
        self.user = User(username="faculty", email="faculty@example.com", role="Faculty", preferred_role="Faculty", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.flush()
        # A platform-wide (unscoped) assignment, matching what a real
        # OIA Faculty Administrator approval creates.
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True, can_view_sensitive_links=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version

    def test_api_serializes_public_foreign_keys_and_opaque_cursor(self):
        task = WorkTask(project_id=self.project.id, title="Prepare", status="Not Started")
        db.session.add(task)
        db.session.commit()
        self.login()
        response = self.client.get("/api/v1/tasks?limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("project_id", response.json["data"][0])
        self.assertEqual(response.json["data"][0]["project_public_id"], self.project.public_id)

    def test_generic_mutation_requires_current_version(self):
        self.login()
        task = WorkTask(project_id=self.project.id, title="Prepare", status="Not Started")
        db.session.add(task)
        db.session.commit()
        conflict = self.client.patch(f"/api/v1/tasks/{task.public_id}", json={"title": "Changed", "version": 0})
        self.assertEqual(conflict.status_code, 409)
        success = self.client.patch(f"/api/v1/tasks/{task.public_id}", json={"title": "Changed", "version": 1})
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.json["data"]["version"], 2)

    def test_generic_patch_cannot_bypass_waiver_workflow(self):
        self.login()
        task = WorkTask(
            project_id=self.project.id, title="Prepare", status="Not Started",
            mandatory_for_closure=True, version=1,
        )
        db.session.add(task)
        db.session.commit()
        response = self.client.patch(
            f"/api/v1/tasks/{task.public_id}",
            json={"waived": True, "waiver_reason": "sneaky", "mandatory_for_closure": False, "version": 1},
        )
        self.assertEqual(response.status_code, 200)
        db.session.refresh(task)
        self.assertFalse(task.waived)
        self.assertIsNone(task.waiver_reason)
        self.assertTrue(task.mandatory_for_closure)

    def test_attendance_and_checklist_items_require_permission_and_scope(self):
        other_campus = Campus(name="Other", code="OTH")
        db.session.add(other_campus)
        db.session.flush()
        other_project = Project(
            code="ICC-2026-OTH-001",
            campus_id=other_campus.id,
            program_type_id=self.program_type.id,
            academic_year_id=self.year.id,
            operating_unit_id=self.unit.id,
            title="Other campus project",
            category="Operational",
            status="Active",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
        )
        db.session.add(other_project)
        db.session.flush()
        own_session = ProjectSession(project_id=self.project.id, code="S1", title="Own", starts_at=datetime(2026, 8, 1, 9), ends_at=datetime(2026, 8, 1, 10))
        other_session = ProjectSession(project_id=other_project.id, code="S1", title="Other", starts_at=datetime(2026, 8, 1, 9), ends_at=datetime(2026, 8, 1, 10))
        db.session.add_all([own_session, other_session])
        db.session.flush()
        person = Person(first_name="Someone", primary_email="someone@example.com", person_type="Student")
        db.session.add(person)
        db.session.flush()
        own_attendance = SessionAttendance(session_id=own_session.id, person_id=person.id, status="Present")
        other_attendance = SessionAttendance(session_id=other_session.id, person_id=person.id, status="Present")
        db.session.add_all([own_attendance, other_attendance])
        db.session.commit()

        # A user with no visibility into either project must see nothing leaked.
        unprivileged = User(username="volunteer", email="volunteer@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        unprivileged.set_password("A-secure-test-password-2026")
        db.session.add(unprivileged)
        db.session.commit()
        with self.client.session_transaction() as session:
            session["user_id"] = unprivileged.id
            session["session_version"] = unprivileged.session_version
        response = self.client.get("/api/v1/attendance")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"], [])

        # A user scoped only to `self.project` must not see the other project's
        # attendance rows, even though they hold `manage_projects`.
        scoped = User(username="scoped_head", email="scoped_head@example.com", role="ICC Events Head", status="Approved", needs_password_reset=False)
        scoped.set_password("A-secure-test-password-2026")
        db.session.add(scoped)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=scoped.id, role_code="ICC_EVENTS_HEAD", project_id=self.project.id, is_active=True))
        db.session.commit()
        with self.client.session_transaction() as session:
            session["user_id"] = scoped.id
            session["session_version"] = scoped.session_version
        response = self.client.get("/api/v1/attendance")
        self.assertEqual(response.status_code, 200)
        returned_ids = {row["public_id"] for row in response.json["data"]}
        self.assertIn(own_attendance.public_id, returned_ids)
        self.assertNotIn(other_attendance.public_id, returned_ids)

    def test_task_decisions_create_immutable_history_and_redacted_notification(self):
        owner = Person(first_name="Owner", primary_email="owner@example.com", person_type="Student")
        owner_user = User(username="owner", email="owner@example.com", role="Volunteer", status="Approved", needs_password_reset=False, person=owner)
        owner_user.set_password("A-secure-owner-password-2026")
        task = WorkTask(project_id=self.project.id, title="Share visa Drive link", status="Submitted", owner_person_id=None, version=1)
        db.session.add_all([owner, owner_user, task])
        db.session.flush()
        task.owner_person_id = owner.id
        db.session.commit()
        change_task_status(task, "Rejected", self.user, expected_version=1, comment="Replace https://drive.google.com/file/d/secret/view")
        self.assertEqual(TaskStatusEvent.query.count(), 1)
        notification = Notification.query.one()
        self.assertNotIn("drive.google.com", notification.body)
        self.assertIn("restricted operational reference", notification.body)

    def test_recruitment_selection_is_program_specific_and_idempotent(self):
        person = Person(first_name="Applicant", primary_email="applicant@example.com")
        application = RecruitmentApplication(person_id=0, project_id=self.project.id, desired_role="Volunteer")
        db.session.add(person)
        db.session.flush()
        application.person_id = person.id
        db.session.add(application)
        db.session.commit()
        decide_recruitment(application, "Selected", self.user, expected_version=1)
        decide_recruitment(application, "Selected", self.user, expected_version=2)
        self.assertEqual(len(person.team_assignments), 1)

    def test_attendance_correction_requires_reason_and_records_history(self):
        person = Person(first_name="Participant")
        session = ProjectSession(project_id=self.project.id, code="MAIN", title="Main", starts_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc), ends_at=datetime(2026, 8, 1, 10, tzinfo=timezone.utc))
        db.session.add_all([person, session])
        db.session.commit()
        record = mark_attendance(session, person, "Present", self.user)
        with self.assertRaises(ValueError):
            mark_attendance(session, person, "Absent", self.user, expected_version=record.version)
        mark_attendance(session, person, "Absent", self.user, expected_version=record.version, reason="Corrected from signed roster")
        self.assertEqual(record.version, 2)
        self.assertEqual(len(record.__class__.query.all()), 1)

    def test_attendance_batch_is_idempotent(self):
        person = Person(first_name="Participant")
        session = ProjectSession(project_id=self.project.id, code="MAIN", title="Main", starts_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc), ends_at=datetime(2026, 8, 1, 10, tzinfo=timezone.utc))
        db.session.add_all([person, session])
        db.session.commit()
        self.login()
        payload = {"session_public_id": session.public_id, "records": [{"person_public_id": person.public_id, "status": "Present"}]}
        first = self.client.post("/api/v1/attendance/batch", json=payload, headers={"Idempotency-Key": "attendance-test-1"})
        second = self.client.post("/api/v1/attendance/batch", json=payload, headers={"Idempotency-Key": "attendance-test-1"})
        self.assertEqual(first.status_code, 201)
        self.assertTrue(second.json["data"]["replayed"])
        self.assertEqual(SessionAttendance.query.count(), 1)

    def test_notification_preferences_do_not_disable_critical_alerts(self):
        db.session.add(NotificationPreference(user_id=self.user.id, event_type="security", email_enabled=False, in_app_enabled=False))
        db.session.commit()
        notification, inserted = queue_notification(user=self.user, event_type="security", title="Security alert", body="Account changed", idempotency_key="security-1", critical=True)
        db.session.commit()
        self.assertTrue(inserted)
        self.assertIsNotNone(notification)

    def test_deadline_job_is_idempotent_and_expires_documents(self):
        person = Person(first_name="Owner", primary_email="deadline@example.com")
        user = User(username="deadline", email="deadline@example.com", role="Volunteer", status="Approved", needs_password_reset=False, person=person)
        user.set_password("A-secure-deadline-password")
        task = WorkTask(project_id=self.project.id, title="Deadline", owner_person_id=None, due_at=datetime.now(timezone.utc) + timedelta(hours=1))
        document = DocumentRecord(project_id=self.project.id, title="Expired", category="Evidence", status="Approved", expires_on=date.today() - timedelta(days=1))
        db.session.add_all([person, user, task, document])
        db.session.flush()
        task.owner_person_id = person.id
        db.session.commit()
        first = generate_deadline_notifications()
        second = generate_deadline_notifications()
        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(document.status, "Expired")

    def test_report_job_generates_reproducible_snapshot(self):
        definition = ReportDefinition(code="PROJECT_OPERATIONAL", name="Project operational", report_type="Project Operational Report", version=1)
        db.session.add(definition)
        db.session.flush()
        job = ReportJob(definition_id=definition.id, project_id=self.project.id, requested_by_id=self.user.id, idempotency_key="report-1")
        db.session.add(job)
        db.session.commit()
        execute_report_job(job)
        self.assertEqual(job.status, "Completed")
        self.assertEqual(job.snapshot.snapshot_json["project"]["code"], self.project.code)

    def test_critical_risk_blocks_project_closure(self):
        self.project.closure_summary = "Complete narrative"
        risk = ProjectRisk(project_id=self.project.id, title="Unresolved safety concern", is_critical=True, status="Open")
        db.session.add(risk)
        db.session.commit()
        self.assertIn("Risk", {item.kind for item in closure_blockers(self.project)})

    def test_drive_validation_rejects_non_google_and_mock_preserves_classification(self):
        self.assertFalse(validate_drive_link("https://example.com/file")["valid"])
        result = validate_drive_link("https://drive.google.com/file/d/abc123/view", "Restricted")
        self.assertTrue(result["valid"])
        self.assertEqual(result["mode"], "mock")

    def test_offline_snapshot_excludes_people_documents_and_drive_references(self):
        session = ProjectSession(project_id=self.project.id, code="MAIN", title="Main", starts_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc), ends_at=datetime(2026, 8, 1, 10, tzinfo=timezone.utc))
        document = DocumentRecord(project_id=self.project.id, title="Restricted", category="Sensitive", permission_classification="Restricted", drive_url="https://drive.google.com/file/d/secret/view")
        db.session.add_all([session, document])
        db.session.commit()
        self.login()
        response = self.client.get("/api/v1/offline-snapshot")
        serialized = str(response.json)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("drive.google.com", serialized)
        self.assertNotIn("people", response.json["data"])

    def test_reset_tokens_expire_and_session_version_rotates(self):
        token = issue_reset_token(self.user)
        self.assertEqual(find_user_for_reset(token).id, self.user.id)
        self.user.password_reset_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        self.assertIsNone(find_user_for_reset(token))

    def test_password_policy_checks_common_and_breached_passwords(self):
        with self.assertRaises(ValueError):
            validate_password("short")
        with self.assertRaises(ValueError):
            validate_password("password123")
        self.app.config["BREACHED_PASSWORD_CHECK_MODE"] = "live"
        breached = MagicMock()
        breached.text = ""  # padded response with no matching suffix
        breached.raise_for_status.return_value = None
        with patch("app.services.passwords.requests.get", return_value=breached) as request_get:
            self.assertTrue(validate_password("A-unique-policy-password-2026"))
            request_get.assert_called_once()

    def test_reset_email_disabled_and_smtp_delivery(self):
        self.assertFalse(send_reset_email(self.user, "https://erp.example/reset/token"))
        self.app.config.update(NOTIFICATION_EMAIL_MODE="smtp", SMTP_FROM_ADDRESS="erp@example.org", SMTP_HOST="smtp.example.org", SMTP_PORT=587, SMTP_USE_TLS=True, SMTP_USERNAME="mailer", SMTP_PASSWORD="secret")
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        with patch("app.services.passwords.smtplib.SMTP", return_value=smtp):
            self.assertTrue(send_reset_email(self.user, "https://erp.example/reset/token"))
            smtp.starttls.assert_called_once()
            smtp.login.assert_called_once()
            smtp.send_message.assert_called_once()

    def test_forgot_password_persists_token_and_readiness_checks_database(self):
        with patch("app.blueprints.auth.send_reset_email", return_value=True):
            response = self.client.post("/forgot-password", data={"identifier": self.user.email})
        self.assertEqual(response.status_code, 302)
        db.session.expire_all()
        persisted = db.session.get(User, self.user.id)
        self.assertIsNotNone(persisted.password_reset_token_hash)
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/readyz").status_code, 200)

    def test_live_drive_metadata_and_restricted_visibility_policy(self):
        self.app.config["DRIVE_VALIDATION_MODE"] = "live"
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = {
            "id": "abc123", "name": "Evidence", "mimeType": "application/pdf",
            "modifiedTime": "2026-07-16T10:00:00Z", "trashed": False,
            "permissions": [{"type": "user", "role": "reader"}],
        }
        with patch("app.services.drive._credentials", return_value=MagicMock()), patch("app.services.drive.build", return_value=service):
            result = validate_drive_link("https://drive.google.com/file/d/abc123/view", "Restricted")
            self.assertTrue(result["valid"])
            document = DocumentRecord(project_id=self.project.id, title="Evidence", category="Report", drive_url="https://drive.google.com/file/d/abc123/view", permission_classification="Restricted")
            db.session.add(document)
            db.session.flush()
            refresh_document_metadata(document)
            self.assertEqual(document.drive_validation_status, "Valid")
            self.assertEqual(document.drive_visibility, "Restricted")
        service.files.return_value.get.return_value.execute.return_value["permissions"] = [{"type": "anyone", "role": "reader"}]
        with patch("app.services.drive._credentials", return_value=MagicMock()), patch("app.services.drive.build", return_value=service):
            self.assertFalse(validate_drive_link("https://drive.google.com/file/d/abc123/view", "Restricted")["valid"])

    def test_restricted_html_document_open_is_permission_checked_and_audited(self):
        document = DocumentRecord(
            project_id=self.project.id,
            title="Restricted evidence",
            category="Sensitive",
            permission_classification="Restricted",
            drive_url="https://drive.google.com/file/d/restricted/view",
        )
        db.session.add(document)
        db.session.commit()
        self.login()
        response = self.client.get(f"/erp/documents/{document.public_id}/open")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("https://drive.google.com/"))
        self.assertEqual(SensitiveAccessEvent.query.filter_by(entity_public_id=document.public_id).count(), 1)

    def test_instantiate_checklist_creates_one_item_status_per_template_item(self):
        template = ChecklistTemplate(code="WIZARD", name="Wizard template", project_type="ICC event")
        db.session.add(template)
        db.session.flush()
        item_a = ChecklistTemplateItem(template_id=template.id, code="A", title="First", sequence=1)
        item_b = ChecklistTemplateItem(template_id=template.id, code="B", title="Second", sequence=2)
        db.session.add_all([item_a, item_b])
        db.session.commit()

        instance = instantiate_checklist(self.project, template, actor=self.user)
        self.assertEqual(ChecklistItemStatus.query.filter_by(checklist_instance_id=instance.id).count(), 2)

        # Idempotent: calling again for the same project+template is a no-op.
        again = instantiate_checklist(self.project, template, actor=self.user)
        self.assertEqual(again.id, instance.id)
        self.assertEqual(ChecklistItemStatus.query.filter_by(checklist_instance_id=instance.id).count(), 2)

    def test_decide_budget_line_enforces_transitions_and_reasons(self):
        line = BudgetLine(project_id=self.project.id, category="Venue", description="Hall rental", estimated_amount=1000, status="Draft", version=1)
        db.session.add(line)
        db.session.commit()
        with self.assertRaises(ValueError):
            decide_budget_line(line, "Approved", self.user, expected_version=1)
        decide_budget_line(line, "Submitted", self.user, expected_version=1)
        with self.assertRaises(ValueError):
            decide_budget_line(line, "Rejected", self.user, expected_version=2)
        decide_budget_line(line, "Approved", self.user, expected_version=2)
        self.assertEqual(line.status, "Approved")
        self.assertEqual(line.approved_amount, line.estimated_amount)
        self.assertEqual(line.version, 3)

    def test_decide_buddy_log_requires_reason_on_rejection(self):
        buddy = User(username="buddy2", email="buddy2@example.com", role="Buddy", status="Approved", needs_password_reset=False)
        student = User(username="student3", email="student3@example.com", role="Exchange Student", status="Approved", needs_password_reset=False)
        buddy.set_password("A-secure-test-password-2026")
        student.set_password("A-secure-test-password-2026")
        db.session.add_all([buddy, student])
        db.session.flush()
        assignment = BuddyAssignment(project_id=self.project.id, buddy_user_id=buddy.id, exchange_student_id=student.id, start_date=date(2026, 8, 1), end_date=date(2026, 8, 10))
        db.session.add(assignment)
        db.session.flush()
        log = BuddyLog(buddy_assignment_id=assignment.id, activity_date=date(2026, 8, 2), description="Coffee chat", status="Pending", version=1)
        db.session.add(log)
        db.session.commit()
        with self.assertRaises(ValueError):
            decide_buddy_log(log, "Rejected", self.user, expected_version=1)
        decide_buddy_log(log, "Approved", self.user, expected_version=1)
        self.assertEqual(log.status, "Approved")
        self.assertEqual(log.verified_by_id, self.user.id)
        self.assertEqual(log.version, 2)

    def test_checklist_and_document_decision_rules(self):
        template = ChecklistTemplate(code="TEST", name="Test", project_type="ICC event")
        db.session.add(template)
        db.session.flush()
        template_item = ChecklistTemplateItem(template_id=template.id, code="ONE", title="Requirement")
        instance = ChecklistInstance(project_id=self.project.id, template_id=template.id, name="Test")
        db.session.add_all([template_item, instance])
        db.session.flush()
        status = ChecklistItemStatus(checklist_instance_id=instance.id, template_item_id=template_item.id)
        document = DocumentRecord(project_id=self.project.id, title="Final report", category="Report", version=1)
        db.session.add_all([status, document])
        db.session.commit()
        with self.assertRaises(ValueError):
            change_checklist_status(status, "Rejected", self.user, expected_version=1)
        change_checklist_status(status, "Waived", self.user, expected_version=1, comment="Faculty exception", waive=True)
        self.assertTrue(status.waived)
        with self.assertRaises(ValueError):
            decide_document(document, "Rejected", self.user, expected_version=1)
        decide_document(document, "Approved", self.user, expected_version=1)
        self.assertEqual(document.status, "Approved")

    def test_notification_delivery_preferences_retry_and_disabled_modes(self):
        notification, _ = queue_notification(user=self.user, event_type="task.status", title="Changed", body="Updated", idempotency_key="delivery-1")
        db.session.commit()
        self.assertEqual(deliver_email(notification), "Disabled")
        db.session.commit()
        notification.delivery_status = "Pending"
        self.app.config.update(NOTIFICATION_EMAIL_MODE="smtp", SMTP_FROM_ADDRESS="erp@example.org", SMTP_HOST="smtp.example.org", SMTP_PORT=587, SMTP_USE_TLS=False, SMTP_USERNAME=None)
        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        with patch("app.services.notifications.smtplib.SMTP", return_value=smtp):
            self.assertEqual(deliver_email(notification), "Delivered")
        db.session.commit()
        notification.delivery_status = "Pending"
        with patch("app.services.notifications.smtplib.SMTP", side_effect=OSError("unavailable")):
            result = deliver_pending()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["retry"], 1)

    def test_internal_job_auth_testing_identity(self):
        with self.app.test_request_context("/internal/jobs/reminders", method="POST"):
            claims = verify_internal_job_request(["scheduler@example.org"])
            self.assertEqual(claims["email"], "test-job@example.invalid")

    def test_retention_job_removes_expired_restricted_references_and_rejected_applications(self):
        person = Person(first_name="Rejected")
        db.session.add(person)
        db.session.flush()
        application = RecruitmentApplication(
            person_id=person.id,
            project_id=self.project.id,
            desired_role="Volunteer",
            decision="Rejected",
            decided_at=datetime.now(timezone.utc) - timedelta(days=3),
        )
        document = DocumentRecord(
            project_id=self.project.id,
            title="Expired reference",
            category="Sensitive",
            permission_classification="Restricted",
            drive_url="https://drive.google.com/file/d/expired/view",
            drive_file_id="expired",
        )
        self.project.archived_at = datetime.now(timezone.utc) - timedelta(days=3)
        db.session.add_all([application, document])
        db.session.commit()
        self.app.config.update(REJECTED_APPLICATION_RETENTION_DAYS=1, OPERATIONAL_RETENTION_DAYS=1, AUDIT_RETENTION_DAYS=2555)
        response = self.client.post("/internal/jobs/retention")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["rejected_applications_removed"], 1)
        self.assertEqual(response.json["restricted_references_removed"], 1)
        self.assertIsNone(document.drive_url)

    def test_standard_people_import_stages_commits_and_replays(self):
        content = b"registration_number,first_name,last_name,email,campus_code,person_type\n1001,Imported,Person,imported@example.com,CEN,Student\n"
        first = stage_uploaded_source("people", FileStorage(stream=io.BytesIO(content), filename="people.csv"), "people-batch-1")
        replay = stage_uploaded_source("people", FileStorage(stream=io.BytesIO(content), filename="people.csv"), "people-batch-1")
        self.assertEqual(first.id, replay.id)
        commit_batch(first, self.user)
        self.assertEqual(first.reconciliation_json["difference"], 0)
        self.assertIsNotNone(Person.query.filter_by(registration_number="1001").first())

    def test_all_standard_operational_imports_commit_and_reconcile(self):
        def import_csv(import_type, content):
            batch = stage_uploaded_source(
                import_type,
                FileStorage(stream=io.BytesIO(content.encode()), filename=f"{import_type}.csv"),
                f"{import_type}-batch",
            )
            commit_batch(batch, self.user)
            self.assertEqual(batch.reconciliation_json["difference"], 0)
            return batch

        import_csv(
            "people",
            "registration_number,first_name,last_name,email,phone,campus_code,person_type,nationality\n"
            "2001,Roster,Member,roster@example.com,,CEN,Student,India\n",
        )
        import_csv(
            "icc_roster",
            "registration_number,email,wing_code,role_label,academic_year\n"
            "2001,roster@example.com,EVENTS,Associate,2026-2027\n",
        )
        self.assertEqual(TeamAssignment.query.filter_by(project_id=None).count(), 1)

        import_csv(
            "projects",
            "code,title,campus_code,program_type,academic_year,start_date,end_date,project_type,category,unit_code,wing_code\n"
            "ICC-2026-CEN-100,Imported Event,CEN,ICC,2026-2027,2026-09-01,2026-09-02,ICC event,Event,ICC,EVENTS\n",
        )
        imported_project = Project.query.filter_by(code="ICC-2026-CEN-100").one()
        session = ProjectSession(
            project_id=imported_project.id,
            code="MAIN",
            title="Main session",
            starts_at=datetime(2026, 9, 1, 9, tzinfo=timezone.utc),
            ends_at=datetime(2026, 9, 1, 10, tzinfo=timezone.utc),
        )
        db.session.add(session)
        db.session.commit()

        import_csv(
            "participants",
            "project_code,registration_number,email,participant_type\n"
            "ICC-2026-CEN-100,2001,roster@example.com,Volunteer\n",
        )
        import_csv(
            "attendance",
            "project_code,session_code,registration_number,email,status\n"
            "ICC-2026-CEN-100,MAIN,2001,roster@example.com,Present\n",
        )
        import_csv(
            "checklists",
            "project_code,template_code,item_code,title,category,mandatory,owner\n"
            "ICC-2026-CEN-100,ICC-EVENT,CLOSE,Closure report,Closure,yes,Events Head\n",
        )
        import_csv(
            "documents",
            "project_code,title,category,status,drive_url,classification,mandatory_for_closure\n"
            "ICC-2026-CEN-100,Final report,Report,Missing,,Internal,yes\n",
        )
        self.assertEqual(SessionAttendance.query.count(), 1)
        self.assertEqual(ChecklistItemStatus.query.count(), 1)
        self.assertEqual(DocumentRecord.query.filter_by(project_id=imported_project.id).count(), 1)

    def test_compile_project_snapshot_rollup_across_multiple_projects(self):
        second_project = Project(
            code="ICC-2026-CEN-998", campus_id=self.campus.id, program_type_id=self.program_type.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Second project",
            category="Operational", status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
            expected_reach=50, actual_reach=40,
        )
        db.session.add(second_project)
        db.session.flush()
        self.project.expected_reach = 100
        self.project.actual_reach = 90
        db.session.add(WorkTask(project_id=self.project.id, title="A", status="Not Started"))
        db.session.add(WorkTask(project_id=second_project.id, title="B", status="Not Started"))
        db.session.commit()

        with self.assertRaises(ValueError):
            compile_project_snapshot()
        with self.assertRaises(ValueError):
            compile_project_snapshot(self.project, projects=[self.project, second_project])

        scope_filters = {"campus_public_id": self.campus.public_id}
        snapshot = compile_project_snapshot(
            projects=[self.project, second_project], actor=self.user,
            report_type="Campus Rollup Report", filters=scope_filters,
        )
        db.session.commit()
        self.assertIsNone(snapshot.project_id)
        self.assertEqual(set(snapshot.source_references), {self.project.public_id, second_project.public_id})
        self.assertEqual(snapshot.snapshot_json["reach"]["expected"], 150)
        self.assertEqual(snapshot.snapshot_json["reach"]["actual"], 130)
        self.assertEqual(snapshot.snapshot_json["execution"]["tasks"], 2)
        self.assertEqual(len(snapshot.snapshot_json["projects"]), 2)
        self.assertEqual(snapshot.version, 1)

        # Re-compiling the same scope (same filters) bumps the version; a
        # differently-scoped rollup gets its own independent version series.
        again = compile_project_snapshot(
            projects=[self.project, second_project], actor=self.user,
            report_type="Campus Rollup Report", filters=scope_filters,
        )
        db.session.commit()
        self.assertEqual(again.version, 2)
        other_scope = compile_project_snapshot(
            projects=[self.project], actor=self.user,
            report_type="Campus Rollup Report", filters={"campus_public_id": "different-campus"},
        )
        db.session.commit()
        self.assertEqual(other_scope.version, 1)

        output, mime_type = render_snapshot(snapshot, "xlsx")
        self.assertTrue(output.read(4).startswith(b"PK"))

    def test_report_snapshots_render_to_all_supported_formats_and_enqueue(self):
        snapshot = compile_project_snapshot(self.project, actor=self.user)
        db.session.commit()
        formats = (
            ("xlsx", b"PK", "spreadsheet"),
            ("docx", b"PK", "wordprocessingml"),
            ("pdf", b"%PDF", "pdf"),
        )
        for output_format, signature, mime_fragment in formats:
            output, mime_type = render_snapshot(snapshot, output_format)
            self.assertTrue(output.read(4).startswith(signature))
            self.assertIn(mime_fragment, mime_type)
        with self.assertRaises(ValueError):
            render_snapshot(snapshot, "html")

        definition = ReportDefinition(code="ENQUEUE", name="Enqueue", report_type="Project Operational Report", version=1)
        db.session.add(definition)
        db.session.flush()
        job = ReportJob(definition_id=definition.id, project_id=self.project.id, requested_by_id=self.user.id, idempotency_key="enqueue-1")
        db.session.add(job)
        db.session.commit()
        self.app.config.update(
            APP_ENV="production",
            GCP_PROJECT_ID="test-project",
            GCP_REGION="asia-south1",
            CLOUD_TASKS_QUEUE="erp-jobs",
            INTERNAL_JOB_BASE_URL="https://erp.example.org",
            TASKS_SERVICE_ACCOUNT="tasks@example.org",
            INTERNAL_JOB_AUDIENCE="https://erp.example.org",
        )
        client = MagicMock()
        client.queue_path.return_value = "projects/test/locations/asia-south1/queues/erp-jobs"
        with patch("app.services.reporting.tasks_v2.CloudTasksClient", return_value=client):
            enqueue_report_job(job)
        client.create_task.assert_called_once()

    def test_api_workflow_decisions_and_boolean_parsing(self):
        task = WorkTask(project_id=self.project.id, title="API task", status="Not Started")
        template = ChecklistTemplate(code="API", name="API", project_type="Operational")
        person = Person(first_name="Contributor")
        db.session.add_all([task, template, person])
        db.session.flush()
        template_item = ChecklistTemplateItem(template_id=template.id, code="ONE", title="API item")
        checklist = ChecklistInstance(project_id=self.project.id, template_id=template.id, name="API checklist")
        contribution = ContributionRecord(project_id=self.project.id, person_id=person.id, activity_type="Event", description="Supported delivery", duration_hours=2)
        operational_request = OperationalRequest(project_id=self.project.id, request_type="Vehicle", title="Airport vehicle")
        feedback_form = FeedbackForm(project_id=self.project.id, title="Experience", is_open=True, public_token="api-feedback")
        db.session.add_all([template_item, checklist, contribution, operational_request, feedback_form])
        db.session.flush()
        checklist_status = ChecklistItemStatus(checklist_instance_id=checklist.id, template_item_id=template_item.id)
        feedback_response = FeedbackResponse(form_id=feedback_form.id, answers_json={"experience": "Good"})
        db.session.add_all([checklist_status, feedback_response])
        db.session.commit()
        self.login()

        response = self.client.post(f"/api/v1/tasks/{task.public_id}/status", json={"status": "In Progress", "version": 1})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/v1/checklist-items/{checklist_status.public_id}/status", json={"status": "Submitted", "version": 1})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/v1/contributions/{contribution.public_id}/decision", json={"status": "Approved", "version": 1})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/v1/operational-requests/{operational_request.public_id}/transition", json={"status": "Submitted", "version": 1})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/v1/operational-requests/{operational_request.public_id}/transition", json={"status": "Approved", "version": 2, "official_reference": "FIN-2026-1"})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/v1/feedback-responses/{feedback_response.public_id}/moderate", json={"status": "Approved"})
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/api/v1/risks",
            json={"project_public_id": self.project.public_id, "title": "Parsed boolean", "is_critical": "false"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json["data"]["is_critical"])

    def test_buddy_api_enforces_igp_and_overlap_rules(self):
        igp_type = ProgramType(name="IGP")
        igp_unit = OperatingUnit(code="IGP", name="India Gateway Program")
        buddy = User(username="buddy-api", email="buddy-api@example.com", role="Buddy", status="Approved", needs_password_reset=False)
        student = User(username="student-api", email="student-api@example.com", role="Exchange Student", status="Approved", needs_password_reset=False)
        buddy.set_password("A-secure-buddy-api-password")
        student.set_password("A-secure-student-api-password")
        db.session.add_all([igp_type, igp_unit, buddy, student])
        db.session.flush()
        project = Project(
            code="IGP-2026-CEN-200",
            campus_id=self.campus.id,
            program_type_id=igp_type.id,
            academic_year_id=self.year.id,
            operating_unit_id=igp_unit.id,
            title="IGP API",
            category="Immersion",
            status="Draft",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 10),
        )
        db.session.add(project)
        db.session.commit()
        self.login()
        payload = {
            "project_public_id": project.public_id,
            "buddy_user_public_id": buddy.public_id,
            "exchange_student_public_id": student.public_id,
            "start_date": "2026-10-01",
            "end_date": "2026-10-10",
        }
        first = self.client.post("/api/v1/buddy-assignments", json=payload)
        second = self.client.post("/api/v1/buddy-assignments", json=payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 422)

    def test_project_form_uses_public_scope_and_api_warns_about_schedule_conflicts(self):
        _reference_data()
        db.session.commit()
        wing = self.unit.wings[0]
        self.login()
        self.assertEqual(self.client.get("/erp/projects").status_code, 200)
        self.assertEqual(self.client.get("/admin/users").status_code, 200)
        response = self.client.post(
            "/erp/projects",
            data={
                "title": "Scoped form project",
                "project_type": "ICC event",
                "category": "Event",
                "campus_public_id": self.campus.public_id,
                "program_type_public_id": self.program_type.public_id,
                "academic_year_public_id": self.year.public_id,
                "wing_public_id": wing.public_id,
                "start_date": "2026-11-01",
                "end_date": "2026-11-01",
            },
        )
        self.assertEqual(response.status_code, 302)
        project = Project.query.filter_by(title="Scoped form project").one()
        self.assertEqual(project.operating_unit_id, self.unit.id)
        self.assertEqual(project.wing_id, wing.id)
        self.assertTrue(project.code.startswith("ICC-2026-CEN-"))

        base = {
            "project_public_id": project.public_id,
            "title": "First session",
            "code": "FIRST",
            "starts_at": "2026-11-01T09:00:00+05:30",
            "ends_at": "2026-11-01T10:00:00+05:30",
            "venue": "Block IV Auditorium",
        }
        first = self.client.post("/api/v1/sessions", json=base)
        second = self.client.post("/api/v1/sessions", json={**base, "title": "Second session", "code": "SECOND"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertIn("warnings", second.json)

    def test_participant_membership_grants_project_and_personal_profile_access(self):
        person = Person(first_name="Exchange", last_name="Student", registration_number="EX-1", primary_email="exchange@example.com")
        participant = User(username="exchange", email="exchange@example.com", role="Participant / Exchange Student", status="Approved", needs_password_reset=False, person=person)
        participant.set_password("A-secure-exchange-password-2026")
        db.session.add_all([person, participant])
        db.session.flush()
        db.session.add(TeamAssignment(project_id=self.project.id, person_id=person.id, assignment_type="Exchange Program", role_label="Exchange Student"))
        db.session.commit()
        self.assertTrue(can_view_project(participant, self.project))
        with self.client.session_transaction() as session:
            session["user_id"] = participant.id
            session["session_version"] = participant.session_version
        self.assertEqual(self.client.get(f"/api/v1/projects/{self.project.public_id}").status_code, 200)
        profile = self.client.get("/api/v1/me")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json["data"]["person"]["registration_number"], "EX-1")


class ErpTabRoutesTestCase(unittest.TestCase):
    """End-to-end coverage for the U2 project_detail tab rebuild: the new
    People/Operations/Insights/Resources forms and decision routes."""

    def setUp(self):
        self.app = create_app()
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc = ProgramType(name="ICC")
        self.igp = ProgramType(name="IGP")
        self.unit = OperatingUnit(code="ICC", name="ICC")
        db.session.add_all([self.year, self.campus, self.icc, self.igp, self.unit])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-001", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Tab test project",
            category="Operational", status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()
        self.person = Person(first_name="Roster", primary_email="roster@example.com", registration_number="REG-1", person_type="Student")
        db.session.add(self.person)
        db.session.flush()
        self.user = User(username="faculty2", email="faculty2@example.com", role="Faculty", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True, can_view_sensitive_links=True))
        db.session.commit()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_team_enroll_route(self):
        response = self.client.post(f"/erp/projects/{self.project.public_id}/team", data={
            "registration_number": "REG-1", "assignment_type": "Project Team", "role_label": "Volunteer",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeamAssignment.query.filter_by(project_id=self.project.id, person_id=self.person.id).count(), 1)

    def _login_as_volunteer(self):
        volunteer = User(username="volunteer2", email="volunteer2@example.com", role="Volunteer", status="Approved", needs_password_reset=False, person_id=self.person.id)
        volunteer.set_password("A-secure-test-password-2026")
        db.session.add(volunteer)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=volunteer.id, role_code="VOLUNTEER", project_id=self.project.id, is_active=True))
        if not TeamAssignment.query.filter_by(person_id=self.person.id, project_id=self.project.id).first():
            db.session.add(TeamAssignment(person_id=self.person.id, project_id=self.project.id, assignment_type="Project Team"))
        db.session.commit()
        with self.client.session_transaction() as session:
            session["user_id"] = volunteer.id
            session["session_version"] = volunteer.session_version
        return volunteer

    def test_contribution_log_and_decision_routes(self):
        self._login_as_volunteer()
        response = self.client.post(f"/erp/projects/{self.project.public_id}/contributions", data={
            "activity_type": "Event support", "description": "Helped set up", "duration_hours": "2",
        })
        self.assertEqual(response.status_code, 302)
        contribution = ContributionRecord.query.filter_by(project_id=self.project.id).one()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version
        response = self.client.post(f"/erp/projects/{self.project.public_id}/contributions/{contribution.public_id}/decision", data={
            "version": str(contribution.version), "status": "Approved",
        })
        self.assertEqual(response.status_code, 302)
        db.session.refresh(contribution)
        self.assertEqual(contribution.approval_status, "Approved")

    def test_budget_line_lifecycle_route(self):
        self.client.post(f"/erp/projects/{self.project.public_id}/budgets", data={
            "category": "Venue", "description": "Hall rental", "estimated_amount": "1000",
        })
        line = BudgetLine.query.filter_by(project_id=self.project.id).one()
        self.client.post(f"/erp/projects/{self.project.public_id}/budgets/{line.public_id}/decision", data={
            "version": str(line.version), "status": "Submitted",
        })
        db.session.refresh(line)
        response = self.client.post(f"/erp/projects/{self.project.public_id}/budgets/{line.public_id}/decision", data={
            "version": str(line.version), "status": "Approved",
        })
        self.assertEqual(response.status_code, 302)
        db.session.refresh(line)
        self.assertEqual(line.status, "Approved")

    def test_document_add_and_decision_route(self):
        self.client.post(f"/erp/projects/{self.project.public_id}/documents", data={
            "title": "Final report", "category": "Report", "drive_url": "", "permission_classification": "Internal",
        })
        document = DocumentRecord.query.filter_by(project_id=self.project.id, title="Final report").one()
        self.assertEqual(document.status, "Submitted")
        response = self.client.post(f"/erp/projects/{self.project.public_id}/documents/{document.public_id}/decision", data={
            "version": str(document.version), "status": "Approved",
        })
        self.assertEqual(response.status_code, 302)
        db.session.refresh(document)
        self.assertEqual(document.status, "Approved")

    def test_feedback_form_open_and_submit_and_moderate_routes(self):
        self.user.person_id = self.person.id
        db.session.commit()
        self.client.post(f"/erp/projects/{self.project.public_id}/feedback-forms", data={"title": "Project Feedback"})
        form = FeedbackForm.query.filter_by(project_id=self.project.id).one()
        self.client.post(f"/erp/projects/{self.project.public_id}/feedback-responses", data={
            "rating": "5", "comments": "Great", "suggestions": "None",
        })
        response_row = FeedbackResponse.query.filter_by(form_id=form.id).one()
        self.assertEqual(response_row.answers_json["rating"], "5")
        moderate = self.client.post(f"/erp/projects/{self.project.public_id}/feedback-responses/{response_row.public_id}/moderate", data={"status": "Approved"})
        self.assertEqual(moderate.status_code, 302)
        db.session.refresh(response_row)
        self.assertEqual(response_row.moderation_status, "Approved")

    def test_igp_buddy_pairing_and_interaction_log_routes(self):
        self.project.program_type_id = self.igp.id
        buddy_person = Person(first_name="Buddy", primary_email="buddyp@example.com", registration_number="REG-BUDDY", person_type="Student")
        student_person = Person(first_name="Student", primary_email="studentp@example.com", registration_number="REG-STUDENT", person_type="Student")
        db.session.add_all([buddy_person, student_person])
        db.session.commit()
        response = self.client.post(f"/erp/projects/{self.project.public_id}/buddy-assignments", data={
            "buddy_registration_number": "REG-BUDDY", "exchange_student_registration_number": "REG-STUDENT",
            "start_date": "2026-08-01", "end_date": "2026-08-10",
        })
        self.assertEqual(response.status_code, 302)
        assignment = BuddyAssignment.query.filter_by(project_id=self.project.id).one()
        self.assertEqual(assignment.buddy_person_id, buddy_person.id)
        self.assertEqual(assignment.exchange_student_person_id, student_person.id)

        self._login_as_volunteer()
        log_response = self.client.post(f"/erp/projects/{self.project.public_id}/buddy-assignments/{assignment.public_id}/logs", data={
            "activity_date": "2026-08-02", "description": "Coffee chat", "duration_hours": "1",
        })
        self.assertEqual(log_response.status_code, 302)
        log = BuddyLog.query.filter_by(buddy_assignment_id=assignment.id).one()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version
        decide_response = self.client.post(f"/erp/projects/{self.project.public_id}/buddy-logs/{log.public_id}/decision", data={
            "version": str(log.version), "status": "Approved",
        })
        self.assertEqual(decide_response.status_code, 302)
        db.session.refresh(log)
        self.assertEqual(log.status, "Approved")

    def test_oversight_dashboard_gated_and_shows_pending_items(self):
        task = WorkTask(project_id=self.project.id, title="Needs approval", status="Submitted", version=1)
        db.session.add(task)
        db.session.commit()

        volunteer = User(username="volunteer3", email="volunteer3@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        volunteer.set_password("A-secure-test-password-2026")
        db.session.add(volunteer)
        db.session.commit()
        with self.client.session_transaction() as session:
            session["user_id"] = volunteer.id
            session["session_version"] = volunteer.session_version
        self.assertEqual(self.client.get("/erp/oversight").status_code, 403)

        with self.client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version
        response = self.client.get("/erp/oversight")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Needs approval", response.data)

    def test_project_setup_wizard_walks_through_steps_and_completes(self):
        # A brand-new project (no sessions/team/checklist/documents/budget
        # yet) should land on the "sessions" step first.
        response = self.client.get(f"/erp/projects/{self.project.public_id}/setup")
        self.assertEqual(response.status_code, 200)

        self.client.post(f"/erp/projects/{self.project.public_id}/sessions", data={
            "next": "setup", "title": "Opening", "starts_at": "2026-08-01T09:00", "ends_at": "2026-08-01T10:00",
        })
        self.assertEqual(ProjectSession.query.filter_by(project_id=self.project.id).count(), 1)
        response = self.client.get(f"/erp/projects/{self.project.public_id}/setup")
        self.assertIn(b"Team", response.data)  # now on the team step

        self.client.post(f"/erp/projects/{self.project.public_id}/team", data={
            "next": "setup", "registration_number": "REG-1", "assignment_type": "Project Team",
        })
        template = ChecklistTemplate(code="WIZ-TEST", name="Wizard checklist", project_type="Operational")
        db.session.add(template)
        db.session.commit()
        self.client.post(f"/erp/projects/{self.project.public_id}/checklists", data={
            "next": "setup", "template_public_id": template.public_id,
        })
        self.client.post(f"/erp/projects/{self.project.public_id}/documents", data={
            "next": "setup", "title": "Schedule", "category": "Schedule", "drive_url": "", "permission_classification": "Internal",
        })
        self.client.post(f"/erp/projects/{self.project.public_id}/budgets", data={
            "next": "setup", "category": "Venue", "description": "Hall", "estimated_amount": "200",
        })

        # Every step is now complete -- the wizard should redirect to the
        # full project page instead of showing another step.
        response = self.client.get(f"/erp/projects/{self.project.public_id}/setup", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/erp/projects/{self.project.public_id}", response.location)
        self.assertNotIn("setup", response.location)

    def test_attendance_roll_call_get_and_post(self):
        session_item = ProjectSession(project_id=self.project.id, code="S1", title="Day 1", starts_at=datetime(2026, 8, 1, 9), ends_at=datetime(2026, 8, 1, 10))
        db.session.add(session_item)
        db.session.add(TeamAssignment(project_id=self.project.id, person_id=self.person.id, assignment_type="Project Team"))
        db.session.commit()
        get_response = self.client.get(f"/erp/projects/{self.project.public_id}/sessions/{session_item.public_id}/attendance")
        self.assertEqual(get_response.status_code, 200)
        post_response = self.client.post(f"/erp/projects/{self.project.public_id}/sessions/{session_item.public_id}/attendance", data={
            f"status_{self.person.id}": "Present",
        })
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(SessionAttendance.query.filter_by(session_id=session_item.id, person_id=self.person.id).one().status, "Present")


if __name__ == "__main__":
    unittest.main()
