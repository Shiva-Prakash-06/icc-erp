"""One page of a list, and the numbers a pager needs to draw itself.

Why this exists. The event workspace used to render every task, every
checklist requirement, every budget line, every document and every team
assignment a record had, all of them stacked inside one ``.ds-scroll``. Two
things followed. The screen scrolled, which the Tile System's one-screen rule
forbids outright; and the reader met forty rows at once when the decision in
front of them concerned one. "Show everything and let them scroll" is not a
density choice, it is the absence of one.

So a section shows one page. ``PAGE_SIZE`` is the number of rows that fit
between the section strip and the pager at the shortest viewport the system
supports -- it is a geometry constant, not a preference, and it is paired with
the ``--row-height`` track in ``tiles.css``. Change one and you must change the
other.

Paging is a **query argument**, resolved on the server: ``?page=2``. The URL
map is frozen and query arguments are not part of it, so this is presentation.
It also means the pager is a set of ordinary links -- it works with JavaScript
off, it is keyboard operable for free, and a page of a section can be
bookmarked and sent to somebody.

A page never hides a row from the reader who was sent to it: ``page_of``
finds the page a given ``public_id`` lands on, so a deep link from the home
decision queue or from a notification opens on the page that actually contains
that record rather than on page 1 of a list it is not in.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Rows per page. See the module docstring: this is the count that fits the
#: shortest supported viewport, not a taste setting.
PAGE_SIZE = 8


@dataclass(frozen=True)
class Page:
    """A slice of a list plus everything the pager template needs.

    ``first`` and ``last`` are 1-based and inclusive, because they are shown
    to a person ("9-16 of 23"), not used as indices.
    """

    items: list
    number: int
    pages: int
    total: int
    per_page: int

    @property
    def first(self) -> int:
        return 0 if not self.total else (self.number - 1) * self.per_page + 1

    @property
    def last(self) -> int:
        return min(self.number * self.per_page, self.total)

    @property
    def has_prev(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.pages

    @property
    def prev(self) -> int:
        return max(1, self.number - 1)

    @property
    def next(self) -> int:
        return min(self.pages, self.number + 1)

    @property
    def multi(self) -> bool:
        """Whether the pager has anything to say. A single page still renders
        its count line, but without the step controls."""
        return self.pages > 1

    @property
    def numbers(self) -> list:
        """Page numbers to draw, with ``None`` where a gap is elided.

        A record with 400 documents must not draw 50 links across the pager.
        The window is the first page, the last page, and the current page with
        one neighbour either side.
        """
        if self.pages <= 7:
            return list(range(1, self.pages + 1))
        window = {1, self.pages, self.number}
        window |= {self.number - 1, self.number + 1}
        shown = sorted(n for n in window if 1 <= n <= self.pages)
        out: list = []
        for index, number in enumerate(shown):
            if index and number - shown[index - 1] > 1:
                out.append(None)
            out.append(number)
        return out


def paginate(items, page: int | str | None, per_page: int = PAGE_SIZE) -> Page:
    """Slice ``items`` for the requested page.

    Anything unusable in ``page`` -- absent, empty, ``"two"``, ``0``, ``-4``,
    or past the end -- resolves to a real page rather than erroring or showing
    an empty list. A pager argument is a hint from a URL somebody may have
    typed or truncated; it is never trusted arithmetic.
    """
    items = list(items)
    total = len(items)
    per_page = max(1, per_page)
    pages = max(1, -(-total // per_page))
    try:
        number = int(page)
    except (TypeError, ValueError):
        number = 1
    number = min(max(number, 1), pages)
    start = (number - 1) * per_page
    return Page(items=items[start:start + per_page], number=number, pages=pages, total=total, per_page=per_page)


def page_of(items, public_id: str | None, per_page: int = PAGE_SIZE) -> int | None:
    """The 1-based page holding ``public_id``, or ``None`` if it is not in
    ``items``. Used to resolve a deep link onto the page that contains the
    record it names."""
    if not public_id:
        return None
    for index, item in enumerate(items):
        if getattr(item, "public_id", None) == public_id:
            return index // max(1, per_page) + 1
    return None
