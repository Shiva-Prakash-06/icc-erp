import os
import unittest
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from flask import Flask, g
from werkzeug.exceptions import Forbidden

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import DocumentRecord, OperatingUnit, RoleAssignment, Wing
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.authorization import has_any_permission, has_permission, permission_required, role_codes
from app.services.job_auth import verify_internal_job_request
from app.services.roles import replace_scoped_assignment


class InternalJobAuthenticationGateTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=False,
            INTERNAL_JOB_AUDIENCE="https://erp.example.test",
        )

    def test_missing_token_and_audience_fail_closed(self):
        with self.app.test_request_context("/internal/jobs/reminders", method="POST"):
            with self.assertRaisesRegex(PermissionError, "Missing OIDC"):
                verify_internal_job_request(["scheduler@example.test"])

        self.app.config["INTERNAL_JOB_AUDIENCE"] = None
        with self.app.test_request_context(
            "/internal/jobs/reminders", method="POST",
            headers={"Authorization": "Bearer token"},
        ):
            with self.assertRaisesRegex(PermissionError, "audience is not configured"):
                verify_internal_job_request(["scheduler@example.test"])

    def test_invalid_verifier_result_is_an_authorization_denial(self):
        with self.app.test_request_context(
            "/internal/jobs/reminders", method="POST",
            headers={"Authorization": "Bearer invalid"},
        ), patch("app.services.job_auth.id_token.verify_oauth2_token", side_effect=ValueError("bad signature")):
            with self.assertRaisesRegex(PermissionError, "token is invalid"):
                verify_internal_job_request(["scheduler@example.test"])

    def test_verified_allowed_identity_succeeds_and_other_identity_fails(self):
        request_headers = {"Authorization": "Bearer valid"}
        claims = {"email": "scheduler@example.test", "email_verified": True}
        with self.app.test_request_context(
            "/internal/jobs/reminders", method="POST", headers=request_headers,
        ), patch("app.services.job_auth.id_token.verify_oauth2_token", return_value=claims) as verifier:
            self.assertEqual(
                verify_internal_job_request(["scheduler@example.test"]),
                claims,
            )
            self.assertEqual(verifier.call_args.args[2], "https://erp.example.test")

        with self.app.test_request_context(
            "/internal/jobs/reminders", method="POST", headers=request_headers,
        ), patch("app.services.job_auth.id_token.verify_oauth2_token", return_value=claims):
            with self.assertRaisesRegex(PermissionError, "not authorized"):
                verify_internal_job_request(["tasks@example.test"])


