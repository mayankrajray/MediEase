"""Patient — a person a clinic treats (FR-PAT-01..06).

The **contact of record** is ``phone``. For a patient under 18 it is the
guardian's phone, ``guardian_name`` names the guardian, and consent is recorded
against the guardian (spec patients §3, decision D1); there is no separate
guardian phone.

Invariants (spec §3):

- **I1** a name, a valid phone, a sex, and either a date of birth or a recorded age;
- **I2** a patient under 18 has a guardian name;
- **I3** the code is unique within the clinic and never edited;
- **I4** a date of birth is not in the future, a recorded age is 0-120.

Names and phone numbers are personal data: ``repr`` shows only the code, and no
error raised here contains a value the caller supplied (CLAUDE.md "Never log PII").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from mediease_api.domain.patients.age import Age
from mediease_api.domain.patients.code import validate_code
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import optional_text, required_text
from mediease_api.domain.shared.time import require_utc


class Sex(StrEnum):
    FEMALE = "FEMALE"
    MALE = "MALE"
    OTHER = "OTHER"
    UNDISCLOSED = "UNDISCLOSED"


class Language(StrEnum):
    """Language of messages to the patient (English and Hindi at MVP, NFR-11)."""

    EN = "en"
    HI = "hi"


class PhoneInvalid(InvalidValue):
    """R1: the text is not a phone number. The value is never echoed (it is personal data)."""

    code = "PAT_PHONE_INVALID"

    def __init__(self, field: str = "phone") -> None:
        super().__init__(field, "is not a valid phone number")


def parse_phone(raw: str, field: str = "phone") -> PhoneNumber:
    """Normalise a typed phone number to E.164 (R1), or raise ``PhoneInvalid``."""
    try:
        return PhoneNumber.parse(raw, field=field)
    except InvalidValue:
        raise PhoneInvalid(field) from None


class PatientOptedOut(DomainError):
    """R6 / M2-P3 decision A: consent cannot be edited while the patient is opted out."""

    code = "PAT_OPTED_OUT"

    def __init__(self) -> None:
        super().__init__(
            "This patient asked not to be messaged. Opt them back in to record new consent."
        )


class PatientNotOptedOut(DomainError):
    """Opt-in is the way back from an opt-out, so it needs one."""

    code = "PAT_NOT_OPTED_OUT"

    def __init__(self) -> None:
        super().__init__("This patient has not opted out. Record consent instead.")


class ConsentGivenBy(StrEnum):
    """Whose answer a consent is: the guardian's for a minor (FR-PAT-06, decision D1)."""

    PATIENT = "patient"
    GUARDIAN = "guardian"


class GuardianRequired(DomainError):
    """I2 / R3: a patient under 18 needs a parent's or guardian's name."""

    code = "PAT_GUARDIAN_REQUIRED"

    def __init__(self) -> None:
        super().__init__("A parent or guardian's name is required for a patient under 18.")


