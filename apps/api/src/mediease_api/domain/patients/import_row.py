"""One row of an ops patient import (spec patients R8, M2-P4): the header and the cells.

The file has exactly the columns in ``IMPORT_COLUMNS``, in any order and case. Each row is
turned into an ``ImportRow`` with the same rules registration applies (R1, R3, I1, I4), or
refused with an ``InvalidValue`` naming the *column*, so the dry-run report can say "row 14,
phone: is not a valid phone number" without repeating what the cell held.

Cells are personal data. Nothing here puts a cell's text into an error: reasons are fixed
strings (CLAUDE.md "Never log PII"). Reading the bytes as CSV is the application's job; this
module sees strings only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from mediease_api.domain.patients.age import ADULT_AGE, MAX_RECORDED_AGE, Age
from mediease_api.domain.patients.patient import Language, Patient, Sex, parse_phone
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import optional_text, required_text

IMPORT_COLUMNS = ("name", "phone", "sex", "dob_or_age", "guardian_name", "language")

_SEX = {
    "f": Sex.FEMALE,
    "female": Sex.FEMALE,
    "m": Sex.MALE,
    "male": Sex.MALE,
    "o": Sex.OTHER,
    "other": Sex.OTHER,
    "u": Sex.UNDISCLOSED,
    "undisclosed": Sex.UNDISCLOSED,
}
_LANGUAGE = {
    "en": Language.EN,
    "english": Language.EN,
    "hi": Language.HI,
    "hindi": Language.HI,
}
# ISO first, then day-first (Indian lists). Month-first (US) order is deliberately absent:
# 03/04/2019 is 3 April, never 4 March.
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
_DIGITS = re.compile(r"\d{1,3}")
_DATE_REASON = "must be an age (0-120) or a date as YYYY-MM-DD or DD/MM/YYYY"


@dataclass(frozen=True, slots=True, repr=False)
class ImportRow:
    """A row that passed every rule: ready to become a ``Patient``."""

    full_name: str
    phone: PhoneNumber
    sex: Sex
    date_of_birth: date | None
    age_years: int | None
    guardian_name: str | None
    language: Language

    @property
    def name_key(self) -> str:
        return name_key(self.full_name)

    def __repr__(self) -> str:
        return "ImportRow(<redacted>)"


def header_problems(header: Sequence[str]) -> list[str]:
    """What is wrong with a header row; empty when it names each column exactly once.

    Problems name our columns or a position, never the text of an unknown heading.
    """
    names = [normalise_heading(cell) for cell in header]
    problems: list[str] = []
    for position, name in enumerate(names, start=1):
        if name not in IMPORT_COLUMNS:
            problems.append(f"column {position} is not one of: {', '.join(IMPORT_COLUMNS)}")
        elif names.index(name) != position - 1:
            problems.append(f"column {name} appears more than once")
    problems.extend(f"column {c} is missing" for c in IMPORT_COLUMNS if c not in names)
    return problems


def normalise_heading(cell: str) -> str:
    """``" Name "`` and ``"NAME"`` are ``name``; an Excel BOM on the first cell is dropped."""
    return cell.lstrip("\ufeff").strip().lower()


def parse_row(cells: Mapping[str, str], *, today: date) -> ImportRow:
    """Validate one row's cells (keyed by column) for a clinic whose local date is ``today``.

    Raises ``InvalidValue`` naming the first column at fault, in column order.
    """
    full_name = required_text(cells["name"], "name", max_length=Patient.NAME_MAX)
    phone = _phone(cells["phone"])
    sex = _choice(cells["sex"], _SEX, "sex", default=Sex.UNDISCLOSED)
    date_of_birth, age_years, age = _age(cells["dob_or_age"], today)
    guardian = optional_text(
        cells["guardian_name"], "guardian_name", max_length=Patient.GUARDIAN_MAX
    )
    if age.is_minor(today) and guardian is None:
        raise InvalidValue("guardian_name", f"is required for a patient under {ADULT_AGE}")
    language = _choice(cells["language"], _LANGUAGE, "language", default=Language.EN)
    return ImportRow(
        full_name=full_name,
        phone=phone,
        sex=sex,
        date_of_birth=date_of_birth,
        age_years=age_years,
        guardian_name=guardian,
        language=language,
    )


def name_key(full_name: str) -> str:
    """The name as compared for "already registered": case and spacing ignored."""
    return " ".join(full_name.split()).casefold()


def _phone(raw: str) -> PhoneNumber:
    if not raw.strip():
        raise InvalidValue("phone", "must not be empty")
    return parse_phone(raw)


def _choice[T](raw: str, allowed: Mapping[str, T], field: str, *, default: T) -> T:
    text = raw.strip().lower()
    if not text:
        return default
    try:
        return allowed[text]
    except KeyError:
        raise InvalidValue(field, f"must be one of: {', '.join(allowed)}") from None


def _age(raw: str, today: date) -> tuple[date | None, int | None, Age]:
    text = raw.strip()
    if not text:
        raise InvalidValue("dob_or_age", "must not be empty")
    if _DIGITS.fullmatch(text):
        years = int(text)
        if years > MAX_RECORDED_AGE:
            raise InvalidValue("dob_or_age", _DATE_REASON)
        return None, years, Age.from_recorded_age(years, recorded_on=today)
    born = _date(text)
    if born > today:
        raise InvalidValue("dob_or_age", "must not be in the future")
    return born, None, Age.from_birth_date(born, today=today)


def _date(text: str) -> date:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()  # a calendar date: no zone involved
        except ValueError:
            continue
    raise InvalidValue("dob_or_age", _DATE_REASON)
