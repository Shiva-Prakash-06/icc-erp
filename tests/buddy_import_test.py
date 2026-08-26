import io
import os
import unittest
from datetime import date
from pathlib import Path

os.environ["TESTING"] = "true"

from werkzeug.datastructures import FileStorage

from app import create_app
from app.database import db
from app.models.erp import OperatingUnit, Person, TeamAssignment
from app.models.project import AcademicYear, BuddyAssignment, Campus, ProgramType, Project
from app.models.user import User
from app.services.buddy_import import BuddyImportError, commit_buddy_batch, stage_buddy_import

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "summer_school_buddies_allocation.csv"


class BuddyImportTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["AUTO_PROVISIONED_BUDDY_DEFAULT_PASSWORD"] = "Temp-Pass-2026!"
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.igp = ProgramType(name="IGP")
        self.unit = OperatingUnit(code="IGP", name="IGP unit")
        db.session.add_all([self.year, self.campus, self.igp, self.unit])
        db.session.flush()
        self.project = Project(
            code="IGP-2026-CEN-901", campus_id=self.campus.id, program_type_id=self.igp.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Summer School",
            category="Exchange", status="Active", start_date=date(2026, 6, 27), end_date=date(2026, 7, 25),
        )
        self.user = User(username="igp_head", email="igp_head@example.com", role="IGP Head", status="Approved")
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.commit()
        self.content = FIXTURE_PATH.read_bytes()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _upload(self, content=None, filename="allocation.csv"):
        return FileStorage(stream=io.BytesIO(content or self.content), filename=filename)

    def test_imports_all_19_supplied_rows(self):
        batch = stage_buddy_import(self.project, self._upload(), "op-key")
        self.assertEqual(batch.staged_count, 19)
        self.assertEqual(batch.valid_count, 19)
        commit_buddy_batch(batch, self.user)
        self.assertEqual(batch.reconciliation_json["committed"], 19)
        self.assertEqual(BuddyAssignment.query.count(), 19)

    def test_provisions_buddy_accounts_with_project_scoped_role(self):
        batch = stage_buddy_import(self.project, self._upload(), "op-key")
        commit_buddy_batch(batch, self.user)
        neha = User.query.filter_by(username="neha").first()
        self.assertIsNotNone(neha)
        self.assertTrue(neha.needs_password_reset)
        self.assertEqual(neha.status, "Approved")
        self.assertIsNone(neha.email)
        role_codes = {ra.role_code for ra in neha.role_assignments}
        self.assertIn("BUDDY", role_codes)
        buddy_role = next(ra for ra in neha.role_assignments if ra.role_code == "BUDDY")
        self.assertEqual(buddy_role.project_id, self.project.id)

    def test_default_password_is_never_exposed_or_stored_in_plaintext(self):
        batch = stage_buddy_import(self.project, self._upload(), "op-key")
        commit_buddy_batch(batch, self.user)
        neha = User.query.filter_by(username="neha").first()
        self.assertNotEqual(neha.password_hash, "Temp-Pass-2026!")
        self.assertNotIn("Temp-Pass-2026!", neha.password_hash)
        for row in batch.rows:
            self.assertNotIn("Temp-Pass-2026!", str(row.source_json))
            self.assertNotIn("Temp-Pass-2026!", str(row.normalized_json))

    def test_handles_ben_ben_role_collision_as_separate_identities(self):
        batch = stage_buddy_import(self.project, self._upload(), "op-key")
        commit_buddy_batch(batch, self.user)
        bens = Person.query.filter_by(first_name="Ben").all()
        self.assertEqual(len(bens), 2)
        ben_roles = {
            TeamAssignment.query.filter_by(project_id=self.project.id, person_id=person.id).first().role_label
            for person in bens
        }
        self.assertEqual(ben_roles, {"Exchange Student", "Buddy"})

    def test_duplicate_first_names_across_rows_stay_distinct(self):
        # "Georgia" appears twice as an International Student (rows 6 and 9,
        # paired with different buddies) -- these are two different people
        # and must not be merged into one Person.
        batch = stage_buddy_import(self.project, self._upload(), "op-key")
        commit_buddy_batch(batch, self.user)
        georgias = Person.query.filter_by(first_name="Georgia").all()
        self.assertEqual(len(georgias), 2)
        self.assertEqual(BuddyAssignment.query.count(), 19)

    def test_reimport_of_identical_file_is_idempotent(self):
        first = stage_buddy_import(self.project, self._upload(), "op-key")
        commit_buddy_batch(first, self.user)
        replay = stage_buddy_import(self.project, self._upload(), "op-key")
        self.assertEqual(first.id, replay.id)

    def test_missing_names_are_staged_as_errors_not_committed(self):
        content = (
            "SNo,International Student,Christ Buddy,Contact\n"
            "1,,Neha,9000535371\n"
            "2,Praveena,,8904713904\n"
        ).encode()
        batch = stage_buddy_import(self.project, self._upload(content, "bad.csv"), "op-key")
        self.assertEqual(batch.error_count, 2)
        self.assertEqual(batch.valid_count, 0)
        commit_buddy_batch(batch, self.user)
        self.assertEqual(BuddyAssignment.query.count(), 0)

    def test_missing_default_password_blocks_buddy_provisioning(self):
        self.app.config["AUTO_PROVISIONED_BUDDY_DEFAULT_PASSWORD"] = None
        content = "SNo,International Student,Christ Buddy,Contact\n1,Elizabeth,Neha,9000535371\n".encode()
        batch = stage_buddy_import(self.project, self._upload(content, "one.csv"), "op-key")
        commit_buddy_batch(batch, self.user)
        self.assertEqual(batch.committed_count, 0)
        self.assertEqual(User.query.filter_by(username="neha").count(), 0)


if __name__ == "__main__":
    unittest.main()