class ReleaseAuthorizationGateTestCase(unittest.TestCase):
    """Fail-closed coverage for account approval and scoped grants."""

    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.year = AcademicYear(
            name="2026-2027", start_date=date(2026, 6, 1),
            end_date=date(2027, 5, 31), is_current=True,
        )
        self.campus = Campus(name="Central", code="CEN")
        self.other_campus = Campus(name="Other", code="OTH")
        self.icc_type = ProgramType(name="ICC")
        self.igp_type = ProgramType(name="IGP")
        self.icc = OperatingUnit(code="ICC", name="International Christite Community")
        self.igp = OperatingUnit(code="IGP", name="International Guest Programme")
        db.session.add_all([
            self.year, self.campus, self.other_campus, self.icc_type,
            self.igp_type, self.icc, self.igp,
        ])
        db.session.flush()
        self.events = Wing(operating_unit_id=self.icc.id, code="EVENTS", name="Events")
        self.media = Wing(operating_unit_id=self.icc.id, code="MEDIA", name="Media")
        db.session.add_all([self.events, self.media])
        db.session.flush()
        self.icc_project = Project(
            code="ICC-2026-CEN-GATE", campus_id=self.campus.id,
            program_type_id=self.icc_type.id, academic_year_id=self.year.id,
            operating_unit_id=self.icc.id, wing_id=self.events.id,
            title="ICC release gate", category="Event", status="Active",
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        self.igp_project = Project(
            code="IGP-2026-CEN-GATE", campus_id=self.campus.id,
            program_type_id=self.igp_type.id, academic_year_id=self.year.id,
            operating_unit_id=self.igp.id, title="IGP release gate",
            category="Exchange", status="Active", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
        )
        self.actor = self._user("approver", campus=self.campus)
        self.target = self._user("target", campus=self.campus)
        db.session.add_all([self.icc_project, self.igp_project])
        db.session.flush()
        db.session.add(RoleAssignment(
            user_id=self.actor.id, role_code="OIA_FACULTY_ADMINISTRATOR",
            is_active=True, can_view_sensitive_links=True,
        ))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _user(self, username, *, campus=None, status="Approved"):
        user = User(
            username=username, email=f"{username}@example.test", role="Pending",
            status=status, campus=campus, needs_password_reset=False,
        )
        user.set_password("A-secure-release-gate-password-2026")
        db.session.add(user)
        db.session.flush()
        return user

    @contextmanager
    def _login(self, user):
        with self.app.test_client() as client:
            with client.session_transaction() as session:
                session["user_id"] = user.id
                session["session_version"] = user.session_version
            yield client

    def test_project_manager_cannot_mutate_unscoped_reference_data(self):
        db.session.add(RoleAssignment(
            user_id=self.target.id, role_code="ICC_EVENTS_HEAD",
            project_id=self.icc_project.id, is_active=True,
        ))
        db.session.commit()

        with self._login(self.target) as client:
            response = client.post(
                "/api/v1/campuses",
                json={"code": "NEW", "name": "Unauthorized campus"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(Campus.query.filter_by(code="NEW").first())

        with self._login(self.actor) as client:
            response = client.post(
                "/api/v1/campuses",
                json={"code": "NEW", "name": "Governed campus"},
            )
        self.assertEqual(response.status_code, 201)

    def test_drive_validation_requires_project_management_permission(self):
        db.session.add(RoleAssignment(
            user_id=self.target.id, role_code="VOLUNTEER",
            project_id=self.icc_project.id, is_active=True,
        ))
        db.session.commit()
        with self._login(self.target) as client:
            response = client.post(
                "/api/v1/documents/validate-drive-link",
                json={"url": "https://drive.google.com/file/d/example/view"},
            )
        self.assertEqual(response.status_code, 403)

    def test_scoped_sensitive_link_grant_is_honored_only_in_its_project(self):
        scoped_head = self._user("scoped-igp-head")
        db.session.add(RoleAssignment(
            user_id=scoped_head.id, role_code="IGP_HEAD",
            project_id=self.igp_project.id, is_active=True,
            can_view_sensitive_links=True,
        ))
        document = DocumentRecord(
            project_id=self.igp_project.id, title="Restricted reference",
            category="Report", permission_classification="Restricted",
            status="Approved", drive_file_id="restricted-file-id",
        )
        db.session.add(document)
        db.session.commit()

        with self._login(scoped_head) as client:
            response = client.get(
                f"/api/v1/documents/{document.public_id}",
                headers={"X-Access-Purpose": "Release-gate verification"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"]["drive_file_id"], "restricted-file-id")

    def test_invalid_replacement_preserves_current_access(self):
        current = RoleAssignment(
            user_id=self.target.id, role_code="VOLUNTEER",
            project_id=self.icc_project.id, is_active=True,
        )
        db.session.add(current)
        db.session.commit()

        with self.assertRaisesRegex(ValueError, "not supported"):
            replace_scoped_assignment(self.target, "Invented role", {}, self.actor)

        self.assertTrue(current.is_active)
        self.assertTrue(has_permission(self.target, "view_assigned", self.icc_project))

    def test_role_specific_scope_requirements_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "academic year"):
            replace_scoped_assignment(self.target, "ICC Events Head", {}, self.actor)
        with self.assertRaisesRegex(ValueError, "require a wing"):
            replace_scoped_assignment(
                self.target, "ICC Associate",
                {"academic_year_public_id": self.year.public_id}, self.actor,
            )
        with self.assertRaisesRegex(ValueError, "specific program"):
            replace_scoped_assignment(self.target, "IGP Program Lead", {}, self.actor)
        with self.assertRaisesRegex(ValueError, "specific project"):
            replace_scoped_assignment(self.target, "Volunteer", {}, self.actor)

    def test_cross_unit_and_fixed_wing_scopes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "designated wing"):
            replace_scoped_assignment(
                self.target, "ICC Events Head",
                {
                    "academic_year_public_id": self.year.public_id,
                    "wing_public_id": self.media.public_id,
                },
                self.actor,
            )
        with self.assertRaisesRegex(ValueError, "operating unit"):
            replace_scoped_assignment(
                self.target, "IGP Program Lead",
                {"project_public_id": self.icc_project.public_id}, self.actor,
            )

    def test_platform_and_sensitive_access_require_privileged_roles_and_actor(self):
        with self.assertRaisesRegex(ValueError, "platform scope"):
            replace_scoped_assignment(
                self.target, "Volunteer",
                {"project_public_id": self.icc_project.public_id, "platform_scope": "on"},
                self.actor,
            )
        with self.assertRaisesRegex(ValueError, "restricted-reference"):
            replace_scoped_assignment(
                self.target, "ICC Events Head",
                {
                    "academic_year_public_id": self.year.public_id,
                    "can_view_sensitive_links": "on",
                },
                self.actor,
            )
        unprivileged_actor = self._user("unprivileged-approver")
        db.session.commit()
        with self.assertRaisesRegex(ValueError, "restricted-reference"):
            replace_scoped_assignment(
                self.target, "OIA Faculty Administrator",
                {"platform_scope": "on", "can_view_sensitive_links": "on"},
                unprivileged_actor,
            )

    def test_valid_replacement_deactivates_old_grant_and_resolves_scope(self):
        old = RoleAssignment(
            user_id=self.target.id, role_code="VOLUNTEER",
            project_id=self.igp_project.id, is_active=True,
        )
        db.session.add(old)
        db.session.commit()

        assignment = replace_scoped_assignment(
            self.target, "ICC Events Head",
            {"academic_year_public_id": self.year.public_id}, self.actor,
        )

        self.assertFalse(old.is_active)
        self.assertEqual(assignment.role_code, "ICC_EVENTS_HEAD")
        self.assertEqual(assignment.operating_unit_id, self.icc.id)
        self.assertEqual(assignment.wing_id, self.events.id)
        self.assertEqual(assignment.academic_year_id, self.year.id)
        self.assertEqual(assignment.campus_id, self.campus.id)

    def test_authorization_helpers_and_decorator_respect_scope(self):
        legacy_only = self._user("legacy", status="Approved")
        legacy_only.role = "System Administrator"
        db.session.commit()
        self.assertIn("SYSTEM_ADMINISTRATOR", role_codes(legacy_only))
        self.assertFalse(has_permission(legacy_only, "platform_admin"))
        self.assertEqual(role_codes(None), set())
        self.assertTrue(has_any_permission(self.actor, "manage_projects"))
        self.assertFalse(has_any_permission(None, "manage_projects"))

        @permission_required("manage_projects", project_loader=lambda project: project)
        def protected(project):
            return project.public_id

        with self.app.test_request_context("/gate"):
            g.user = self.actor
            self.assertEqual(protected(self.icc_project), self.icc_project.public_id)
            g.user = legacy_only
            with self.assertRaises(Forbidden):
                protected(self.icc_project)


if __name__ == "__main__":
    unittest.main()
