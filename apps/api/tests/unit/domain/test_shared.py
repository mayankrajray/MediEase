"""Value objects and shared rules: phone, email, text, time (AGENTS.md "Phones")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import optional_text, required_text
from mediease_api.domain.shared.time import require_utc

# --- PhoneNumber ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "9000000001",
        "90000 00001",
        "090000-00001",
        "919000000001",
        "+91 90000 00001",
        "+91-(900)-000-0001",
        "0091 9000000001",
    ],
)
def test_fr_auth_01_indian_input_forms_normalise_to_e164(raw: str) -> None:
    assert PhoneNumber.parse(raw).e164 == "+919000000001"


def test_landline_with_std_code_is_accepted() -> None:
    assert PhoneNumber.parse("011 2345 6789").e164 == "+911123456789"


def test_other_countries_are_accepted_with_a_plus() -> None:
    assert PhoneNumber.parse("+44 20 7946 0000").e164 == "+442079460000"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "12345",
        "0000000000",
        "900000000",  # 9 digits
        "+91 900000000",  # 9 national digits
        "+91 900000000012",  # 12 national digits
        "+0123456789",
        "+1234567890123456",  # 16 digits
        "90000abc01",
        "9000000001 ext 2",
    ],
)
def test_invalid_phone_numbers_are_rejected_without_echoing_them(raw: str) -> None:
    with pytest.raises(InvalidValue) as excinfo:
        PhoneNumber.parse(raw, field="clinic_phone")
    assert excinfo.value.field == "clinic_phone"
    assert excinfo.value.code == "REQ_VALIDATION_FAILED"
    if raw:
        assert raw not in str(excinfo.value)


def test_constructor_rejects_non_e164() -> None:
    with pytest.raises(InvalidValue):
        PhoneNumber("9000000001")


def test_phone_is_masked_in_repr_and_str() -> None:
    phone = PhoneNumber.parse("9000003210")
    assert phone.masked() == "+91******3210"
    assert "9000003210" not in repr(phone)
    assert "9000003210" not in str(phone)
    assert f"{phone}" == "PhoneNumber('+91******3210')"


def test_phones_compare_by_value() -> None:
    assert PhoneNumber.parse("9000000001") == PhoneNumber.parse("+91 90000 00001")


# --- EmailAddress --------------------------------------------------------------------


def test_email_is_trimmed_and_lower_cased() -> None:
    assert EmailAddress.parse("  Owner@Sample-Clinic.Example ").value == (
        "owner@sample-clinic.example"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "no-at-sign",
        "@example.test",
        "user@",
        "user@localhost",
        "user@exa mple.test",
        "a@b@example.test",
        "user@-bad.example",
        "user@example..test",
        f"{'x' * 65}@example.test",
        f"user@{'x' * 250}.test",
    ],
)
def test_invalid_emails_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidValue) as excinfo:
        EmailAddress.parse(raw, field="owner_email")
    assert excinfo.value.field == "owner_email"


def test_email_constructor_requires_normalised_value() -> None:
    with pytest.raises(InvalidValue):
        EmailAddress("Owner@example.test")


def test_email_is_masked_in_repr() -> None:
    email = EmailAddress.parse("owner@example.test")
    assert email.masked() == "o***@example.test"
    assert "owner@" not in repr(email)
    assert str(email) == "EmailAddress('o***@example.test')"


# --- text and time ---------------------------------------------------------------------


def test_required_text_trims_and_bounds() -> None:
    assert required_text("  Sample  ", "name", max_length=10) == "Sample"
    with pytest.raises(InvalidValue, match="must not be empty"):
        required_text("   ", "name", max_length=10)
    with pytest.raises(InvalidValue, match="at most 3"):
        required_text("abcd", "name", max_length=3)


def test_optional_text_turns_blank_into_none() -> None:
    assert optional_text(None, "city", max_length=5) is None
    assert optional_text("  ", "city", max_length=5) is None
    assert optional_text(" Pune ", "city", max_length=5) == "Pune"


def test_require_utc_accepts_utc_and_rejects_naive_or_offset() -> None:
    utc = datetime(2026, 10, 2, 4, 30, tzinfo=UTC)
    assert require_utc(utc, "now") == utc
    zero_offset = datetime(2026, 10, 2, 4, 30, tzinfo=timezone(timedelta(0)))
    assert require_utc(zero_offset, "now").tzinfo is UTC

    with pytest.raises(InvalidValue, match="timezone-aware"):
        require_utc(datetime(2026, 10, 2, 4, 30), "now")
    ist = timezone(timedelta(hours=5, minutes=30))
    with pytest.raises(InvalidValue, match="in UTC"):
        require_utc(datetime(2026, 10, 2, 10, 0, tzinfo=ist), "now")
