"""ClinicAccess — which clinic a user may work in, and as what (read model).

Built by a platform repository from a membership and its clinic, for sign-in
responses and (from M1-P3) for resolving the request's active clinic (R6).
Carries IDs, the clinic's display name and enums only — never clinical data.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.membership import Role


@dataclass(frozen=True, slots=True)
class ClinicAccess:
    membership_id: UUID
    clinic_id: UUID
    clinic_name: str
    clinic_status: ClinicStatus
    role: Role
