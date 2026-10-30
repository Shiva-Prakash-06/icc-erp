"""The rebuilt event page: one to-do list and folded cards.

Each test is one thing a person does on the page, written the way they do
it: tick something off, skip it, take it off the list and put it back,
paste a list of names, ask for money, add a file, share a feedback link.
"""

import io
import os
import re
import unittest
from datetime import date, datetime, timedelta, timezone

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import (
    DocumentRecord,
    FeedbackForm,
    FeedbackResponse,
    OperatingUnit,
    Person,
    ReimbursementEntry,
    RoleAssignment,
    TeamAssignment,
    WorkTask,
)
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.people import parse_people_list
from app.services.stage import event_stage


class StageTestCase(unittest.TestCase):
    def _project(self, start, end, status="Active", **extra):
        return Project(start_date=start, end_date=end, status=status, **extra)

    def test_stages_come_from_dates(self):
        today = date(2026, 9, 10)
        self.assertEqual(event_stage(self._project(date(2026, 9, 12), date(2026, 9, 12)), today), "coming_up")
        self.assertEqual(event_stage(self._project(date(2026, 9, 9), date(2026, 9, 11)), today), "happening")
        self.assertEqual(event_stage(self._project(date(2026, 9, 1), date(2026, 9, 2)), today), "needs_finishing")
        self.assertEqual(event_stage(self._project(date(2026, 9, 1), date(2026, 9, 2), finish_requested_at=datetime.now(timezone.utc)), today), "waiting")
        self.assertEqual(event_stage(self._project(date(2026, 9, 1), date(2026, 9, 2), status="Completed"), today), "finished")
        self.assertEqual(event_stage(self._project(date(2026, 9, 12), date(2026, 9, 12), status="Cancelled"), today), "cancelled")


class PasteListTestCase(unittest.TestCase):
    def test_reads_names_emails_numbers_and_jobs_in_any_order(self):
        rows = parse_people_list(
            "Name\tEmail\n"
            "Asha Rao\n"
            "Rahul Dsouza, rahul.d@christuniversity.in\n"
            "Zoya Khan\t2312345\tBuddy\n"
            "\n"
            "zoya@christuniversity.in\n"
        )
        self.assertEqual([(r["name"], r["email"], r["reg_no"], r["job"]) for r in rows], [
            ("Asha Rao", None, None, None),
            ("Rahul Dsouza", "rahul.d@christuniversity.in", None, None),
            ("Zoya Khan", None, "2312345", "Buddy"),
            ("", "zoya@christuniversity.in", None, None),
        ])


class EventPageTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc = ProgramType(name="ICC")
        self.unit = OperatingUnit(code="ICC", name="ICC")
        db.session.add_all([self.year, self.campus, self.icc, self.unit])
        db.session.flush()
        self.project = Project(
            code="ICC-2026-CEN-800", campus_id=self.campus.id, program_type_id=self.icc.id,
            academic_year_id=self.year.id, operating_unit_id=self.unit.id, title="Welcome mixer",
            category="Operational", status="Active", venue="Quad",
            start_date=date.today() + timedelta(days=5), end_date=date.today() + timedelta(days=5),
        )
        db.session.add(self.project)
        db.session.flush()
        self.head = self._user("head", "ICC_EVENTS_HEAD", operating_unit_id=self.unit.id, campus_id=self.campus.id, academic_year_id=self.year.id)
        self.media = self._user("media", "ICC_MEDIA_HEAD", operating_unit_id=self.unit.id, campus_id=self.campus.id, academic_year_id=self.year.id)
        self.volunteer = self._user("vol", "VOLUNTEER", campus_id=self.campus.id)
        db.session.commit()
        self.url = f"/erp/projects/{self.project.public_id}"

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

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

    def login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.id
            session["session_version"] = user.session_version

    def _task(self, title, **extra):
        task = WorkTask(project_id=self.project.id, title=title, status="Not Started", **extra)
        db.session.add(task)
        db.session.commit()
        return task

    # --- To do -----------------------------------------------------------

    def test_one_press_marks_an_item_done(self):
        task = self._task("Book the hall")
        self.login(self.head)
        response = self.client.post(self.url + "/todos/done", data={"done": f"t-{task.public_id}"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.status, "Completed")
        page = self.client.get(self.url).get_data(as_text=True)
        self.assertIn("✓ 1 done", page)
        self.assertIn("nothing left to do", page)

    def test_several_items_can_be_ticked_together(self):
        first, second, third = self._task("One"), self._task("Two"), self._task("Three")
        self.login(self.head)
        self.client.post(self.url + "/todos/done", data={"items": [f"t-{first.public_id}", f"t-{second.public_id}"]})
        self.assertEqual([first.status, second.status, third.status], ["Completed", "Completed", "Not Started"])

    def test_skipping_needs_a_reason_and_counts_as_done(self):
        task = self._task("Print banners")
        self.login(self.head)
        self.client.post(self.url + f"/todos/t-{task.public_id}/skip", data={"reason": ""})
        self.assertEqual(task.status, "Not Started")
        self.client.post(self.url + f"/todos/t-{task.public_id}/skip", data={"reason": "No budget this year"})
        self.assertTrue(task.waived)
        self.assertIn("Skipped: No budget this year", self.client.get(self.url).get_data(as_text=True))

    def test_removing_offers_undo_and_undo_puts_it_back(self):
        task = self._task("Order cake")
        self.login(self.head)
        self.client.post(self.url + f"/todos/t-{task.public_id}/remove")
        page = self.client.get(self.url).get_data(as_text=True)
        self.assertIn("Removed “Order cake”.", page)
        self.assertIn(f"/todos/t-{task.public_id}/restore", page)
        self.assertNotIn(f'id="t-{task.public_id}"', page)
        # The offer is shown once, not on every later page.
        self.assertNotIn("Removed “Order cake”.", self.client.get(self.url).get_data(as_text=True))
        self.client.post(self.url + f"/todos/t-{task.public_id}/restore")
        self.assertEqual(task.status, "Not Started")

    def test_adding_an_item_for_a_team(self):
        self.login(self.head)
        self.client.post(self.url + "/tasks", data={"title": "Design the poster", "who": "media", "due": "2026-12-01"})
        task = WorkTask.query.filter_by(title="Design the poster").one()
        self.assertEqual(task.assigned_team, "media")
        self.assertIsNotNone(task.due_at)

    def test_media_head_ticks_their_teams_item_but_nothing_else(self):
        poster = self._task("Design the poster", assigned_team="media")
        venue = self._task("Book the hall")
        self.login(self.media)
        page = self.client.get(self.url).get_data(as_text=True)
        self.assertIn("Design the poster", page)
        self.assertNotIn("Book the hall", page)
        self.client.post(self.url + "/todos/done", data={"done": f"t-{venue.public_id}"})
        self.assertEqual(venue.status, "Not Started")
        self.client.post(self.url + "/todos/done", data={"done": f"t-{poster.public_id}"})
        self.assertEqual(poster.status, "Completed")
        self.assertEqual(self.client.post(self.url + f"/todos/t-{poster.public_id}/remove").status_code, 403)

    def test_adding_the_file_an_item_asks_for_ticks_it(self):
        poster = self._task("Upload the poster", assigned_team="media")
        self.login(self.media)
        self.client.post(self.url + f"/todos/t-{poster.public_id}/file",
                         data={"file": (io.BytesIO(b"png-bytes"), "poster.png")}, content_type="multipart/form-data")
        self.assertEqual(poster.status, "Completed")
        document = DocumentRecord.query.filter_by(project_id=self.project.id).one()
        self.assertEqual(poster.evidence_reference, document.public_id)

    def test_a_list_shows_five_then_show_all(self):
        for number in range(7):
            self._task(f"Item {number}")
        self.login(self.head)
        page = self.client.get(self.url).get_data(as_text=True)
        self.assertEqual(len(re.findall(r'<li class="cv-item" id="t-', page)), 5)
        self.assertIn("Show all 7", page)
        page = self.client.get(self.url + "?card=todo&all=1").get_data(as_text=True)
        self.assertEqual(len(re.findall(r'<li class="cv-item" id="t-', page)), 7)

    # --- People ----------------------------------------------------------

    def test_pasting_a_list_adds_everyone_once(self):
        self.login(self.head)
        self.client.post(self.url + "/team/paste", data={"people": "Asha Rao\nRahul Dsouza, rahul@christuniversity.in", "job": "Volunteer"})
        response = self.client.post(self.url + "/team/paste", data={"people": "Rahul Dsouza, rahul@christuniversity.in"}, follow_redirects=True)
        self.assertIn(b"1 already on the list", response.data)
        names = sorted(a.person.display_name for a in TeamAssignment.query.filter_by(project_id=self.project.id))
        self.assertEqual(names, ["Asha Rao", "Rahul Dsouza"])

    def test_a_listed_volunteer_sees_only_their_part(self):
        db.session.add(TeamAssignment(person_id=self.volunteer.person_id, project_id=self.project.id,
                                      assignment_type="Project Team", role_label="Buddy"))
        db.session.add(TeamAssignment(person_id=self.head.person_id, project_id=self.project.id, assignment_type="Project Team"))
        self._task("Book the hall")
        self.login(self.volunteer)
        page = self.client.get(self.url).get_data(as_text=True)
        self.assertIn("Your job", page)
        self.assertIn("Buddy", page)
        for hidden in ("Book the hall", "Head", "card-money", "To do"):
            self.assertNotIn(hidden, page)

    # --- Money -----------------------------------------------------------

    def test_asking_for_money_takes_what_and_how_much(self):
        self.login(self.head)
        response = self.client.post(self.url + "/reimbursements", data={"particular": "Banner printing", "amount": "₹1,200"})
        self.assertEqual(response.status_code, 302)
        entry = ReimbursementEntry.query.filter_by(project_id=self.project.id).one()
        self.assertEqual((entry.particular, float(entry.amount), entry.status, entry.date), ("Banner printing", 1200.0, "Asked", date.today()))
        self.client.post(self.url + f"/reimbursements/{entry.public_id}/remove")
        self.assertEqual(entry.status, "Removed")
        self.assertNotIn(f'id="{entry.public_id}"', self.client.get(self.url + "?card=money").get_data(as_text=True))
        self.client.post(self.url + f"/reimbursements/{entry.public_id}/restore")
        self.assertEqual(entry.status, "Asked")

    def test_a_blank_money_sheet_downloads(self):
        self.login(self.head)
        response = self.client.get(self.url + "/templates/money.xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"PK"))

    # --- Files -----------------------------------------------------------

    def test_a_file_is_stored_as_what_the_person_says_it_is(self):
        self.login(self.head)
        self.client.post(self.url + "/files", data={"kind": "report", "files": (io.BytesIO(b"pdf"), "notes.pdf")},
                         content_type="multipart/form-data")
        document = DocumentRecord.query.filter_by(project_id=self.project.id).one()
        self.assertEqual(document.category, "Event Report")
        page = self.client.get(self.url).get_data(as_text=True)
        self.assertIn("event report added ✓", page)

    def test_a_drive_link_can_be_added_in_the_same_box(self):
        self.login(self.head)
        self.client.post(self.url + "/files", data={"kind": "photos", "drive_url": "https://drive.google.com/file/d/abcdefghijk123/view"})
        document = DocumentRecord.query.filter_by(project_id=self.project.id).one()
        self.assertEqual((document.category, document.title), ("Images/Photos", "Photos"))

    # --- Feedback --------------------------------------------------------

    def test_a_feedback_link_is_answered_without_signing_in(self):
        self.login(self.head)
        self.client.post(self.url + "/feedback-link", data={"questions": "What was best?"})
        form = FeedbackForm.query.filter_by(project_id=self.project.id).one()
        self.assertTrue(form.public_token)
        anonymous = self.app.test_client()
        page = anonymous.get(f"/public/feedback/{form.public_token}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"What was best?", page.data)
        self.assertEqual(anonymous.post(f"/public/feedback/{form.public_token}", data={}).status_code, 422)
        anonymous.post(f"/public/feedback/{form.public_token}", data={"rating": "5", "q_1": "The music"})
        response = FeedbackResponse.query.filter_by(form_id=form.id).one()
        self.assertEqual((response.answers_json["rating"], response.moderation_status), (5, "Approved"))
        self.client.post(self.url + "/feedback-link/close")
        self.assertIn(b"closed", anonymous.get(f"/public/feedback/{form.public_token}").data)
        self.assertEqual(anonymous.get("/public/feedback/not-a-token").status_code, 404)


if __name__ == "__main__":
    unittest.main()
