"""Phone numbers: one E.164 form inside the system, masked whenever displayed in logs.

AGENTS.md "Phones": validated and normalised at the boundary, masked in logs.
Input without a country code is read as Indian (the pilot market): a 10-digit
national number, optionally written with a leading ``0`` or ``91``. Numbers with
``+`` or ``00`` are accepted for any country.

This is structural validation (length, digits, country code shape), not a
carrier lookup: it rejects typos, not numbers that are unassigned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mediease_api.domain.shared.errors import InvalidValue

_INDIA_CODE = "91"
_INDIA_NATIONAL = re.compile(r"[1-9]\d{9}")
# E.164: up to 15 digits after "+", no leading zero. Below 8 digits no
# real subscriber number exists, so shorter input is a typo.
_E164_DIGITS = re.compile(r"[1-9]\d{7,14}")
# Separators people type; anything else (letters, extensions) is rejected.
_SEPARATORS = re.compile(r"[\s\-().]")


@dataclass(frozen=True, slots=True, repr=False)
class PhoneNumber:
    """A validated phone number in E.164 form, e.g. ``+919000000001``."""

    e164: str

    def __post_init__(self) -> None:
        digits = self.e164[1:]
        if not self.e164.startswith("+") or not _E164_DIGITS.fullmatch(digits):
            raise InvalidValue("phone", "must be in E.164 form")
        if digits.startswith(_INDIA_CODE) and not _INDIA_NATIONAL.fullmatch(digits[2:]):
            raise InvalidValue("phone", "an Indian number has 10 digits after +91")

    @classmethod
    def parse(cls, raw: str, field: str = "phone") -> PhoneNumber:
        """Normalise user input to E.164, or raise ``InvalidValue`` naming ``field``."""
        compact = _SEPARATORS.sub("", raw)
        if compact.startswith("00"):
            compact = "+" + compact[2:]

        if compact.startswith("+"):
            candidate = compact
        elif _INDIA_NATIONAL.fullmatch(compact):
            candidate = f"+{_INDIA_CODE}{compact}"
        elif compact.startswith("0") and _INDIA_NATIONAL.fullmatch(compact[1:]):
            candidate = f"+{_INDIA_CODE}{compact[1:]}"
        elif compact.startswith(_INDIA_CODE) and _INDIA_NATIONAL.fullmatch(compact[2:]):
            candidate = f"+{compact}"
        else:
            raise InvalidValue(field, "is not a valid phone number")

        try:
            return cls(candidate)
        except InvalidValue as exc:
            raise InvalidValue(field, exc.reason) from None

    def masked(self) -> str:
        """``+91******3210``: country prefix and last four digits only (for logs)."""
        hidden = len(self.e164) - 7
        return f"{self.e164[:3]}{'*' * hidden}{self.e164[-4:]}"

    def __repr__(self) -> str:
        # Keeps full numbers out of tracebacks, debug output and log fields.
        return f"PhoneNumber({self.masked()!r})"

    __str__ = __repr__
