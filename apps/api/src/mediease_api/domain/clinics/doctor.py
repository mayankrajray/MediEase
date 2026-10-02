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

    def deactivate(self, *, now: datetime) -> None:
        """Stop offering this doctor for new work; history keeps referring to them."""
        if not self.is_active:
            raise InvalidTransition("doctor", "INACTIVE", "deactivate")
        self.updated_at = require_utc(now, "now")
        self.is_active = False
