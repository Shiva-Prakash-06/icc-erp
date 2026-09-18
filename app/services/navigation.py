"""Single source of truth for the rail, the command palette, and the
narrow-viewport bottom bar.

Previously each of those surfaces hand-duplicated the same link list in
base.html with no shared "is this active" logic, so they could (and did)
drift out of sync and show more than one active item at once. See PLAN.md
"USC sidebar" finding.

The Tile System put navigation back in a rail, so ``topnav`` (which chose
the deleted desktop top bar) is gone and every visible entry is a rail
entry. ``foot`` sinks an entry to the bottom of the rail: the account chip
and the alert bell are destinations, but they are not part of the
drill-down, and grouping them at the foot is what keeps the rail readable
at four to seven icons.

``icon`` values are ``ph-*`` classes and are named only here, in Python --
``app/services/**/*.py`` must stay in the PurgeCSS content globs or the
mask rules behind these names are stripped and every rail icon renders as
a solid square.
"""

from __future__ import annotations

from app.services.authorization import has_any_permission

NAV_REGISTRY = [
    {"key": "home", "label": "Campuses", "mobile_label": "Campuses", "bottom_nav": True, "rail": True, "icon": "ph-buildings", "group": "Workspace", "endpoint": "dashboard.index",
     "active_endpoints": {"dashboard.index", "erp.campus_detail", "erp.division"}},
    {
        "key": "projects", "label": "Events", "mobile_label": "Events", "bottom_nav": True, "rail": True, "icon": "ph-calendar", "group": "Workspace",
        "endpoint": "erp.projects", "active_blueprint": "erp",
        "active_exclude_endpoints": {
            "erp.notifications", "erp.audit", "erp.campuses", "erp.campus_detail",
            "erp.division", "erp.imports", "erp.analytics", "erp.analytics_division",
        },
    },
    {"key": "analytics", "label": "Analytics", "mobile_label": "Analytics", "bottom_nav": True, "rail": True, "icon": "ph-chart-bar", "group": "Workspace", "endpoint": "erp.analytics",
     "active_endpoints": {"erp.analytics", "erp.analytics_division"}},
    {"key": "reports", "label": "Published reports", "mobile_label": "Reports", "bottom_nav": True, "rail": True, "icon": "ph-file-pdf", "group": "Workspace", "endpoint": "public.reports"},

    {"key": "imports", "label": "Data imports", "mobile_label": "Imports", "bottom_nav": False, "rail": True, "icon": "ph-database", "group": "Records", "endpoint": "erp.imports", "permission": "manage_imports"},
    {"key": "audit", "label": "Audit trail", "mobile_label": "Audit", "bottom_nav": False, "rail": True, "icon": "ph-clock-counter-clockwise", "group": "Records", "endpoint": "erp.audit", "permission": "audit"},
    {"key": "admin_users", "label": "Administration", "mobile_label": "Admin", "bottom_nav": False, "rail": True, "icon": "ph-shield-check", "group": "Records", "endpoint": "dashboard.admin_users", "permission": "manage_users"},

    # Neither of these is in the phone bar. The design-system contract is
    # four primary destinations plus Menu, and the bar was carrying seven
    # icons plus a sign-out (audit P0-05). Both live in the Menu drawer,
    # which is labelled and lists every remaining destination.
    {"key": "notifications", "label": "Notification centre", "mobile_label": "Alerts", "bottom_nav": False, "rail": True, "foot": True, "icon": "ph-bell", "group": "Records", "endpoint": "erp.notifications"},
    {"key": "profile", "label": "My account", "mobile_label": "Account", "bottom_nav": False, "rail": True, "foot": True, "icon": "ph-user-circle", "group": "Workspace", "endpoint": "dashboard.profile"},

    # Reachable from the command palette and from the campus tiles; it has
    # no rail slot because the campus screen IS the campus list.
    {"key": "campuses", "label": "Campus list", "mobile_label": "Campus list", "bottom_nav": False, "rail": False, "icon": "ph-buildings", "group": "Records", "endpoint": "erp.campuses"},
]


#: Exactly the destinations the phone bar carries. Asserted by the
#: accessibility suite, because "four plus Menu" is a contract and not a
#: preference: eleven 48px targets do not fit a 375px viewport.
MAX_BOTTOM_NAV_ITEMS = 4


def build_nav(user, current_endpoint, current_blueprint):
    """Return NAV_REGISTRY entries visible to `user`, each with a resolved
    `active` flag. Exactly one entry can be active for any given request:
    Campuses claims the drill-down endpoints it owns, and Events explicitly
    excludes every endpoint owned by a more specific entry so it does not
    also light up for those pages."""
    items = []
    for entry in NAV_REGISTRY:
        if entry.get("permission") and not has_any_permission(user, entry["permission"]):
            continue
        if entry.get("active_endpoints"):
            active = current_endpoint in entry["active_endpoints"]
        elif entry.get("active_blueprint"):
            active = current_blueprint == entry["active_blueprint"] and current_endpoint not in entry.get("active_exclude_endpoints", set())
        else:
            active = current_endpoint == entry["endpoint"]
        items.append({**{"rail": True, "bottom_nav": False, "foot": False}, **entry, "active": active})
    return items
