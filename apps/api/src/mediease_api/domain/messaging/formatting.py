"""Dates, times and tokens as a patient reads them, in the clinic's time zone (spec R8).

Formatted here, without the platform locale, so a message reads the same on every server.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.time import require_utc

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _local(instant: datetime, timezone: str) -> datetime:
    return require_utc(instant, "instant").astimezone(ZoneInfo(timezone))


def _date(local: datetime, language: Language) -> str:
    if language is Language.HI:
        return f"{local.day:02d}/{local.month:02d}/{local.year}"
    return f"{_WEEKDAYS[local.weekday()]} {local.day} {_MONTHS[local.month - 1]} {local.year}"


def _time(local: datetime, language: Language) -> str:
    if language is Language.HI:
        return f"{local.hour:02d}:{local.minute:02d}"
    hour = local.hour % 12 or 12
    return f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def appointment_when(
    *, starts_at: datetime, token_number: int | None, timezone: str, language: Language
) -> str:
    """``Mon 20 Oct 2026, 10:30 AM`` for a slot; ``…, 9:00 AM, token 12`` for a token session.

    ``starts_at`` is the slot's start, or the session's start in token mode.
    """
    local = _local(starts_at, timezone)
    text = f"{_date(local, language)}, {_time(local, language)}"
    if token_number is not None:
        word = "टोकन" if language is Language.HI else "token"
        text = f"{text}, {word} {token_number}"
    return text
