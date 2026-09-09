"""One timezone convention for the whole application.

Audit finding B09: itinerary import attached `Asia/Kolkata` to session times
while manual session creation stored a naive local datetime, and templates
formatted whatever was stored without converting it. On PostgreSQL, whose
`timestamptz` normalises to UTC, the same 09:00 session displayed as 09:00 if
typed in by hand and 03:30 if imported. SQLite keeps everything naive, which
is why the audit's local run did not reproduce it.

The convention is: **store UTC-aware, render campus-local with a label.**

* Every ingress path converts to UTC before the value reaches the database
  (`to_utc`).
* Every template renders through the `localdate`/`localtime`/`localdatetime`
  Jinja filters, which convert to `APP_TIMEZONE` and label the result.

A naive datetime read back from the database is treated as UTC. That is
correct for values written through `to_utc`, and it is the only defensible
reading on SQLite, where the driver discards the offset.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import current_app

DEFAULT_TIMEZONE = "Asia/Kolkata"


def campus_zone() -> ZoneInfo:
    return ZoneInfo(current_app.config.get("APP_TIMEZONE", DEFAULT_TIMEZONE) if current_app else DEFAULT_TIMEZONE)


def timezone_label() -> str:
    """Short label shown beside a rendered time, e.g. `IST`."""
    return datetime.now(campus_zone()).strftime("%Z")


def to_utc(value: datetime | None) -> datetime | None:
    """Interpret a naive datetime as campus-local and return it in UTC.

    Use on every path that accepts a wall-clock time from a person: an
    ``<input type="datetime-local">``, a spreadsheet cell, an itinerary row.
    An already-aware value is simply converted.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=campus_zone())
    return value.astimezone(timezone.utc)


def to_campus(value: datetime | None) -> datetime | None:
    """Return `value` in campus-local time, treating naive input as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(campus_zone())


def format_campus(value: datetime | None, fmt: str, *, with_label: bool = False) -> str:
    local = to_campus(value)
    if local is None:
        return "—"
    rendered = local.strftime(fmt)
    return f"{rendered} {timezone_label()}" if with_label else rendered


def register_filters(app) -> None:
    """Install the rendering filters. Times carry a timezone label; bare
    dates do not, since a labelled date reads as noise."""
    app.jinja_env.filters["localdate"] = lambda value, fmt="%a, %d %b %Y": format_campus(value, fmt)
    app.jinja_env.filters["localtime"] = lambda value, fmt="%I:%M %p", label=True: format_campus(value, fmt, with_label=label)
    app.jinja_env.filters["localdatetime"] = lambda value, fmt="%d %b %Y, %I:%M %p", label=True: format_campus(value, fmt, with_label=label)
