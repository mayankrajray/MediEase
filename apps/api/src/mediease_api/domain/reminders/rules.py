"""When a reminder is due (spec R1, R4; FR-REM-01, 04). Pure: the caller passes the time.

A follow-up reminder is due at 09:00 clinic time on the day before the follow-up date (FR-REM-01);
if that has passed, it is due now. Nothing is sent between 21:00 and 08:00 clinic time
(FR-REM-04): a due time in that window moves to the next 08:00. Both are fixed for the pilot
(M5-P4); per-clinic values would be settings.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from mediease_api.domain.shared.time import require_utc

SEND_AT = time(9, 0)
DAYS_BEFORE = 1
QUIET_FROM = time(21, 0)
QUIET_UNTIL = time(8, 0)


def in_quiet_hours(instant: datetime, timezone: str) -> bool:
    local = require_utc(instant, "instant").astimezone(ZoneInfo(timezone)).time()
    return local >= QUIET_FROM or local < QUIET_UNTIL


def outside_quiet_hours(instant: datetime, timezone: str) -> datetime:
    """``instant``, or the next 08:00 clinic time if it falls in the quiet hours (R4, AC2)."""
    instant = require_utc(instant, "instant")
    if not in_quiet_hours(instant, timezone):
        return instant
    zone = ZoneInfo(timezone)
    local = instant.astimezone(zone)
    day = local.date() if local.time() < QUIET_UNTIL else local.date() + timedelta(days=1)
    return datetime.combine(day, QUIET_UNTIL, tzinfo=zone).astimezone(UTC)


def follow_up_due_at(follow_up: date, timezone: str, now: datetime) -> datetime:
    """R1, AC1: 09:00 clinic time the day before (now if already past), outside quiet hours."""
    now = require_utc(now, "now")
    zone = ZoneInfo(timezone)
    planned = datetime.combine(follow_up - timedelta(days=DAYS_BEFORE), SEND_AT, tzinfo=zone)
    due = max(planned.astimezone(UTC), now)
    return outside_quiet_hours(due, timezone)
