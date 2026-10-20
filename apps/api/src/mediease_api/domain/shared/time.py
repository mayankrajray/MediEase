"""Timestamps entering the domain are timezone-aware UTC (CLAUDE.md "Time is explicit")."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from mediease_api.domain.shared.errors import InvalidValue


def require_utc(value: datetime, field: str) -> datetime:
    """Return ``value`` with the UTC tzinfo; reject naive or non-UTC timestamps.

    A naive datetime has no defined instant, and a non-UTC offset usually means
    a clinic-local time leaked past the edge, where it should have been converted.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidValue(field, "must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise InvalidValue(field, "must be in UTC")
    return value.astimezone(UTC)


def local_date(instant: datetime, timezone: str) -> date:
    """The calendar date at ``instant`` in an IANA time zone (a clinic's own "today").

    Ages, birthdays and the under-18 rule are questions about a date, and the date
    depends on where the clinic is: 23:30 UTC on 2 October is already 3 October in
    Asia/Kolkata. The caller passes the clinic's zone; the server's is never used.
    """
    return require_utc(instant, "instant").astimezone(ZoneInfo(timezone)).date()


def local_day_start(day: date, timezone: str) -> datetime:
    """The UTC instant a clinic-local date begins (M6-P1: "today" as a range of instants)."""
    return datetime.combine(day, datetime.min.time(), tzinfo=ZoneInfo(timezone)).astimezone(UTC)
