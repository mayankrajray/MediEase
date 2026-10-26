"""Doctor — a prescriber at one clinic (FR-ORG-02).

A doctor may be linked to a ``User`` who signs in, or not (a visiting doctor
whose prescriptions the front desk prepares). Invariant **I3**: qualification,
registration number and council are always present, because they are printed
on every prescription.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mediease_api.domain.clinics.verification import (
    LANGUAGES,
    MAX_FEE_PAISE,
    VerificationSource,
)
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from mediease_api.domain.shared.text import optional_text, required_text
from mediease_api.domain.shared.time import require_utc


@dataclass(slots=True)
class Doctor:
    """A doctor profile. Build new ones with ``Doctor.create``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    user_id: UUID | None
    display_name: str
    qualification: str
    registration_number: str
    registration_council: str
    specialty: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # M6c-P3 (FR-ONB-06, 09): verified by a MediEase reviewer; cleared when the registration
    # changes (R47).
    verified_at: datetime | None = None
    verified_by: UUID | None = None
    verification_source: VerificationSource | None = None
    # M6c-P4 (FR-ONB-09): shown in the directory only when verified and visible.
    visible: bool = False
    # M6c-P5 (FR-DIS-03): what a public profile may show.
    languages: tuple[str, ...] = ()
    fee_paise: int | None = None

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    @property
    def is_public(self) -> bool:
        """M6c-P5 (R54, R59): on the public page, its availability and requests, and in the
        directory: active, verified by MediEase and shown by the owner."""
        return self.is_active and self.is_verified and self.visible

    def verify(self, *, by: UUID, source: VerificationSource, now: datetime) -> bool:
        """Record MediEase's check of this registration (R43, R45); False if already verified."""
        if self.is_verified:
            return False
        now = require_utc(now, "now")
        self.verified_at = now
        self.verified_by = by
        self.verification_source = source
        self.updated_at = now
        return True

    def set_visible(self, visible: bool, *, now: datetime) -> None:
        self.visible = visible
        self.updated_at = require_utc(now, "now")

    def set_profile(
        self, *, languages: tuple[str, ...] | None, fee_paise: int | None, now: datetime
    ) -> None:
        """P5 (FR-DIS-03): the profile's languages (from the published list) and an optional
        consultation fee in paise (0 to 10 000 rupees)."""
        if languages is not None:
            cleaned = tuple(dict.fromkeys(languages))
            for index, language in enumerate(cleaned):
                if language not in LANGUAGES:
                    raise InvalidValue(f"languages.{index}", "is not on the list")
            self.languages = cleaned
        if fee_paise is not None and not 0 <= fee_paise <= MAX_FEE_PAISE:
            raise InvalidValue("fee_paise", "must be between 0 and 1000000")
        self.fee_paise = fee_paise
        self.updated_at = require_utc(now, "now")

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        display_name: str,
        qualification: str,
        registration_number: str,
        registration_council: str,
        now: datetime,
        user_id: UUID | None = None,
        specialty: str | None = None,
    ) -> Doctor:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            user_id=user_id,
            display_name=required_text(display_name, "display_name", max_length=200),
            qualification=required_text(qualification, "qualification", max_length=200),
            registration_number=required_text(
                registration_number, "registration_number", max_length=50
            ),
            registration_council=required_text(
                registration_council, "registration_council", max_length=200
            ),
            specialty=optional_text(specialty, "specialty", max_length=100),
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    def update_details(
        self,
        *,
        now: datetime,
        display_name: str | None = None,
        qualification: str | None = None,
        registration_number: str | None = None,
        registration_council: str | None = None,
        specialty: str | None = None,
        user_id: UUID | None = None,
    ) -> None:
        """Correct a doctor's details (FR-ORG-02, M1-P5).

        Only the fields given are touched. I3 still holds: the required fields
        can be corrected but never emptied. Linking a staff account
        (``user_id``) is allowed here; the application checks that the user is
        an active member of this clinic.
        """
        required = {
            "display_name": (display_name, 200),
            "qualification": (qualification, 200),
            "registration_number": (registration_number, 50),
            "registration_council": (registration_council, 200),
        }
        validated = {
            name: required_text(value, name, max_length=limit)
            for name, (value, limit) in required.items()
            if value is not None
        }
        cleaned_specialty = optional_text(specialty, "specialty", max_length=100)
        self.updated_at = require_utc(now, "now")
        # R47 (M6c-P3): a changed registration must be checked again.
        changed = any(
            name in validated and validated[name] != getattr(self, name)
            for name in ("registration_number", "registration_council")
        )
        if changed:
            self.verified_at = None
            self.verified_by = None
            self.verification_source = None
        for name, value in validated.items():
            setattr(self, name, value)
        if cleaned_specialty is not None:
            self.specialty = cleaned_specialty
        if user_id is not None:
            self.user_id = user_id

    def deactivate(self, *, now: datetime) -> None:
        """Stop offering this doctor for new work; history keeps referring to them."""
        if not self.is_active:
            raise InvalidTransition("doctor", "INACTIVE", "deactivate")
        self.updated_at = require_utc(now, "now")
        self.is_active = False
