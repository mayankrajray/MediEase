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
from typing import Protocol
from uuid import UUID

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import ClinicMembership
from mediease_api.domain.identity.user import User
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.phone import PhoneNumber

# --- Platform repositories ---------------------------------------------------------------


class ClinicRepository(Protocol):
    def add(self, clinic: Clinic) -> None: ...
    def get(self, clinic_id: UUID) -> Clinic | None: ...
    def get_by_slug(self, slug: str) -> Clinic | None: ...
    def update(self, clinic: Clinic) -> None: ...


class UserRepository(Protocol):
    def add(self, user: User) -> None: ...
    def get(self, user_id: UUID) -> User | None: ...
    def get_by_email(self, email: EmailAddress) -> User | None: ...
    def get_by_phone(self, phone: PhoneNumber) -> User | None: ...
    def update(self, user: User) -> None: ...


# --- Tenant repositories (bound to one clinic) ---------------------------------------------


class DoctorRepository(Protocol):
    def add(self, doctor: Doctor) -> None: ...
    def get(self, doctor_id: UUID) -> Doctor | None: ...
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

    def update(self, membership: ClinicMembership) -> None: ...
