"""Shared project-scope queries.

Before this module existed, "which projects can this user see" and "which
projects can this user approve" were each recomputed inline with
``Project.query.all()`` plus a Python-side filter in four separate places
(``mission_control.build_mission_control``, ``erp.hub``, ``erp.campuses``,
``erp.oversight``). Centralising them here is the first step toward merging
those pages into one home -- see PLAN and
in-the-operation-checklists-crystalline-dongarra.md Step 1.
"""

from __future__ import annotations

from app.models.project import Project
from app.services.authorization import can_view_project, has_permission


def visible_projects(user):
    """Every project ``user`` may view, ordered newest-start-date first.

    Callers slice the result (``[:8]``) rather than this function returning
    a bounded list, so every existing call site's slicing behaviour is
    preserved exactly.
    """
    return [
        project
        for project in Project.query.order_by(Project.start_date.desc()).all()
        if can_view_project(user, project)
    ]


def approvable_projects(user):
    """Every project ``user`` holds the ``approve`` permission on.

    Deliberately narrower than :func:`visible_projects` -- widening this to
    ``can_view_project`` would leak rows into the decision queue that the
    user cannot act on.
    """
    return [project for project in Project.query.all() if has_permission(user, "approve", project)]
