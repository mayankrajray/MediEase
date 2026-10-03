"""Repository ports: how the application loads and saves domain entities.

Two kinds (ADR-0003, ARCHITECTURE.md §6):

- **Platform repositories** (``ClinicRepository``, ``UserRepository``) hold rows
  that are not owned by one clinic: the clinics themselves, and users, who may
  work at several clinics. They never return clinical content.
- **Tenant repositories** (``DoctorRepository``, ``MembershipRepository``) are
  bound to one clinic when the unit of work creates them. No method takes a
  clinic ID, so a query for another clinic cannot be expressed: another
  clinic's row is simply not found (spec R8 → ``REQ_NOT_FOUND``).

``add`` stores a new entity; ``update`` saves a changed one and raises
``NotFound`` if it is not (or no longer) visible to the repository. Changes are
durable only after ``UnitOfWork.commit``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.onboarding import OnboardingChecklist
from mediease_api.domain.identity.access import ClinicAccess, StaffMember
from mediease_api.domain.identity.membership import ClinicMembership
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.identity.user import User
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.phone import PhoneNumber

# --- Platform repositories ---------------------------------------------------------------


class ClinicRepository(Protocol):
    def add(self, clinic: Clinic) -> None: ...
    def get(self, clinic_id: UUID) -> Clinic | None: ...
    def get_by_slug(self, slug: str) -> Clinic | None: ...
    def update(self, clinic: Clinic) -> None: ...
    def list_onboarding(self) -> Sequence[tuple[Clinic, OnboardingChecklist | None]]:
        """Every clinic with its checklist, newest first — the ops console list (FR-OPS-01).

        A deliberate cross-clinic read for platform staff (ADR-0003): clinics
        are not tenant-owned, and no clinical content is involved.
        """
        ...


class UserRepository(Protocol):
    def add(self, user: User) -> None: ...
    def get(self, user_id: UUID, *, for_update: bool = False) -> User | None: ...
    def get_by_email(self, email: EmailAddress, *, for_update: bool = False) -> User | None:
        """``for_update`` locks the row until the unit of work ends (sign-in counting)."""
        ...

    def get_by_phone(self, phone: PhoneNumber, *, for_update: bool = False) -> User | None: ...
    def update(self, user: User) -> None: ...


class RefreshTokenRepository(Protocol):
    """Refresh tokens are owned by users, not clinics (platform repository)."""

    def add(self, token: RefreshToken) -> None: ...
    def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> RefreshToken | None: ...
    def update(self, token: RefreshToken) -> None: ...
    def revoke_family(self, family_id: UUID, *, now: datetime) -> int:
        """Revoke every not-yet-revoked token in the family; returns how many."""
        ...

    def is_family_live(self, family_id: UUID, *, now: datetime) -> bool:
        """True while the session has an unrevoked, unexpired token (checked per request)."""
        ...


class ClinicAccessRepository(Protocol):
    """Which clinics a user may work in — a deliberate cross-clinic read (ADR-0003).

    Platform repository keyed by user: it returns IDs, clinic names and roles
    only, never tenant content.
    """

    def list_active_for_user(self, user_id: UUID) -> Sequence[ClinicAccess]:
        """The user's ``ACTIVE`` memberships with their clinic, ordered by clinic name."""
        ...


class StaffInviteRepository(Protocol):
    """Finds the membership a pending invitation belongs to (M1-P5).

    Keyed by the digest of a 256-bit secret, like ``RefreshTokenRepository``:
    the invitee has no session and no clinic context yet, so this read cannot
    be clinic-scoped (ADR-0003 "platform repositories"). Writes go through the
    tenant-scoped ``MembershipRepository``.
    """

    def get_by_invite_digest(self, token_hash: str) -> ClinicMembership | None: ...


# --- Tenant repositories (bound to one clinic) ---------------------------------------------


class DoctorRepository(Protocol):
    def add(self, doctor: Doctor) -> None: ...
    def get(self, doctor_id: UUID) -> Doctor | None: ...
    def get_for_user(self, user_id: UUID) -> Doctor | None:
        """This clinic's doctor profile for ``user_id``, if the account is linked to one.

        At most one exists: a partial unique index enforces one profile per user
        per clinic (spec §8 "owner who is also a doctor").
        """
        ...

    def list(self) -> Sequence[Doctor]:
        """All of this clinic's doctors, oldest first."""
        ...

    def update(self, doctor: Doctor) -> None: ...


class MembershipRepository(Protocol):
    def add(self, membership: ClinicMembership) -> None: ...
    def get(self, membership_id: UUID) -> ClinicMembership | None: ...
    def get_for_user(self, user_id: UUID) -> ClinicMembership | None:
        """This clinic's membership for ``user_id`` (at most one, invariant I2)."""
        ...

    def list(self) -> Sequence[ClinicMembership]:
        """All of this clinic's memberships, oldest first."""
        ...

    def count_active_owners(self) -> int:
        """Active ``OWNER`` memberships, for I1 and R9."""
        ...

    def list_staff(self) -> Sequence[StaffMember]:
        """Every membership of this clinic with the member's name, ordered by name."""
        ...

    def update(self, membership: ClinicMembership) -> None: ...


class ChecklistRepository(Protocol):
    """This clinic's onboarding checklist (FR-OPS-04, spec R12). One row per clinic."""

    def add(self, checklist: OnboardingChecklist) -> None: ...
    def get(self) -> OnboardingChecklist | None: ...
    def update(self, checklist: OnboardingChecklist) -> None: ...
