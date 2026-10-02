"""Timestamps entering the domain are timezone-aware UTC (CLAUDE.md "Time is explicit")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
