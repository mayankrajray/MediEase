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
from mediease_api.ports.jobs import JobQueue, RetentionRepository
from mediease_api.ports.messaging import (
    MessageLookup,
    MessageRepository,
    WebhookEventRepository,
)
from mediease_api.ports.repositories import (
    AppointmentHistoryRepository,
    AppointmentRepository,
    ChecklistRepository,
    ClinicAccessRepository,
    ClinicRepository,
    DoctorRepository,
    FavouriteRepository,
    MembershipRepository,
    PatientLinkRepository,
    PatientRepository,
    PrescriptionRepository,
    RateLimitRepository,
    RefreshTokenRepository,
    ScheduleExceptionRepository,
    ScheduleRepository,
    SessionRepository,
    StaffInviteRepository,
    TemplateRepository,
    UserRepository,
    VisitAddendumRepository,
    VisitRepository,
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
    @property
    def patients(self) -> PatientRepository: ...
    @property
    def schedules(self) -> ScheduleRepository: ...
    @property
    def schedule_exceptions(self) -> ScheduleExceptionRepository: ...
    @property
    def sessions(self) -> SessionRepository: ...
    @property
    def appointments(self) -> AppointmentRepository: ...
    @property
    def appointment_history(self) -> AppointmentHistoryRepository: ...
    @property
    def visits(self) -> VisitRepository: ...
    @property
    def visit_addenda(self) -> VisitAddendumRepository: ...
    @property
    def prescriptions(self) -> PrescriptionRepository: ...
    @property
    def rx_favourites(self) -> FavouriteRepository: ...
    @property
    def rx_templates(self) -> TemplateRepository: ...
    @property
    def patient_links(self) -> PatientLinkRepository: ...
    @property
    def messages(self) -> MessageRepository: ...


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
    def rate_limits(self) -> RateLimitRepository:
        """Public-route request counts (M4-P5); not tenant data."""
        ...

    @property
    def audit(self) -> AuditWriter:
        """Appends audit events in this transaction, so a change is never unaudited (R11)."""
        ...

    @property
    def jobs(self) -> JobQueue:
        """Enqueues background work in this transaction (M5-P1, the outbox)."""
        ...

    @property
    def retention(self) -> RetentionRepository:
        """Expired-row deletion for the worker's purge job (M5-P1)."""
        ...

    @property
    def message_lookup(self) -> MessageLookup:
        """Which clinic a provider status belongs to (M5-P3, a reviewed cross-clinic read)."""
        ...

    @property
    def webhook_events(self) -> WebhookEventRepository:
        """Stored provider webhooks (M5-P3); not tenant data."""
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
