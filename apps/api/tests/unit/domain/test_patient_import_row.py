"""The rows of an ops patient import (M2-P4; FR-PAT-08, spec patients R8)."""

from __future__ import annotations

from datetime import date

import pytest

from mediease_api.domain.patients.import_row import (
    IMPORT_COLUMNS,
    header_problems,
    name_key,
    normalise_heading,
    parse_row,
)
from mediease_api.domain.patients.patient import Language, Sex
from mediease_api.domain.shared.errors import InvalidValue

TODAY = date(2026, 10, 5)


def _cells(**overrides: str) -> dict[str, str]:
    cells = {
        "name": "Asha Rao",
        "phone": "90000 00101",
        "sex": "F",
        "dob_or_age": "1990-05-17",
        "guardian_name": "",
        "language": "",
    }
    cells.update(overrides)
    return cells


def _refused(**overrides: str) -> InvalidValue:
    with pytest.raises(InvalidValue) as caught:
        parse_row(_cells(**overrides), today=TODAY)
    return caught.value


# --- header ------------------------------------------------------------------------------------


def test_r8_the_header_names_each_column_once_in_any_order_and_case() -> None:
    assert header_problems(list(IMPORT_COLUMNS)) == []
    assert (
        header_problems(["\ufeffLanguage", " PHONE ", "Name", "sex", "DOB_or_age", "guardian_name"])
        == []
    )


def test_r8_a_missing_column_rejects_the_file() -> None:
    assert header_problems(["name", "phone", "sex", "dob_or_age", "language"]) == [
        "column guardian_name is missing"
    ]


def test_r8_an_unknown_column_is_named_by_position_not_by_its_text() -> None:
    problems = header_problems([*IMPORT_COLUMNS, "Diagnosis"])

    assert problems == [f"column 7 is not one of: {', '.join(IMPORT_COLUMNS)}"]
    assert "Diagnosis" not in str(problems) and "diagnosis" not in str(problems)


def test_r8_a_repeated_column_is_reported() -> None:
    assert header_problems([*IMPORT_COLUMNS, "phone"]) == ["column phone appears more than once"]


def test_headings_are_trimmed_lower_cased_and_lose_the_excel_bom() -> None:
    assert normalise_heading("\ufeff Name ") == "name"


# --- a good row ----------------------------------------------------------------------------------


def test_fr_pat_08_a_row_becomes_an_import_row_with_registrations_rules() -> None:
    row = parse_row(_cells(), today=TODAY)

    assert row.full_name == "Asha Rao"
    assert row.phone.e164 == "+919000000101"  # R1: normalised as in registration
    assert row.sex is Sex.FEMALE
    assert (row.date_of_birth, row.age_years) == (date(1990, 5, 17), None)
    assert row.guardian_name is None
    assert row.language is Language.EN  # blank is English
    assert "Asha" not in repr(row)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("F", Sex.FEMALE),
        ("female", Sex.FEMALE),
        ("M", Sex.MALE),
        ("Male", Sex.MALE),
        ("o", Sex.OTHER),
        ("OTHER", Sex.OTHER),
        ("U", Sex.UNDISCLOSED),
        ("undisclosed", Sex.UNDISCLOSED),
        ("", Sex.UNDISCLOSED),  # decision 2A
        ("  ", Sex.UNDISCLOSED),
    ],
)
def test_sex_accepts_letters_and_words_and_blank_is_undisclosed(text: str, expected: Sex) -> None:
    assert parse_row(_cells(sex=text), today=TODAY).sex is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("en", Language.EN), ("English", Language.EN), ("HI", Language.HI), ("hindi", Language.HI)],
)
def test_language_accepts_codes_and_names(text: str, expected: Language) -> None:
    assert parse_row(_cells(language=text), today=TODAY).language is expected


