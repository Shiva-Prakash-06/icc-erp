import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import OperatingUnit, OperationalRequest, Person, RoleAssignment, TeamAssignment, Wing
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.authorization import can_view_project, has_permission
from app.services.operations import decide_operational_request


class AuthorizationScopeTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
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

    def test_unapproved_user_never_has_permission(self):
        self.user.status = "Pending"
        self.assertFalse(has_permission(self.user, "manage_projects", self.project))

    def test_sensitive_check_requires_can_view_sensitive_links(self):
        self.assertFalse(has_permission(self.user, "manage_projects", self.project, sensitive=True))
        assignment = RoleAssignment.query.filter_by(user_id=self.user.id).first()
        assignment.can_view_sensitive_links = True
        db.session.commit()
        self.assertTrue(has_permission(self.user, "manage_projects", self.project, sensitive=True))

    def test_operating_unit_and_wing_scope_are_respected(self):
        unit = OperatingUnit(code="ICC2", name="ICC Unit 2")
        other_unit = OperatingUnit(code="OTHER", name="Other Unit")
        db.session.add_all([unit, other_unit])
        db.session.flush()
        wing = Wing(operating_unit_id=unit.id, code="EVENTS", name="Events")
        db.session.add(wing)
        db.session.flush()
        self.project.operating_unit_id = unit.id
        self.project.wing_id = wing.id
        db.session.commit()

        scoped_user = User(username="wing_scope", email="wing_scope@example.com", role="ICC Events Head", status="Approved", needs_password_reset=False)
        scoped_user.set_password("A-secure-test-password-2026")
        db.session.add(scoped_user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=scoped_user.id, role_code="ICC_EVENTS_HEAD", operating_unit_id=other_unit.id, is_active=True))
        db.session.commit()
        self.assertFalse(has_permission(scoped_user, "manage_projects", self.project))

    def test_can_view_project_falls_back_to_active_team_assignment(self):
        person = Person(first_name="Contributor")
        db.session.add(person)
        db.session.flush()
        contributor = User(username="contributor", email="contributor@example.com", role="Volunteer", status="Approved", needs_password_reset=False, person_id=person.id)
        contributor.set_password("A-secure-test-password-2026")
        db.session.add(contributor)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=contributor.id, role_code="VOLUNTEER", is_active=True))
        self.assertFalse(can_view_project(contributor, self.project))
        db.session.add(TeamAssignment(person_id=person.id, project_id=self.project.id, assignment_type="Project Team", status="Active"))
        db.session.commit()
        self.assertTrue(can_view_project(contributor, self.project))


