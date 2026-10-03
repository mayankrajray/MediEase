"""Age as a fact plus a date (spec patients §3, D4).

A date of birth never changes; "age 6" is true only on the day it was said. So a
patient stores a date of birth *or* an age with the clinic-local date it was
recorded on, and the age is computed for whichever date the question is about.
The guardian rule ("under 18") therefore never depends on a number that went
stale.

All arithmetic is on calendar dates handed in by the caller: the domain does no
time-zone conversion (CLAUDE.md "Time is explicit").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from mediease_api.domain.shared.errors import InvalidValue

ADULT_AGE = 18
MAX_RECORDED_AGE = 120


@dataclass(frozen=True, slots=True)
class Age:
    """Either a date of birth, or an age in years recorded on ``recorded_on``."""

    date_of_birth: date | None
    recorded_years: int | None
    recorded_on: date | None

    def __post_init__(self) -> None:
        if self.date_of_birth is not None:
            if self.recorded_years is not None:
                raise InvalidValue("age", "give a date of birth or an age, not both")
            return
        if self.recorded_years is None or self.recorded_on is None:
            raise InvalidValue("age", "a date of birth or an age is required")
        if not 0 <= self.recorded_years <= MAX_RECORDED_AGE:
            raise InvalidValue("age", f"must be between 0 and {MAX_RECORDED_AGE} years")

    @classmethod
    def from_birth_date(cls, date_of_birth: date, *, today: date) -> Age:
        """``today`` is the clinic-local date; a birth date after it is in the future."""
        if date_of_birth > today:
            raise InvalidValue("date_of_birth", "must not be in the future")
        return cls(date_of_birth=date_of_birth, recorded_years=None, recorded_on=None)

    @classmethod
    def from_recorded_age(cls, years: int, *, recorded_on: date) -> Age:
        return cls(date_of_birth=None, recorded_years=years, recorded_on=recorded_on)

    def years(self, on: date) -> int:
        """Whole years of age on ``on`` (never negative)."""
        if self.date_of_birth is not None:
            return _whole_years(self.date_of_birth, on)
        assert self.recorded_years is not None and self.recorded_on is not None
        return self.recorded_years + _whole_years(self.recorded_on, on)

    def is_minor(self, on: date) -> bool:
        return self.years(on) < ADULT_AGE


def _whole_years(start: date, end: date) -> int:
    """Completed years from ``start`` to ``end``; a 29 February birthday falls on 1 March."""
    if end <= start:
        return 0
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return years
