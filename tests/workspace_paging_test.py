"""The event workspace is a strip of sections with one of them open, paged.

Three things were wrong with the workspace this replaced, and each one has a
test here.

*Information overload.* A tab rendered every list it owned at once: Logistics
printed the fact strip, the tasks, every checklist and the schedule; People
printed five lists in a row. ``test_a_tab_opens_one_section_at_a_time`` and
``test_the_section_strip_carries_every_section_of_the_tab`` pin the drill-down
that replaced it.

*The screen scrolled*, which the Tile System's one-screen rule forbids
outright. ``test_a_work_tab_declares_no_scroll_container`` is the structural
half of that rule; the geometric half -- that a page of rows fits the viewport
-- is measured in the browser by ``e2e/``.

*Nothing was reachable any more once it was paged.* That is the real risk of
pagination in a workflow tool, so it gets the most tests: a page argument is
clamped rather than trusted, `focus` resolves a record to the section and page
that hold it, and every form inside a panel posts `next` so a decision returns
to where it was taken.
"""

import os
import unittest
from datetime import date, datetime, timedelta

os.environ["TESTING"] = "true"

from app import create_app
from app.database import db
from app.models.erp import BudgetLine, RoleAssignment, WorkTask
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.paging import PAGE_SIZE, Page, page_of, paginate


class PaginateUnitTestCase(unittest.TestCase):
    """`paginate` takes its page number from a URL, so it never trusts it."""

    def test_a_short_list_is_one_page(self):
        page = paginate(["a", "b"], None)
        self.assertEqual(page.items, ["a", "b"])
        self.assertEqual((page.number, page.pages, page.total), (1, 1, 2))
        self.assertEqual((page.first, page.last), (1, 2))
        self.assertFalse(page.multi)

    def test_an_empty_list_still_has_a_first_page(self):
        page = paginate([], 3)
        self.assertEqual((page.items, page.number, page.pages, page.total), ([], 1, 1, 0))
        # Not "1-0 of 0": the template prints "Nothing here yet" instead.
        self.assertEqual(page.first, 0)

    def test_an_unusable_page_argument_resolves_to_a_real_page(self):
        items = list(range(20))
        for argument in (None, "", "two", 0, -4, 99, "99"):
            with self.subTest(page=argument):
                page = paginate(items, argument, per_page=8)
                self.assertIn(page.number, range(1, page.pages + 1))
                self.assertTrue(page.items)

    def test_the_last_page_holds_the_remainder(self):
        page = paginate(list(range(21)), 3, per_page=8)
        self.assertEqual(page.items, [16, 17, 18, 19, 20])
        self.assertEqual((page.first, page.last, page.pages), (17, 21, 3))
        self.assertTrue(page.has_prev)
        self.assertFalse(page.has_next)

    def test_a_long_pager_elides_rather_than_drawing_fifty_links(self):
        page = Page(items=[], number=25, pages=50, total=400, per_page=8)
        self.assertEqual(page.numbers, [1, None, 24, 25, 26, None, 50])
        self.assertEqual(Page(items=[], number=1, pages=5, total=40, per_page=8).numbers, [1, 2, 3, 4, 5])

    def test_page_of_finds_the_page_a_record_lands_on(self):
        class Row:
            def __init__(self, public_id):
                self.public_id = public_id

        rows = [Row(f"r{n}") for n in range(20)]
        self.assertEqual(page_of(rows, "r0", 8), 1)
        self.assertEqual(page_of(rows, "r8", 8), 2)
        self.assertEqual(page_of(rows, "r19", 8), 3)
        self.assertIsNone(page_of(rows, "not-here", 8))
        self.assertIsNone(page_of(rows, None, 8))


class WorkspaceSectionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.program_type = ProgramType(name="ICC")
        db.session.add_all([year, self.campus, self.program_type])
        db.session.flush()

        self.project = Project(
            code="ICC-2026-CEN-900", campus_id=self.campus.id, program_type_id=self.program_type.id,
            academic_year_id=year.id, title="Paging test event", category="Operational",
            status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
        )
        db.session.add(self.project)
        db.session.flush()

        # Twenty tasks: enough for three pages at PAGE_SIZE 8, and enough that
        # a record on the last page is genuinely off the first one.
        self.tasks = [
            WorkTask(project_id=self.project.id, title=f"Task {n:02d}", status="In Progress",
                     due_at=datetime(2026, 8, 1) + timedelta(days=n), version=1)
            for n in range(20)
        ]
        db.session.add_all(self.tasks)
        db.session.add(BudgetLine(project_id=self.project.id, category="Venue", description="Hall",
                                  estimated_amount=1000, status="Draft", version=1))

        self.manager = User(username="manager", email="manager@example.com", role="Faculty",
                            status="Approved", needs_password_reset=False)
        self.manager.set_password("A-secure-test-password-2026")
        db.session.add(self.manager)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.manager.id, role_code="OIA_FACULTY_ADMINISTRATOR",
                                      is_active=True, can_view_sensitive_links=True))
        db.session.commit()
        self.login()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.manager.id
            session["session_version"] = self.manager.session_version

    def get(self, **query):
        response = self.client.get(f"/erp/projects/{self.project.public_id}", query_string=query)
        self.assertEqual(response.status_code, 200, query)
        return response.get_data(as_text=True)

    # ── Sections ────────────────────────────────────────────────────────

    def test_the_section_strip_carries_every_section_of_the_tab(self):
        html = self.get(tab="logistics")
        for label in ("Details", "Tasks", "Schedule"):
            self.assertIn(f'<span class="ds-section__label">{label}</span>', html)
        self.assertIn('class="ds-sections"', html)

    def test_a_tab_opens_one_section_at_a_time(self):
        """The whole point of the strip. Opening Tasks must not also print the
        schedule, or the drill-down has bought nothing."""
        html = self.get(tab="logistics", section="tasks")
        self.assertIn("Task 00", html)
        self.assertNotIn('<span>Session</span>', html)

        html = self.get(tab="logistics", section="schedule")
        self.assertNotIn("Task 00", html)
        self.assertIn('<span>Session</span>', html)

    def test_an_unknown_section_falls_back_to_the_tab_s_first(self):
        html = self.get(tab="logistics", section="not-a-section")
        self.assertIn('class="ds-section ds-section--pine is-active"', html)
        self.assertIn('<span class="ds-section__label">Details</span>', html)

    def test_the_open_section_is_the_only_one_marked_current(self):
        html = self.get(tab="logistics", section="tasks")
        self.assertEqual(html.count('aria-current="true"'), 1)

    def test_a_work_tab_declares_no_scroll_container(self):
        """The structural half of the one-screen rule. `.ds-scroll` is the
        only element allowed to move, and a paged section does not need one --
        a tab that still had one would be scrolling again."""
        for tab in ("logistics", "finance", "documents", "people"):
            with self.subTest(tab=tab):
                self.assertNotIn('class="ds-scroll"', self.get(tab=tab))

    # ── Paging ──────────────────────────────────────────────────────────

    def test_a_section_shows_one_page_of_rows_and_a_pager(self):
        html = self.get(tab="logistics", section="tasks")
        self.assertEqual(html.count('class="ds-row ds-row--'), PAGE_SIZE)
        self.assertIn("Task 00", html)
        self.assertNotIn("Task 19", html)
        self.assertIn(f"of {len(self.tasks)}", html)
        self.assertIn('class="ds-pager"', html)

    def test_the_last_page_holds_the_rest(self):
        html = self.get(tab="logistics", section="tasks", page=3)
        self.assertIn("Task 19", html)
        self.assertNotIn("Task 00", html)
        self.assertIn('<span class="ds-pager__range">17–20</span>', html)

    def test_a_nonsense_page_argument_never_errors(self):
        for argument in ("0", "-1", "500", "two", ""):
            with self.subTest(page=argument):
                self.assertIn('class="ds-pager"', self.get(tab="logistics", section="tasks", page=argument))

    def test_a_single_page_keeps_its_count_and_drops_the_steps(self):
        """"1-1 of 1" is what tells the reader nothing is hidden behind a
        pager that has nowhere to go."""
        html = self.get(tab="finance", section="budget")
        self.assertIn('<span class="ds-pager__range">1–1</span>', html)
        self.assertNotIn('class="ds-pager__steps"', html)

    # ── Reachability ────────────────────────────────────────────────────

    def test_focus_opens_the_section_and_page_holding_the_record(self):
        """A deep link from the decision queue names a record, not a page.
        Landing on page 1 of a list the row is not in is the same as not
        arriving at all."""
        html = self.get(tab="logistics", focus=self.tasks[19].public_id)
        self.assertIn("Task 19", html)
        self.assertIn('<span class="ds-pager__range">17–20</span>', html)

    def test_focus_crosses_sections_within_the_tab(self):
        html = self.get(tab="finance", focus=self.project.budget_lines[0].public_id)
        self.assertIn('<span class="ds-section__label">Budget</span>', html)
        self.assertIn("Hall", html)

    def test_focus_resolves_the_publication_anchor(self):
        """Public disclosure holds no records, so `focus` cannot find it by
        public_id -- the decision queue's publication row points at the
        literal anchor instead."""
        html = self.get(tab="documents", focus="publication")
        self.assertIn('id="publication"', html)

    def test_an_unknown_focus_falls_back_rather_than_failing(self):
        """A truncated or stale link still opens the tab's first section
        rather than erroring."""
        html = self.get(tab="logistics", focus="no-such-record")
        self.assertIn('<span class="ds-section__label">Details</span>', html)
        self.assertIn('class="ds-section ds-section--pine is-active"', html)

    def test_a_decision_form_posts_back_the_page_it_was_taken_on(self):
        """`next` is honoured by `_redirect_to_tab`, so saving returns to the
        section and page the reader was on rather than to page 1 of the tab's
        first section."""
        html = self.get(tab="logistics", section="tasks", page=2)
        self.assertIn(
            f'<input type="hidden" name="next" value="/erp/projects/{self.project.public_id}'
            "?tab=logistics&amp;section=tasks&amp;page=2\">",
            html,
        )

    def test_saving_returns_to_the_section_and_page_it_came_from(self):
        task = self.tasks[10]
        target = f"/erp/projects/{self.project.public_id}?tab=logistics&section=tasks&page=2"
        response = self.client.post(
            f"/erp/projects/{self.project.public_id}/tasks/{task.public_id}/status",
            data={"version": task.version, "status": "Completed", "comment": "", "next": target},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], target)

    # ── Dialogs ─────────────────────────────────────────────────────────

    def test_an_add_form_is_a_target_dialog_rather_than_an_inline_disclosure(self):
        """The sixteen foot-forms were most of the reason a tab could not fit
        one viewport. The dialog opens on the URL fragment alone, so it needs
        no JavaScript and no inline handler -- the CSP would kill the second
        and `tests/ui_contract_test.py` forbids it."""
        html = self.get(tab="logistics", section="tasks")
        self.assertIn('href="#m-task-add"', html)
        self.assertIn('<div class="ds-modal" id="m-task-add"', html)
        self.assertNotIn("data-ui-target=\"#collapseTaskAdd\"", html)

    def test_a_dialog_is_absent_when_its_trigger_is(self):
        """A reader who cannot add a task should not carry a hidden form for
        adding one."""
        html = self.get(tab="logistics", section="schedule")
        self.assertNotIn('id="m-task-add"', html)


if __name__ == "__main__":
    unittest.main()
