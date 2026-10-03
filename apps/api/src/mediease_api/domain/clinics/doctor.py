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

from mediease_api.domain.shared.errors import InvalidTransition
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
