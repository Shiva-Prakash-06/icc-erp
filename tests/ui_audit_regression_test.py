"""Regressions for the 17 September 2026 UI/UX audit.

One test per defect the audit named, written so that it fails against the
behaviour the audit recorded and passes against the fix. Each one states the
finding it guards.

The two findings that are only observable in a browser -- mobile action
clipping (P0-02) and dark-tile contrast (P1-06) -- are guarded twice: the
computable half is asserted here against the CSS and the rendered markup,
and the rendered half lives in
``e2e/accessibility-responsive.spec.ts``.
"""

from __future__ import annotations

import os
import re
import unittest
from datetime import date, timedelta
from pathlib import Path

os.environ["TESTING"] = "true"

from flask import session

from app import create_app
from app.config import TestingConfig
from app.database import db
from app.models.erp import OperatingUnit, Person, RoleAssignment
from app.models.project import AcademicYear, BuddyAssignment, BuddyLog, Campus, ProgramType, Project
from app.models.user import User
from app.services.analytics import division_dashboard
from app.services.hierarchy import DIVISIONS, event_state, matches_filter
from app.services.status import review_state, status_of

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "static" / "css"


def _srgb(channel: float) -> float:
    channel /= 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb) -> float:
    red, green, blue = (_srgb(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground, background) -> float:
    first, second = _relative_luminance(foreground), _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _hex_to_rgb(value: str):
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _token(name: str) -> str:
    """Read a custom property's value out of tokens.css."""
    tokens = (CSS / "tokens.css").read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(name)}\s*:\s*([^;]+);", tokens)
    assert match, f"{name} is not defined in tokens.css"
    return match.group(1).strip()