class OperationalRequestApprovalTestCase(unittest.TestCase):
    """USC, IGP Program Lead, and System Administrator status alone must not
    authorize business approval of operational requests -- PLAN.md "USC
    operational approvals" finding."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.program_type = ProgramType(name="ICC")
        db.session.add_all([self.year, self.campus, self.program_type])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-501", campus_id=self.campus.id, program_type_id=self.program_type.id,
            academic_year_id=self.year.id, title="Approval scoped project", category="Operational", status="Draft",
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()

        def make_user(username, role_code, unscoped=True):
            user = User(username=username, email=f"{username}@example.com", role=role_code, status="Approved", needs_password_reset=False)
            user.set_password("A-secure-test-password-2026")
            db.session.add(user)
            db.session.flush()
            db.session.add(RoleAssignment(
                user_id=user.id, role_code=role_code, is_active=True,
                project_id=None if unscoped else self.project.id,
            ))
            return user

        self.creator = make_user("creator", "OIA_FACULTY_ADMINISTRATOR")
        self.usc = make_user("usc", "ICC_SECRETARY_USC")
        self.igp_lead = make_user("igp_lead", "IGP_PROGRAM_LEAD")
        self.sysadmin = make_user("sysadmin", "SYSTEM_ADMINISTRATOR")
        self.events_head = make_user("events_head", "ICC_EVENTS_HEAD")
        db.session.commit()

        self.request = OperationalRequest(project_id=self.project.id, request_type="Vehicle", title="Airport pickup", created_by_id=self.creator.id)
        db.session.add(self.request)
        db.session.commit()
        decide_operational_request(self.request, "Submitted", self.creator, expected_version=1)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_usc_cannot_approve_operational_request(self):
        with self.assertRaises(PermissionError):
            decide_operational_request(self.request, "Approved", self.usc, expected_version=self.request.version)

    def test_igp_program_lead_cannot_approve_operational_request(self):
        with self.assertRaises(PermissionError):
            decide_operational_request(self.request, "Approved", self.igp_lead, expected_version=self.request.version)

    def test_system_administrator_status_alone_cannot_approve_operational_request(self):
        with self.assertRaises(PermissionError):
            decide_operational_request(self.request, "Approved", self.sysadmin, expected_version=self.request.version)

    def test_creator_cannot_approve_own_request(self):
        with self.assertRaises(PermissionError):
            decide_operational_request(self.request, "Approved", self.creator, expected_version=self.request.version)

    def test_scoped_head_can_approve_operational_request(self):
        decide_operational_request(self.request, "Approved", self.events_head, expected_version=self.request.version)
        self.assertEqual(self.request.status, "Approved")

    def _login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    def test_generic_api_records_maker_and_blocks_creator_approval(self):
        self._login(self.creator)
        response = self.client.post("/api/v1/operational-requests", json={
            "project_public_id": self.project.public_id,
            "request_type": "Vehicle",
            "title": "API-created vehicle",
        })
        self.assertEqual(response.status_code, 201)
        item = OperationalRequest.query.filter_by(title="API-created vehicle").one()
        self.assertEqual(item.created_by_id, self.creator.id)

        self._login(self.usc)
        response = self.client.post(
            f"/api/v1/operational-requests/{item.public_id}/transition",
            json={"status": "Submitted", "version": item.version},
        )
        self.assertEqual(response.status_code, 200)

        self._login(self.creator)
        response = self.client.post(
            f"/api/v1/operational-requests/{item.public_id}/transition",
            json={"status": "Approved", "version": item.version},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(item.status, "Submitted")

    def test_decision_rejects_missing_maker_or_submitter_history(self):
        ambiguous = OperationalRequest(
            project_id=self.project.id,
            request_type="Vehicle",
            title="Ambiguous legacy request",
            status="Submitted",
        )
        db.session.add(ambiguous)
        db.session.commit()
        with self.assertRaisesRegex(ValueError, "incomplete maker/submission history"):
            decide_operational_request(ambiguous, "Approved", self.events_head, expected_version=ambiguous.version)


class PeopleApiScopeTestCase(unittest.TestCase):
    """The generic /api/v1/people collection has no project scoping (Person
    has no project_id), so it must be platform-admin-only; project managers
    get only the narrow, project-scoped search endpoint. See PLAN.md
    "Additional release blockers" finding."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.program_type = ProgramType(name="ICC")
        db.session.add_all([self.year, self.campus, self.program_type])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-600", campus_id=self.campus.id, program_type_id=self.program_type.id,
            academic_year_id=self.year.id, title="People scope project", category="Operational", status="Draft",
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()
        self.manager = User(username="events_head", email="events_head@example.com", role="ICC Events Head", status="Approved", needs_password_reset=False)
        self.manager.set_password("A-secure-test-password-2026")
        self.admin = User(username="sysadmin", email="sysadmin@example.com", role="System Administrator", status="Approved", needs_password_reset=False)
        self.admin.set_password("A-secure-test-password-2026")
        db.session.add_all([self.manager, self.admin])
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.manager.id, role_code="ICC_EVENTS_HEAD", project_id=self.project.id, is_active=True))
        db.session.add(RoleAssignment(user_id=self.admin.id, role_code="SYSTEM_ADMINISTRATOR", is_active=True))
        self.person = Person(first_name="Searchable", last_name="Student", registration_number="REG-001")
        db.session.add(self.person)
        db.session.flush()
        db.session.add(TeamAssignment(project_id=self.project.id, person_id=self.person.id, assignment_type="Project Team", status="Active"))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    def test_project_manager_cannot_list_generic_people_collection(self):
        self.login(self.manager)
        response = self.client.get("/api/v1/people")
        self.assertEqual(response.status_code, 403)

    def test_platform_admin_can_list_generic_people_collection(self):
        self.login(self.admin)
        response = self.client.get("/api/v1/people")
        self.assertEqual(response.status_code, 200)

    def test_project_manager_can_use_scoped_people_search(self):
        self.login(self.manager)
        response = self.client.get(f"/api/v1/projects/{self.project.public_id}/people-search?q=Searchable")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["data"]), 1)
        result = response.json["data"][0]
        self.assertEqual(set(result), {"public_id", "display_name", "registration_number", "membership_state"})
        self.assertEqual(result["membership_state"], "Active member")

    def test_scoped_people_search_denies_out_of_scope_manager(self):
        other_campus = Campus(name="Other", code="OTH")
        db.session.add(other_campus)
        db.session.flush()
        other_project = Project(
            code="ICC-2026-OTH-600", campus_id=other_campus.id, program_type_id=self.program_type.id,
            academic_year_id=self.year.id, title="Other project", category="Operational", status="Draft",
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(other_project)
        db.session.commit()
        self.login(self.manager)
        response = self.client.get(f"/api/v1/projects/{other_project.public_id}/people-search?q=Searchable")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
