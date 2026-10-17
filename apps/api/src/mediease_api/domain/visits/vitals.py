"""Vital signs recorded at a visit (FR-VIS-02; docs/DATA_MODEL.md ``visits.vitals``).

A closed set of optional numbers. The unit is fixed by the key, so a value is never ambiguous.
The bounds only catch typing errors (a temperature of 370, an SpO2 of 990); they are input checks,
not clinical ranges, and nothing in MediEase interprets the values (CLAUDE.md: no medical logic).
Errors name the key and the rule, never the value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mediease_api.domain.shared.errors import InvalidValue


@dataclass(frozen=True, slots=True)
class VitalSpec:
    unit: str
    low: float
    high: float
    whole: bool  # counted or measured in whole units (mmHg, beats, %, breaths)


VITALS: Mapping[str, VitalSpec] = MappingProxyType(
    {
        "bp_systolic": VitalSpec("mmHg", 40, 300, whole=True),
        "bp_diastolic": VitalSpec("mmHg", 20, 200, whole=True),
        "pulse": VitalSpec("/min", 20, 250, whole=True),
        "temp_c": VitalSpec("°C", 25, 45, whole=False),
        "weight_kg": VitalSpec("kg", 0.3, 400, whole=False),
        "height_cm": VitalSpec("cm", 20, 260, whole=False),
        "spo2": VitalSpec("%", 50, 100, whole=True),
        "resp_rate": VitalSpec("/min", 4, 80, whole=True),
    }
)


@dataclass(frozen=True, slots=True)
class Vitals:
    """Recorded vitals by key; absent keys were not taken."""

    values: Mapping[str, float]

    @classmethod
    def empty(cls) -> Vitals:
        return cls(MappingProxyType({}))

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> Vitals:
        """Validate a submitted map. ``None`` values mean "not taken" and are dropped."""
        values: dict[str, float] = {}
        for key, value in raw.items():
            spec = VITALS.get(key)
            if spec is None:
                raise InvalidValue(f"vitals.{key}", "is not a recorded vital")
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise InvalidValue(f"vitals.{key}", "must be a number")
            number = float(value)
            if spec.whole and not number.is_integer():
                raise InvalidValue(f"vitals.{key}", "must be a whole number")
            if not spec.low <= number <= spec.high:
                raise InvalidValue(
                    f"vitals.{key}", f"must be between {spec.low:g} and {spec.high:g} {spec.unit}"
                )
            values[key] = number if not spec.whole else float(int(number))
        return cls(MappingProxyType(dict(sorted(values.items()))))

    def as_json(self) -> dict[str, int | float]:
        """Whole-unit vitals as integers, the rest as given (rounded to 0.1)."""
        return {
            key: int(value) if VITALS[key].whole else round(value, 1)
            for key, value in self.values.items()
        }

    def __bool__(self) -> bool:
        return bool(self.values)
