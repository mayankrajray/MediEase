"""SQLAlchemy unit of work — one session and one transaction per command.

``with uow:`` opens a session; every repository it hands out shares that
session. Leaving the block without ``commit()`` rolls back, including when an
exception escapes, and the session is always closed. A unit of work can be
entered again afterwards (a use case keeps one and enters it per ``execute``),
but not while it is already open, and it is not shared between threads: the
composition root creates one per request (M1-P2).
"""

from __future__ import annotations

from types import TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.db.audit import SqlAlchemyAuditReader, SqlAlchemyAuditWriter
from mediease_api.adapters.db.booking import (
    SqlAlchemyBookingRequestLookup,
    SqlAlchemyBookingRequestRepository,
)
from mediease_api.adapters.db.dashboard import SqlAlchemyDashboardReads
from mediease_api.adapters.db.jobs import SqlAlchemyJobQueue, SqlAlchemyRetentionRepository
from mediease_api.adapters.db.messages import (
    SqlAlchemyMessageCostReport,
    SqlAlchemyMessageLookup,
    SqlAlchemyMessageRepository,
    SqlAlchemyOptOutLookup,
    SqlAlchemyWebhookEventRepository,
)
from mediease_api.adapters.db.notifications import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyPreferenceRepository,
)
from mediease_api.adapters.db.portal import (
    SqlAlchemyEmailTokenRepository,
    SqlAlchemyExternalIdentityRepository,
    SqlAlchemyPatientAccountRepository,
    SqlAlchemyPatientRefreshTokenRepository,
)
from mediease_api.adapters.db.portal_links import (
    SqlAlchemyDoseLifecycle,
    SqlAlchemyDoseRecordRepository,
    SqlAlchemyPortalInviteRepository,
    SqlAlchemyPortalLinkRepository,
    SqlAlchemyPortalLookup,
    SqlAlchemyReminderPrefRepository,
)
from mediease_api.adapters.db.reminders import SqlAlchemyNoShowSweep, SqlAlchemyReminderRepository
from mediease_api.adapters.db.repositories import (
    SqlAlchemyAppointmentHistoryRepository,
    SqlAlchemyAppointmentRepository,
    SqlAlchemyChecklistRepository,
    SqlAlchemyClinicAccessRepository,
    SqlAlchemyClinicRepository,
    SqlAlchemyDoctorRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyPatientLinkRepository,
    SqlAlchemyPatientRepository,
    SqlAlchemyPrescriptionRepository,
    SqlAlchemyRateLimitRepository,
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyRxFavouriteRepository,
    SqlAlchemyRxTemplateRepository,
    SqlAlchemyScheduleExceptionRepository,
    SqlAlchemyScheduleRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyStaffInviteRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyVisitAddendumRepository,
    SqlAlchemyVisitRepository,
)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Sessions for units of work.

    ``expire_on_commit=False``: entities are mapped out of rows before commit,
    so nothing needs reloading after it; ``autoflush=False``: repositories
    flush explicitly at the call that changed something.
    """
    return sessionmaker(engine, expire_on_commit=False, autoflush=False)


class SqlAlchemyTenantRepositories:
    """The tenant repositories for one clinic, sharing the unit of work's session."""

    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._clinic_id = clinic_id
        self._doctors = SqlAlchemyDoctorRepository(session, clinic_id)
        self._memberships = SqlAlchemyMembershipRepository(session, clinic_id)
        self._checklist = SqlAlchemyChecklistRepository(session, clinic_id)
        self._patients = SqlAlchemyPatientRepository(session, clinic_id)
        self._schedules = SqlAlchemyScheduleRepository(session, clinic_id)
        self._schedule_exceptions = SqlAlchemyScheduleExceptionRepository(session, clinic_id)
        self._sessions = SqlAlchemySessionRepository(session, clinic_id)
        self._appointments = SqlAlchemyAppointmentRepository(session, clinic_id)
        self._appointment_history = SqlAlchemyAppointmentHistoryRepository(session, clinic_id)
        self._visits = SqlAlchemyVisitRepository(session, clinic_id)
        self._visit_addenda = SqlAlchemyVisitAddendumRepository(session, clinic_id)
        self._prescriptions = SqlAlchemyPrescriptionRepository(session, clinic_id)
        self._rx_favourites = SqlAlchemyRxFavouriteRepository(session, clinic_id)
        self._rx_templates = SqlAlchemyRxTemplateRepository(session, clinic_id)
        self._patient_links = SqlAlchemyPatientLinkRepository(session, clinic_id)
        self._portal_links = SqlAlchemyPortalLinkRepository(session, clinic_id)
        self._portal_invites = SqlAlchemyPortalInviteRepository(session, clinic_id)
        self._reminder_prefs = SqlAlchemyReminderPrefRepository(session, clinic_id)
        self._dose_records = SqlAlchemyDoseRecordRepository(session, clinic_id)
        self._booking_requests = SqlAlchemyBookingRequestRepository(session, clinic_id)
        self._messages = SqlAlchemyMessageRepository(session, clinic_id)
        self._reminders = SqlAlchemyReminderRepository(session, clinic_id)
        self._notifications = SqlAlchemyNotificationRepository(session, clinic_id)
        self._notification_preferences = SqlAlchemyPreferenceRepository(session, clinic_id)
        self._dashboard = SqlAlchemyDashboardReads(session, clinic_id)
        self._audit_log = SqlAlchemyAuditReader(session, clinic_id)

    @property
    def clinic_id(self) -> UUID:
        return self._clinic_id

    @property
    def doctors(self) -> SqlAlchemyDoctorRepository:
        return self._doctors

    @property
    def memberships(self) -> SqlAlchemyMembershipRepository:
        return self._memberships

    @property
    def checklist(self) -> SqlAlchemyChecklistRepository:
        return self._checklist

    @property
    def patients(self) -> SqlAlchemyPatientRepository:
        return self._patients

    @property
    def schedules(self) -> SqlAlchemyScheduleRepository:
        return self._schedules

    @property
    def schedule_exceptions(self) -> SqlAlchemyScheduleExceptionRepository:
        return self._schedule_exceptions

    @property
    def sessions(self) -> SqlAlchemySessionRepository:
        return self._sessions

    @property
    def appointments(self) -> SqlAlchemyAppointmentRepository:
        return self._appointments

    @property
    def appointment_history(self) -> SqlAlchemyAppointmentHistoryRepository:
        return self._appointment_history

    @property
    def visits(self) -> SqlAlchemyVisitRepository:
        return self._visits

    @property
    def visit_addenda(self) -> SqlAlchemyVisitAddendumRepository:
        return self._visit_addenda

    @property
    def prescriptions(self) -> SqlAlchemyPrescriptionRepository:
        return self._prescriptions

    @property
    def rx_favourites(self) -> SqlAlchemyRxFavouriteRepository:
        return self._rx_favourites

    @property
    def rx_templates(self) -> SqlAlchemyRxTemplateRepository:
        return self._rx_templates

    @property
    def patient_links(self) -> SqlAlchemyPatientLinkRepository:
        return self._patient_links

    @property
    def portal_links(self) -> SqlAlchemyPortalLinkRepository:
        return self._portal_links

    @property
    def portal_invites(self) -> SqlAlchemyPortalInviteRepository:
        return self._portal_invites

    @property
    def reminder_prefs(self) -> SqlAlchemyReminderPrefRepository:
        return self._reminder_prefs

    @property
    def dose_records(self) -> SqlAlchemyDoseRecordRepository:
        return self._dose_records

    @property
    def booking_requests(self) -> SqlAlchemyBookingRequestRepository:
        return self._booking_requests

    @property
    def messages(self) -> SqlAlchemyMessageRepository:
        return self._messages

    @property
    def reminders(self) -> SqlAlchemyReminderRepository:
        return self._reminders

    @property
    def notifications(self) -> SqlAlchemyNotificationRepository:
        return self._notifications

    @property
    def notification_preferences(self) -> SqlAlchemyPreferenceRepository:
        return self._notification_preferences

    @property
    def dashboard(self) -> SqlAlchemyDashboardReads:
        return self._dashboard

    @property
    def audit_log(self) -> SqlAlchemyAuditReader:
        return self._audit_log


