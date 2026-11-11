"""What the patient assistant needs to book from plain words (M7c-P7; spec assistant R22-R25).

The browser sends only the visible conversation, so a model that is told "1", "yes" or "the
first one" has the clinic's and doctor's *names*, a date and a time, not the IDs a tool returned
earlier. These helpers turn those words back into the records, so a choice made in the
conversation always lands on the same clinic and time:

- ``resolve_clinic`` and ``resolve_doctor``: a slug or ID, or a name (an exact name wins over a
  fuzzy one, so "Sample Clinic" never means "Sample Clinic Two"); several matches is a question
  back to the user, never a guess.
- ``part_of_day``: morning (before 12:00), afternoon (12:00-16:59), evening (17:00 on) on the
  clinic's clock, the words patients use ("subah", "dopahar", "shaam" are mapped too).
- ``find_offer``: the free time at a given local date and time, from the same availability the
  public page shows, or ``None`` when it is not free any more.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from mediease_api.application.assistant.tools import ToolArgumentError
from mediease_api.application.booking.public import DayOffer, PublicDoctor, SessionOffer
from mediease_api.domain.scheduling.mode import BookingMode

MORNING_ENDS = time(12, 0)
AFTERNOON_ENDS = time(17, 0)

_PARTS = {
    "morning": "morning",
    "subah": "morning",
    "subha": "morning",
    "सुबह": "morning",
    "afternoon": "afternoon",
    "noon": "afternoon",
    "dopahar": "afternoon",
    "dophar": "afternoon",
    "dopehar": "afternoon",
    "दोपहर": "afternoon",
    "evening": "evening",
    "night": "evening",
    "shaam": "evening",
    "sham": "evening",
    "शाम": "evening",
}
_TITLE = re.compile(r"^(?:dr\.?|doctor)\s+", re.IGNORECASE)
_SPACES = re.compile(r"\s+")
_CLOCK = re.compile(r"^(\d{1,2})[:.](\d{2})\s*(am|pm)?$", re.IGNORECASE)


def plain(name: str) -> str:
    """A name compared without case, extra spaces or a leading "Dr."."""
    return _TITLE.sub("", _SPACES.sub(" ", name).strip()).lower()


def part_of_day(value: str | None) -> str | None:
    """``morning``, ``afternoon``, ``evening`` or ``None``; an unknown word is an argument error."""
    if value is None or not value.strip():
        return None
    part = _PARTS.get(value.strip().lower())
    if part is None:
        raise ToolArgumentError("'part_of_day' must be morning, afternoon or evening")
    return part


def in_part(local: time, part: str | None) -> bool:
    if part is None:
        return True
    if part == "morning":
        return local < MORNING_ENDS
    if part == "afternoon":
        return MORNING_ENDS <= local < AFTERNOON_ENDS
    return local >= AFTERNOON_ENDS


def clock(value: str) -> time:
    """``10:00``, ``4:30 pm`` or ``16.30`` as a time of day."""
    match = _CLOCK.match(value.strip())
    if match is None:
        raise ToolArgumentError("'time' must be a time like 10:00 or 4:30 PM")
    hour, minute, half = int(match.group(1)), int(match.group(2)), (match.group(3) or "").lower()
    if half == "pm" and hour < 12:
        hour += 12
    if half == "am" and hour == 12:
        hour = 0
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ToolArgumentError("'time' must be a time like 10:00 or 4:30 PM")
    return time(hour, minute)


@dataclass(frozen=True, slots=True)
class Named:
    """One clinic or doctor a name may mean: what to call it and its key."""

    key: str
    name: str


def pick(wanted: str, candidates: Sequence[Named], what: str) -> Named:
    """The one candidate ``wanted`` names: by key, by exact name, or the only fuzzy match."""
    for c in candidates:
        if c.key == wanted:
            return c
    exact = [c for c in candidates if plain(c.name) == plain(wanted)]
    if len(exact) == 1:
        return exact[0]
    near = exact or [c for c in candidates if plain(wanted) in plain(c.name)]
    if len(near) == 1:
        return near[0]
    if not near:
        raise ToolArgumentError(f"no {what} called '{wanted}'; call search_clinics")
    names = "; ".join(c.name for c in near[:5])
    raise ToolArgumentError(f"'{wanted}' could be more than one {what} ({names}); ask which one")


def resolve_doctor(doctors: Sequence[PublicDoctor], wanted: str | None) -> PublicDoctor:
    """The clinic's doctor by ID or name; with no name, the clinic's only doctor."""
    if wanted is None:
        if len(doctors) == 1:
            return doctors[0]
        names = "; ".join(d.display_name for d in doctors[:8])
        raise ToolArgumentError(f"the clinic has more than one doctor ({names}); ask which one")
    chosen = pick(wanted, [Named(str(d.id), d.display_name) for d in doctors], "doctor")
    return next(d for d in doctors if str(d.id) == chosen.key)


@dataclass(frozen=True, slots=True)
class Offer:
    """One free time: the session it belongs to and, in slot mode, the slot's start."""

    session_start: datetime
    slot_start: datetime | None

    @property
    def starts_at(self) -> datetime:
        return self.slot_start or self.session_start


def offers_of(session: SessionOffer, limit: int) -> list[Offer]:
    if session.mode is BookingMode.TOKENS:
        return [Offer(session.starts_at, None)]
    return [Offer(session.starts_at, s.starts_at) for s in session.slots[:limit]]


def find_offer(days: Sequence[DayOffer], on: date, at: time, timezone: str) -> Offer | None:
    """The free time on ``on`` that starts at ``at`` (a slot, or a token session's start, or a
    time inside a token session), on the clinic's clock; ``None`` if it is not free."""
    zone = ZoneInfo(timezone)
    for day in days:
        if day.on_date != on:
            continue
        for session in day.sessions:
            if session.mode is BookingMode.SLOTS:
                for slot in session.slots:
                    if slot.starts_at.astimezone(zone).time().replace(second=0) == at:
                        return Offer(session.starts_at, slot.starts_at)
                continue
            start = session.starts_at.astimezone(zone).time()
            end = session.ends_at.astimezone(zone).time()
            if start <= at < end or start == at:
                return Offer(session.starts_at, None)
    return None


def is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True
