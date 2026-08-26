"""Single source of truth for the desktop sidebar, mobile drawer, and command
palette. Previously each of those three surfaces hand-duplicated the same
link list in base.html with no shared "is this active" logic, so they could
(and did) drift out of sync and show more than one active item at once. See
PLAN.md "USC sidebar" finding.

Entries carry a ``rail`` flag (default True) so a destination can appear in
the mobile drawer and command palette without occupying a desktop rail
slot -- used to demote low-traffic destinations (Campuses, Data imports,
Notification centre, Audit trail) after the Mission Control / ERP hub /
Oversight merge freed up rail space that would otherwise sit unused. See
in-the-operation-checklists-crystalline-dongarra.md Step 7.
"""

from __future__ import annotations

from app.services.authorization import has_any_permission

NAV_REGISTRY = [
    {"key": "home", "label": "Home", "mobile_label": "Home", "bottom_nav": True, "rail": True, "icon": "ph-gauge", "group": "Workspace", "endpoint": "dashboard.index"},
    {
        "key": "projects", "label": "Projects", "mobile_label": "Projects", "bottom_nav": True, "rail": True, "icon": "ph-folder-open", "group": "Workspace",
        "endpoint": "erp.projects", "active_blueprint": "erp",
        "active_exclude_endpoints": {"erp.notifications", "erp.audit", "erp.campuses", "erp.campus_detail", "erp.imports"},
    },
    {"key": "reports", "label": "Published reports", "mobile_label": "Reports", "bottom_nav": True, "rail": True, "icon": "ph-chart-bar", "group": "Workspace", "endpoint": "public.reports"},
    {"key": "profile", "label": "My Account & Activity", "mobile_label": "Account", "bottom_nav": True, "rail": True, "icon": "ph-user-circle", "group": "Workspace", "endpoint": "dashboard.profile"},
    {"key": "admin_users", "label": "Administration", "mobile_label": "Admin", "bottom_nav": False, "rail": True, "icon": "ph-shield-check", "group": "Workspace", "endpoint": "dashboard.admin_users", "permission": "manage_users"},

    {"key": "campuses", "label": "Campuses", "mobile_label": "Campuses", "bottom_nav": False, "rail": False, "icon": "ph-buildings", "group": "Records", "endpoint": "erp.campuses"},
    {"key": "imports", "label": "Data imports", "mobile_label": "Imports", "bottom_nav": False, "rail": False, "icon": "ph-database", "group": "Records", "endpoint": "erp.imports", "permission": "manage_imports"},
    {"key": "notifications", "label": "Notification centre", "mobile_label": "Alerts", "bottom_nav": False, "rail": False, "icon": "ph-bell", "group": "Records", "endpoint": "erp.notifications"},
    {"key": "audit", "label": "Audit trail", "mobile_label": "Audit", "bottom_nav": False, "rail": False, "icon": "ph-clock-counter-clockwise", "group": "Records", "endpoint": "erp.audit", "permission": "audit"},
]


def build_nav(user, current_endpoint, current_blueprint):
    """Return NAV_REGISTRY entries visible to `user`, each with a resolved
    `active` flag. Exactly one entry can be active for any given request:
    the Projects entry explicitly excludes the endpoints owned by the more
    specific demoted entries (Notifications, Audit trail, Data imports,
    Campuses) so it doesn't also light up for those pages."""
    items = []
    for entry in NAV_REGISTRY:
        if entry.get("permission") and not has_any_permission(user, entry["permission"]):
            continue
        if entry.get("active_blueprint"):
            active = current_blueprint == entry["active_blueprint"] and current_endpoint not in entry.get("active_exclude_endpoints", set())
        else:
            active = current_endpoint == entry["endpoint"]
        items.append({**{"rail": True, "bottom_nav": False}, **entry, "active": active})
    return items
