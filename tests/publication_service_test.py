import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.publication import decide_project_publication, submit_project_publication


class PublicationServiceTestCase(unittest.TestCase):
    """Unit coverage for the publication state machine itself (as opposed to
    the HTTP-level tests in public_site_test.py), matching PLAN.md's 90%
    target for publication workflows."""

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
            code="ICC-2026-CEN-970", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Publication service project", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()

        def make_user(username, role_code):
            user = User(username=username, email=f"{username}@example.com", role=role_code, status="Approved", needs_password_reset=False)
            user.set_password("A-secure-test-password-2026")
            db.session.add(user)
            db.session.flush()
            db.session.add(RoleAssignment(user_id=user.id, role_code=role_code, is_active=True))
            return user

        self.manager = make_user("manager", "ICC_EVENTS_HEAD")
        self.governance = make_user("governance", "OIA_FACULTY_ADMINISTRATOR")
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_project_defaults_to_private(self):
        self.assertEqual(self.project.publication_status, "Private")

    def test_manager_can_submit_for_publication(self):
        submit_project_publication(self.project, self.manager, expected_version=self.project.version)
        self.assertEqual(self.project.publication_status, "Pending")
        self.assertEqual(self.project.publication_requested_by_id, self.manager.id)

    def test_submit_rejects_stale_version(self):
        with self.assertRaises(ValueError):
            submit_project_publication(self.project, self.manager, expected_version=self.project.version + 1)

    def test_manager_without_manage_projects_cannot_submit(self):
        outsider = User(username="outsider", email="outsider@example.com", role="Volunteer", status="Approved", needs_password_reset=False)
        outsider.set_password("A-secure-test-password-2026")
        db.session.add(outsider)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=outsider.id, role_code="VOLUNTEER", is_active=True))
        db.session.commit()
        with self.assertRaises(PermissionError):
            submit_project_publication(self.project, outsider, expected_version=self.project.version)

    def test_manager_cannot_directly_decide_publication(self):
        submit_project_publication(self.project, self.manager, expected_version=self.project.version)
        with self.assertRaises(PermissionError):
            decide_project_publication(self.project, "Published", self.manager, expected_version=self.project.version)

    def test_requester_cannot_review_own_publication_request(self):
        dual_role = User(username="dual", email="dual@example.com", role="Faculty", status="Approved", needs_password_reset=False)
        dual_role.set_password("A-secure-test-password-2026")
        db.session.add(dual_role)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=dual_role.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True))
        db.session.commit()
        submit_project_publication(self.project, dual_role, expected_version=self.project.version)
        with self.assertRaisesRegex(PermissionError, "cannot review"):
            decide_project_publication(self.project, "Published", dual_role, expected_version=self.project.version)

    def test_governance_can_publish_pending_project(self):
        submit_project_publication(self.project, self.manager, expected_version=self.project.version)
        decide_project_publication(self.project, "Published", self.governance, expected_version=self.project.version)
        self.assertEqual(self.project.publication_status, "Published")
        self.assertIsNotNone(self.project.published_at)
        self.assertEqual(self.project.publication_approved_by_id, self.governance.id)

    def test_cannot_publish_directly_from_private(self):
        with self.assertRaises(ValueError):
            decide_project_publication(self.project, "Published", self.governance, expected_version=self.project.version)

    def test_rejecting_to_private_requires_reason(self):
        submit_project_publication(self.project, self.manager, expected_version=self.project.version)
        with self.assertRaises(ValueError):
            decide_project_publication(self.project, "Private", self.governance, expected_version=self.project.version, reason="")

    def test_rejecting_to_private_with_reason_succeeds(self):
        submit_project_publication(self.project, self.manager, expected_version=self.project.version)
        decide_project_publication(self.project, "Private", self.governance, expected_version=self.project.version, reason="Not ready")
        self.assertEqual(self.project.publication_status, "Private")

    def test_withdraw_requires_reason_and_clears_after_republish(self):
        submit_project_publication(self.project, self.manager, expected_version=self.project.version)
        decide_project_publication(self.project, "Published", self.governance, expected_version=self.project.version)
        with self.assertRaises(ValueError):
            decide_project_publication(self.project, "Withdrawn", self.governance, expected_version=self.project.version, reason="")
        decide_project_publication(self.project, "Withdrawn", self.governance, expected_version=self.project.version, reason="Event cancelled")
        self.assertEqual(self.project.publication_status, "Withdrawn")
        self.assertIsNotNone(self.project.withdrawn_at)


if __name__ == "__main__":
    unittest.main()
