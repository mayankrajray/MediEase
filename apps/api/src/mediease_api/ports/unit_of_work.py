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

from mediease_api.ports.audit import AuditReader, AuditWriter
from mediease_api.ports.booking import BookingRequestLookup, BookingRequestRepository
from mediease_api.ports.dashboard import DashboardReads
from mediease_api.ports.jobs import JobQueue, RetentionRepository
from mediease_api.ports.messaging import (
    MessageCostReport,
    MessageLookup,
    MessageRepository,
    OptOutLookup,
    WebhookEventRepository,
)
from mediease_api.ports.notifications import NotificationRepository, PreferenceRepository
from mediease_api.ports.portal import (
    DoseLifecycle,
    DoseRecordRepository,
    PortalInviteRepository,
    PortalLinkRepository,
    PortalLookup,
    ReminderPrefRepository,
)
from mediease_api.ports.reminders import NoShowSweep, ReminderRepository
from mediease_api.ports.repositories import (
    AppointmentHistoryRepository,
    AppointmentRepository,
    ChecklistRepository,
    ClinicAccessRepository,
    ClinicRepository,
    DoctorRepository,
    EmailTokenRepository,
    ExternalIdentityRepository,
    FavouriteRepository,
    MembershipRepository,
    PatientAccountRepository,
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
    def portal_links(self) -> PortalLinkRepository:
        """Patient accounts linked to this clinic's records (M6b-P1)."""
        ...

    @property
    def portal_invites(self) -> PortalInviteRepository: ...
    @property
    def reminder_prefs(self) -> ReminderPrefRepository:
        """A patient account's medicine-reminder preferences (M6b-P3)."""
        ...

    @property
    def booking_requests(self) -> BookingRequestRepository:
        """Online booking requests, and the soft hold they are (M6b-P4, ADR-0018)."""
        ...

    @property
    def dose_records(self) -> DoseRecordRepository:
        """A patient account's dose marks (M6b-P3b); reached only from patient routes."""
        ...

    @property
    def messages(self) -> MessageRepository: ...
    @property
    def reminders(self) -> ReminderRepository: ...
    @property
    def notifications(self) -> NotificationRepository:
        """In-app notifications (M6a-P7, ADR-0017)."""
        ...

    @property
    def notification_preferences(self) -> PreferenceRepository: ...
    @property
    def dashboard(self) -> DashboardReads:
        """Counts for the *Today* screen (M6-P1)."""
        ...

    @property
    def audit_log(self) -> AuditReader:
        """This clinic's audit log, read-only (M6a-P8, FR-AUD-03)."""
        ...


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
    def patient_accounts(self) -> PatientAccountRepository:
        """Patient portal accounts (M6a-P3); not tenant data."""
        ...

    @property
    def patient_refresh_tokens(self) -> RefreshTokenRepository:
        """Portal session families, in their own table (M6a-P3); ``user_id`` is the account."""
        ...

    @property
    def external_identities(self) -> ExternalIdentityRepository:
        """Google identities of staff users and patient accounts (M6a-P3)."""
        ...

    @property
    def email_tokens(self) -> EmailTokenRepository:
        """Email verification and password-reset tokens (M6a-P4)."""
        ...

    @property
    def staff_invites(self) -> StaffInviteRepository: ...
    @property
    def portal_lookup(self) -> PortalLookup:
        """An account's active links and an invite's clinic (M6b-P1, reviewed cross-clinic)."""
        ...

    @property
    def booking_request_lookup(self) -> BookingRequestLookup:
        """A patient account's own requests in every clinic (M6b-P4, reviewed exception)."""
        ...

    @property
    def dose_lifecycle(self) -> DoseLifecycle:
        """One account's dose records in every clinic, for export or deletion (M6b-P3b, R54)."""
        ...

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

    @property
    def no_show_sweep(self) -> NoShowSweep:
        """Clinics with overdue bookings (M5-P4, a reviewed cross-clinic read of IDs)."""
        ...

    @property
    def opt_out_lookup(self) -> OptOutLookup:
        """Who a STOP reply opts out (M5-P5, a reviewed cross-clinic read of IDs)."""
        ...

    @property
    def message_costs(self) -> MessageCostReport:
        """Monthly message counts and costs per clinic (M5-P5, a reviewed ops read)."""
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