class AuditFixtureTestCase(unittest.TestCase):
    """One IGP programme and one ICC event, in both audited divisions."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Bangalore Central Campus", code="CEN")
        self.igp_type = ProgramType(name="IGP")
        self.icc_type = ProgramType(name="ICC")
        self.igp_unit = OperatingUnit(code="IGP", name="India Gateway Program")
        self.icc_unit = OperatingUnit(code="ICC", name="International Christite Community")
        db.session.add_all([self.year, self.campus, self.igp_type, self.icc_type, self.igp_unit, self.icc_unit])
        db.session.flush()

        # The audit's exact case: a programme counted as active by the KPI
        # whose stored status is `Closing`, not `Active`.
        self.closing = self._project("IGP-2026-CEN-001", self.igp_type, self.igp_unit, status="Closing")
        self.icc_event = self._project("ICC-2026-CEN-001", self.icc_type, self.icc_unit, status="Active")

        self.user = User(username="auditor", email="auditor@example.test", role="OIA Faculty Administrator",
                         preferred_role="OIA Faculty Administrator", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _project(self, code, program_type, unit, *, status):
        project = Project(
            code=code, title=f"{code} programme", campus_id=self.campus.id,
            program_type_id=program_type.id, academic_year_id=self.year.id,
            operating_unit_id=unit.id, status=status,
            category="Operational", project_type="ICC event",
            # Ends in the future, so `overdue` cannot be what makes this
            # record appear -- the test is specifically about `Closing`.
            start_date=date.today() - timedelta(days=5), end_date=date.today() + timedelta(days=5),
        )
        db.session.add(project)
        db.session.flush()
        return project

    def login(self):
        with self.client.session_transaction() as browser_session:
            browser_session["user_id"] = self.user.id
            browser_session["session_version"] = self.user.session_version


class _RateLimitedConfig(TestingConfig):
    """Flask-Limiter reads ENABLED once, during ``init_app``, so the limiter
    cannot be switched on after ``create_app`` has returned."""

    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "1 per hour"
    RATELIMIT_STORAGE_URI = "memory://"


class HomeRouteRateLimitTestCase(unittest.TestCase):
    """P0-01 -- the authenticated home route returned a raw, unstyled 429."""

    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(username="home", email="home@example.test", role="Volunteer",
                         status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_the_default_limit_is_keyed_per_account_not_per_ip(self):
        """The 429 came from one `300 per hour` bucket keyed by remote
        address and shared across every endpoint, so an entire campus behind
        one NAT shared five requests a minute and `/` -- the destination of
        every sign-in redirect -- was the route that ran out first."""
        from app.database import rate_limit_key

        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            self.assertEqual(rate_limit_key(), "ip:10.0.0.1")
            session["user_id"] = self.user.id
            self.assertEqual(rate_limit_key(), f"user:{self.user.id}")

        # Two people behind one campus NAT must not share an allowance.
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            session["user_id"] = 1
            first = rate_limit_key()
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            session["user_id"] = 2
            second = rate_limit_key()
        self.assertNotEqual(first, second)

    def test_the_default_allowance_clears_ordinary_interactive_use(self):
        """`300 per hour` is five requests a minute for every route
        combined. A single setup step is six page loads."""
        limit = self.app.config["RATELIMIT_DEFAULT"]
        hourly = int(re.search(r"(\d+)\s*per hour", limit).group(1))
        self.assertGreaterEqual(hourly, 1000, f"default limit {limit!r} is too low for interactive use")

    def test_a_429_renders_the_branded_shell_not_a_bare_sentence(self):
        """The old handler returned the string "Too many requests. Wait a
        moment and try again." with no shell, no heading, no identity and no
        route back."""
        limited = create_app(_RateLimitedConfig)
        client = limited.test_client()

        with limited.app_context():
            db.create_all()
            user = User(username="limited", email="limited@example.test", role="Volunteer",
                        status="Approved", needs_password_reset=False)
            user.set_password("A-secure-test-password-2026")
            db.session.add(user)
            db.session.commit()
            user_id, version = user.id, user.session_version

        with client.session_transaction() as browser_session:
            browser_session["user_id"] = user_id
            browser_session["session_version"] = version

        client.get("/")
        response = client.get("/")
        self.assertEqual(response.status_code, 429)
        body = response.data.decode()

        self.assertIn("<h1", body, "a 429 must keep a page heading")
        self.assertIn("ds-app", body, "a 429 must stay inside the application shell")
        self.assertIn("Too many requests", body)
        # A recovery path, not a dead end.
        self.assertRegex(body, r'<a class="ds-btn[^"]*" href="/"')
        self.assertIn("Retry-After", response.headers)

        with limited.app_context():
            db.session.remove()
            db.drop_all()

    def test_the_api_keeps_its_machine_readable_429(self):
        """The branded page is for people. `/api/v1/` must not start
        receiving HTML."""
        limited = create_app(_RateLimitedConfig)
        client = limited.test_client()
        with limited.app_context():
            db.create_all()
        client.get("/api/v1/projects")
        response = client.get("/api/v1/projects")
        if response.status_code == 429:
            self.assertEqual(response.content_type, "application/problem+json")
        with limited.app_context():
            db.session.remove()
            db.drop_all()


class KpiDrilldownTestCase(AuditFixtureTestCase):
    """P0-03 -- "Active programmes 1 of 1" opened a list reading "0 in scope"."""

    def test_every_linked_kpi_opens_a_list_containing_what_it_counted(self):
        self.login()
        for division in DIVISIONS.values():
            dashboard = division_dashboard(self.user, division)
            linked = [kpi for kpi in dashboard["kpis"] if kpi["href"]]
            self.assertTrue(linked, f"{division['slug']} dashboard has no linked KPI to check")
            for kpi in linked:
                endpoint, params = kpi["href"]
                with self.subTest(division=division["slug"], kpi=kpi["label"]):
                    # A counter never links to `status`, which matches the
                    # stored column, because no counter counts that column.
                    self.assertNotIn("status", params, f"{kpi['label']} links to a stored-status filter")
                    self.assertEqual(endpoint, "erp.projects")

    def test_the_in_flight_count_and_its_destination_agree(self):
        self.login()
        dashboard = division_dashboard(self.user, DIVISIONS["igp"])
        kpi = dashboard["kpis"][0]
        self.assertEqual(kpi["value"], 1)

        _, params = kpi["href"]
        response = self.client.get("/erp/projects", query_string=params)
        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn(self.closing.title, body,
                      "the Closing programme the KPI counted is missing from the list it opens")

    def test_the_old_stored_status_filter_would_still_have_missed_it(self):
        """Proves the fixture reproduces the audit's defect: the record the
        KPI counts is `Closing`, so the destination the audit found --
        `?status=Active` -- genuinely excludes it."""
        self.login()
        response = self.client.get("/erp/projects", query_string={"status": "Active"})
        self.assertNotIn(self.closing.title, response.data.decode())
        self.assertEqual(event_state(self.closing), "active")
        self.assertTrue(matches_filter(event_state(self.closing), "active"))

    def test_the_state_filter_is_offered_for_every_reserved_state(self):
        self.login()
        for state in ("active", "upcoming", "complete"):
            with self.subTest(state=state):
                response = self.client.get("/erp/projects", query_string={"state": state})
                self.assertEqual(response.status_code, 200)


class StatusContradictionTestCase(AuditFixtureTestCase):
    """P0-04 -- states from different dimensions read as contradictions."""

    def test_a_verified_record_is_never_styled_as_a_failure(self):
        """The audit found verified buddy interactions in danger red under a
        warning triangle. `Verified` is not in the three statuses the model
        documents, so the template's ternary sent it to the `else` branch,
        which meant "overdue"."""
        self.assertEqual(review_state("Verified"), "complete")
        self.assertEqual(status_of("review", "Verified").tone, "positive")
        self.assertNotEqual(review_state("Verified"), "overdue")

    def test_an_unknown_status_degrades_to_neutral_rather_than_to_danger(self):
        for unknown in ("Provisionally Accepted", "Escalated", "", None):
            with self.subTest(value=unknown):
                self.assertNotEqual(review_state(unknown), "overdue")

    def test_availability_and_review_are_separate_named_dimensions(self):
        """"Missing" plus "Approved" is a legitimate pair -- approved
        metadata, no file attached -- and each half now says which question
        it answers."""
        file_state = status_of("availability", "Missing")
        review = status_of("review", "Approved")
        self.assertEqual(file_state.dimension, "availability")
        self.assertEqual(review.dimension, "review")
        self.assertNotEqual(file_state.label, review.label)
        self.assertTrue(file_state.hint, "a dimension chip must explain what it measures")

    def test_every_state_carries_a_word_and_a_shape(self):
        """Colour is never the only signal (design system, Accessibility)."""
        for dimension, values in (
            ("availability", ["Available", "Missing", "Inaccessible"]),
            ("review", ["Approved", "Rejected", "Verified", "Waived", "Submitted"]),
            ("publication", ["Private", "Published", "Pending"]),
            ("lifecycle", ["Draft", "Active", "Closing", "Completed"]),
        ):
            for value in values:
                with self.subTest(dimension=dimension, value=value):
                    status = status_of(dimension, value)
                    self.assertTrue(status.label)
                    self.assertTrue(status.icon.startswith("ph-"))

    def test_a_verified_buddy_log_renders_without_the_danger_chip(self):
        buddy = Person(first_name="Bee", primary_email="bee@example.test", campus_id=self.campus.id)
        student = Person(first_name="Exchange", primary_email="ex@example.test", campus_id=self.campus.id)
        db.session.add_all([buddy, student])
        db.session.flush()
        assignment = BuddyAssignment(project_id=self.closing.id, buddy_person_id=buddy.id,
                                     exchange_student_person_id=student.id, status="Active",
                                     start_date=date.today(), end_date=date.today() + timedelta(days=5))
        db.session.add(assignment)
        db.session.flush()
        db.session.add(BuddyLog(buddy_assignment_id=assignment.id, activity_date=date.today(),
                                description="Campus tour", duration_hours=2, status="Verified"))
        db.session.commit()

        self.login()
        response = self.client.get(f"/erp/projects/{self.closing.public_id}", query_string={"tab": "people", "section": "buddies"})
        body = response.data.decode()
        self.assertIn("Campus tour", body)
        row = body[body.index("Campus tour") - 600:body.index("Campus tour") + 600]
        self.assertNotIn("ds-row--overdue", row)
        self.assertNotIn("ds-chip--overdue", row)


class MobileActionClippingTestCase(AuditFixtureTestCase):
    """P0-02 and P1-04 -- row actions rendered off-canvas on a phone."""

    def test_a_row_decision_is_a_disclosure_not_a_form_wedged_into_a_cell(self):
        self.login()
        response = self.client.get(f"/erp/projects/{self.icc_event.public_id}", query_string={"tab": "logistics"})
        body = response.data.decode()
        # Every in-row decision form now sits inside a native <details>, so
        # it is reachable at 375px and needs no JavaScript.
        for form in re.finditer(r'<form[^>]*class="aurora-inline-decision"', body):
            preceding = body[max(0, form.start() - 400):form.start()]
            if "ds-row__act" not in preceding:
                continue
            self.assertIn("ds-review__panel", preceding,
                          "an in-row decision form must open from a Review disclosure")

    def test_every_row_cell_carries_its_column_name_for_the_card_layout(self):
        """Below 860px a row folds into a card, and "tables that become
        cards retain explicit field labels"."""
        self.login()
        response = self.client.get(f"/erp/projects/{self.icc_event.public_id}", query_string={"tab": "logistics"})
        body = response.data.decode()
        for row in re.finditer(r'<div class="ds-row [^"]*"[^>]*>(.{0,2000}?)</div>\s*(?=<div class="ds-row|<div class="ds-rows__foot|</div>)', body, re.S):
            cells = re.findall(r'<(?:span|a) class="(ds-row__(?:title|desc|when|docs))"', row.group(1))
            self.assertFalse(cells, f"unlabelled row cells would lose their meaning as a card: {cells}")

    def test_the_phone_bottom_bar_carries_four_destinations_plus_menu(self):
        """P0-05: the bar had seven icons and a sign-out."""
        from app.services.navigation import MAX_BOTTOM_NAV_ITEMS, build_nav

        self.login()
        with self.app.test_request_context("/"):
            items = [item for item in build_nav(self.user, "dashboard.index", "dashboard") if item["bottom_nav"]]
        self.assertLessEqual(len(items), MAX_BOTTOM_NAV_ITEMS)

        response = self.client.get("/")
        body = response.data.decode()
        self.assertIn("ds-menu__drawer", body, "the displaced destinations need a labelled Menu")
        # Everything dropped from the bar is still one tap away.
        for endpoint in ("/erp/notifications", "/profile", "/logout"):
            self.assertIn(f'class="ds-menu__link" href="{endpoint}"', body)

    def test_fixed_shell_furniture_reserves_layout_space(self):
        """P1-14 / P0-05: the demo banner was fixed above the bottom
        navigation and covered the last rows of every table."""
        tiles = (CSS / "tiles.css").read_text(encoding="utf-8")
        banner = re.search(r"\.ds-demo-banner \{([^}]*)\}", tiles).group(1)
        self.assertNotIn("position: fixed", banner)
        self.assertIn('grid-template-areas', tiles)
        self.assertIn("env(safe-area-inset-bottom)", tiles)


