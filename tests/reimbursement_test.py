import io
import os
import unittest
from datetime import date
from decimal import Decimal

os.environ["TESTING"] = "true"

from werkzeug.datastructures import FileStorage

from app import create_app
from app.database import db
from app.models.erp import OperatingUnit, ReimbursementEntry
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.reimbursements import commit_reimbursement_batch, export_reimbursements, stage_reimbursement_import


class ReimbursementImportTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
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
            code="IGP-2026-CEN-902", campus_id=self.campus.id, program_type_id=self.igp.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Summer School",
            category="Exchange", status="Active", start_date=date(2026, 6, 27), end_date=date(2026, 7, 25),
        )
        self.user = User(username="igp_head", email="igp_head@example.com", role="IGP Head", status="Approved")
        self.user.set_password("A-secure-test-password-2026")
        db.session.add_all([self.project, self.user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _upload(self, content, filename="reimbursements.csv"):
        return FileStorage(stream=io.BytesIO(content), filename=filename)

    def test_valid_rows_import_and_ignore_serial_number(self):
        content = (
            "S. No,Date,Party Name,Bill Number,Amount,Particular,Status\n"
            "1,2026-07-01,ABC Caterers,BILL-001,1500.50,Lunch catering,\n"
            "2,2026-07-02,XYZ Transport,BILL-002,2500,Bus rental,Reimbursed\n"
        ).encode()
        batch = stage_reimbursement_import(self.project, self._upload(content), "op-key")
        self.assertEqual(batch.valid_count, 2)
        commit_reimbursement_batch(batch, self.user)
        entries = ReimbursementEntry.query.order_by(ReimbursementEntry.date).all()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].status, "Pending")  # blank defaults to Pending
        self.assertEqual(entries[1].status, "Reimbursed")  # supplied status preserved
        self.assertEqual(entries[0].amount, Decimal("1500.50"))
        self.assertFalse(hasattr(entries[0], "s_no"))

    def test_negative_amount_is_rejected(self):
        content = "S. No,Date,Party Name,Bill Number,Amount,Particular,Status\n1,2026-07-01,ABC,B1,-100,x,\n".encode()
        batch = stage_reimbursement_import(self.project, self._upload(content), "op-key")
        self.assertEqual(batch.error_count, 1)
        commit_reimbursement_batch(batch, self.user)
        self.assertEqual(ReimbursementEntry.query.count(), 0)

    def test_invalid_date_is_rejected(self):
        content = "S. No,Date,Party Name,Bill Number,Amount,Particular,Status\n1,notadate,ABC,B1,100,x,\n".encode()
        batch = stage_reimbursement_import(self.project, self._upload(content), "op-key")
        self.assertEqual(batch.error_count, 1)

    def test_reimport_of_identical_file_is_idempotent(self):
        content = "S. No,Date,Party Name,Bill Number,Amount,Particular,Status\n1,2026-07-01,ABC,B1,100,x,\n".encode()
        first = stage_reimbursement_import(self.project, self._upload(content), "op-key")
        commit_reimbursement_batch(first, self.user)
        replay = stage_reimbursement_import(self.project, self._upload(content), "op-key")
        self.assertEqual(first.id, replay.id)

    def test_csv_and_xlsx_export_round_trip(self):
        entry = ReimbursementEntry(project_id=self.project.id, date=date(2026, 7, 1), party_name="ABC", amount=Decimal("100.00"), status="Pending")
        db.session.add(entry)
        db.session.commit()
        csv_buffer = export_reimbursements(self.project, "csv")
        text = csv_buffer.read().decode()
        self.assertIn("ABC", text)
        self.assertIn("S. No", text)
        xlsx_buffer = export_reimbursements(self.project, "xlsx")
        self.assertGreater(len(xlsx_buffer.read()), 0)


if __name__ == "__main__":
    unittest.main()