@pytest.mark.parametrize(
    ("text", "born"),
    [
        ("1990-05-17", date(1990, 5, 17)),
        ("17/05/1990", date(1990, 5, 17)),
        ("17-05-1990", date(1990, 5, 17)),
        ("03/04/2019", date(2019, 4, 3)),  # day first: 3 April, never 4 March
        (" 2026-10-05 ", TODAY),  # born today is not in the future
    ],
)
def test_dates_are_iso_or_day_first(text: str, born: date) -> None:
    row = parse_row(_cells(dob_or_age=text, guardian_name="Guardian Name"), today=TODAY)

    assert (row.date_of_birth, row.age_years) == (born, None)


@pytest.mark.parametrize("years", [0, 18, 45, 120])
def test_a_whole_number_is_an_age_recorded_on_the_clinics_today(years: int) -> None:
    row = parse_row(_cells(dob_or_age=str(years), guardian_name="Guardian Name"), today=TODAY)

    assert (row.date_of_birth, row.age_years) == (None, years)


def test_fr_pat_06_a_minor_with_a_guardian_is_accepted() -> None:
    row = parse_row(_cells(dob_or_age="6", guardian_name=" Asha Rao "), today=TODAY)

    assert row.guardian_name == "Asha Rao"


# --- refused rows ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "field", "reason"),
    [
        ({"name": "  "}, "name", "must not be empty"),
        ({"name": "x" * 201}, "name", "must be at most 200 characters"),
        ({"phone": ""}, "phone", "must not be empty"),
        ({"phone": "12345"}, "phone", "is not a valid phone number"),
        ({"phone": "call me"}, "phone", "is not a valid phone number"),
        ({"sex": "woman"}, "sex", "must be one of: f, female, m, male, o, other, u, undisclosed"),
        ({"dob_or_age": ""}, "dob_or_age", "must not be empty"),
        (
            {"dob_or_age": "121"},
            "dob_or_age",
            "must be an age (0-120) or a date as YYYY-MM-DD or DD/MM/YYYY",
        ),
        (
            {"dob_or_age": "-3"},
            "dob_or_age",
            "must be an age (0-120) or a date as YYYY-MM-DD or DD/MM/YYYY",
        ),
        (
            {"dob_or_age": "4.5"},
            "dob_or_age",
            "must be an age (0-120) or a date as YYYY-MM-DD or DD/MM/YYYY",
        ),
        (
            {"dob_or_age": "05/17/1990"},
            "dob_or_age",
            "must be an age (0-120) or a date as YYYY-MM-DD or DD/MM/YYYY",
        ),
        (
            {"dob_or_age": "31/02/2020"},
            "dob_or_age",
            "must be an age (0-120) or a date as YYYY-MM-DD or DD/MM/YYYY",
        ),
        ({"dob_or_age": "2026-10-06"}, "dob_or_age", "must not be in the future"),
        ({"dob_or_age": "6"}, "guardian_name", "is required for a patient under 18"),
        ({"dob_or_age": "2020-01-01"}, "guardian_name", "is required for a patient under 18"),
        ({"language": "tamil"}, "language", "must be one of: en, english, hi, hindi"),
    ],
)
def test_r8_a_bad_cell_names_its_column_and_never_its_value(
    overrides: dict[str, str], field: str, reason: str
) -> None:
    error = _refused(**overrides)

    assert (error.field, error.reason) == (field, reason)
    for value in overrides.values():
        if value.strip():
            assert value not in error.message


def test_the_first_bad_column_in_column_order_is_reported() -> None:
    assert _refused(name="", phone="bad").field == "name"


def test_an_adult_turning_18_today_needs_no_guardian() -> None:
    row = parse_row(_cells(dob_or_age="2008-10-05"), today=TODAY)

    assert row.guardian_name is None


# --- names for "already registered" ---------------------------------------------------------------


def test_name_keys_ignore_case_and_spacing() -> None:
    assert name_key("  Asha   RAO ") == name_key("asha rao") == "asha rao"
    assert name_key("Asha Rao") != name_key("Asha Rai")
