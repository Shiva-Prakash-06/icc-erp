import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import Person, RoleAssignment, TeamAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User


class IgpEnrollmentTestCase(unittest.TestCase):
    """The database already permits a Person with no registration number,
    but enrollment and buddy forms required one -- a confirmed workflow
    defect. See PLAN.md "IGP registration number" finding."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.igp = ProgramType(name="IGP")
        db.session.add_all([self.year, self.campus, self.igp])
        db.session.flush()
        self.project = Project(
            code="IGP-2026-CEN-500", campus_id=self.campus.id, program_type_id=self.igp.id,
            academic_year_id=self.year.id, title="IGP enrollment project", category="Exchange",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        self.other_project = Project(
            code="IGP-2026-CEN-501", campus_id=self.campus.id, program_type_id=self.igp.id,
            academic_year_id=self.year.id, title="Other IGP project", category="Exchange",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add_all([self.project, self.other_project])
        db.session.flush()
        self.manager = User(username="igp_head", email="igp_head@example.com", role="IGP Head", status="Approved", needs_password_reset=False)
        self.manager.set_password("A-secure-test-password-2026")
        db.session.add(self.manager)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.manager.id, role_code="IGP_HEAD", is_active=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.manager.id
            session["session_version"] = self.manager.session_version

    def test_create_and_enroll_participant_with_only_first_name(self):
        self.login()
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/team/create-and-enroll",
            data={"first_name": "Jamie"},
        )
        self.assertEqual(response.status_code, 302)
        person = Person.query.filter_by(first_name="Jamie").one()
        self.assertIsNone(person.registration_number)
        self.assertIsNone(person.primary_email)
        assignment = TeamAssignment.query.filter_by(person_id=person.id, project_id=self.project.id).one()
        self.assertEqual(assignment.assignment_type, "Project Team")

    def test_create_and_enroll_requires_first_name(self):
        self.login()
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/team/create-and-enroll",
            data={"first_name": "  "},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Person.query.count(), 0)

    def test_create_and_enroll_dedupes_on_email(self):
        existing = Person(first_name="Existing", primary_email="dup@example.com", person_type="Student")
        db.session.add(existing)
        db.session.commit()
        self.login()
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/team/create-and-enroll",
            data={"first_name": "Different Name", "email": "DUP@example.com"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Person.query.count(), 1)
        assignment = TeamAssignment.query.filter_by(project_id=self.project.id).one()
        self.assertEqual(assignment.person_id, existing.id)

    def test_conflicting_email_and_registration_identifiers_are_rejected(self):
        email_owner = Person(first_name="EmailOwner", primary_email="conflict@example.com")
        registration_owner = Person(first_name="RegistrationOwner", registration_number="CONFLICT-1")
        db.session.add_all([email_owner, registration_owner])
        db.session.commit()
        self.login()
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/team/create-and-enroll",
            data={
                "first_name": "Conflicting",
                "email": "conflict@example.com",
                "registration_number": "CONFLICT-1",
            },
            follow_redirects=True,
        )
        self.assertIn(b"belong to different people", response.data)
        self.assertEqual(TeamAssignment.query.filter_by(project_id=self.project.id).count(), 0)

    def test_api_creates_registrationless_participant_with_version_check(self):
        self.login()
        response = self.client.post(
            f"/api/v1/projects/{self.project.public_id}/participants",
            json={"version": self.project.version, "first_name": "API Jamie"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json["data"]["person_created"])
        self.assertIsNone(response.json["data"]["person"]["registration_number"])
        self.assertEqual(response.json["data"]["project_version"], 2)

        stale = self.client.post(
            f"/api/v1/projects/{self.project.public_id}/participants",
            json={"version": 1, "first_name": "Stale participant"},
        )
        self.assertEqual(stale.status_code, 409)
        self.assertIsNone(Person.query.filter_by(first_name="Stale participant").first())

    def test_buddy_pairing_rejects_non_participant(self):
        outsider = Person(first_name="Outsider", person_type="Student")
        member = Person(first_name="Member", person_type="Student")
        db.session.add_all([outsider, member])
        db.session.flush()
        db.session.add(TeamAssignment(person_id=member.id, project_id=self.project.id, assignment_type="IGP Program Team", status="Active"))
        db.session.commit()
        self.login()
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/buddy-assignments",
            data={
                "buddy_person_public_id": outsider.public_id, "exchange_student_person_public_id": member.public_id,
                "start_date": "2026-08-01", "end_date": "2026-08-10",
            },
            follow_redirects=True,
        )
        self.assertIn(b"must be active participants", response.data)

    def test_buddy_pairing_rejects_cross_project_participant(self):
        cross_project_person = Person(first_name="CrossProject", person_type="Student")
        member = Person(first_name="Member2", person_type="Student")
        db.session.add_all([cross_project_person, member])
        db.session.flush()
        db.session.add(TeamAssignment(person_id=cross_project_person.id, project_id=self.other_project.id, assignment_type="IGP Program Team", status="Active"))
        db.session.add(TeamAssignment(person_id=member.id, project_id=self.project.id, assignment_type="IGP Program Team", status="Active"))
        db.session.commit()
        self.login()
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/buddy-assignments",
            data={
                "buddy_person_public_id": cross_project_person.public_id, "exchange_student_person_public_id": member.public_id,
                "start_date": "2026-08-01", "end_date": "2026-08-10",
            },
            follow_redirects=True,
        )
        self.assertIn(b"must be active participants", response.data)

    def test_buddy_pairing_rejects_self_pairing(self):
        member = Person(first_name="SoloMember", person_type="Student")
        db.session.add(member)
        db.session.flush()
        db.session.add(TeamAssignment(person_id=member.id, project_id=self.project.id, assignment_type="IGP Program Team", status="Active"))
        db.session.commit()
        self.login()
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/buddy-assignments",
            data={
                "buddy_person_public_id": member.public_id, "exchange_student_person_public_id": member.public_id,
                "start_date": "2026-08-01", "end_date": "2026-08-10",
            },
            follow_redirects=True,
        )
        self.assertIn(b"cannot be paired with themselves", response.data)


if __name__ == "__main__":
    unittest.main()
