"""Audit findings B10 and B11: supplied import sources and the USC handoff.

B10 -- staging the supplied "2026 events summary" failed in the deployment
with a bare `/var/2026 ICC EVENTS REPORT SUMMARY.xlsx`. The workbooks were
resolved against the folder above the repository, which is `/var` on Vercel,
so they were never packaged.

B11 -- USC staged a valid batch, clicked Commit, and got Access denied.
Committing needs the global `approve` capability, which USC does not hold.
"""

import os
import unittest
import unittest.mock
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import ImportBatch, OperatingUnit, RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.authorization import has_permission
from app.services.imports import (
    BUNDLED_SOURCE_DIR,
    SOURCE_LABELS,
    SOURCE_PATHS,
    MissingSourceError,
    available_supplied_sources,
    stage_supplied_source,
)


class SuppliedSourceAvailabilityTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_the_two_small_workbooks_are_bundled_with_the_application(self):
        """These ship inside the package so a deployment can stage them. The
        Coffee Meet & Greet source is deliberately excluded: it is a 79 MB
        folder of supporting media."""
        for import_type in ("events_summary", "summer_school"):
            with self.subTest(import_type=import_type):
                path = SOURCE_PATHS[import_type]
                self.assertTrue(path.exists(), f"{import_type} source is missing")
                self.assertEqual(path.parent, BUNDLED_SOURCE_DIR)

    def test_bundled_sources_stay_small_enough_to_deploy(self):
        total = sum(path.stat().st_size for path in BUNDLED_SOURCE_DIR.iterdir() if path.is_file())
        self.assertLess(total, 5 * 1024 * 1024, "bundled import sources should stay well under the function bundle limit")

    def test_only_present_sources_are_offered(self):
        offered = dict(available_supplied_sources())
        self.assertIn("events_summary", offered)
        self.assertEqual(offered["events_summary"], SOURCE_LABELS["events_summary"])
        for import_type, path in SOURCE_PATHS.items():
            self.assertEqual(import_type in offered, path.exists())

    def test_a_missing_source_never_leaks_a_server_path(self):
        with self.assertRaises(MissingSourceError) as caught:
            with unittest.mock.patch.dict(SOURCE_PATHS, {"events_summary": BUNDLED_SOURCE_DIR / "absent.xlsx"}):
                stage_supplied_source("events_summary")
        message = str(caught.exception)
        self.assertIn("2026 events summary", message)
        self.assertIn("Bulk upload", message)
        self.assertNotIn("/", message)
        self.assertNotIn("\\\\", message)


class ImportCommitHandoffTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc = ProgramType(name="ICC")
        self.unit = OperatingUnit(code="ICC", name="ICC unit")
        db.session.add_all([self.year, self.campus, self.icc, self.unit])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-700", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Handoff project",
            category="Operational", status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        self.usc = User(username="usc", email="usc@example.com", role="USC", status="Approved", needs_password_reset=False)
        self.usc.set_password("A-secure-test-password-2026")
        self.faculty = User(username="faculty", email="faculty@example.com", role="Faculty", status="Approved", needs_password_reset=False)
        self.faculty.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.usc, self.faculty])
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.usc.id, role_code="ICC_SECRETARY_USC", is_active=True))
        db.session.add(RoleAssignment(user_id=self.faculty.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True))
        self.batch = ImportBatch(
            import_type="people", source_file="people.csv", source_sha256="a" * 64,
            status="Staged", staged_count=1, valid_count=1, error_count=0, committed_count=0,
            idempotency_key="usc-people-batch",
        )
        db.session.add(self.batch)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    def test_usc_can_reach_imports_but_does_not_hold_the_commit_capability(self):
        self.assertTrue(has_permission(self.usc, "manage_imports"))
        self.assertFalse(has_permission(self.usc, "approve"))

    def test_usc_is_shown_the_handoff_rather_than_a_commit_button_that_403s(self):
        self._login(self.usc)
        response = self.client.get("/erp/imports")
        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Awaiting faculty commit", body)
        self.assertNotIn(f"/imports/{self.batch.public_id}/commit", body)

    def test_faculty_is_shown_the_commit_action(self):
        self._login(self.faculty)
        response = self.client.get("/erp/imports")
        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn(f"/imports/{self.batch.public_id}/commit", body)
        self.assertNotIn("Awaiting faculty commit", body)

    def test_the_route_itself_still_refuses_usc(self):
        """The UI change must not be mistaken for a permission change: the
        audit performed no access broadening and neither does this fix."""
        self._login(self.usc)
        response = self.client.post(f"/erp/imports/{self.batch.public_id}/commit")
        self.assertEqual(response.status_code, 403)

    def test_the_imports_screen_never_offers_an_unavailable_supplied_source(self):
        self._login(self.faculty)
        body = self.client.get("/erp/imports").data.decode()
        for import_type, label in SOURCE_LABELS.items():
            if not SOURCE_PATHS[import_type].exists():
                self.assertNotIn(f'value="{import_type}"', body)


if __name__ == "__main__":
    unittest.main()
