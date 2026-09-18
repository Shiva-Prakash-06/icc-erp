"""The canonical names for the two divisions, and the one noun for a record.

Audit finding P1-08. `IGP` expanded to "India Gateway Program" in a project's
metadata strip and to "International Guest Programmes" in campus navigation.
`ICC` was "International Christite Community" on the sign-in lockup and
"Institutional Collaboration Cell" one screen later. A reader cannot tell
whether those are two names or two things.

**Settled on 17 September 2026: the offices' own names win.** P1-08 picked the
``hierarchy.DIVISIONS`` strings only because the drill-down already showed
them; it was a tie-break between two live spellings, not a ruling on which is
correct. The offices are named **India Gateway Program** and **International
Christite Community**, so those are the expansions everywhere -- this module,
``hierarchy.DIVISIONS``, the seeded operating units and the public copy were
all changed together, because one canonical name that disagrees with another
screen is the bug P1-08 was raised to fix.

The differing strings are also stored in ``operating_units.name``, seeded years
ago and referenced by imports; renaming that column on a populated database
would be a data migration to fix a caption. So this module maps **code ->
display name** at render time and existing rows stay exactly as they are.

``RECORD_NOUN`` settles the other half of the finding. The routes say
`project`, the IGP screens say `programme` and the ICC screens say `event`.
The URL map is frozen and the model is called ``Project``, so the internal
name does not move; the *interface* says "event" for ICC, "programme" for
IGP, and "record" where it must cover both.
"""

from __future__ import annotations

#: Operating-unit / program-type code -> what the interface calls it.
DIVISION_NAMES = {
    "IGP": "India Gateway Program",
    "ICC": "International Christite Community",
}

#: The singular noun each division's records take in interface copy.
RECORD_NOUN = {"IGP": "programme", "ICC": "event"}
RECORD_NOUN_PLURAL = {"IGP": "programmes", "ICC": "events"}

#: Covers both divisions in one phrase, for screens that list them together.
GENERIC_NOUN = "event"
GENERIC_NOUN_PLURAL = "events"

#: The institution's own lockup. "International Christite Community" is the
#: ICC division, not the university, so it never belongs under the wordmark.
ORGANISATION = "Christ University"
OFFICE = "Office of International Affairs"


def division_name(code_or_unit) -> str:
    """Canonical expansion for a division code, an OperatingUnit or a
    ProgramType. Anything unrecognised keeps its stored name."""
    if code_or_unit is None:
        return ""
    code = getattr(code_or_unit, "code", None) or getattr(code_or_unit, "name", None) or code_or_unit
    key = str(code).strip().upper()
    if key in DIVISION_NAMES:
        return DIVISION_NAMES[key]
    stored = getattr(code_or_unit, "name", None)
    return str(stored if stored is not None else code_or_unit)


def record_noun(code_or_unit, *, plural: bool = False) -> str:
    code = getattr(code_or_unit, "code", None) or getattr(code_or_unit, "name", None) or code_or_unit
    key = str(code or "").strip().upper()
    table = RECORD_NOUN_PLURAL if plural else RECORD_NOUN
    return table.get(key, GENERIC_NOUN_PLURAL if plural else GENERIC_NOUN)


def register_globals(app) -> None:
    app.jinja_env.globals["audit_action"] = audit_action
    app.jinja_env.globals["audit_entity"] = audit_entity
    app.jinja_env.globals["division_name"] = division_name
    app.jinja_env.globals["record_noun"] = record_noun
    app.jinja_env.globals["ORGANISATION"] = ORGANISATION
    app.jinja_env.globals["OFFICE"] = OFFICE


# ── Audit vocabulary ────────────────────────────────────────────────────
# Audit finding, Audit history: "Raw entity/action identifiers such as
# `Report Generate` and `ReportSnapshot` are primary copy." The ledger
# should read as prose; the identifiers stay, demoted to a technical-details
# disclosure (reports-admin override, "Audit").

#: Verb phrases for the actions the application records. An action with no
#: entry falls back to its own words rather than being hidden -- an unknown
#: action is exactly what an auditor needs to see.
AUDIT_ACTIONS = {
    "project.create": "created the event",
    "project.update": "updated the event",
    "project.transition": "changed the event's lifecycle state",
    "task.create": "added a task",
    "task.update": "changed a task",
    "task.decision": "decided a task",
    "checklist.create": "added a checklist",
    "checklist.item.decision": "decided a checklist requirement",
    "document.create": "indexed a document",
    "document.upload": "uploaded a document",
    "document.decision": "decided a document",
    "budget.create": "added a budget line",
    "budget.decision": "decided a budget line",
    "operational_request.create": "raised an operational request",
    "operational_request.decision": "decided an operational request",
    "report.generate": "generated a report",
    "report.approve": "approved a report",
    "publication.request": "requested publication",
    "publication.decision": "decided publication",
    "attendance.mark": "recorded attendance",
    "import.stage": "staged an import",
    "import.commit": "committed an import",
    "user.approve": "approved an account",
    "user.role": "changed a role assignment",
    "contribution.decision": "decided a contribution",
    "buddy.decision": "decided a buddy interaction log",
    "feedback.moderate": "moderated a feedback response",
    "recruitment.decision": "decided a recruitment application",
}

#: The nouns behind the ORM class names.
AUDIT_ENTITIES = {
    "Project": "event",
    "WorkTask": "task",
    "ChecklistInstance": "checklist",
    "ChecklistItemStatus": "checklist requirement",
    "DocumentRecord": "document",
    "BudgetLine": "budget line",
    "OperationalRequest": "operational request",
    "ReportSnapshot": "report",
    "ReimbursementEntry": "reimbursement",
    "SessionAttendance": "attendance record",
    "ProjectSession": "session",
    "ImportBatch": "import batch",
    "User": "account",
    "RoleAssignment": "role assignment",
    "ContributionRecord": "contribution",
    "BuddyLog": "buddy interaction log",
    "FeedbackResponse": "feedback response",
    "RecruitmentApplication": "recruitment application",
    "TeamAssignment": "team assignment",
    "BuddyAssignment": "buddy pairing",
}


def audit_action(action: str) -> str:
    if not action:
        return "recorded an event"
    known = AUDIT_ACTIONS.get(action)
    if known:
        return known
    return action.replace(".", " ").replace("_", " ")


def audit_entity(entity_type: str) -> str:
    if not entity_type:
        return ""
    return AUDIT_ENTITIES.get(entity_type, entity_type)
