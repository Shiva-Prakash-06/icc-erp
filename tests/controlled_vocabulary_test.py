import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import BudgetLine, OperatingUnit, OperationalRequest, ProjectSession, RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.vocabulary import resolve_vocabulary_value, vocabulary_options


class VocabularyHelperTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_options_always_end_in_other(self):
        self.assertEqual(vocabulary_options("project_category")[-1], "Other")

    def test_resolve_returns_value_directly_when_not_other(self):
        self.assertEqual(resolve_vocabulary_value("Logistics", "", domain="budget_category"), "Logistics")

    def test_resolve_requires_detail_when_other_chosen(self):
        with self.assertRaises(ValueError):
            resolve_vocabulary_value("Other", "  ", domain="budget_category")

    def test_resolve_uses_detail_when_other_chosen(self):
        self.assertEqual(resolve_vocabulary_value("Other", "Bespoke value", domain="budget_category"), "Bespoke value")

    def test_resolve_rejects_blank_value(self):
        with self.assertRaises(ValueError):
            resolve_vocabulary_value("", "", domain="budget_category")

    def test_resolve_rejects_crafted_value_outside_domain(self):
        with self.assertRaises(ValueError):
            resolve_vocabulary_value("water bottles", "", domain="budget_category")


class VocabularyDrivenFormsTestCase(unittest.TestCase):
    """Free-text fields for project category, session type, budget category,
    and operational-request type let UAT data drift into inconsistent
    spelling/taxonomy. See PLAN.md "ICC form ambiguity" finding -- these
    fields must now be constrained selects with an "Other" + required-detail
    escape hatch."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc = ProgramType(name="ICC")
        self.unit = OperatingUnit(code="ICC", name="ICC Unit")
        db.session.add_all([self.year, self.campus, self.icc, self.unit])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-990", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, title="Vocab form project", category="Operational",
            status="Draft", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()
        self.user = User(username="vocab_admin", email="vocab_admin@example.com", role="System Administrator", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="SYSTEM_ADMINISTRATOR", is_active=True))
        db.session.commit()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_project_creation_accepts_other_category_with_detail(self):
        response = self.client.post("/erp/projects", data={
            "title": "Other Category Project", "campus_public_id": self.campus.public_id,
            "program_type_public_id": self.icc.public_id, "academic_year_public_id": self.year.public_id,
            "start_date": "2026-08-01", "end_date": "2026-08-02",
            "category": "Other", "category_other": "Bespoke Category",
        })
        self.assertEqual(response.status_code, 302)
        project = Project.query.filter_by(title="Other Category Project").one()
        self.assertEqual(project.category, "Bespoke Category")

    def test_session_type_other_requires_detail(self):
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/sessions",
            data={"title": "Kickoff", "session_type": "Other", "session_type_other": "", "starts_at": "2026-08-01T09:00", "ends_at": "2026-08-01T10:00"},
            follow_redirects=True,
        )
        self.assertIn(b"Provide details for", response.data)
        self.assertEqual(ProjectSession.query.filter_by(project_id=self.project.id).count(), 0)

    def test_session_type_other_stores_detail(self):
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/sessions",
            data={"title": "Kickoff", "session_type": "Other", "session_type_other": "Retreat", "starts_at": "2026-08-01T09:00", "ends_at": "2026-08-01T10:00"},
        )
        self.assertEqual(response.status_code, 302)
        session = ProjectSession.query.filter_by(project_id=self.project.id).one()
        self.assertEqual(session.session_type, "Retreat")

    def test_operational_request_type_is_constrained(self):
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/operational-requests",
            data={"request_type": "Vehicle", "title": "Airport pickup"},
        )
        self.assertEqual(response.status_code, 302)
        request_item = OperationalRequest.query.filter_by(project_id=self.project.id).one()
        self.assertEqual(request_item.request_type, "Vehicle")

    def test_budget_category_other_requires_detail(self):
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/budgets",
            data={"category": "Other", "category_other": "", "estimated_amount": "10"},
            follow_redirects=True,
        )
        self.assertIn(b"Provide details for", response.data)
        self.assertEqual(BudgetLine.query.filter_by(project_id=self.project.id).count(), 0)

    def test_generic_api_rejects_value_outside_active_vocabulary(self):
        response = self.client.post("/api/v1/budgets", json={
            "project_public_id": self.project.public_id,
            "category": "water bottles",
            "description": "Hydration",
            "estimated_amount": 10,
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(BudgetLine.query.filter_by(project_id=self.project.id).count(), 0)


if __name__ == "__main__":
    unittest.main()
