"""The medicine-schedule engine's vocabulary: slots, frequency patterns, duration kinds (M6b-P3).

Developer decisions D1-D3, D8, D9 (design note M6b, "Medicine planner"); prescriptions spec R21-R24.

**One definition of a day.** A structured frequency is a pattern of ``0`` and ``1`` read against
the **slot set for its length**, defined here and nowhere else:

- 3 digits: morning, afternoon, night (``1-0-1`` is morning and night, as Indian prescriptions
  are written);
- 4 digits: morning, afternoon, evening, night.

A ``1`` schedules the medicine in that slot; a ``0`` does not. All-zero patterns, other lengths
and other characters are refused when the doctor enters a structured frequency: anything else
(``2-0-2``, ``½-0-½``, "every 6 hours") is ``CUSTOM`` with the doctor's words, because digits
other than 0 and 1 carry a dose, and MediEase never reads a dose. ``SOS``, ``ONCE`` and
``CUSTOM`` have no slot and are never reminded.

Nothing here decides how a medicine is taken: it only says which of the doctor's own marks fall
in which slot, and words what the doctor chose. The API publishes these sets
(``GET /rx-vocabulary``); no client keeps a copy.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar

from mediease_api.domain.shared.errors import InvalidValue


class Slot(StrEnum):
    """A time of day a dose can be scheduled in, in the order of the day."""

    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"
    NIGHT = "NIGHT"


# D1: the pattern length chooses the slot set. Read-only, the single source of truth.
SLOT_SETS: Mapping[int, tuple[Slot, ...]] = MappingProxyType(
    {
        3: (Slot.MORNING, Slot.AFTERNOON, Slot.NIGHT),
        4: (Slot.MORNING, Slot.AFTERNOON, Slot.EVENING, Slot.NIGHT),
    }
)
DAY_ORDER: tuple[Slot, ...] = (Slot.MORNING, Slot.AFTERNOON, Slot.EVENING, Slot.NIGHT)


class FrequencyKind(StrEnum):
    PATTERN = "PATTERN"
    SOS = "SOS"
    ONCE = "ONCE"
    CUSTOM = "CUSTOM"


_SPECIALS = frozenset(
    {FrequencyKind.SOS.value, FrequencyKind.ONCE.value, FrequencyKind.CUSTOM.value}
)
_CANONICAL = re.compile(r"^[01](-[01]){2,3}$")
_PATTERN_HINT = "use 0 and 1 for 3 or 4 times of day (e.g. 1-0-1), or choose CUSTOM"


@dataclass(frozen=True, slots=True)
class Frequency:
    """A line's frequency: a canonical pattern (``1-0-1``, ``1-0-1-1``) or SOS, ONCE, CUSTOM.

    The constructor takes a stored, canonical value (it is checked); ``parse`` takes what was
    entered, which may be written ``101`` or ``1 0 1``.
    """

    value: str

    SOS: ClassVar[Frequency]
    ONCE: ClassVar[Frequency]
    CUSTOM: ClassVar[Frequency]

    def __post_init__(self) -> None:
        if self.value in _SPECIALS:
            return
        if not _CANONICAL.fullmatch(self.value) or "1" not in self.value:
            raise InvalidValue("frequency", _PATTERN_HINT)

    @classmethod
    def parse(cls, raw: str, field: str = "frequency") -> Frequency:
        text = raw.strip()
        if text.upper() in _SPECIALS:
            return cls(text.upper())
        digits = re.sub(r"[\s-]", "", text)
        if len(digits) not in SLOT_SETS or set(digits) - {"0", "1"} or "1" not in digits:
            raise InvalidValue(field, _PATTERN_HINT)
        return cls("-".join(digits))

    @property
    def kind(self) -> FrequencyKind:
        return FrequencyKind(self.value) if self.value in _SPECIALS else FrequencyKind.PATTERN

    @property
    def is_custom(self) -> bool:
        return self.value == FrequencyKind.CUSTOM.value

    @property
    def slots(self) -> tuple[Slot, ...]:
        """The slots a ``1`` falls in, in the day's order; none for SOS, ONCE and CUSTOM."""
        if self.kind is not FrequencyKind.PATTERN:
            return ()
        digits = self.value.split("-")
        return tuple(
            slot for slot, d in zip(SLOT_SETS[len(digits)], digits, strict=True) if d == "1"
        )

    def __str__(self) -> str:
        return self.value


Frequency.SOS = Frequency(FrequencyKind.SOS.value)
Frequency.ONCE = Frequency(FrequencyKind.ONCE.value)
Frequency.CUSTOM = Frequency(FrequencyKind.CUSTOM.value)


class DurationKind(StrEnum):
    """D3: how long, as the doctor chose; no kind means "not stated"."""

    DAYS = "DAYS"
    UNTIL_REVIEW = "UNTIL_REVIEW"
    ONGOING = "ONGOING"
