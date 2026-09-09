"""Per-request memoisation of role assignments (audit B13).

`has_permission` is called once per project by `approvable_projects`,
`visible_projects`, the action queue and several templates, and each call
re-queried `RoleAssignment`. These tests pin the two properties that matter:
the query happens once per request, and a role change inside a request is
still honoured by later checks in that same request.
"""

import os
import unittest
from datetime import date

os.environ["TESTING"] = "true"

from sqlalchemy import event

from app import create_app
from app.database import db
from app.models.erp import RoleAssignment
from app.models.project import AcademicYear, Campus, ProgramType, Project
from app.models.user import User
from app.services.authorization import (
    has_permission,
    invalidate_assignment_cache,
    role_codes,
)


class AssignmentCacheTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.year = AcademicYear(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31), is_current=True)
        self.campus = Campus(name="Central", code="CEN")
        self.icc = ProgramType(name="ICC")
        db.session.add_all([self.year, self.campus, self.icc])
        db.session.flush()
        self.projects = []
        for index in range(5):
            project = Project(
                code=f"ICC-2026-CEN-{800 + index}", campus_id=self.campus.id, program_type_id=self.icc.id,
                academic_year_id=self.year.id, title=f"Cache project {index}", category="Operational",
                status="Active", start_date=date(2026, 8, 1), end_date=date(2026, 8, 2),
            )
            db.session.add(project)
            self.projects.append(project)
        self.user = User(username="cacheuser", email="cache@example.com", role="Faculty", status="Approved", needs_password_reset=False)
        self.user.set_password("A-secure-test-password-2026")
        db.session.add(self.user)
        db.session.flush()
        db.session.add(RoleAssignment(user_id=self.user.id, role_code="OIA_FACULTY_ADMINISTRATOR", is_active=True))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _count_assignment_queries(self, action):
        counter = {"n": 0}

        def listener(conn, cursor, statement, parameters, ctx, many):
            if "role_assignments" in statement:
                counter["n"] += 1

        event.listen(db.engine, "before_cursor_execute", listener)
        try:
            action()
        finally:
            event.remove(db.engine, "before_cursor_execute", listener)
        return counter["n"]

    def test_repeated_permission_checks_query_assignments_once(self):
        def check_every_project():
            for project in self.projects:
                has_permission(self.user, "approve", project)

        self.assertEqual(self._count_assignment_queries(check_every_project), 1)

    def test_the_answer_is_unchanged_by_caching(self):
        for project in self.projects:
            self.assertTrue(has_permission(self.user, "approve", project))
        self.assertFalse(has_permission(self.user, "platform_admin", self.projects[0]))

    def test_a_revoked_role_is_honoured_after_invalidation(self):
        self.assertTrue(has_permission(self.user, "approve", self.projects[0]))
        RoleAssignment.query.filter_by(user_id=self.user.id).update({"is_active": False})
        db.session.commit()
        invalidate_assignment_cache(self.user)
        self.assertFalse(has_permission(self.user, "approve", self.projects[0]))

    def test_invalidating_without_a_user_clears_every_entry(self):
        has_permission(self.user, "approve", self.projects[0])
        RoleAssignment.query.filter_by(user_id=self.user.id).update({"is_active": False})
        db.session.commit()
        invalidate_assignment_cache()
        self.assertFalse(has_permission(self.user, "approve", self.projects[0]))

    def test_role_codes_uses_the_same_cache(self):
        def read_codes_repeatedly():
            for _ in range(4):
                role_codes(self.user)

        self.assertEqual(self._count_assignment_queries(read_codes_repeatedly), 1)

    def test_separate_requests_do_not_share_a_cache(self):
        """The cache lives on `flask.g`, so it must not leak between
        requests -- a stale grant surviving a request boundary would be an
        authorization bug, not merely a performance one."""
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.user.id
            session["session_version"] = self.user.session_version
        self.assertEqual(client.get("/").status_code, 200)

        RoleAssignment.query.filter_by(user_id=self.user.id).update({"is_active": False})
        db.session.commit()
        # A signed-in user with no active assignment can no longer act; the
        # second request must not reuse the first request's cached grant.
        response = client.get("/erp/imports")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
