"""When a reminder is due (spec R1, R4; FR-REM-01, 04). Pure: the caller passes the time.

A follow-up reminder is due at 09:00 clinic time on the day before the follow-up date (FR-REM-01);
if that has passed, it is due now. Nothing is sent between 21:00 and 08:00 clinic time
(FR-REM-04): a due time in that window moves to the next 08:00. Both are fixed for the pilot
(M5-P4); per-clinic values would be settings.

M6a-P8 (FR-APT-08, decision 2A): an appointment's reminders go at 19:00 clinic time the day
before and a clinic-chosen number of hours before the visit, each moved out of the quiet hours,
and skipped when that is under an hour away or not before the visit.
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


EVENING_AT = time(19, 0)
# A reminder due this soon after the booking adds nothing: the confirmation has just said it.
MIN_LEAD = timedelta(minutes=60)
HOURS_BEFORE_MAX = 6


def appointment_reminder_times(
    *,
    starts_at: datetime,
    timezone: str,
    now: datetime,
    evening_before: bool,
    hours_before: int,
) -> list[datetime]:
    """When an appointment's reminders are due (decision 2A), earliest first; possibly none.

    ``starts_at`` is the slot's start, or the session's in token mode.
    """
    starts_at = require_utc(starts_at, "starts_at")
    now = require_utc(now, "now")
    zone = ZoneInfo(timezone)
    planned: list[datetime] = []
    if evening_before:
        day_before = starts_at.astimezone(zone).date() - timedelta(days=1)
        planned.append(datetime.combine(day_before, EVENING_AT, tzinfo=zone).astimezone(UTC))
    if hours_before:
        planned.append(starts_at - timedelta(hours=hours_before))
    due = {outside_quiet_hours(p, timezone) for p in planned}
    return sorted(d for d in due if now + MIN_LEAD <= d < starts_at)
