"""Money in integer paise (AGENTS.md "Money"; M6d decision B1).

Amounts are never floats. A price on the fee schedule or a bill line is 0 to ₹1,00,000
(10,000,000 paise); a percentage is applied with half-up rounding to the paisa.
"""

from __future__ import annotations

from mediease_api.domain.shared.errors import InvalidValue

PAISE_PER_RUPEE = 100
# B1: one line (and so one price) up to ₹1,00,000.
MAX_LINE_PAISE = 100_000 * PAISE_PER_RUPEE


def check_price(paise: int, field: str) -> int:
    """A price on the fee schedule or a line: whole paise, 0 to ₹1,00,000."""
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise InvalidValue(field, "must be a whole number of paise")
    if not 0 <= paise <= MAX_LINE_PAISE:
        raise InvalidValue(field, f"must be between 0 and {MAX_LINE_PAISE} paise")
    return paise


def percent_of(paise: int, percent_basis_points: int) -> int:
    """``paise`` times a percent, where the percent is in hundredths (1250 = 12.5%), half up."""
    return (paise * percent_basis_points + 5_000) // 10_000