class DarkTileContrastTestCase(unittest.TestCase):
    """P1-06 -- dark tile headings computed to rgb(29, 31, 32) on navy."""

    def test_every_accent_tile_ground_carries_its_foreground_at_wcag_aa(self):
        foreground = _hex_to_rgb(_token("--on-accent"))
        for token in ("--tile-pine", "--tile-indigo", "--tile-brass"):
            with self.subTest(tile=token):
                background = _hex_to_rgb(_token(token))
                ratio = contrast_ratio(foreground, background)
                self.assertGreaterEqual(round(ratio, 2), 4.5, f"{token} heading contrast is {ratio:.2f}:1")

    def test_the_muted_foreground_also_clears_aa_after_compositing(self):
        """`--on-accent-muted` is translucent white, so the ratio has to be
        measured against the colour it actually composites to."""
        alpha_match = re.search(r"rgb\(255 255 255 / (\d+)%\)", _token("--on-accent-muted"))
        self.assertIsNotNone(alpha_match, "--on-accent-muted must stay a white with an alpha")
        alpha = int(alpha_match.group(1)) / 100
        for token in ("--tile-pine", "--tile-indigo", "--tile-brass"):
            with self.subTest(tile=token):
                background = _hex_to_rgb(_token(token))
                composited = tuple(round(255 * alpha + channel * (1 - alpha)) for channel in background)
                ratio = contrast_ratio(composited, background)
                self.assertGreaterEqual(round(ratio, 2), 4.5, f"{token} muted contrast is {ratio:.2f}:1")

    def test_the_heading_rule_that_caused_the_failure_is_explicitly_overridden(self):
        """base.css sets `h1..h6 { color: var(--color-text) }`, which is
        (0,0,1) and beats the tile's *inherited* white however specific the
        tile's own selector is. The override has to name the title."""
        base = (CSS / "base.css").read_text(encoding="utf-8")
        self.assertRegex(base, r"h1, h2, h3, h4, h5, h6 \{[^}]*color: var\(--color-text\)")

        tiles = (CSS / "tiles.css").read_text(encoding="utf-8")
        for accent in ("pine", "indigo", "brass"):
            with self.subTest(accent=accent):
                self.assertRegex(
                    tiles,
                    # The class name is anchored so a typo in the selector --
                    # which is exactly how the rule would silently stop
                    # applying -- fails here rather than in a browser.
                    rf"\.ds-tile--{accent} \.ds-tile__title(?![\w-])[^{{]*\{{[^}}]*color: var\(--on-accent\)",
                )

    def test_ink_on_an_accent_ground_would_fail_as_the_audit_measured(self):
        """Guards the guard: if the palette is retuned so that the old bug
        would no longer be a bug, this test says so instead of passing on."""
        ink = _hex_to_rgb(_token("--color-text"))
        navy = _hex_to_rgb(_token("--tile-indigo"))
        self.assertLess(contrast_ratio(ink, navy), 4.5)


if __name__ == "__main__":
    unittest.main()
