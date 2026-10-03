"""ClinicMembership — a user's single role at one clinic (FR-ORG-03, FR-ORG-04).

Lifecycle (spec §3): ``INVITED → ACTIVE → DEACTIVATED``; an invited member can
also be deactivated before accepting. There is no way back from
``DEACTIVATED``: a clinic that deactivated someone by mistake invites them
again, and the audit trail shows both steps.

Invariant **I2** (one membership per user per clinic) is enforced by a unique
constraint, because only the database sees every membership at once.

Rule **R9**: the last active owner can be neither demoted nor deactivated. The
caller passes the clinic's current count of active owners (this one included);
the domain decides.

**The invitation is this row (M1-P5).** An ``INVITED`` membership carries the
digest of a single-use secret and its expiry; presenting the secret accepts
the invitation and activates the membership. Nothing else models an invite, so
there is no second state to keep in step, and re-inviting is a new digest here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.errors import DomainError, InvalidTransition
from mediease_api.domain.shared.time import require_utc

# How long an invitation stays usable. A constant, not a setting: nothing
# operational tunes it, and the owner can always invite again.
INVITE_TTL = timedelta(days=7)


class Role(StrEnum):
    OWNER = "OWNER"
    DOCTOR = "DOCTOR"
    FRONT_DESK = "FRONT_DESK"


class MembershipStatus(StrEnum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"


class InviteState(StrEnum):
    """What a presented invitation secret is worth now."""

    NONE = "NONE"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"
    ACCEPTED = "ACCEPTED"


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
    # The pending invitation (M1-P5). Only the digest is stored, never the secret.
    invite_token_hash: str | None = None
    invite_expires_at: datetime | None = None
    invite_accepted_at: datetime | None = None

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

    # --- invitations -----------------------------------------------------------------------

    def issue_invite(self, token_hash: str, *, now: datetime, ttl: timedelta = INVITE_TTL) -> None:
        """Attach a fresh secret, replacing any earlier one (which stops working)."""
        if self.status is not MembershipStatus.INVITED:
            raise InvalidTransition("membership", self.status, "invite")
        self._touch(now)
        self.invite_token_hash = token_hash
        self.invite_expires_at = self.updated_at + ttl
        self.invite_accepted_at = None

    def invite_state(self, now: datetime) -> InviteState:
        now = require_utc(now, "now")
        if self.invite_token_hash is None:
            return InviteState.NONE
        if self.invite_accepted_at is not None:
            return InviteState.ACCEPTED
        if self.invite_expires_at is not None and now >= self.invite_expires_at:
            return InviteState.EXPIRED
        return InviteState.PENDING

    def accept_invite(self, *, now: datetime) -> None:
        """Activate the membership by presenting a pending invitation.

        The digest is kept: it tells a replay apart from an unknown secret, so
        the invitee is told "already used" instead of "not found".
        """
        if self.invite_state(now) is not InviteState.PENDING:
            raise InvalidTransition("invitation", self.invite_state(now), "accept")
        self.activate(now=now)
        self.invite_accepted_at = self.updated_at

    # --- role and status -------------------------------------------------------------------

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
        # A pending invitation dies with the membership.
        self.invite_token_hash = None
        self.invite_expires_at = None

    def _guard_last_owner(self, active_owner_count: int) -> None:
        if self.is_active_owner and active_owner_count <= 1:
            raise LastOwnerError()

    def _touch(self, now: datetime) -> None:
        # Validated before any field changes, so a bad timestamp leaves the entity untouched.
        self.updated_at = require_utc(now, "now")
