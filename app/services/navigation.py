"""Single source of truth for the rail, the command palette, and the
narrow-viewport bottom bar.

Four places and a Menu on a phone, and no more: Campuses, My work, Events,
and Reports (Faculty and the USC) or Account (everyone else). + New event
is in the rail on a laptop and in the Menu on a phone. Everything that
is not one of those four -- alerts, people, imports, the audit trail, your
account -- sits in the Menu on a phone and lower down the rail on a laptop.
Entries are dropped for anyone who cannot use them, so a volunteer's bar is
My activities, Account and the Menu.

``foot`` sinks an entry to the bottom of the rail. ``icon`` values are
``ph-*`` classes and are named only here, in Python --
``app/services/**/*.py`` must stay in the PurgeCSS content globs or the
mask rules behind these names are stripped and every rail icon renders as
a solid square.
"""

from __future__ import annotations

from app.services.authorization import has_any_permission

#: The roles that see the Reports page: Faculty and the USC.
REPORT_TEAMS = {"faculty", "usc"}

NAV_REGISTRY = [
    # The landing page for everyone who works on events: campuses, then a
    # campus's programs, then one program's actions and their owners.
    {"key": "overview", "label": "Campuses", "mobile_label": "Campuses", "bottom_nav": True, "rail": True, "icon": "ph-buildings", "group": "Go to",
     "endpoint": "dashboard.overview", "hide_for_view_only": True,
     "active_endpoints": {"dashboard.overview", "dashboard.overview_campus", "dashboard.overview_program"}},
    {"key": "home", "label": "My work", "mobile_label": "My work", "bottom_nav": True, "rail": True, "icon": "ph-check-square", "group": "Go to", "endpoint": "dashboard.index",
     "active_endpoints": {"dashboard.index", "dashboard.queue"}},
    {
        "key": "projects", "label": "Events", "mobile_label": "Events", "bottom_nav": True, "rail": True, "icon": "ph-calendar", "group": "Go to",
        "endpoint": "erp.projects", "active_blueprint": "erp", "hide_for_view_only": True,
        "active_exclude_endpoints": {"erp.notifications", "erp.audit", "erp.imports", "erp.new_project"},
    },
    {"key": "new", "label": "New event", "mobile_label": "New", "bottom_nav": False, "rail": True, "icon": "ph-plus-circle", "group": "Go to", "endpoint": "erp.new_project",
     "permission": "manage_projects"},
    {"key": "reports", "label": "Reports", "mobile_label": "Reports", "bottom_nav": True, "rail": True, "icon": "ph-chart-bar", "group": "Go to", "endpoint": "dashboard.reports",
     "teams": REPORT_TEAMS},

    {"key": "people", "label": "People", "mobile_label": "People", "bottom_nav": False, "rail": True, "icon": "ph-users", "group": "More", "endpoint": "dashboard.admin_users", "permission": "manage_users"},
    {"key": "imports", "label": "Upload a sheet", "mobile_label": "Upload", "bottom_nav": False, "rail": True, "icon": "ph-database", "group": "More", "endpoint": "erp.imports", "permission": "manage_imports"},
    {"key": "audit", "label": "Who changed what", "mobile_label": "History", "bottom_nav": False, "rail": True, "icon": "ph-clock-counter-clockwise", "group": "More", "endpoint": "erp.audit", "permission": "audit"},

    {"key": "notifications", "label": "Alerts", "mobile_label": "Alerts", "bottom_nav": False, "rail": True, "foot": True, "icon": "ph-bell", "group": "More", "endpoint": "erp.notifications"},
    # Account takes the fourth phone slot from anyone who has no Reports.
    {"key": "profile", "label": "Account", "mobile_label": "Account", "bottom_nav": False, "rail": True, "foot": True, "icon": "ph-user-circle", "group": "More", "endpoint": "dashboard.profile"},
]


#: Exactly the destinations the phone bar carries. Asserted by the
#: accessibility suite, because "four plus Menu" is a contract and not a
#: preference: eleven 48px targets do not fit a 375px viewport.
MAX_BOTTOM_NAV_ITEMS = 4


def build_nav(user, current_endpoint, current_blueprint):
    """Return NAV_REGISTRY entries visible to `user`, each with a resolved
    `active` flag. Exactly one entry can be active for any given request."""
    from app.services.home import is_view_only
    from app.services.teams import user_teams

    view_only = is_view_only(user)
    teams = user_teams(user)
    items = []
    for entry in NAV_REGISTRY:
        if entry.get("permission") and not has_any_permission(user, entry["permission"]):
            continue
        if entry.get("teams") and not (teams & entry["teams"]):
            continue
        if entry.get("hide_for_view_only") and view_only:
            continue
        if entry.get("active_endpoints"):
            active = current_endpoint in entry["active_endpoints"]
        elif entry.get("active_blueprint"):
            active = current_blueprint == entry["active_blueprint"] and current_endpoint not in entry.get("active_exclude_endpoints", set())
        else:
            active = current_endpoint == entry["endpoint"]
        item = {**{"rail": True, "bottom_nav": False, "foot": False}, **entry, "active": active}
        if entry["key"] == "home" and view_only:
            item.update(label="My activities", mobile_label="My activities")
        items.append(item)
    # Account fills the fourth phone slot when Reports is not there.
    if sum(item["bottom_nav"] for item in items) < MAX_BOTTOM_NAV_ITEMS:
        for item in items:
            if item["key"] == "profile":
                item.update(bottom_nav=True, foot=False)
    return items
