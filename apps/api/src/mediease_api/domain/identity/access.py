"""Read models of who may work where (ADR-0003 platform and tenant reads).

``ClinicAccess`` — one of a user's active memberships with its clinic, built
by a platform repository keyed by user (sign-in, ``/me``, clinic resolution
R6). ``StaffMember`` — one membership of a clinic with the member's name,
built by a tenant repository. Both carry IDs, names and enums only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.membership import MembershipStatus, Role
from mediease_api.domain.identity.permissions import Permission, permissions_for


@dataclass(frozen=True, slots=True)
class ClinicAccess:
    membership_id: UUID
    clinic_id: UUID
    clinic_name: str
    clinic_status: ClinicStatus
    role: Role
    # The user also has a doctor profile at this clinic (owner-who-is-a-doctor, spec §8).
    has_doctor_profile: bool = False
    # M6a-P6 (decision 2A): that profile's ID, for the web's workspaces and *My Patients*.
    doctor_id: UUID | None = None

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role, has_doctor_profile=self.has_doctor_profile)


@dataclass(frozen=True, slots=True)
class StaffMember:
    membership_id: UUID
    user_id: UUID
    full_name: str
    role: Role
    status: MembershipStatus
    # M6a-P5 (decision 2A): what the owner's Team page needs to tell two people apart. The contact
    # details are the member's sign-in identifiers; the owner already knows them.
    email: str | None = None
    phone_e164: str | None = None
    # When a pending invitation's link stops working; None while an emailed one is being sent.
    invite_expires_at: datetime | None = None
    has_doctor_profile: bool = False
