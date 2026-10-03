"""How a lookup text is read (spec patients R5, FR-PAT-04).

In order: a phone number, a patient code, otherwise the start of a name. Pure, so
the rule is testable without a database and the repository stays a dumb query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from mediease_api.domain.patients.code import parse_code_query
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber

MAX_RESULTS = 20
# Fewer digits than this is not a phone number anyone would search by.
MIN_PHONE_DIGITS = 7

_PHONE_SEPARATORS = re.compile(r"[\s\-+().]")


class QueryKind(StrEnum):
    PHONE = "PHONE"
    CODE = "CODE"
    NAME = "NAME"


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """``value`` is the E.164 number, the canonical code, or the lower-cased name prefix.

    ``None`` for a phone-looking text that is not a valid number: it matches nobody.
    """

    kind: QueryKind
    value: str | None


def classify_query(text: str) -> ParsedQuery | None:
    """The reading of ``text``, or ``None`` when it is blank (nothing to look up)."""
    stripped = text.strip()
    if not stripped:
        return None

    digits_only = _PHONE_SEPARATORS.sub("", stripped)
    if digits_only.isdigit() and len(digits_only) >= MIN_PHONE_DIGITS:
        try:
            return ParsedQuery(QueryKind.PHONE, PhoneNumber.parse(stripped).e164)
        except InvalidValue:
            return ParsedQuery(QueryKind.PHONE, None)

    code = parse_code_query(stripped)
    if code is not None:
        return ParsedQuery(QueryKind.CODE, code)

    return ParsedQuery(QueryKind.NAME, stripped.lower())
