"""Patients, domain level (M2-P1; spec patients §3, R3, R4, R5, R6).

No database: ages, the guardian rule, codes, lookup classification, consent and the
clinic's code counter are all pure.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from mediease_api.domain.patients.age import Age
from mediease_api.domain.patients.code import (
    derive_code_prefix,
    format_code,
    parse_code_query,
    validate_code,
    validate_code_prefix,
)
from mediease_api.domain.patients.lookup import QueryKind, classify_query
from mediease_api.domain.patients.patient import GuardianRequired, Language, Patient, Sex
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from tests.builders import LATER, NOW, a_clinic, a_patient, new_id

TODAY = date(2026, 10, 2)
PHONE = PhoneNumber.parse("9000000001")


def _patient(**overrides: object) -> Patient:
    return a_patient(new_id(), new_id(), **overrides)


# --- Age -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("born", "on", "years"),
    [
        (date(2020, 10, 2), date(2026, 10, 2), 6),  # birthday today
        (date(2020, 10, 3), date(2026, 10, 2), 5),  # birthday tomorrow
        (date(2008, 10, 2), date(2026, 10, 1), 17),  # the day before the 18th birthday
        (date(2008, 10, 2), date(2026, 10, 2), 18),
        (date(2024, 2, 29), date(2025, 2, 28), 0),  # leap day: not yet in a non-leap year
        (date(2024, 2, 29), date(2025, 3, 1), 1),
        (date(2026, 10, 2), date(2026, 10, 2), 0),  # born today
    ],
)
def test_age_from_a_birth_date_counts_completed_years(born: date, on: date, years: int) -> None:
    assert Age.from_birth_date(born, today=max(born, on)).years(on) == years


def test_age_from_a_recorded_age_advances_with_time() -> None:
    age = Age.from_recorded_age(6, recorded_on=date(2026, 3, 10))

    assert age.years(date(2026, 3, 10)) == 6
    assert age.years(date(2027, 3, 9)) == 6
    assert age.years(date(2027, 3, 10)) == 7
    assert age.years(date(2030, 6, 1)) == 10


def test_age_is_never_negative() -> None:
    assert Age.from_recorded_age(5, recorded_on=date(2026, 3, 10)).years(date(2020, 1, 1)) == 5
    assert Age.from_birth_date(date(2026, 3, 10), today=TODAY).years(date(2020, 1, 1)) == 0


def test_age_is_minor_until_the_eighteenth_birthday() -> None:
    age = Age.from_birth_date(date(2008, 10, 2), today=TODAY)

    assert not age.is_minor(date(2026, 10, 2))
    assert age.is_minor(date(2026, 10, 1))


def test_i4_a_birth_date_in_the_future_is_refused() -> None:
    with pytest.raises(InvalidValue) as refused:
        Age.from_birth_date(date(2026, 10, 3), today=TODAY)
    assert refused.value.field == "date_of_birth"


@pytest.mark.parametrize("years", [-1, 121])
def test_i4_a_recorded_age_outside_0_to_120_is_refused(years: int) -> None:
    with pytest.raises(InvalidValue):
        Age.from_recorded_age(years, recorded_on=TODAY)


def test_an_age_needs_a_birth_date_or_a_recorded_age_but_not_both() -> None:
    with pytest.raises(InvalidValue):
        Age(None, None, None)
    with pytest.raises(InvalidValue):
        Age(date(2000, 1, 1), 26, TODAY)


# --- Codes -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prefix", "sequence", "code"),
    [
        ("ME", 142, "ME-0142"),
        ("ME", 1, "ME-0001"),
        ("ABCD", 9999, "ABCD-9999"),
        ("ME", 10000, "ME-10000"),
    ],
)
def test_r4_codes_are_padded_to_four_digits_and_grow_past_them(
    prefix: str, sequence: int, code: str
) -> None:
    assert format_code(prefix, sequence) == code
    assert validate_code(code) == code


@pytest.mark.parametrize("prefix", ["M", "me", "MEDIA", "M1", "", "M E"])
def test_r4_a_prefix_is_two_to_four_upper_case_letters(prefix: str) -> None:
    with pytest.raises(InvalidValue):
        validate_code_prefix(prefix)


@pytest.mark.parametrize("bad", ["ME0142", "me-0142", "ME-142", "ME-", "0142", "ME-01x2"])
def test_a_malformed_code_is_refused(bad: str) -> None:
    with pytest.raises(InvalidValue):
        validate_code(bad)


def test_the_sequence_starts_at_one() -> None:
    with pytest.raises(InvalidValue):
        format_code("ME", 0)


@pytest.mark.parametrize(
    ("name", "prefix"),
    [
        ("Sample Clinic", "SC"),
        ("Aarogya Clinic", "AC"),
        ("Apollo", "AP"),
        ("Dr. Rao's Children & Family Clinic", "DRSC"),
        ("one two three four five six", "OTTF"),
        ("A", "CL"),
        ("123 456", "CL"),
        ("आरोग्य क्लिनिक", "CL"),
    ],
)
def test_d2_the_prefix_is_derived_from_the_clinic_name(name: str, prefix: str) -> None:
    assert derive_code_prefix(name) == prefix
    validate_code_prefix(prefix)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("ME-0142", "ME-0142"),
        ("me-142", "ME-0142"),
        ("ME0142", "ME-0142"),
        (" abcd-7 ", "ABCD-0007"),
    ],
)
def test_a_search_text_in_code_form_becomes_the_canonical_code(text: str, code: str) -> None:
    assert parse_code_query(text) == code


@pytest.mark.parametrize("text", ["Asha", "0142", "M-1", "MEDIA-1", "ME 0142", "ME-", ""])
def test_other_texts_are_not_codes(text: str) -> None:
    assert parse_code_query(text) is None


def test_clinic_code_allocation_counts_forward_and_never_repeats() -> None:
    clinic = a_clinic(name="Sample Clinic", patient_code_prefix=None)

    codes = [clinic.allocate_patient_code(now=NOW) for _ in range(3)]

    assert codes == ["SC-0001", "SC-0002", "SC-0003"]
    assert clinic.next_patient_seq == 4


def test_a_clinic_may_be_given_a_prefix_at_creation() -> None:
    assert a_clinic(patient_code_prefix="ME").patient_code_prefix == "ME"
    with pytest.raises(InvalidValue):
        a_clinic(patient_code_prefix="x")


# --- Lookup classification (R5) --------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["9000000001", "090000 00001", "+91 90000-00001", "(+91) 9000000001", "919000000001"],
)
def test_r5_a_phone_is_read_as_the_normalised_number(text: str) -> None:
    parsed = classify_query(text)

    assert parsed is not None
    assert (parsed.kind, parsed.value) == (QueryKind.PHONE, "+919000000001")


def test_r5_a_phone_shaped_text_that_is_not_a_number_matches_nobody() -> None:
    parsed = classify_query("0000000")

    assert parsed is not None
    assert (parsed.kind, parsed.value) == (QueryKind.PHONE, None)


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("ME-0142", QueryKind.CODE, "ME-0142"),
        ("me-142", QueryKind.CODE, "ME-0142"),
        ("Asha", QueryKind.NAME, "asha"),
        ("  Asha  Rao ", QueryKind.NAME, "asha  rao"),
        ("0142", QueryKind.NAME, "0142"),  # too few digits for a phone; a code has letters
        ("123456", QueryKind.NAME, "123456"),
    ],
)
def test_r5_otherwise_a_code_and_then_the_start_of_a_name(
    text: str, kind: QueryKind, value: str
) -> None:
    parsed = classify_query(text)

    assert parsed is not None
    assert (parsed.kind, parsed.value) == (kind, value)


@pytest.mark.parametrize("text", ["", "   ", "\t"])
def test_r5_blank_text_looks_nothing_up(text: str) -> None:
    assert classify_query(text) is None


# --- Creating a patient (I1-I4, R3) ----------------------------------------------------------


def test_a_new_patient_starts_without_consent_or_opt_out() -> None:
    patient = _patient(full_name="  Asha Rao ")

    assert patient.full_name == "Asha Rao"
    assert (patient.whatsapp_consent, patient.sms_consent) == (False, False)
    assert patient.consent_recorded_at is None and patient.opted_out_at is None
    assert patient.language is Language.EN
    assert not patient.may_receive_whatsapp and not patient.may_receive_sms


def test_i1_a_patient_needs_a_name() -> None:
    with pytest.raises(InvalidValue) as refused:
        _patient(full_name="   ")
    assert refused.value.field == "full_name"


def test_i1_a_patient_needs_a_date_of_birth_or_an_age() -> None:
    with pytest.raises(InvalidValue):
        _patient(date_of_birth=None)
    with pytest.raises(InvalidValue):
        _patient(age_years=30)  # both given


def test_a_patient_can_be_registered_with_an_age_only() -> None:
    patient = _patient(date_of_birth=None, age_years=34)

    assert patient.date_of_birth is None
    assert patient.age_years(date(2026, 10, 2)) == 34
    assert patient.age_years(date(2028, 10, 2)) == 36


def test_r3_ac2_a_six_year_old_needs_a_guardian() -> None:
    with pytest.raises(GuardianRequired) as refused:
        _patient(date_of_birth=date(2020, 1, 1))
    assert refused.value.code == "PAT_GUARDIAN_REQUIRED"


def test_r3_a_minor_with_a_guardian_is_registered_and_the_phone_is_theirs() -> None:
    patient = _patient(date_of_birth=date(2020, 1, 1), guardian_name=" Meera Rao ", phone=PHONE)

    assert patient.guardian_name == "Meera Rao"
    assert patient.phone == PHONE
    assert patient.is_minor(TODAY)


@pytest.mark.parametrize(
    ("born", "needs_guardian"), [(date(2008, 10, 3), True), (date(2008, 10, 2), False)]
)
def test_r3_the_guardian_rule_changes_on_the_eighteenth_birthday(
    born: date, needs_guardian: bool
) -> None:
    if needs_guardian:
        with pytest.raises(GuardianRequired):
            _patient(date_of_birth=born)
    else:
        assert _patient(date_of_birth=born).guardian_name is None


def test_r3_a_recorded_age_of_17_is_a_minor_today_but_not_in_two_years() -> None:
    patient = _patient(date_of_birth=None, age_years=17, guardian_name="Meera Rao")

    assert patient.is_minor(TODAY)
    assert not patient.is_minor(date(2028, 10, 2))


def test_i3_a_code_must_have_the_patient_code_shape() -> None:
    with pytest.raises(InvalidValue):
        _patient(code="nonsense")


def test_repr_never_contains_the_name_or_phone() -> None:
    patient = _patient(full_name="Asha Rao")

    assert "Asha" not in repr(patient)
    assert "+91" not in repr(patient)
    assert patient.code in repr(patient)


# --- Editing (R7) ----------------------------------------------------------------------------


def test_r7_editing_returns_the_names_of_the_fields_that_changed() -> None:
    patient = _patient(full_name="Asha Rao", phone=PHONE)

    changed = patient.update_details(
        today=TODAY, now=LATER, full_name="Asha R. Rao", sex=Sex.FEMALE, language=Language.HI
    )

    assert changed == ["full_name", "sex", "language"]
    assert patient.updated_at == LATER
    assert patient.code.startswith("TS-")  # never changes


def test_r7_an_edit_that_changes_nothing_reports_nothing_and_leaves_the_timestamp() -> None:
    patient = _patient(full_name="Asha Rao")

    assert patient.update_details(today=TODAY, now=LATER, full_name="Asha Rao") == []
    assert patient.updated_at == NOW


def test_r7_the_age_columns_are_reported_as_one_field() -> None:
    patient = _patient(date_of_birth=date(1990, 1, 1))

    changed = patient.update_details(today=TODAY, now=LATER, age_years=40)

    assert changed == ["age"]
    assert patient.date_of_birth is None
    assert (patient.age_years_at_registration, patient.registered_on) == (40, TODAY)


def test_r3_editing_a_birth_date_into_childhood_demands_a_guardian_and_changes_nothing() -> None:
    patient = _patient(full_name="Asha Rao")

    with pytest.raises(GuardianRequired):
        patient.update_details(today=TODAY, now=LATER, date_of_birth=date(2020, 1, 1))

    assert patient.date_of_birth == date(1990, 5, 17)
    assert patient.updated_at == NOW


def test_r3_a_guardian_cannot_be_removed_from_a_minor() -> None:
    patient = _patient(date_of_birth=date(2020, 1, 1), guardian_name="Meera Rao")

    with pytest.raises(GuardianRequired):
        patient.update_details(today=TODAY, now=LATER, guardian_name="  ")


def test_r3_a_minor_turning_18_may_lose_the_guardian() -> None:
    patient = _patient(date_of_birth=date(2008, 10, 3), guardian_name="Meera Rao")

    patient.update_details(today=date(2026, 10, 3), now=LATER, guardian_name="")

    assert patient.guardian_name is None


# --- Consent and opt-out (R6, AC5) -----------------------------------------------------------


def test_r6_recording_consent_says_who_and_when() -> None:
    patient = _patient()
    staff = uuid4()

    patient.record_consent(whatsapp=True, sms=False, by=staff, now=LATER)

    assert patient.may_receive_whatsapp and not patient.may_receive_sms
    assert (patient.consent_recorded_at, patient.consent_recorded_by) == (LATER, staff)


def test_r6_ac5_an_opt_out_overrides_consent_until_an_explicit_opt_in() -> None:
    patient = _patient()
    staff = uuid4()
    patient.record_consent(whatsapp=True, sms=True, by=staff, now=NOW)

    assert patient.opt_out(by=staff, now=LATER) is True
    assert not patient.may_receive_whatsapp and not patient.may_receive_sms

    # Editing the flags while opted out stores them but changes nothing in effect.
    patient.record_consent(whatsapp=True, sms=True, by=staff, now=LATER)
    assert not patient.may_receive_whatsapp

    patient.opt_in(whatsapp=True, sms=False, by=staff, now=LATER)
    assert patient.may_receive_whatsapp and not patient.may_receive_sms
    assert patient.opted_out_at is None


def test_r6_opting_out_twice_keeps_the_first_moment() -> None:
    patient = _patient()
    staff = uuid4()
    patient.opt_out(by=staff, now=NOW)

    assert patient.opt_out(by=staff, now=LATER) is False
    assert patient.opted_out_at == NOW


def test_r6_opting_in_is_only_possible_after_an_opt_out() -> None:
    with pytest.raises(InvalidTransition):
        _patient().opt_in(whatsapp=True, sms=True, by=uuid4(), now=LATER)


def test_timestamps_must_be_utc() -> None:
    naive = datetime(2026, 10, 2, 4, 30)
    with pytest.raises(InvalidValue):
        _patient(now=naive)
    assert naive.replace(tzinfo=UTC) == NOW