class _OpenUnit:
    """The session and platform repositories of one open unit of work."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.clinics = SqlAlchemyClinicRepository(session)
        self.users = SqlAlchemyUserRepository(session)
        self.refresh_tokens = SqlAlchemyRefreshTokenRepository(session)
        self.clinic_access = SqlAlchemyClinicAccessRepository(session)
        # M6a-P3 (ADR-0015): patient accounts, their sessions and Google identities.
        self.patient_accounts = SqlAlchemyPatientAccountRepository(session)
        self.patient_refresh_tokens = SqlAlchemyPatientRefreshTokenRepository(session)
        self.external_identities = SqlAlchemyExternalIdentityRepository(session)
        # M6a-P4: email verification and password-reset tokens.
        self.email_tokens = SqlAlchemyEmailTokenRepository(session)
        self.staff_invites = SqlAlchemyStaffInviteRepository(session)
        # M6b-P1: the portal's cross-clinic start (an account's active links, IDs only).
        self.portal_lookup = SqlAlchemyPortalLookup(session)
        # M6b-P3b (R54): one account's dose records, for its export or deletion on request.
        self.dose_lifecycle = SqlAlchemyDoseLifecycle(session)
        # M6b-P4: a patient's own requests in every clinic (selected by account alone).
        self.booking_request_lookup = SqlAlchemyBookingRequestLookup(session)
        self.rate_limits = SqlAlchemyRateLimitRepository(session)
        # Shares the session, so an audit row commits with the change (R11).
        self.audit = SqlAlchemyAuditWriter(session)
        # M5-P1: jobs commit with the change that enqueues them (the outbox).
        self.jobs = SqlAlchemyJobQueue(session)
        self.retention = SqlAlchemyRetentionRepository(session)
        # M5-P3: provider webhooks name no clinic.
        self.message_lookup = SqlAlchemyMessageLookup(session)
        self.webhook_events = SqlAlchemyWebhookEventRepository(session)
        # M5-P4: which clinics have bookings overdue for NO_SHOW (IDs only).
        self.no_show_sweep = SqlAlchemyNoShowSweep(session)
        # M5-P5: who a STOP reply opts out (IDs only).
        self.opt_out_lookup = SqlAlchemyOptOutLookup(session)
        self.message_costs = SqlAlchemyMessageCostReport(session)


class SqlAlchemyUnitOfWork:
    """``UnitOfWork`` over a SQLAlchemy session factory."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._open: _OpenUnit | None = None

    def __enter__(self) -> Self:
        if self._open is not None:
            raise RuntimeError("unit of work is already open")
        self._open = _OpenUnit(self._session_factory())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_open().session
        try:
            # Anything not committed is discarded — on success and on error alike.
            session.rollback()
        finally:
            session.close()
            self._open = None

    @property
    def clinics(self) -> SqlAlchemyClinicRepository:
        return self._require_open().clinics

    @property
    def users(self) -> SqlAlchemyUserRepository:
        return self._require_open().users

    @property
    def refresh_tokens(self) -> SqlAlchemyRefreshTokenRepository:
        return self._require_open().refresh_tokens

    @property
    def clinic_access(self) -> SqlAlchemyClinicAccessRepository:
        return self._require_open().clinic_access

    @property
    def patient_accounts(self) -> SqlAlchemyPatientAccountRepository:
        return self._require_open().patient_accounts

    @property
    def patient_refresh_tokens(self) -> SqlAlchemyPatientRefreshTokenRepository:
        return self._require_open().patient_refresh_tokens

    @property
    def external_identities(self) -> SqlAlchemyExternalIdentityRepository:
        return self._require_open().external_identities

    @property
    def email_tokens(self) -> SqlAlchemyEmailTokenRepository:
        return self._require_open().email_tokens

    @property
    def staff_invites(self) -> SqlAlchemyStaffInviteRepository:
        return self._require_open().staff_invites

    @property
    def portal_lookup(self) -> SqlAlchemyPortalLookup:
        return self._require_open().portal_lookup

    @property
    def booking_request_lookup(self) -> SqlAlchemyBookingRequestLookup:
        return self._require_open().booking_request_lookup

    @property
    def dose_lifecycle(self) -> SqlAlchemyDoseLifecycle:
        return self._require_open().dose_lifecycle

    @property
    def rate_limits(self) -> SqlAlchemyRateLimitRepository:
        return self._require_open().rate_limits

    @property
    def audit(self) -> SqlAlchemyAuditWriter:
        return self._require_open().audit

    @property
    def jobs(self) -> SqlAlchemyJobQueue:
        return self._require_open().jobs

    @property
    def retention(self) -> SqlAlchemyRetentionRepository:
        return self._require_open().retention

    @property
    def message_lookup(self) -> SqlAlchemyMessageLookup:
        return self._require_open().message_lookup

    @property
    def webhook_events(self) -> SqlAlchemyWebhookEventRepository:
        return self._require_open().webhook_events

    @property
    def no_show_sweep(self) -> SqlAlchemyNoShowSweep:
        return self._require_open().no_show_sweep

    @property
    def opt_out_lookup(self) -> SqlAlchemyOptOutLookup:
        return self._require_open().opt_out_lookup

    @property
    def message_costs(self) -> SqlAlchemyMessageCostReport:
        return self._require_open().message_costs

    def tenant(self, clinic_id: UUID) -> SqlAlchemyTenantRepositories:
        return SqlAlchemyTenantRepositories(self._require_open().session, clinic_id)

    def commit(self) -> None:
        self._require_open().session.commit()

    def rollback(self) -> None:
        self._require_open().session.rollback()

    def _require_open(self) -> _OpenUnit:
        if self._open is None:
            raise RuntimeError("unit of work is not open; use it in a `with` block")
        return self._open