@dataclass(slots=True, repr=False)
class Patient:
    """A patient. Build new ones with ``Patient.create``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    code: str
    full_name: str
    phone: PhoneNumber
    sex: Sex
    date_of_birth: date | None
    age_years_at_registration: int | None
    registered_on: date
    guardian_name: str | None
    language: Language
    whatsapp_consent: bool
    sms_consent: bool
    consent_recorded_at: datetime | None
    consent_recorded_by: UUID | None
    opted_out_at: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    NAME_MAX: ClassVar[int] = 200
    GUARDIAN_MAX: ClassVar[int] = 200

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        code: str,
        full_name: str,
        phone: PhoneNumber,
        sex: Sex,
        registered_on: date,
        created_by: UUID,
        now: datetime,
        date_of_birth: date | None = None,
        age_years: int | None = None,
        guardian_name: str | None = None,
        language: Language = Language.EN,
    ) -> Patient:
        """Register a patient. ``registered_on`` is the clinic-local date (from the clinic's zone).

        Consent starts false and nobody has opted out (R6).
        """
        now = require_utc(now, "now")
        age = _age_from(date_of_birth, age_years, registered_on)
        guardian = optional_text(guardian_name, "guardian_name", max_length=cls.GUARDIAN_MAX)
        if age.is_minor(registered_on) and guardian is None:
            raise GuardianRequired()
        return cls(
            id=id,
            clinic_id=clinic_id,
            code=validate_code(code),
            full_name=required_text(full_name, "full_name", max_length=cls.NAME_MAX),
            phone=phone,
            sex=sex,
            date_of_birth=age.date_of_birth,
            age_years_at_registration=age.recorded_years,
            registered_on=registered_on,
            guardian_name=guardian,
            language=language,
            whatsapp_consent=False,
            sms_consent=False,
            consent_recorded_at=None,
            consent_recorded_by=None,
            opted_out_at=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    # --- age ---------------------------------------------------------------------------------

    @property
    def age(self) -> Age:
        return Age(self.date_of_birth, self.age_years_at_registration, self.registered_on)

    def age_years(self, on: date) -> int:
        """Whole years of age on ``on`` (a clinic-local date)."""
        return self.age.years(on)

    def is_minor(self, on: date) -> bool:
        return self.age.is_minor(on)

    # --- demographics ------------------------------------------------------------------------

    def update_details(
        self,
        *,
        today: date,
        now: datetime,
        full_name: str | None = None,
        phone: PhoneNumber | None = None,
        sex: Sex | None = None,
        date_of_birth: date | None = None,
        age_years: int | None = None,
        guardian_name: str | None = None,
        language: Language | None = None,
    ) -> list[str]:
        """Correct demographics (R7); returns the names of the fields that actually changed.

        Only the fields given are touched. The code never changes (I3). Giving a date of
        birth or an age replaces the whole age fact (an age is recorded on ``today``), and
        a blank ``guardian_name`` clears it. I2 is re-checked for ``today`` before anything
        is applied, so a refused edit changes nothing. The caller audits the returned
        field *names*, never values.
        """
        now = require_utc(now, "now")
        new_name = (
            required_text(full_name, "full_name", max_length=self.NAME_MAX)
            if full_name is not None
            else self.full_name
        )
        if date_of_birth is not None or age_years is not None:
            age = _age_from(date_of_birth, age_years, today)
        else:
            age = self.age
        new_guardian = (
            optional_text(guardian_name, "guardian_name", max_length=self.GUARDIAN_MAX)
            if guardian_name is not None
            else self.guardian_name
        )
        if age.is_minor(today) and new_guardian is None:
            raise GuardianRequired()

        proposed: dict[str, object] = {
            "full_name": new_name,
            "phone": phone if phone is not None else self.phone,
            "sex": sex if sex is not None else self.sex,
            "date_of_birth": age.date_of_birth,
            "age_years_at_registration": age.recorded_years,
            "registered_on": age.recorded_on if age.recorded_on is not None else self.registered_on,
            "guardian_name": new_guardian,
            "language": language if language is not None else self.language,
        }
        changed = [name for name, value in proposed.items() if getattr(self, name) != value]
        if not changed:
            return []
        for name, value in proposed.items():
            setattr(self, name, value)
        self.updated_at = now
        return _report_names(changed)

    # --- consent and opt-out (R6, FR-PAT-05, FR-MSG-05) ---------------------------------------

    @property
    def is_opted_out(self) -> bool:
        return self.opted_out_at is not None

    @property
    def may_receive_whatsapp(self) -> bool:
        """Consent given *and* not opted out: an opt-out overrides consent (R6, AC5)."""
        return self.whatsapp_consent and not self.is_opted_out

    @property
    def may_receive_sms(self) -> bool:
        return self.sms_consent and not self.is_opted_out

    @property
    def consent_was_asked(self) -> bool:
        """False until someone records an answer: "not asked" is not "said no" (M2-P3)."""
        return self.consent_recorded_at is not None

    def consent_given_by(self, on: date) -> ConsentGivenBy:
        """Whose answer consent recorded on ``on`` is: the guardian's while a minor (FR-PAT-06)."""
        return ConsentGivenBy.GUARDIAN if self.is_minor(on) else ConsentGivenBy.PATIENT

    def record_consent(self, *, whatsapp: bool, sms: bool, by: UUID, now: datetime) -> None:
        """Record who agreed to which channel, and when (R6). For a minor it is the guardian's.

        Refused while the patient is opted out (decision A): a consent box that silently does
        nothing is worse than a clear message, and ``opt_in`` takes the new consent instead.
        """
        if self.is_opted_out:
            raise PatientOptedOut()
        self._set_consent(whatsapp=whatsapp, sms=sms, by=by, now=now)

    def opt_out(self, *, now: datetime) -> bool:
        """Stop all messages. Returns False (and changes nothing) if already opted out.

        Who asked is the audit row's actor; the consent record is left as it was.
        """
        if self.is_opted_out:
            return False
        self.updated_at = require_utc(now, "now")
        self.opted_out_at = self.updated_at
        return True

    def opt_in(self, *, whatsapp: bool, sms: bool, by: UUID, now: datetime) -> None:
        """The explicit way back after an opt-out (AC5): clears it and records the new consent."""
        if not self.is_opted_out:
            raise PatientNotOptedOut()
        self._set_consent(whatsapp=whatsapp, sms=sms, by=by, now=now)
        self.opted_out_at = None

    def _set_consent(self, *, whatsapp: bool, sms: bool, by: UUID, now: datetime) -> None:
        self.updated_at = require_utc(now, "now")
        self.whatsapp_consent = whatsapp
        self.sms_consent = sms
        self.consent_recorded_at = self.updated_at
        self.consent_recorded_by = by

    def __repr__(self) -> str:
        # Code and clinic only: never the name or phone (CLAUDE.md "Never log PII").
        return f"Patient(code={self.code!r}, clinic_id={self.clinic_id})"


def _age_from(date_of_birth: date | None, age_years: int | None, on: date) -> Age:
    if date_of_birth is not None and age_years is not None:
        raise InvalidValue("age", "give a date of birth or an age, not both")
    if date_of_birth is not None:
        return Age.from_birth_date(date_of_birth, today=on)
    if age_years is not None:
        return Age.from_recorded_age(age_years, recorded_on=on)
    raise InvalidValue("age", "a date of birth or an age is required")


_REPORTED = {
    "date_of_birth": "age",
    "age_years_at_registration": "age",
    "registered_on": "age",
}


def _report_names(changed: list[str]) -> list[str]:
    """The three age columns are one fact to the audit trail and the API."""
    return list(dict.fromkeys(_REPORTED.get(name, name) for name in changed))
