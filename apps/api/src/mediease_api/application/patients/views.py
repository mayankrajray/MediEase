"""What the patient use cases return: plain data, with the age worked out for the clinic's today.

Personal data lives here only on its way to the signed-in staff member's response.
``repr`` of a view would show a name and a phone, so the dataclasses hide it: a view
that ends up in a log line or a traceback prints its code, not the person.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

from mediease_api.domain.patients.patient import Language, Patient, Sex


@dataclass(frozen=True, slots=True, repr=False)
class PatientView:
    id: UUID
    code: str
    full_name: str = field(repr=False)
    phone_e164: str = field(repr=False)
    sex: Sex
    date_of_birth: date | None
    age_years: int
    age_is_estimated: bool
    is_minor: bool
    guardian_name: str | None = field(repr=False)
    language: Language
    whatsapp_consent: bool
    sms_consent: bool
    opted_out: bool
    opted_out_at: datetime | None
    whatsapp_allowed: bool
    sms_allowed: bool
    consent_recorded_at: datetime | None
    consent_recorded_by: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, patient: Patient, today: date) -> PatientView:
        return cls(
            id=patient.id,
            code=patient.code,
            full_name=patient.full_name,
            phone_e164=patient.phone.e164,
            sex=patient.sex,
            date_of_birth=patient.date_of_birth,
            age_years=patient.age_years(today),
            age_is_estimated=patient.date_of_birth is None,
            is_minor=patient.is_minor(today),
            guardian_name=patient.guardian_name,
            language=patient.language,
            whatsapp_consent=patient.whatsapp_consent,
            sms_consent=patient.sms_consent,
            opted_out=patient.is_opted_out,
            opted_out_at=patient.opted_out_at,
            whatsapp_allowed=patient.may_receive_whatsapp,
            sms_allowed=patient.may_receive_sms,
            consent_recorded_at=patient.consent_recorded_at,
            consent_recorded_by=patient.consent_recorded_by,
            created_at=patient.created_at,
            updated_at=patient.updated_at,
        )

    def __repr__(self) -> str:
        return f"PatientView(code={self.code!r})"


@dataclass(frozen=True, slots=True, repr=False)
class CandidateView:
    """A patient already on the number being registered (spec R2): enough to recognise them."""

    id: UUID
    code: str
    full_name: str = field(repr=False)
    age_years: int

    @classmethod
    def of(cls, patient: Patient, today: date) -> CandidateView:
        return cls(
            id=patient.id,
            code=patient.code,
            full_name=patient.full_name,
            age_years=patient.age_years(today),
        )

    def __repr__(self) -> str:
        return f"CandidateView(code={self.code!r})"
