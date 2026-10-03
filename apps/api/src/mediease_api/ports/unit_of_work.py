"""Unit of work port: one transaction per command (apps/api/CLAUDE.md "Patterns").

Usage in a use case::

    with self._uow as uow:
        clinic = uow.clinics.get(clinic_id)
        staff = uow.tenant(clinic_id)
        staff.memberships.add(membership)
        uow.commit()

Every repository obtained from one unit of work shares its transaction, so the
change commits or rolls back as a whole. Leaving the ``with`` block without
``commit()`` — normally or through an exception — rolls back. M1-P4 adds the
audit writer here, which is how an audit entry is written in the same
transaction as the change (spec R11).
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from mediease_api.ports.audit import AuditWriter
from mediease_api.ports.repositories import (
    ChecklistRepository,
    ClinicAccessRepository,
    ClinicRepository,
    DoctorRepository,
    MembershipRepository,
    RefreshTokenRepository,
    StaffInviteRepository,
    UserRepository,
)


class TenantRepositories(Protocol):
    """Repositories bound to one clinic (ADR-0003)."""

    @property
    def clinic_id(self) -> UUID: ...
    @property
    def doctors(self) -> DoctorRepository: ...
    @property
    def memberships(self) -> MembershipRepository: ...
    @property
    def checklist(self) -> ChecklistRepository: ...


class UnitOfWork(Protocol):
    @property
    def clinics(self) -> ClinicRepository: ...
    @property
    def users(self) -> UserRepository: ...
    @property
    def refresh_tokens(self) -> RefreshTokenRepository: ...
    @property
    def clinic_access(self) -> ClinicAccessRepository: ...
    @property
    def staff_invites(self) -> StaffInviteRepository: ...
    @property
    def audit(self) -> AuditWriter:
        """Appends audit events in this transaction, so a change is never unaudited (R11)."""
        ...

    def tenant(self, clinic_id: UUID) -> TenantRepositories:
        """Repositories scoped to ``clinic_id``; the only way to reach tenant rows."""
        ...

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
