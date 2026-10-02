"""ClinicMembership — a user's single role at one clinic (FR-ORG-03).

Lifecycle (spec §3): ``INVITED → ACTIVE → DEACTIVATED``; an invited member can
also be deactivated before accepting. Invariant **I2** (one membership per user
per clinic) is enforced by a unique constraint, because only the database sees
every membership at once.

Rule **R9**: the last active owner can be neither demoted nor deactivated. The
caller passes the clinic's current count of active owners (this one included);
the domain decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.errors import DomainError, InvalidTransition
from mediease_api.domain.shared.time import require_utc


class Role(StrEnum):
    OWNER = "OWNER"
    DOCTOR = "DOCTOR"
    FRONT_DESK = "FRONT_DESK"


class MembershipStatus(StrEnum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"


class LastOwnerError(DomainError):
    """R9: removing this owner would leave the clinic without one."""

    code = "CLN_LAST_OWNER"

    def __init__(self) -> None:
        super().__init__("A clinic needs at least one owner.")


@dataclass(slots=True)
class ClinicMembership:
    """Build new memberships with ``invite``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    user_id: UUID
    role: Role
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def invite(
        cls, *, id: UUID, clinic_id: UUID, user_id: UUID, role: Role, now: datetime
    ) -> ClinicMembership:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            user_id=user_id,
            role=role,
            status=MembershipStatus.INVITED,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_active_owner(self) -> bool:
        return self.role is Role.OWNER and self.status is MembershipStatus.ACTIVE

    def activate(self, *, now: datetime) -> None:
        """``INVITED`` → ``ACTIVE`` (the invitee has set up their account)."""
        if self.status is not MembershipStatus.INVITED:
            raise InvalidTransition("membership", self.status, "activate")
        self._touch(now)
        self.status = MembershipStatus.ACTIVE

    def change_role(self, role: Role, *, active_owner_count: int, now: datetime) -> None:
        """Give the member a different role (FR-ORG-04); refuses to demote the last owner."""
        if self.status is MembershipStatus.DEACTIVATED:
            raise InvalidTransition("membership", self.status, "change the role of")
        if role is self.role:
            return
        self._guard_last_owner(active_owner_count)
        self._touch(now)
        self.role = role

    def deactivate(self, *, active_owner_count: int, now: datetime) -> None:
        """Takes effect on the member's next request (FR-ORG-04, R7)."""
        if self.status is MembershipStatus.DEACTIVATED:
            raise InvalidTransition("membership", self.status, "deactivate")
        self._guard_last_owner(active_owner_count)
        self._touch(now)
        self.status = MembershipStatus.DEACTIVATED

    def _guard_last_owner(self, active_owner_count: int) -> None:
        if self.is_active_owner and active_owner_count <= 1:
            raise LastOwnerError()

    def _touch(self, now: datetime) -> None:
        # Validated before any field changes, so a bad timestamp leaves the entity untouched.
        self.updated_at = require_utc(now, "now")
