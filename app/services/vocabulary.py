"""Controlled-vocabulary helpers shared by every form that previously
accepted free text for a constrained concept (project category, session
type, budget category, operational-request type, assignment role, contribution
activity, and document category). UAT data
already showed spelling and taxonomy drift from these free-text fields --
see PLAN.md "ICC form ambiguity" finding.
"""

from __future__ import annotations

from app.models.production import ControlledVocabulary

OTHER_VALUE = "Other"

# Seed values for a domain that hasn't been populated into
# ControlledVocabulary yet (fresh installs, tests) so forms never break, and
# the canonical source `scripts`/`imports.py` seeding pulls from.
DEFAULT_VOCABULARY = {
    "project_category": ["Operational", "Cultural", "Sports", "Leadership", "Exchange", "Academic", "Social Work"],
    "project_type": ["ICC event", "ICC internal activity", "IGP inbound program", "Immersion", "Exchange cohort", "Visitor program"],
    "session_type": ["Orientation", "Session", "Workshop", "Meeting", "Excursion", "Ceremony"],
    "budget_category": ["Logistics", "Hospitality", "Transport", "Materials", "Honorarium", "Venue", "Marketing"],
    "operational_request_type": ["Vehicle", "Venue Booking", "Catering", "Equipment", "Guest Invitation", "Printing"],
    "assignment_role": ["Volunteer", "Coordinator", "Lead", "Buddy", "Mentor", "Logistics Support"],
    "contribution_activity": ["Event support", "Media support", "Logistics support", "Administrative"],
    "document_category": [
        "Report", "Poster", "Presentation", "Photo", "Video",
        "Screen Banner", "Lamppost", "Welcome Notes", "Participant Certificates", "Buddy Certificates",
        "Daywise Buddy Allocation", "Inauguration Schedule", "Valedictory Schedule", "Attendance Claim",
        "Buddy Allocation Source", "Operational Checklist", "Event Poster", "Stage Backdrop",
        "Program Details", "Images/Photos", "Event Report", "Script", "Testimonial",
    ],
}


def vocabulary_options(domain):
    """Active labels for `domain`, always ending in "Other" so a value
    outside the controlled set can still be entered via a required
    free-text detail field rather than blocking the form."""
    rows = (
        ControlledVocabulary.query.filter_by(domain=domain, is_active=True)
        .order_by(ControlledVocabulary.sort_order, ControlledVocabulary.label)
        .all()
    )
    labels = [row.label for row in rows] if rows else list(DEFAULT_VOCABULARY.get(domain, []))
    return [label for label in labels if label != OTHER_VALUE] + [OTHER_VALUE]


def resolve_vocabulary_value(value, other_detail, *, domain, legacy_value=None):
    """Resolve a `vocabulary_options()`-bound select (plus its companion
    "<field>_other" detail input) into the value to store. Historical
    unknown strings already in the database are left untouched by this --
    it only governs new input."""
    value = (value or "").strip()
    if value == OTHER_VALUE:
        other_detail = (other_detail or "").strip()
        if not other_detail:
            raise ValueError('Provide details for "Other".')
        return other_detail
    if not value:
        raise ValueError("This field is required.")
    if value == (legacy_value or "").strip():
        return value
    allowed = set(vocabulary_options(domain))
    if value not in allowed:
        raise ValueError("Choose a value from the available options or select Other.")
    return value


def vocabulary_display(domain, value):
    """Make historical taxonomy drift visible without rewriting old data."""
    value = (value or "").strip()
    if not value or value in set(vocabulary_options(domain)):
        return value
    return f"{value} (Legacy value)"
