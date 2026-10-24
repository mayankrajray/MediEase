"""The structured instruction vocabulary (spec prescriptions §3; M4-P2 decision 4A).

These are *formatting* vocabularies the doctor chooses from, not clinical recommendations: the
codes say how an instruction is phrased for the patient, in English or Hindi (P4/P5 phrasebook).
Nothing here knows a medicine, a dose or what is appropriate (FR-RX-10, principle 6). Wording is
not defined here; only the codes and the shape of their parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.text import optional_text


class Timing(StrEnum):
    BEFORE_FOOD = "BEFORE_FOOD"
    AFTER_FOOD = "AFTER_FOOD"
    WITH_FOOD = "WITH_FOOD"
    EMPTY_STOMACH = "EMPTY_STOMACH"
    BEDTIME = "BEDTIME"
    ANY = "ANY"


class PreparationCode(StrEnum):
    SHAKE_WELL = "SHAKE_WELL"
    DILUTE_IN_WATER = "DILUTE_IN_WATER"  # + amount ("10 ml")
    DISSOLVE = "DISSOLVE"
    CHEW = "CHEW"
    DO_NOT_CRUSH = "DO_NOT_CRUSH"
    # M6b-P3 (prescriptions R25): the doctor picks these; the system never adds one.
    WITH_WATER = "WITH_WATER"
    WITH_WARM_WATER = "WITH_WARM_WATER"
    WITH_MILK = "WITH_MILK"
    CUSTOM = "CUSTOM"  # + text


class StorageCode(StrEnum):
    ROOM_TEMP = "ROOM_TEMP"
    REFRIGERATE = "REFRIGERATE"
    AWAY_FROM_LIGHT = "AWAY_FROM_LIGHT"
    DISCARD_AFTER_DAYS = "DISCARD_AFTER_DAYS"  # + days


PHRASE_TEXT_MAX = 100
DISCARD_DAYS_MAX = 365


@dataclass(frozen=True, slots=True)
class Preparation:
    """One preparation phrase; ``text`` is the amount (dilute) or the doctor's words (custom)."""

    code: PreparationCode
    text: str | None = None

    @classmethod
    def of(cls, code: PreparationCode, text: str | None, field: str) -> Preparation:
        cleaned = optional_text(text, f"{field}.text", max_length=PHRASE_TEXT_MAX)
        needs_text = code in (PreparationCode.DILUTE_IN_WATER, PreparationCode.CUSTOM)
        if needs_text and cleaned is None:
            raise InvalidValue(f"{field}.text", f"is required for {code.value}")
        if not needs_text and cleaned is not None:
            raise InvalidValue(f"{field}.text", f"is not used with {code.value}")
        return cls(code, cleaned)

    def as_json(self) -> dict[str, str | None]:
        return {"code": self.code.value, "text": self.text}


@dataclass(frozen=True, slots=True)
class Storage:
    """One storage phrase; ``days`` only for ``DISCARD_AFTER_DAYS``."""

    code: StorageCode
    days: int | None = None

    @classmethod
    def of(cls, code: StorageCode, days: int | None, field: str) -> Storage:
        if code is StorageCode.DISCARD_AFTER_DAYS:
            if days is None or not 1 <= days <= DISCARD_DAYS_MAX:
                raise InvalidValue(f"{field}.days", f"must be 1-{DISCARD_DAYS_MAX}")
        elif days is not None:
            raise InvalidValue(f"{field}.days", f"is not used with {code.value}")
        return cls(code, days)

    def as_json(self) -> dict[str, str | int | None]:
        return {"code": self.code.value, "days": self.days}
