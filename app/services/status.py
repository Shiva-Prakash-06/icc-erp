"""The status model: five named dimensions, one vocabulary each.

Audit finding P0-04. A document read `Missing` and `Approved` at the same
time; a *verified* buddy interaction was painted in danger red under a
warning triangle; a report said it was assembled from authoritative
documents while its own dependency table said none were found. None of
those were contradictions in the data. They were five different questions
being answered in the same unlabelled voice.

So the dimensions are named, and a chip carries its dimension:

===============  ==========================================================
``availability`` Is the file actually there? (the bytes, or a live link)
``workflow``     Where has the work item got to?
``review``       What did an approver decide about it?
``publication``  Who outside the office can see it?
``lifecycle``    Where is the record in its own life?
===============  ==========================================================

`Missing` + `Approved` is a legitimate, common pair -- the metadata was
approved and the file was never attached -- and it now reads as
"File missing · Review approved" instead of as a bug.

Three rules the callers depend on:

* **Every state carries a word.** The tone is redundant with the label, the
  icon and the pip, never the only carrier (design system, "Status is never
  conveyed by colour alone").
* **An unknown value degrades to neutral**, never to danger. The old
  ternaries used `else` as a synonym for "bad", which is how a seeded
  `Verified` log ended up styled as an error.
* **Tone is about the reader's next action, not about sentiment.**
  `attention` means somebody has to do something; `critical` means
  something is wrong. A verified record is neither.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Tone -> the `ds-chip--*` modifier that paints it. The four reserved Tile
#: System states are the whole palette; nothing here invents a fifth.
TONE_STATE = {
    "positive": "complete",
    "progress": "active",
    "attention": "upcoming",
    "critical": "overdue",
    "neutral": "complete",
}


@dataclass(frozen=True)
class Status:
    """One state of one dimension, ready to render."""

    dimension: str
    label: str
    tone: str = "neutral"
    #: Sentence shown on hover and to assistive tech, explaining what the
    #: dimension means. This is what stops two chips reading as a
    #: contradiction.
    hint: str = ""

    @property
    def state(self) -> str:
        return TONE_STATE.get(self.tone, "complete")

    @property
    def icon(self) -> str:
        return {
            "positive": "ph-check-circle",
            "critical": "ph-warning",
            "attention": "ph-clock",
            "progress": "ph-dots-three-circle",
        }.get(self.tone, "ph-circle")

    @property
    def accessible_label(self) -> str:
        return f"{DIMENSION_LABELS.get(self.dimension, self.dimension)}: {self.label}"


DIMENSION_LABELS = {
    "availability": "File",
    "workflow": "Work",
    "review": "Review",
    "publication": "Visibility",
    "lifecycle": "Lifecycle",
}


def _table(dimension: str, rows: dict[str, tuple[str, str, str]]) -> dict[str, Status]:
    return {
        key: Status(dimension=dimension, label=label, tone=tone, hint=hint)
        for key, (label, tone, hint) in rows.items()
    }


# ── File availability ───────────────────────────────────────────────────
# `compute_availability` already returns these three words. They describe
# the bytes, and nothing else: a Missing file may still have approved
# metadata, and that pair is normal rather than broken.

AVAILABILITY = _table("availability", {
    "Available": ("Stored", "positive", "The file is stored and can be opened."),
    "Missing": ("No file", "attention", "No file or Drive link has been attached yet. Approval of the record is tracked separately."),
    "Inaccessible": ("Link broken", "critical", "A link exists but Drive rejected it. The file cannot be opened."),
})


# ── Review / approval ───────────────────────────────────────────────────
# What a person with authority decided. `Waived` is a decision, not a
# failure, so it is positive; `Submitted` is waiting on somebody.

# The label is the stored word. Renaming these was tempting -- "Sent back"
# reads better than "Rejected" -- but `Pending` and `Submitted` are distinct
# states in different workflows, and collapsing both to "Awaiting review"
# destroyed a distinction the records genuinely carry. The audit asked for
# each state to have *one* label, icon and colour and for two states of one
# record to say which dimension each belongs to; neither needs the domain's
# vocabulary rewritten. The explanation lives in the hint instead.
REVIEW = _table("review", {
    "Draft": ("Draft", "neutral", "Not yet submitted for review."),
    "Not Started": ("Not Started", "neutral", "No work recorded against this yet."),
    "Submitted": ("Submitted", "attention", "Sent for review and waiting on an approver."),
    "Pending": ("Pending", "attention", "Waiting on an approver."),
    "In Progress": ("In Progress", "progress", "Being worked on."),
    "Blocked": ("Blocked", "critical", "Cannot proceed until something else is resolved."),
    "Approved": ("Approved", "positive", "An approver accepted this record."),
    "Verified": ("Verified", "positive", "Checked and confirmed by an approver."),
    "Completed": ("Completed", "positive", "Finished."),
    "Waived": ("Waived", "positive", "An approver decided this requirement does not apply. This is a decision, not a failure."),
    "Rejected": ("Rejected", "critical", "Returned by an approver with a written reason."),
    "Cancelled": ("Cancelled", "neutral", "Withdrawn before completion."),
    "Hidden": ("Hidden", "neutral", "Kept on the record but not shown publicly."),
    "Selected": ("Selected", "positive", "Accepted."),
    "Waitlisted": ("Waitlisted", "attention", "Held for a later decision."),
    "Interview Scheduled": ("Interview Scheduled", "progress", "An interview is booked."),
    "Paid": ("Paid", "positive", "Settled."),
})


# ── Publication ─────────────────────────────────────────────────────────

PUBLICATION = _table("publication", {
    "Private": ("Internal only", "neutral", "Visible only inside the office."),
    "Pending": ("Publication requested", "attention", "Waiting for a publication decision."),
    "Published": ("Public", "positive", "Visible on the public transparency site."),
    "Withdrawn": ("Withdrawn", "neutral", "Removed from the public site."),
})


# ── Record lifecycle ────────────────────────────────────────────────────

LIFECYCLE = _table("lifecycle", {
    "Draft": ("Draft", "neutral", "Being set up; not yet running."),
    "Planned": ("Planned", "attention", "Scheduled but not started."),
    "Active": ("Active", "progress", "Running now."),
    "Closing": ("Closing", "progress", "Finished on the ground; closure work outstanding."),
    "Completed": ("Completed", "positive", "Closed."),
    "Cancelled": ("Cancelled", "neutral", "Called off."),
    "Archived": ("Archived", "neutral", "Retained for the record only."),
    "Inactive": ("Inactive", "neutral", "No longer in use."),
})


_TABLES = {
    "availability": AVAILABILITY,
    "review": REVIEW,
    "publication": PUBLICATION,
    "lifecycle": LIFECYCLE,
}


def status_of(dimension: str, value: str | None) -> Status:
    """Resolve one raw stored value into its dimension's vocabulary.

    An unrecognised value keeps its own word and renders neutral. That is
    deliberate: showing the raw value tells an operator that something new
    reached the database, whereas the old `else` branch quietly painted it
    as an error (which is how a seeded ``Verified`` buddy log came to look
    like a failure).
    """
    table = _TABLES.get(dimension, {})
    if value in table:
        return table[value]
    return Status(dimension=dimension, label=str(value or "Not recorded"), tone="neutral")


def review_state(value: str | None) -> str:
    """The row-pip state for a review value, via the vocabulary above.

    Replaces the hand-written ternaries that read
    ``'complete' if x == 'Approved' else 'overdue'``. Those treated `else`
    as "bad", so a seeded ``Verified`` buddy log -- a *successful*
    verification -- was painted in danger red under a warning triangle,
    which is audit finding P0-04.
    """
    return status_of("review", value).state


def availability_status(document) -> Status:
    from app.services.documents import compute_availability

    return status_of("availability", compute_availability(document))


def register_globals(app) -> None:
    app.jinja_env.globals["status_of"] = status_of
    app.jinja_env.globals["review_state"] = review_state
    app.jinja_env.globals["availability_status"] = availability_status
    app.jinja_env.globals["DIMENSION_LABELS"] = DIMENSION_LABELS
