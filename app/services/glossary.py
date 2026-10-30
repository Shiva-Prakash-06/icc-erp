"""The canonical names for the two divisions, and the one noun for a record.

Audit finding P1-08. `IGP` expanded to "India Gateway Program" in a project's
metadata strip and to "International Guest Programmes" in campus navigation.
`ICC` was "International Christite Community" on the sign-in lockup and
"Institutional Collaboration Cell" one screen later. A reader cannot tell
whether those are two names or two things.

**Settled on 17 September 2026: the offices' own names win.** The offices
are named **India Gateway Program** and **International Christite
Community**, so those are the expansions everywhere -- this module, the
seeded operating units and the public copy -- because one canonical name
that disagrees with another screen is the bug P1-08 was raised to fix.

The differing strings are also stored in ``operating_units.name``, seeded years
ago and referenced by imports; renaming that column on a populated database
would be a data migration to fix a caption. So this module maps **code ->
display name** at render time and existing rows stay exactly as they are.

``RECORD_NOUN`` settles the other half of the finding. The routes say
`project`, the IGP screens say `programme` and the ICC screens say `event`.
The URL map is frozen and the model is called ``Project``, so the internal
name does not move; the *interface* says "event" for ICC, "programme" for
IGP, and "record" where it must cover both.

It is also the plain-language dictionary (:data:`PLAIN_WORDS`): the words
the screens used to say, and what they say now. Anyone using the app is
assumed to read like a twelve-year-old, so a screen never shows a word on
the left; ``tests/plain_language_test.py`` fails if one comes back.
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

#: Plain words for every action the application records. An action with no
#: entry falls back to its own words rather than being hidden -- an unknown
#: action is exactly what someone checking the history needs to see.
AUDIT_ACTIONS = {
    "account.signup": "signed up",
    "account.approve": "let someone in",
    "account.reject": "turned someone away",
    "account.role_change": "changed what someone is",
    "account.password_changed": "changed their password",
    "account.password_recovered": "set a new password",
    "account.password_reset_requested": "asked for a new password",
    "project.create": "made the event",
    "project.basics": "changed the event's details",
    "projects.update": "changed the event",
    "project.transition": "changed whether the event is on",
    "checklist.instantiate": "made the event's to-do list",
    "project.finish_request": "sent the event to Faculty to finish",
    "project.finish_signoff": "signed off the event",
    "project.finish_returned": "sent the event back",
    "project.publication_request": "asked to show the event on the website",
    "project.publication_decision": "decided about the website",
    "task.create": "added a to-do",
    "task.status": "ticked or changed a to-do",
    "checklist.status": "ticked or changed a to-do",
    "todo.remove": "took a to-do off the list",
    "todo.restore": "put a to-do back",
    "session.create": "added a time",
    "session.edit": "changed a time",
    "session.remove": "removed a time",
    "session.restore": "put a time back",
    "attendance.mark": "took attendance",
    "person.create": "added a person",
    "person.update_own": "changed their own details",
    "team.enroll": "added someone to the event",
    "team.remove": "took someone off the event",
    "team.restore": "put someone back on the event",
    "contribution.log": "gave volunteer hours",
    "contribution.decision": "changed volunteer hours",
    "buddy_assignment.create": "paired up buddies",
    "buddy_log.create": "wrote what buddies did",
    "buddy_log.decision": "changed a buddy note",
    "reimbursement.create": "asked for money",
    "reimbursement.status": "changed a money request",
    "reimbursement.remove": "took back a money request",
    "reimbursement.restore": "put a money request back",
    "budget_line.transition": "changed an old budget line",
    "operational_request.transition": "changed an old request",
    "document.upload": "added a file",
    "document.index": "added a file link",
    "document.kind": "said what a file is",
    "document.remove": "removed a file",
    "document.restore": "put a file back",
    "document.status": "changed a file",
    "document.drive_validate": "checked a Drive link",
    "document.link_checklist": "added a file to a to-do",
    "document.unlink_checklist": "took a file off a to-do",
    "feedback_form.link": "made a feedback link",
    "feedback.moderate": "changed a feedback reply",
    "recruitment.decision": "picked or did not pick someone",
    "report.generate": "made a report",
    "report.approve": "OK'd a report",
    "report.publish": "put a report on the website",
    "report.download_complete_pdf": "downloaded the report",
    "import.stage": "checked a sheet",
    "import.commit": "saved a sheet",
    "import.event_folder": "read an event folder",
}

#: The nouns behind the ORM class names.
AUDIT_ENTITIES = {
    "Project": "event",
    "WorkTask": "to-do",
    "ChecklistInstance": "to-do list",
    "ChecklistItemStatus": "to-do",
    "DocumentRecord": "file",
    "BudgetLine": "old budget line",
    "OperationalRequest": "old request",
    "ReportSnapshot": "report",
    "ReimbursementEntry": "money request",
    "SessionAttendance": "attendance",
    "ProjectSession": "time",
    "ImportBatch": "sheet",
    "User": "account",
    "RoleAssignment": "role",
    "ContributionRecord": "volunteer hours",
    "BuddyLog": "buddy note",
    "FeedbackResponse": "feedback reply",
    "FeedbackForm": "feedback link",
    "RecruitmentApplication": "application",
    "TeamAssignment": "person on the event",
    "BuddyAssignment": "buddy pair",
    "Person": "person",
}


# ── Plain words ─────────────────────────────────────────────────────────
#: Word a screen must never show -> what it says instead. Matched whole-word
#: and case-blind against the text a template actually puts on the page
#: (comments, tags and code are ignored), and against flash messages.
PLAIN_WORDS = {
    "operational request": "money (or a to-do)",
    "waiver": "skip",
    "waive": "skip",
    "waived": "skipped",
    "evidence": "file",
    "disclosure": "show on website",
    "publication": "website",
    "lifecycle": "where the event is",
    "provenance": "where it came from",
    "moderation": "(nothing -- replies show straight away)",
    "moderate": "(nothing -- replies show straight away)",
    "classification": "what this is",
    "stage": "check",
    "staged": "checked",
    "staging": "checking",
    "commit": "save",
    "committed": "saved",
    "blocker": "what is missing",
    "blockers": "what is missing",
    "oversight": "needs your OK",
    "portfolio": "your events",
    "governance": "Faculty",
    "reconciled": "matched",
    "workflow": "steps",
    "scope": "what you can see",
    "scoped": "you can see",
    "metadata": "details",
    "artefact": "file",
    "submitted": "sent",
    "audit trail": "who changed what",
    "verify": "check",
    "verified": "checked",
    "approver": "Faculty",
    "reimbursement": "money",
    "reimbursements": "money",
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
