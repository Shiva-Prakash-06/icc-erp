"""Phase 1 of the simplification: who may do what.

Faculty is the only approver. Heads and the USC run events. The Media and
Culturals heads own no events and reach one only through items handed to
their team -- including IGP programmes -- without seeing its people or
money. Volunteers only view the events they are listed on.
"""

import os
import unittest
from datetime import date
from decimal import Decimal

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    OperatingUnit,
    Person,
    ReimbursementEntry,
    RoleAssignment,
    TeamAssignment,
    WorkTask,
)
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.authorization import ROLE_PERMISSIONS, can_view_project, has_permission
from app.services.operations import instantiate_checklist
from app.services.reimbursements import MoneyDecisionError, change_money_status, normalize_money_status
from app.services.teams import can_contribute, contributor_projects, team_from_label, user_teams

APPROVALS = {"approve", "approve_operational_requests", "waive", "manage_governance"}
FACULTY_ROLES = {"OIA_FACULTY_ADMINISTRATOR", "FACULTY_COORDINATOR"}


class PermissionMatrixTestCase(unittest.TestCase):
    def test_only_faculty_holds_any_approval(self):
        for role_code, permissions in ROLE_PERMISSIONS.items():
            with self.subTest(role=role_code):
                if role_code in FACULTY_ROLES:
                    self.assertTrue(APPROVALS <= permissions)
                else:
                    self.assertFalse(APPROVALS & permissions)

    def test_contributors_and_volunteers_cannot_manage(self):
        for role_code in ("ICC_MEDIA_HEAD", "ICC_CULTURALS_HEAD", "VOLUNTEER", "ICC_ASSOCIATE", "BUDDY", "PARTICIPANT", "IGP_PROGRAM_LEAD"):
            with self.subTest(role=role_code):
                self.assertNotIn("manage_projects", ROLE_PERMISSIONS[role_code])
                self.assertNotIn("manage_people", ROLE_PERMISSIONS[role_code])

    def test_team_from_label(self):
        self.assertEqual(team_from_label("Media"), "media")
        self.assertEqual(team_from_label(None, "Poster / invite designed"), "media")
        self.assertEqual(team_from_label("Cultural performances"), "culturals")
        self.assertEqual(team_from_label("IGP office"), "igp")
        self.assertEqual(team_from_label("Faculty coordinator"), "faculty")
        self.assertIsNone(team_from_label("Logistics", "Operations"))

    def test_money_status_reads_old_words(self):
        self.assertEqual(normalize_money_status(""), "Asked")
        self.assertEqual(normalize_money_status("Pending"), "Asked")
        self.assertEqual(normalize_money_status("Reimbursed"), "Paid")
        self.assertEqual(normalize_money_status("Rejected"), "Not approved")
        self.assertEqual(normalize_money_status("approved"), "Approved")


class SimplifiedRolesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.other_campus = Campus(name="Kengeri", code="KEN")
        self.icc_type = ProgramType(name="ICC")
        self.igp_type = ProgramType(name="IGP")
        self.icc = OperatingUnit(code="ICC", name="ICC")
        self.igp = OperatingUnit(code="IGP", name="IGP")
        db.session.add_all([self.year, self.campus, self.other_campus, self.icc_type, self.igp_type, self.icc, self.igp])
        db.session.flush()
        self.icc_event = self._project("ICC-2026-CEN-900", self.icc_type, self.icc, self.campus)
        self.igp_programme = self._project("IGP-2026-CEN-900", self.igp_type, self.igp, self.campus)
        self.far_programme = self._project("IGP-2026-KEN-900", self.igp_type, self.igp, self.other_campus)

        self.faculty = self._user("faculty", "OIA_FACULTY_ADMINISTRATOR")
        self.other_faculty = self._user("faculty2", "FACULTY_COORDINATOR")
        self.events_head = self._user("events", "ICC_EVENTS_HEAD", operating_unit_id=self.icc.id, campus_id=self.campus.id, academic_year_id=self.year.id)
        self.media_head = self._user("media", "ICC_MEDIA_HEAD", operating_unit_id=self.icc.id, campus_id=self.campus.id, academic_year_id=self.year.id)
        self.igp_head = self._user("igp", "IGP_HEAD", operating_unit_id=self.igp.id, campus_id=self.campus.id, academic_year_id=self.year.id)
        self.usc = self._user("usc", "ICC_SECRETARY_USC", operating_unit_id=self.icc.id, campus_id=self.campus.id, academic_year_id=self.year.id)
        self.volunteer = self._user("vol", "VOLUNTEER", campus_id=self.campus.id)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _project(self, code, program_type, unit, campus):
        project = Project(
            code=code, title=code, campus_id=campus.id, program_type_id=program_type.id,
            academic_year_id=self.year.id, operating_unit_id=unit.id, wing_id=None,
            category="Event", status="Active", start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
        )
        db.session.add(project)
        db.session.flush()
        return project

    def _user(self, name, role_code, **scope):
        person = Person(first_name=name.title(), primary_email=f"{name}@christuniversity.in")
        db.session.add(person)
        db.session.flush()
        user = User(username=name, email=f"{name}@christuniversity.in", role=role_code, status="Approved",
                    needs_password_reset=False, person_id=person.id)
        user.set_password("A-secure-test-password-2026")
        db.session.add(user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=user.id, role_code=role_code, is_active=True, **scope))
        return user

    def _login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    # --- who runs what -----------------------------------------------------

    def test_events_head_runs_unwinged_icc_events_but_not_igp(self):
        self.assertTrue(has_permission(self.events_head, "manage_projects", self.icc_event))
        self.assertFalse(has_permission(self.events_head, "manage_projects", self.igp_programme))
        self.assertFalse(has_permission(self.events_head, "approve", self.icc_event))

    def test_usc_edits_icc_but_approves_nothing(self):
        self.assertTrue(has_permission(self.usc, "manage_projects", self.icc_event))
        for permission in APPROVALS:
            self.assertFalse(has_permission(self.usc, permission, self.icc_event))

    def test_head_cannot_finish_an_event_but_faculty_can(self):
        self._login(self.events_head)
        response = self.client.post(f"/erp/projects/{self.icc_event.public_id}/transition", data={
            "version": self.icc_event.version, "target_status": "Completed",
        })
        self.assertEqual(response.status_code, 403)

    # --- contributors ------------------------------------------------------

    def test_media_head_reaches_an_igp_programme_only_through_a_media_item(self):
        self.assertFalse(can_contribute(self.media_head, self.igp_programme))
        db.session.add(WorkTask(project_id=self.igp_programme.id, title="Welcome poster", assigned_team="media"))
        db.session.commit()
        self.assertEqual(user_teams(self.media_head), {"media"})
        self.assertTrue(can_contribute(self.media_head, self.igp_programme))
        self.assertFalse(can_contribute(self.media_head, self.icc_event))
        self.assertEqual(contributor_projects(self.media_head), [self.igp_programme])
        # Contributing is not running the event: no people, no money.
        self.assertFalse(has_permission(self.media_head, "manage_projects", self.igp_programme))
        self.assertFalse(can_view_project(self.media_head, self.igp_programme))
        # They can open the event, but see only their team's item: no people
        # list, no money, no other files.
        db.session.add(TeamAssignment(person_id=self.volunteer.person_id, project_id=self.igp_programme.id, assignment_type="Project Team"))
        db.session.commit()
        self._login(self.media_head)
        response = self.client.get(f"/erp/projects/{self.igp_programme.public_id}?tab=people")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Welcome poster", html)
        for hidden in ('id="card-people"', 'id="card-money"', 'id="card-schedule"', self.volunteer.person.display_name):
            self.assertNotIn(hidden, html)
        # And a programme without a Media item stays closed to them.
        self.assertEqual(self.client.get(f"/erp/projects/{self.far_programme.public_id}").status_code, 403)

    def test_contributor_never_crosses_campus(self):
        db.session.add(WorkTask(project_id=self.far_programme.id, title="Photos", assigned_team="media"))
        db.session.commit()
        self.assertFalse(can_contribute(self.media_head, self.far_programme))
        self.assertEqual(contributor_projects(self.media_head), [])

    def test_a_culturals_item_does_not_reach_the_media_head(self):
        db.session.add(WorkTask(project_id=self.icc_event.id, title="Dance act", assigned_team="culturals"))
        db.session.commit()
        self.assertFalse(can_contribute(self.media_head, self.icc_event))

    def test_checklist_items_are_handed_to_teams_from_their_labels(self):
        template = ChecklistTemplate(code="T", name="Standard", project_type="ICC event", version=1)
        db.session.add(template)
        db.session.flush()
        db.session.add_all([
            ChecklistTemplateItem(template_id=template.id, code="VENUE", title="Venue booked", category="Logistics", sequence=1, mandatory=True),
            ChecklistTemplateItem(template_id=template.id, code="POSTER", title="Poster designed", category="Media", sequence=2, mandatory=True),
        ])
        db.session.commit()
        instance = instantiate_checklist(self.icc_event, template, self.faculty)
        teams = {item.template_item.code: item.assigned_team for item in instance.item_statuses}
        self.assertEqual(teams, {"VENUE": None, "POSTER": "media"})
        self.assertTrue(can_contribute(self.media_head, self.icc_event))

    # --- volunteers --------------------------------------------------------

    def test_volunteer_sees_only_the_events_they_are_on(self):
        self.assertFalse(can_view_project(self.volunteer, self.icc_event))
        db.session.add(TeamAssignment(person_id=self.volunteer.person_id, project_id=self.icc_event.id, assignment_type="Project Team"))
        db.session.commit()
        self.assertTrue(can_view_project(self.volunteer, self.icc_event))
        self.assertFalse(can_view_project(self.volunteer, self.igp_programme))
        self.assertFalse(has_permission(self.volunteer, "manage_projects", self.icc_event))
        self._login(self.volunteer)
        self.assertEqual(self.client.get(f"/erp/projects/{self.igp_programme.public_id}").status_code, 403)

    # --- money -------------------------------------------------------------

    def _money(self, created_by):
        entry = ReimbursementEntry(project_id=self.icc_event.id, date=date(2026, 9, 1), party_name="",
                                   amount=Decimal("1200"), particular="Snacks", status="Asked", created_by_id=created_by.id)
        db.session.add(entry)
        db.session.commit()
        return entry

    def test_only_faculty_approves_money_and_never_their_own(self):
        entry = self._money(self.events_head)
        for actor in (self.events_head, self.usc, self.igp_head, self.media_head):
            with self.subTest(actor=actor.username), self.assertRaises(MoneyDecisionError):
                change_money_status(entry, "Approved", actor)
        own = self._money(self.faculty)
        with self.assertRaisesRegex(MoneyDecisionError, "Someone else"):
            change_money_status(own, "Approved", self.faculty)
        change_money_status(entry, "Approved", self.faculty)
        self.assertEqual((entry.status, entry.approved_by_id), ("Approved", self.faculty.id))

    def test_money_is_approved_before_it_is_paid_and_a_no_needs_a_reason(self):
        entry = self._money(self.events_head)
        with self.assertRaisesRegex(MoneyDecisionError, "approved before"):
            change_money_status(entry, "Paid", self.events_head)
        with self.assertRaisesRegex(MoneyDecisionError, "Say why"):
            change_money_status(entry, "Not approved", self.faculty)
        change_money_status(entry, "Approved", self.other_faculty)
        change_money_status(entry, "Paid", self.events_head)
        self.assertEqual(entry.status, "Paid")

    def test_money_route_asks_without_a_payee(self):
        self._login(self.events_head)
        response = self.client.post(f"/erp/projects/{self.icc_event.public_id}/reimbursements", data={
            "date": "2026-09-01", "amount": "300", "particular": "Banner printing",
        })
        self.assertEqual(response.status_code, 302)
        entry = ReimbursementEntry.query.filter_by(project_id=self.icc_event.id).one()
        self.assertEqual((entry.status, entry.party_name, entry.created_by_id), ("Asked", "", self.events_head.id))
        response = self.client.post(
            f"/erp/projects/{self.icc_event.public_id}/reimbursements/{entry.public_id}/status",
            data={"status": "Approved"}, follow_redirects=True,
        )
        self.assertIn(b"Only Faculty can approve money", response.data)
        self.assertEqual(entry.status, "Asked")


if __name__ == "__main__":
    unittest.main()
