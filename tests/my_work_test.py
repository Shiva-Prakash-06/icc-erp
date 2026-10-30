"""Phase 3 of the simplification: the home page is each person's own list.

Every role opens on My work, filled from its own data: Faculty's OK list
and the items handed to Faculty, a head's items and their team's, the Media
and Culturals heads' team items from any ICC or IGP event. Volunteers open
on My activities instead. The rail is four places and a Menu.
"""

import os
import re
import unittest
from datetime import date, datetime, timedelta, timezone

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import OperatingUnit, Person, ProjectSession, ReimbursementEntry, RoleAssignment, TeamAssignment, WorkTask
from app.models.project import AcademicYear, BuddyAssignment, Campus, ProgramType, Project
from app.models.user import User
from app.services.home import build_my_activities, build_my_work, is_view_only
from app.services.navigation import MAX_BOTTOM_NAV_ITEMS, build_nav

TODAY = date.today()


class MyWorkTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="This year", start_date=TODAY - timedelta(days=100), end_date=TODAY + timedelta(days=265), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc_type = ProgramType(name="ICC")
        self.igp_type = ProgramType(name="IGP")
        self.icc = OperatingUnit(code="ICC", name="ICC")
        self.igp = OperatingUnit(code="IGP", name="IGP")
        db.session.add_all([self.year, self.campus, self.icc_type, self.igp_type, self.icc, self.igp])
        db.session.flush()
        self.icc_event = self._project("Coffee meet", self.icc_type, self.icc, TODAY, TODAY)
        self.igp_programme = self._project("Summer school", self.igp_type, self.igp, TODAY + timedelta(days=20), TODAY + timedelta(days=30))
        self.done_event = self._project("Old fair", self.icc_type, self.icc, TODAY - timedelta(days=40), TODAY - timedelta(days=40))
        self.done_event.status = "Completed"

        icc_scope = dict(operating_unit_id=self.icc.id, campus_id=self.campus.id, academic_year_id=self.year.id)
        self.faculty = self._user("faculty", "OIA_FACULTY_ADMINISTRATOR")
        self.events_head = self._user("events", "ICC_EVENTS_HEAD", **icc_scope)
        self.media_head = self._user("media", "ICC_MEDIA_HEAD", **icc_scope)
        self.usc = self._user("usc", "ICC_SECRETARY_USC", **icc_scope)
        self.volunteer = self._user("vol", "VOLUNTEER", campus_id=self.campus.id)

        self.unassigned = self._task(self.icc_event, "Book the hall")
        self.events_item = self._task(self.icc_event, "Call the caterer", team="events")
        self.media_icc = self._task(self.icc_event, "Make the poster", team="media")
        self.media_igp = self._task(self.igp_programme, "Take welcome photos", team="media", due=TODAY + timedelta(days=21))
        self.faculty_item = self._task(self.icc_event, "Sign the letter", team="faculty")
        self.usc_item = self._task(self.icc_event, "Send the minutes", team="usc")
        self.old_item = self._task(self.done_event, "Return the chairs")

        db.session.add(ProjectSession(project_id=self.icc_event.id, code="MAIN", title="Main session", session_type="Event",
                                      starts_at=datetime.now(timezone.utc).replace(hour=12, minute=0), ends_at=datetime.now(timezone.utc).replace(hour=13, minute=0)))
        db.session.add(ReimbursementEntry(project_id=self.icc_event.id, date=TODAY, particular="Snacks", party_name="Canteen", amount=900, status="Asked", created_by_id=self.events_head.id))
        db.session.add(ReimbursementEntry(project_id=self.done_event.id, date=TODAY, particular="Chairs", party_name="Hire shop", amount=1200, status="Paid", created_by_id=self.events_head.id))
        db.session.add(TeamAssignment(project_id=self.icc_event.id, person_id=self.volunteer.person_id, user_id=self.volunteer.id,
                                      assignment_type="Project Team", role_label="Usher", status="Active"))
        self.student = Person(first_name="Ana", last_name="Lima", primary_email="ana@example.test")
        db.session.add(self.student)
        db.session.flush()
        db.session.add(BuddyAssignment(project_id=self.igp_programme.id, buddy_user_id=self.volunteer.id, exchange_student_person_id=self.student.id,
                                       start_date=self.igp_programme.start_date, end_date=self.igp_programme.end_date, status="Active"))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _project(self, title, program_type, unit, start, end):
        project = Project(code=title.upper().replace(" ", "-"), title=title, campus_id=self.campus.id, program_type_id=program_type.id,
                          academic_year_id=self.year.id, operating_unit_id=unit.id, category="Event", status="Active",
                          start_date=start, end_date=end, venue="Main hall")
        db.session.add(project)
        db.session.flush()
        return project

    def _user(self, name, role_code, **scope):
        person = Person(first_name=name.title(), primary_email=f"{name}@christuniversity.in")
        db.session.add(person)
        db.session.flush()
        user = User(username=name, email=person.primary_email, role=role_code, status="Approved", needs_password_reset=False, person_id=person.id)
        user.set_password("A-secure-test-password-2026")
        db.session.add(user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=user.id, role_code=role_code, is_active=True, **scope))
        return user

    def _task(self, project, title, team=None, due=None):
        task = WorkTask(project_id=project.id, title=title, status="Not Started", assigned_team=team,
                        due_at=datetime.combine(due, datetime.min.time(), tzinfo=timezone.utc).replace(hour=6) if due else None)
        db.session.add(task)
        db.session.flush()
        return task

    def _login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    @staticmethod
    def _titles(context):
        return {item.title for group in context["todo_groups"] for item in group["items"]}

    # --- whose items are whose ------------------------------------------

    def test_events_head_gets_unassigned_and_events_team_items_only(self):
        titles = self._titles(build_my_work(self.events_head))
        self.assertEqual(titles, {"Book the hall", "Call the caterer"})

    def test_media_head_gets_media_items_from_icc_and_igp_events(self):
        context = build_my_work(self.media_head)
        self.assertEqual(self._titles(context), {"Make the poster", "Take welcome photos"})
        # Only the events their team has items on, counting only their items.
        self.assertEqual({row["project"].title: row["left"] for row in context["your_events"]}, {"Coffee meet": 1, "Summer school": 1})
        self.assertFalse(context["can_create"])

    def test_faculty_gets_its_own_items_and_the_ok_list(self):
        context = build_my_work(self.faculty)
        self.assertEqual(self._titles(context), {"Sign the letter"})
        self.assertEqual([item["kind"] for item in context["needs_ok"]], ["Money"])

    def test_usc_gets_usc_items_and_nothing_to_approve(self):
        context = build_my_work(self.usc)
        self.assertEqual(self._titles(context), {"Send the minutes"})
        self.assertEqual(context["needs_ok_total"], 0)

    def test_finished_events_leave_the_list(self):
        self.assertNotIn("Return the chairs", self._titles(build_my_work(self.events_head)))

    def test_today_is_open_and_later_is_folded(self):
        groups = build_my_work(self.media_head)["todo_groups"]
        self.assertEqual([(group["key"], group["open"]) for group in groups], [("today", True), ("later", False)])

    def test_an_event_day_offers_take_attendance(self):
        sessions = build_my_work(self.events_head)["todays_sessions"]
        self.assertEqual([session.project.title for session in sessions], ["Coffee meet"])
        self.assertEqual(build_my_work(self.media_head)["todays_sessions"], [])

    # --- the page --------------------------------------------------------

    def test_home_page_ticks_in_one_press_and_comes_back(self):
        self._login(self.events_head)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("things to do</strong> today", html)
        self.assertIn(f'value="t-{self.unassigned.public_id}"', html)
        self.assertIn("Take attendance", html)
        response = self.client.post(f"/erp/projects/{self.icc_event.public_id}/todos/done",
                                    data={"done": f"t-{self.unassigned.public_id}", "next": "/"})
        self.assertEqual(response.headers["Location"], "/")
        self.assertEqual(db.session.get(WorkTask, self.unassigned.id).status, "Completed")

    def test_media_head_can_tick_and_add_a_file_from_home(self):
        self._login(self.media_head)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Make the poster", html)
        self.assertIn("Add file", html)
        self.assertNotIn("Book the hall", html)
        response = self.client.post(f"/erp/projects/{self.igp_programme.public_id}/todos/done",
                                    data={"done": f"t-{self.media_igp.public_id}", "next": "/"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(db.session.get(WorkTask, self.media_igp.id).status, "Completed")

    def test_faculty_approves_money_from_home(self):
        self._login(self.faculty)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Needs your OK", html)
        self.assertIn("1 needs your OK", html)
        entry = ReimbursementEntry.query.filter_by(particular="Snacks").one()
        response = self.client.post(f"/erp/projects/{self.icc_event.public_id}/reimbursements/{entry.public_id}/status",
                                    data={"status": "Approved", "next": "/"})
        self.assertEqual(response.headers["Location"], "/")
        self.assertEqual(db.session.get(ReimbursementEntry, entry.id).status, "Approved")

    def test_volunteer_sees_only_their_activities(self):
        self.assertTrue(is_view_only(self.volunteer))
        activities = build_my_activities(self.volunteer)["activities"]
        self.assertEqual([(row["project"].title, row["job"]) for row in activities], [("Coffee meet", "Usher"), ("Summer school", "Buddy")])
        self.assertEqual(activities[1]["buddies"], ["Ana Lima"])
        self._login(self.volunteer)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("My activities", html)
        self.assertIn("Your job: <strong>Usher</strong>", html)
        self.assertIn("Your buddy: <strong>Ana Lima</strong>", html)
        for hidden in ("Book the hall", "Snacks", "Old fair", "/erp/projects\""):
            self.assertNotIn(hidden, html)

    # --- getting around -------------------------------------------------

    def _bar(self, user):
        return [item["key"] for item in build_nav(user, "dashboard.index", "dashboard") if item["bottom_nav"]]

    def test_the_phone_bar_is_four_places_at_most(self):
        with self.app.test_request_context("/"):
            self.assertEqual(self._bar(self.faculty), ["home", "projects", "new", "reports"])
            self.assertEqual(self._bar(self.usc), ["home", "projects", "new", "reports"])
            self.assertEqual(self._bar(self.events_head), ["home", "projects", "new", "profile"])
            self.assertEqual(self._bar(self.media_head), ["home", "projects", "profile"])
            self.assertEqual(self._bar(self.volunteer), ["home", "profile"])
            for user in (self.faculty, self.events_head, self.volunteer):
                self.assertLessEqual(len(self._bar(user)), MAX_BOTTOM_NAV_ITEMS)

    def test_every_rail_icon_has_a_mask_rule(self):
        # The rail's icons are named in Python, where the template icon check
        # cannot see them; one without a rule draws as a solid square.
        from pathlib import Path

        from app.services.navigation import NAV_REGISTRY

        css = Path(self.app.root_path, "static/css/icons.css").read_text()
        missing = [entry["icon"] for entry in NAV_REGISTRY if not re.search(rf"\.{entry['icon']}\b", css)]
        self.assertEqual(missing, [])

    def test_reports_is_for_faculty_and_usc(self):
        for user, status in ((self.faculty, 200), (self.usc, 200), (self.events_head, 403), (self.volunteer, 403)):
            with self.subTest(user=user.username):
                self._login(user)
                self.assertEqual(self.client.get("/reports").status_code, status)
        self._login(self.faculty)
        html = self.client.get("/reports").get_data(as_text=True)
        self.assertIn("Old fair", html)
        self.assertRegex(html, r"Money paid</dt>\s*<dd>[^<]*1,200")

    def test_old_addresses_redirect(self):
        self._login(self.faculty)
        self.assertTrue(self.client.get("/erp/analytics").headers["Location"].endswith("/reports"))
        self._login(self.events_head)
        self.assertTrue(self.client.get("/erp/analytics/icc").headers["Location"].endswith("/erp/projects"))
        self.assertTrue(self.client.get("/queue").headers["Location"].endswith("/"))

    def test_events_list_reaches_contributor_events_and_hides_finished(self):
        self._login(self.media_head)
        html = self.client.get("/erp/projects").get_data(as_text=True)
        self.assertIn("Summer school", html)
        self._login(self.events_head)
        html = self.client.get("/erp/projects").get_data(as_text=True)
        self.assertIn("Coffee meet", html)
        self.assertNotIn("Old fair", html)
        self.assertIn("Old fair", self.client.get("/erp/projects?show=finished").get_data(as_text=True))

    def test_faculty_makes_someone_a_head_with_one_choice(self):
        self._login(self.faculty)
        html = self.client.get("/admin/users", query_string={"q": "vol"}).get_data(as_text=True)
        self.assertIn("vol@christuniversity.in", html)
        self.assertNotIn("academic_year_public_id", html)
        response = self.client.post(f"/admin/users/modify-role/{self.volunteer.id}", data={"role": "ICC Culturals Head"})
        self.assertEqual(response.status_code, 302)
        assignment = RoleAssignment.query.filter_by(user_id=self.volunteer.id, is_active=True).one()
        self.assertEqual(assignment.role_code, "ICC_CULTURALS_HEAD")
        self.assertEqual(assignment.academic_year_id, self.year.id)

    def test_onboarding_tour_is_three_steps_at_most(self):
        from app.services.roles import ONBOARDING_TOURS

        for audience, steps in ONBOARDING_TOURS.items():
            with self.subTest(audience=audience):
                self.assertLessEqual(len(steps), 3)
        self._login(self.media_head)
        html = self.client.get("/").get_data(as_text=True)
        steps = re.search(r'"steps": (\[.*?\])\}</script>', html).group(1)
        self.assertIn('"target": "file"', steps)


if __name__ == "__main__":
    unittest.main()
