import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import ChecklistInstance, ChecklistItemStatus, ChecklistTemplate, ChecklistTemplateItem, DocumentRecord, RoleAssignment, WorkTask
from app.models.production import ContributionRecord, RecruitmentApplication
from app.models.erp import OperationalRequest
from app.models.project import AcademicYear, BuddyAssignment, BuddyLog, Campus, ProgramType, Project
from app.models.user import User
from app.services.action_queue import ACTION_QUEUE_KINDS, build_action_queue


class ActionQueueTestCase(unittest.TestCase):
    """The 10-source decision queue, extracted verbatim out of the old
    erp.oversight view body -- see
    in-the-operation-checklists-crystalline-dongarra.md Step 1. Both the
    merged home's "Awaiting your decision" tile and its full queue must
    agree with this builder, which is the fix for Mission Control's tile
    previously counting only 2 of these 10 kinds."""

    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc = ProgramType(name="ICC")
        db.session.add_all([self.year, self.campus, self.icc])
        db.session.flush()

        self.project = Project(
            code="ICC-2026-CEN-500", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Queue test project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()

        self.approver = User(username="approver", email="approver@example.com", role="Faculty", status="Approved", needs_password_reset=False)
        self.approver.set_password("A-secure-test-password-2026")
        self.op_request_approver = User(username="opreqapprover", email="opreq@example.com", role="ICC Events Head", status="Approved", needs_password_reset=False)
        self.op_request_approver.set_password("A-secure-test-password-2026")
        self.no_permission_user = User(username="volunteer", email="volunteer@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        self.no_permission_user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.approver, self.op_request_approver, self.no_permission_user])
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.approver.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True))
        db.session.add(RoleAssignment(user_id=self.op_request_approver.id, role_code="ICC_EVENTS_HEAD", project_id=self.project.id, is_active=True))
        db.session.commit()

        self._seed_one_pending_item_of_every_kind()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _seed_one_pending_item_of_every_kind(self):
        db.session.add(WorkTask(project_id=self.project.id, title="Pending task", status="Submitted", version=1))

        template = ChecklistTemplate(code="Q", name="Queue checklist", project_type="ICC event")
        db.session.add(template)
        db.session.flush()
        template_item = ChecklistTemplateItem(template_id=template.id, code="ONE", title="Requirement")
        instance = ChecklistInstance(project_id=self.project.id, template_id=template.id, name="Queue checklist")
        db.session.add_all([template_item, instance])
        db.session.flush()
        db.session.add(ChecklistItemStatus(checklist_instance_id=instance.id, template_item_id=template_item.id, status="Submitted", version=1))

        db.session.add(DocumentRecord(project_id=self.project.id, title="Pending doc", category="Report", status="Submitted", version=1))

        db.session.add_all([
            self.project,
        ])
        db.session.flush()

        from app.models.erp import Person
        person = Person(first_name="Queue", last_name="Person")
        db.session.add(person)
        db.session.flush()
        db.session.add(ContributionRecord(project_id=self.project.id, person_id=person.id, activity_type="Event support", description="Help", duration_hours=1, approval_status="Pending", version=1))

        from app.models.erp import OperationalRequest
        db.session.add(OperationalRequest(project_id=self.project.id, request_type="Equipment", title="Pending request", status="Submitted", created_by_id=self.approver.id, version=1))

        from app.models.erp import BudgetLine
        db.session.add(BudgetLine(project_id=self.project.id, category="Travel", description="Pending line", estimated_amount=100, status="Submitted", version=1))

        buddy_user = User(username="buddy1", email="buddy1@example.com", role="Buddy", status="Approved", needs_password_reset=False)
        buddy_user.set_password("A-secure-test-password-2026")
        exchange_student = User(username="student1", email="student1@example.com", role="Exchange Student", status="Approved", needs_password_reset=False)
        exchange_student.set_password("A-secure-test-password-2026")
        db.session.add_all([buddy_user, exchange_student])
        db.session.flush()
        assignment = BuddyAssignment(project_id=self.project.id, buddy_user_id=buddy_user.id, exchange_student_id=exchange_student.id, start_date=date(2026, 8, 1), end_date=date(2026, 8, 2))
        db.session.add(assignment)
        db.session.flush()
        db.session.add(BuddyLog(buddy_assignment_id=assignment.id, activity_date=date(2026, 8, 1), description="Pending log", duration_hours=1, status="Pending", version=1))

        from app.models.erp import FeedbackForm, FeedbackResponse
        form = FeedbackForm(project_id=self.project.id, title="Feedback")
        db.session.add(form)
        db.session.flush()
        db.session.add(FeedbackResponse(form_id=form.id, answers_json={}, moderation_status="Pending"))

        db.session.add(RecruitmentApplication(person_id=person.id, project_id=self.project.id, desired_role="Volunteer", decision="Submitted", version=1))

        from app.models.erp import ReportSnapshot
        db.session.add(ReportSnapshot(project_id=self.project.id, report_type="Event Report", title="Pending report", approval_status="Draft"))

        db.session.commit()

    def test_all_ten_kinds_present_for_an_approver(self):
        queue = build_action_queue(self.approver)
        found_kinds = {item["kind"] for item in queue}
        self.assertEqual(found_kinds, set(ACTION_QUEUE_KINDS))

    def test_operational_request_scoped_separately_from_approve(self):
        # A user can hold "approve" on a project without holding
        # "approve_operational_requests" on it -- IGP_PROGRAM_LEAD is one
        # such role. The Operational request kind must then be absent even
        # though the other nine kinds (scoped only by "approve") are
        # present, proving the two-tier scoping in build_action_queue.
        igp_type = ProgramType(name="IGP")
        db.session.add(igp_type)
        db.session.flush()
        igp_project = Project(
            code="IGP-2026-CEN-500", campus_id=self.campus.id, program_type_id=igp_type.id,
            academic_year_id=self.year.id, title="IGP queue project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(igp_project)
        db.session.flush()
        db.session.add(WorkTask(project_id=igp_project.id, title="IGP pending task", status="Submitted", version=1))
        db.session.add(OperationalRequest(project_id=igp_project.id, request_type="Equipment", title="IGP pending request", status="Submitted", created_by_id=self.op_request_approver.id, version=1))
        db.session.commit()
        db.session.add(RoleAssignment(user_id=self.op_request_approver.id, role_code="IGP_PROGRAM_LEAD", project_id=igp_project.id, is_active=True))
        db.session.commit()

        queue = build_action_queue(self.op_request_approver)
        request_titles = {item["title"] for item in queue if item["kind"] == "Operational request"}
        task_titles = {item["title"] for item in queue if item["kind"] == "Task"}
        self.assertIn("IGP pending task", task_titles)  # approve alone is enough for Task
        self.assertIn("Pending request", request_titles)  # approve_operational_requests on self.project
        self.assertNotIn("IGP pending request", request_titles)  # but not on igp_project

    def test_no_permission_user_sees_empty_queue(self):
        self.assertEqual(build_action_queue(self.no_permission_user), [])

    def test_queue_items_use_new_tab_values(self):
        queue = build_action_queue(self.approver)
        by_kind = {item["kind"]: item["tab"] for item in queue}
        self.assertEqual(by_kind["Task"], "delivery")
        self.assertEqual(by_kind["Checklist"], "delivery")
        self.assertEqual(by_kind["Contribution"], "contributions")
        self.assertEqual(by_kind["Buddy log"], "contributions")
        self.assertEqual(by_kind["Operational request"], "finance")
        self.assertEqual(by_kind["Budget line"], "finance")
        self.assertEqual(by_kind["Document"], "resources")
        self.assertEqual(by_kind["Feedback moderation"], "insights")
        self.assertEqual(by_kind["Report approval"], "insights")
        self.assertEqual(by_kind["Recruitment"], "people")


if __name__ == "__main__":
    unittest.main()
