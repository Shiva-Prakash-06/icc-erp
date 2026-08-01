import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.authorization import has_permission


class AuthorizationScopeTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.other_campus = Campus(name="Other", code="OTH")
        self.program_type = ProgramType(name="ICC")
        db.session.add_all([self.year, self.campus, self.other_campus, self.program_type])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-500", campus_id=self.campus.id, program_type_id=self.program_type.id,
            academic_year_id=self.year.id, title="Scoped project", category="Operational", status="Draft",
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        self.other_project = Project(
            code="ICC-2026-OTH-500", campus_id=self.other_campus.id, program_type_id=self.program_type.id,
            academic_year_id=self.year.id, title="Other campus project", category="Operational", status="Draft",
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add_all([self.project, self.other_project])
        db.session.flush()
        self.user = User(username="wing_head", email="wing_head@example.com", role="ICC Events Head", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="ICC_EVENTS_HEAD", project_id=self.project.id, is_active=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_project_scoped_check_respects_scope(self):
        self.assertTrue(has_permission(self.user, "manage_projects", self.project))
        self.assertFalse(has_permission(self.user, "manage_projects", self.other_project))

    def test_project_less_check_does_not_globally_grant_scoped_permission(self):
        # A project-scoped assignment must not satisfy a project-less check for
        # a permission that isn't inherently platform-wide.
        self.assertFalse(has_permission(self.user, "manage_projects"))

    def test_project_less_check_still_grants_genuinely_global_permissions(self):
        # manage_users/manage_governance/manage_imports/audit are platform-wide
        # by nature and should still be reachable without a project, but only
        # for a role that actually holds them (not ICC_EVENTS_HEAD).
        admin = User(username="sysadmin", email="sysadmin@example.com", role="System Administrator", status="Approved", needs_password_reset=False)
        admin.set_password("A-secure-test-password-2026")
        db.session.add(admin)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=admin.id, role_code="SYSTEM_ADMINISTRATOR", is_active=True))
        db.session.commit()
        self.assertTrue(has_permission(admin, "manage_users"))
        self.assertFalse(has_permission(self.user, "manage_users"))


if __name__ == "__main__":
    unittest.main()
