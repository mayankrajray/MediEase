"""Composition root — the Flask application factory.

CLAUDE.md ("Composition root"): configuration, logging, adapters, middleware and
routes are wired in exactly one place, with **no import-time side effects**.
Importing this module does nothing; only calling ``create_app(settings)`` builds
an app. This is also the only place that chooses adapters (apps/api/CLAUDE.md).
"""

from __future__ import annotations

import os
import random
import secrets
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import structlog
from flask import Flask
from sqlalchemy.orm import Session, sessionmaker
from ulid import ULID

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.engine import build_engine
from mediease_api.adapters.db.jobs import SqlAlchemyJobStore
from mediease_api.adapters.db.readiness import SqlAlchemyDatabaseCheck
from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork, build_session_factory
from mediease_api.adapters.email.console import ConsoleEmailAdapter
from mediease_api.adapters.email.smtp import SmtpEmailAdapter
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.messaging.catalog import YamlTemplateCatalog
from mediease_api.adapters.messaging.console import ConsoleMessagingAdapter
from mediease_api.adapters.messaging.console_sms import ConsoleSmsAdapter
from mediease_api.adapters.messaging.prices import load_price_table
from mediease_api.adapters.messaging.whatsapp_cloud import WhatsAppCloudAdapter
from mediease_api.adapters.messaging.whatsapp_webhook import PROVIDER as WHATSAPP_PROVIDER
from mediease_api.adapters.messaging.whatsapp_webhook import (
    HmacWebhookVerifier,
    WhatsAppWebhookParser,
)
from mediease_api.adapters.oidc.fake import FakeOidcProvider
from mediease_api.adapters.oidc.google import GoogleOidcProvider
from mediease_api.adapters.pdf.weasy import WeasyPrintRenderer
from mediease_api.adapters.security.argon2_hasher import Argon2PasswordHasher
from mediease_api.adapters.security.ip_hash import HmacIpHasher
from mediease_api.adapters.security.jwt_flow import JwtFlowSealer
from mediease_api.adapters.security.jwt_tokens import PORTAL_AUDIENCE, JwtAccessTokenIssuer
from mediease_api.adapters.security.link_signer import HmacLinkSigner
from mediease_api.adapters.security.phone_cipher import FernetPhoneCipher
from mediease_api.adapters.security.refresh_secrets import Sha256RefreshTokenSecrets
from mediease_api.adapters.storage.local import LocalBlobStorage
from mediease_api.adapters.storage.s3 import S3BlobStorage
from mediease_api.application.appointments.book import BookAppointment
from mediease_api.application.appointments.cancel import CancelAppointment
from mediease_api.application.appointments.no_show import MarkNoShows, SweepNoShows
from mediease_api.application.appointments.queries import GetAppointment, ListPatientAppointments
from mediease_api.application.appointments.queue import AddWalkIn, GetQueue, TransitionAppointment
from mediease_api.application.appointments.reschedule import RescheduleAppointment
from mediease_api.application.appointments.to_move import ListBookingsToMove
from mediease_api.application.audit_log.use_cases import ExportAuditEvents, ListAuditEvents
from mediease_api.application.auth._session import SessionIssuer
from mediease_api.application.auth.authenticate import AuthenticateRequest
from mediease_api.application.auth.emails import SendAuthEmail
from mediease_api.application.auth.google import CompleteGoogleSignIn, StartGoogleSignIn
from mediease_api.application.auth.password_reset import (
    CompletePasswordReset,
    RequestPasswordReset,
    ResendVerification,
    VerifyEmail,
)
from mediease_api.application.auth.refresh_session import RefreshSession
from mediease_api.application.auth.sign_in import SignIn
from mediease_api.application.auth.sign_out import SignOut
from mediease_api.application.clinics.change_staff_role import ChangeStaffRole
from mediease_api.application.clinics.deactivate_staff import DeactivateStaff
from mediease_api.application.clinics.invite_email import SendStaffInvite
from mediease_api.application.clinics.invite_staff import InviteStaff, ResendStaffInvite
from mediease_api.application.clinics.onboard_clinic import (
    AddDoctor,
    CreateClinic,
    UpdateClinic,
    UpdateDoctor,
)
from mediease_api.application.clinics.queries import GetClinic, GetDoctor, ListDoctors, ListStaff
from mediease_api.application.dashboard.today import GetToday
from mediease_api.application.identity.accept_invite import AcceptInvite, DescribeInvite
from mediease_api.application.jobs.purge import PurgeExpired
from mediease_api.application.jobs.run import JobHandler, RunJob
from mediease_api.application.jobs.schedule import ScheduleRecurring
from mediease_api.application.links.use_cases import (
    DescribeLink,
    GetLink,
    LinkTokens,
    ProveWithLink,
    ReplaceLink,
    ResetLink,
    VerifyChallenge,
    ViewPrescription,
)
from mediease_api.application.messaging.booking import SendBookingConfirmation
from mediease_api.application.messaging.cancellation import SendCancellationNotice
from mediease_api.application.messaging.opt_out import OptOutByReply, SendOptOutConfirmation
from mediease_api.application.messaging.rx_link import SendRxLink
from mediease_api.application.messaging.sender import MessageSender
from mediease_api.application.messaging.webhooks import (
    ProcessWebhookEvent,
    ReceiveWebhook,
    ReconcileMessages,
    VerifyWebhookSubscription,
)
from mediease_api.application.notifications.use_cases import (
    GetNotificationPreferences,
    GetNotificationSummary,
    ListNotifications,
    ReadAllNotifications,
    ReadNotification,
    SetNotificationPreferences,
)
from mediease_api.application.ops.queries import GetClinicOnboarding, ListClinics, MessagingCosts
from mediease_api.application.patients.consent import OptIn, OptOut, RecordConsent
from mediease_api.application.patients.import_patients import ImportPatients
from mediease_api.application.patients.my_patients import ListMyPatients
from mediease_api.application.patients.queries import GetPatient, LookupPatients
from mediease_api.application.patients.register_patient import RegisterPatient
from mediease_api.application.patients.update_patient import UpdatePatient
from mediease_api.application.portal.doses import ClearDose, GetDoseHistory, MarkDose
from mediease_api.application.portal.linking import (
    AcceptPortalInvite,
    DescribePortalInvite,
    GetPortalStatus,
    InviteToPortal,
    LinkByPrescription,
    UnlinkPatient,
    UnlinkPortal,
)
from mediease_api.application.portal.medicines import (
    GetMedicinePlan,
    ListMedicineCourses,
    SetMedicineReminder,
)
from mediease_api.application.portal.records import (
    GetPortalPrescription,
    ListPortalAppointments,
    ListPortalLinks,
    ListPortalPrescriptions,
    ListPortalReminders,
    PortalPrescriptionPdf,
)
from mediease_api.application.portal.sessions import PatientSessionIssuer
from mediease_api.application.portal.use_cases import (
    AuthenticatePatient,
    RefreshPatientSession,
    SetPortalLanguage,
    SignInPatient,
    SignOutPatient,
    SignUpPatient,
)
from mediease_api.application.prescriptions.library import (
    DeleteFavourite,
    DeleteTemplate,
    GetTemplate,
    ListFavourites,
    ListTemplates,
    SaveFavourite,
    SaveTemplate,
    SuggestMedicines,
)
from mediease_api.application.prescriptions.pdf import DownloadPrescriptionPdf, ListPrintable
from mediease_api.application.prescriptions.use_cases import (
    CreateDraft,
    DiscardDraft,
    GetPrescription,
    IssuePrescription,
    PreviewPrescription,
    ReplaceDraft,
    RevisePrescription,
)
from mediease_api.application.reminders.fallback import SendSmsFallback, SmsFallback
from mediease_api.application.reminders.send import SendReminder
from mediease_api.application.reminders.use_cases import (
    ChangeReminder,
    ListPatientMessages,
    ListPatientReminders,
    ListPendingFollowUps,
    ScheduleReminder,
)
from mediease_api.application.scheduling.exceptions import AddException, RemoveException
from mediease_api.application.scheduling.schedules import GetSchedule, ReplaceSchedule
from mediease_api.application.scheduling.sessions import ListSessions
from mediease_api.application.visits.use_cases import (
    AddAddendum,
    CompleteVisit,
    GetConsultation,
    ListPatientVisits,
    StartVisit,
    UpdateVisit,
)
from mediease_api.config.logging import configure_logging
from mediease_api.config.settings import AppEnv, AppSettings
from mediease_api.delivery.errors import register_error_handlers
from mediease_api.delivery.http.access import check_every_route_has_policy, register_access_control
from mediease_api.delivery.http.appointments import create_appointments_blueprint
from mediease_api.delivery.http.audit_log import create_audit_log_blueprint
from mediease_api.delivery.http.auth import create_auth_blueprint
from mediease_api.delivery.http.clinic import create_clinic_blueprint
from mediease_api.delivery.http.csrf import register_csrf_protection
from mediease_api.delivery.http.dashboard import create_dashboard_blueprint
from mediease_api.delivery.http.google import create_google_blueprint
from mediease_api.delivery.http.invites import create_invite_blueprint
from mediease_api.delivery.http.me import create_me_blueprint
from mediease_api.delivery.http.notifications import create_notifications_blueprint
from mediease_api.delivery.http.ops import create_ops_blueprint
from mediease_api.delivery.http.patient_portal import (
    create_patient_portal_blueprint,
    create_portal_records_blueprint,
)
from mediease_api.delivery.http.patients import (
    create_my_patients_blueprint,
    create_patients_blueprint,
)
from mediease_api.delivery.http.platform import create_platform_blueprint
from mediease_api.delivery.http.portal import create_portal_blueprint
from mediease_api.delivery.http.prescriptions import create_prescriptions_blueprint
from mediease_api.delivery.http.public_links import create_public_links_blueprint
from mediease_api.delivery.http.reminders import create_reminders_blueprint
from mediease_api.delivery.http.request_info import register_request_info
from mediease_api.delivery.http.rx_library import create_rx_library_blueprint
from mediease_api.delivery.http.scheduling import create_scheduling_blueprint
from mediease_api.delivery.http.visits import create_visits_blueprint
from mediease_api.delivery.middleware import register_request_middleware
from mediease_api.delivery.webhooks.whatsapp import create_whatsapp_webhook_blueprint
from mediease_api.delivery.worker.heartbeat import beat
from mediease_api.delivery.worker.loop import LockRenewer, Worker
from mediease_api.domain.jobs.job import (
    AUTH_EMAIL_KIND,
    MARK_NO_SHOWS_KIND,
    NO_SHOW_SWEEP_KIND,
    PURGE_KIND,
    RECONCILE_KIND,
    STAFF_INVITE_KIND,
    WEBHOOK_KIND,
)
from mediease_api.domain.messaging.jobs import (
    BOOKING_CONFIRMATION_KIND,
    CANCELLATION_NOTICE_KIND,
    OPT_OUT_CONFIRMATION_KIND,
    REMINDER_KIND,
    RX_LINK_KIND,
    SMS_FALLBACK_KIND,
)
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.email import EmailPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.messaging import MessagingPort, PhoneCipherPort
from mediease_api.ports.oidc import OidcPort
from mediease_api.ports.pdf import PdfRendererPort
from mediease_api.ports.readiness import DatabaseCheck
from mediease_api.ports.security import AccessTokenIssuer, FlowSealer, PasswordHasher
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _UseCases:
    """Builds each use case with a fresh unit of work, once per request.

    The HTTP blueprints each declare the subset they need as a Protocol, so
    this one container satisfies all of them structurally without any of them
    depending on the others.
    """

    session_factory: sessionmaker[Session]
    clock: ClockPort
    ids: Uuid7Generator
    hasher: PasswordHasher
    refresh_secrets: Sha256RefreshTokenSecrets
    # The same adapter: an invitation needs exactly what a refresh token needs
    # — an unguessable value stored only as a digest (ports/security.py).
    invite_secrets: Sha256RefreshTokenSecrets
    access_tokens: AccessTokenIssuer
    sessions: SessionIssuer
    dummy_password_hash: str
    # M4-P4 (ADR-0012): built once; both are safe to share between requests.
    pdf_renderer: PdfRendererPort
    blob_storage: BlobStoragePort
    # M4-P5: patient link tokens (the signer holds the keys) and their lifetime.
    link_tokens: LinkTokens
    link_ttl_days: int
    # M6a-P3 (ADR-0015): portal sessions apart from staff, and Google sign-in.
    portal_access_tokens: AccessTokenIssuer
    patient_sessions: PatientSessionIssuer
    oidc: OidcPort
    flow_sealer: FlowSealer
    google_redirect_uri: str
    # M5-P3: the WhatsApp webhook's secrets (empty: the webhook refuses everything).
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    # M5-P5: a STOP sender's number is stored encrypted until processed (decision 1A).
    phones: PhoneCipherPort | None = None

    def schedule_reminder(self) -> ScheduleReminder:
        return ScheduleReminder(uow=self._uow(), clock=self.clock, ids=self.ids)

    def change_reminder(self) -> ChangeReminder:
        return ChangeReminder(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_patient_reminders(self) -> ListPatientReminders:
        return ListPatientReminders(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_pending_follow_ups(self) -> ListPendingFollowUps:
        return ListPendingFollowUps(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_patient_messages(self) -> ListPatientMessages:
        return ListPatientMessages(uow=self._uow(), clock=self.clock, ids=self.ids)

    def verify_whatsapp_subscription(self) -> VerifyWebhookSubscription:
        return VerifyWebhookSubscription(verify_token=self.whatsapp_verify_token)

    def receive_whatsapp_webhook(self) -> ReceiveWebhook:
        assert self.phones is not None, "create_app sets the phone cipher"
        return ReceiveWebhook(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            verifier=HmacWebhookVerifier(self.whatsapp_app_secret),
            parser=WhatsAppWebhookParser(self.phones),
            provider=WHATSAPP_PROVIDER,
        )

    def sign_in(self) -> SignIn:
        return SignIn(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            hasher=self.hasher,
            sessions=self.sessions,
            dummy_password_hash=self.dummy_password_hash,
        )

    def refresh(self) -> RefreshSession:
        return RefreshSession(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            secrets=self.refresh_secrets,
            sessions=self.sessions,
        )

    def sign_out(self) -> SignOut:
        return SignOut(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.refresh_secrets
        )

    def authenticate(self) -> AuthenticateRequest:
        return AuthenticateRequest(
            uow=self._uow(), clock=self.clock, access_tokens=self.access_tokens
        )

    def authenticate_patient(self) -> AuthenticatePatient:
        return AuthenticatePatient(
            uow=self._uow(), clock=self.clock, access_tokens=self.portal_access_tokens
        )

    def sign_up_patient(self) -> SignUpPatient:
        return SignUpPatient(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            hasher=self.hasher,
            sessions=self.patient_sessions,
        )

    def sign_in_patient(self) -> SignInPatient:
        return SignInPatient(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            hasher=self.hasher,
            sessions=self.patient_sessions,
            dummy_password_hash=self.dummy_password_hash,
        )

    def refresh_patient(self) -> RefreshPatientSession:
        return RefreshPatientSession(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            secrets=self.refresh_secrets,
            sessions=self.patient_sessions,
        )

    def sign_out_patient(self) -> SignOutPatient:
        return SignOutPatient(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.refresh_secrets
        )

    def request_password_reset(self) -> RequestPasswordReset:
        return RequestPasswordReset(uow=self._uow(), clock=self.clock, ids=self.ids)

    def complete_password_reset(self) -> CompletePasswordReset:
        return CompletePasswordReset(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            hasher=self.hasher,
            secrets=self.refresh_secrets,
        )

    def verify_email(self) -> VerifyEmail:
        return VerifyEmail(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.refresh_secrets
        )

    def resend_verification(self) -> ResendVerification:
        return ResendVerification(uow=self._uow(), clock=self.clock, ids=self.ids)

    def start_google_sign_in(self) -> StartGoogleSignIn:
        return StartGoogleSignIn(
            uow=self._uow(),
            clock=self.clock,
            oidc=self.oidc,
            sealer=self.flow_sealer,
            redirect_uri=self.google_redirect_uri,
        )

    def complete_google_sign_in(self) -> CompleteGoogleSignIn:
        return CompleteGoogleSignIn(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            oidc=self.oidc,
            sealer=self.flow_sealer,
            redirect_uri=self.google_redirect_uri,
            staff_sessions=self.sessions,
            patient_sessions=self.patient_sessions,
        )

    def get_clinic(self) -> GetClinic:
        return GetClinic(uow=self._uow())

    def update_clinic(self) -> UpdateClinic:
        return UpdateClinic(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_doctors(self) -> ListDoctors:
        return ListDoctors(uow=self._uow())

    def get_doctor(self) -> GetDoctor:
        return GetDoctor(uow=self._uow())

    def add_doctor(self) -> AddDoctor:
        return AddDoctor(uow=self._uow(), clock=self.clock, ids=self.ids)

    def update_doctor(self) -> UpdateDoctor:
        return UpdateDoctor(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_staff(self) -> ListStaff:
        return ListStaff(uow=self._uow())

    def invite_staff(self) -> InviteStaff:
        return InviteStaff(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.invite_secrets
        )

    def resend_staff_invite(self) -> ResendStaffInvite:
        return ResendStaffInvite(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.invite_secrets
        )

    def change_staff_role(self) -> ChangeStaffRole:
        return ChangeStaffRole(uow=self._uow(), clock=self.clock, ids=self.ids)

    def deactivate_staff(self) -> DeactivateStaff:
        return DeactivateStaff(uow=self._uow(), clock=self.clock, ids=self.ids)

    def describe_invite(self) -> DescribeInvite:
        return DescribeInvite(uow=self._uow(), clock=self.clock, secrets=self.invite_secrets)

    def accept_invite(self) -> AcceptInvite:
        return AcceptInvite(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            hasher=self.hasher,
            secrets=self.invite_secrets,
            sessions=self.sessions,
        )

    def create_clinic(self) -> CreateClinic:
        return CreateClinic(uow=self._uow(), clock=self.clock, ids=self.ids)

    def register_patient(self) -> RegisterPatient:
        return RegisterPatient(uow=self._uow(), clock=self.clock, ids=self.ids)

    def update_patient(self) -> UpdatePatient:
        return UpdatePatient(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_patient(self) -> GetPatient:
        return GetPatient(uow=self._uow(), clock=self.clock)

    def lookup_patients(self) -> LookupPatients:
        return LookupPatients(uow=self._uow(), clock=self.clock)

    def list_my_patients(self) -> ListMyPatients:
        return ListMyPatients(uow=self._uow(), clock=self.clock)

    # M6a-P7: the notification centre and preferences.
    def list_notifications(self) -> ListNotifications:
        return ListNotifications(uow=self._uow())

    def notification_summary(self) -> GetNotificationSummary:
        return GetNotificationSummary(uow=self._uow())

    def read_notification(self) -> ReadNotification:
        return ReadNotification(uow=self._uow(), clock=self.clock)

    def read_all_notifications(self) -> ReadAllNotifications:
        return ReadAllNotifications(uow=self._uow(), clock=self.clock)

    def notification_preferences(self) -> GetNotificationPreferences:
        return GetNotificationPreferences(uow=self._uow())

    def set_notification_preferences(self) -> SetNotificationPreferences:
        return SetNotificationPreferences(uow=self._uow(), clock=self.clock, ids=self.ids)

    # M6a-P8: the owner's audit log and the bookings a schedule change left to move.
    def list_audit_events(self) -> ListAuditEvents:
        return ListAuditEvents(uow=self._uow(), clock=self.clock)

    def export_audit_events(self) -> ExportAuditEvents:
        return ExportAuditEvents(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_bookings_to_move(self) -> ListBookingsToMove:
        return ListBookingsToMove(uow=self._uow(), clock=self.clock)

    def record_consent(self) -> RecordConsent:
        return RecordConsent(uow=self._uow(), clock=self.clock, ids=self.ids)

    def opt_out(self) -> OptOut:
        return OptOut(uow=self._uow(), clock=self.clock, ids=self.ids)

    def opt_in(self) -> OptIn:
        return OptIn(uow=self._uow(), clock=self.clock, ids=self.ids)

    def import_patients(self) -> ImportPatients:
        return ImportPatients(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_schedule(self) -> GetSchedule:
        return GetSchedule(uow=self._uow(), clock=self.clock)

    def replace_schedule(self) -> ReplaceSchedule:
        return ReplaceSchedule(uow=self._uow(), clock=self.clock, ids=self.ids)

    def add_schedule_exception(self) -> AddException:
        return AddException(uow=self._uow(), clock=self.clock, ids=self.ids)

    def remove_schedule_exception(self) -> RemoveException:
        return RemoveException(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_sessions(self) -> ListSessions:
        return ListSessions(uow=self._uow(), clock=self.clock, ids=self.ids)

    def book_appointment(self) -> BookAppointment:
        return BookAppointment(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_appointment(self) -> GetAppointment:
        return GetAppointment(uow=self._uow())

    def cancel_appointment(self) -> CancelAppointment:
        return CancelAppointment(uow=self._uow(), clock=self.clock, ids=self.ids)

    def reschedule_appointment(self) -> RescheduleAppointment:
        return RescheduleAppointment(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_patient_appointments(self) -> ListPatientAppointments:
        return ListPatientAppointments(uow=self._uow())

    def transition_appointment(self) -> TransitionAppointment:
        return TransitionAppointment(uow=self._uow(), clock=self.clock, ids=self.ids)

    def add_walk_in(self) -> AddWalkIn:
        return AddWalkIn(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_queue(self) -> GetQueue:
        return GetQueue(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_today(self) -> GetToday:
        return GetToday(uow=self._uow(), clock=self.clock, ids=self.ids)

    def start_visit(self) -> StartVisit:
        return StartVisit(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_consultation(self) -> GetConsultation:
        return GetConsultation(uow=self._uow(), clock=self.clock, ids=self.ids)

    def update_visit(self) -> UpdateVisit:
        return UpdateVisit(uow=self._uow(), clock=self.clock, ids=self.ids)

    def complete_visit(self) -> CompleteVisit:
        return CompleteVisit(uow=self._uow(), clock=self.clock, ids=self.ids)

    def add_addendum(self) -> AddAddendum:
        return AddAddendum(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_patient_visits(self) -> ListPatientVisits:
        return ListPatientVisits(uow=self._uow(), clock=self.clock, ids=self.ids)

    def create_prescription(self) -> CreateDraft:
        return CreateDraft(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_prescription(self) -> GetPrescription:
        return GetPrescription(uow=self._uow(), clock=self.clock, ids=self.ids)

    def replace_prescription(self) -> ReplaceDraft:
        return ReplaceDraft(uow=self._uow(), clock=self.clock, ids=self.ids)

    def discard_prescription(self) -> DiscardDraft:
        return DiscardDraft(uow=self._uow(), clock=self.clock, ids=self.ids)

    def issue_prescription(self) -> IssuePrescription:
        return IssuePrescription(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            link_key_id=self.link_tokens.current_key_id,
            link_ttl_days=self.link_ttl_days,
        )

    def describe_link(self) -> DescribeLink:
        return DescribeLink(
            uow=self._uow(), clock=self.clock, ids=self.ids, tokens=self.link_tokens
        )

    def verify_link(self) -> VerifyChallenge:
        return VerifyChallenge(
            uow=self._uow(), clock=self.clock, ids=self.ids, tokens=self.link_tokens
        )

    def view_link_prescription(self) -> ViewPrescription:
        return ViewPrescription(
            uow=self._uow(), clock=self.clock, ids=self.ids, tokens=self.link_tokens
        )

    def _staff_link(self, kind: type[GetLink] | type[ResetLink] | type[ReplaceLink]) -> Any:
        return kind(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            tokens=self.link_tokens,
            ttl_days=self.link_ttl_days,
        )

    def get_patient_link(self) -> GetLink:
        link: GetLink = self._staff_link(GetLink)
        return link

    def reset_patient_link(self) -> ResetLink:
        link: ResetLink = self._staff_link(ResetLink)
        return link

    def replace_patient_link(self) -> ReplaceLink:
        link: ReplaceLink = self._staff_link(ReplaceLink)
        return link

    def preview_prescription(self) -> PreviewPrescription:
        return PreviewPrescription(uow=self._uow(), clock=self.clock, ids=self.ids)

    def revise_prescription(self) -> RevisePrescription:
        return RevisePrescription(uow=self._uow(), clock=self.clock, ids=self.ids)

    def download_prescription_pdf(self) -> DownloadPrescriptionPdf:
        return DownloadPrescriptionPdf(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            renderer=self.pdf_renderer,
            storage=self.blob_storage,
        )

    def set_portal_language(self) -> SetPortalLanguage:
        return SetPortalLanguage(uow=self._uow(), clock=self.clock)

    # M6b-P1: linking a patient account and the portal's reads.
    def invite_to_portal(self) -> InviteToPortal:
        return InviteToPortal(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.invite_secrets
        )

    def get_portal_status(self) -> GetPortalStatus:
        return GetPortalStatus(uow=self._uow(), clock=self.clock, ids=self.ids)

    def unlink_patient(self) -> UnlinkPatient:
        return UnlinkPatient(uow=self._uow(), clock=self.clock, ids=self.ids)

    def describe_portal_invite(self) -> DescribePortalInvite:
        return DescribePortalInvite(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.invite_secrets
        )

    def accept_portal_invite(self) -> AcceptPortalInvite:
        return AcceptPortalInvite(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.invite_secrets
        )

    def link_by_prescription(self) -> LinkByPrescription:
        proof = ProveWithLink(
            uow=self._uow(), clock=self.clock, ids=self.ids, tokens=self.link_tokens
        )
        return LinkByPrescription(clock=self.clock, ids=self.ids, proof=proof)

    def unlink_portal(self) -> UnlinkPortal:
        return UnlinkPortal(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_portal_links(self) -> ListPortalLinks:
        return ListPortalLinks(uow=self._uow())

    def list_portal_appointments(self) -> ListPortalAppointments:
        return ListPortalAppointments(uow=self._uow(), clock=self.clock)

    def list_portal_prescriptions(self) -> ListPortalPrescriptions:
        return ListPortalPrescriptions(uow=self._uow())

    def get_portal_prescription(self) -> GetPortalPrescription:
        return GetPortalPrescription(uow=self._uow())

    def portal_prescription_pdf(self) -> PortalPrescriptionPdf:
        return PortalPrescriptionPdf(uow=self._uow(), pdf=self.download_prescription_pdf())

    def list_portal_reminders(self) -> ListPortalReminders:
        return ListPortalReminders(uow=self._uow())

    # M6b-P3: the medicine plan and the person's reminder choices.
    def get_medicine_plan(self) -> GetMedicinePlan:
        return GetMedicinePlan(uow=self._uow(), clock=self.clock)

    def list_medicine_courses(self) -> ListMedicineCourses:
        return ListMedicineCourses(uow=self._uow(), clock=self.clock)

    def set_medicine_reminder(self) -> SetMedicineReminder:
        return SetMedicineReminder(uow=self._uow(), clock=self.clock, ids=self.ids)

    # M6b-P3b: the patient's own dose marks.
    def mark_dose(self) -> MarkDose:
        return MarkDose(uow=self._uow(), clock=self.clock, ids=self.ids)

    def clear_dose(self) -> ClearDose:
        return ClearDose(uow=self._uow(), clock=self.clock, ids=self.ids)

    def dose_history(self) -> GetDoseHistory:
        return GetDoseHistory(uow=self._uow(), clock=self.clock)

    def list_printable(self) -> ListPrintable:
        return ListPrintable(uow=self._uow())

    def list_favourites(self) -> ListFavourites:
        return ListFavourites(uow=self._uow(), clock=self.clock, ids=self.ids)

    def save_favourite(self) -> SaveFavourite:
        return SaveFavourite(uow=self._uow(), clock=self.clock, ids=self.ids)

    def delete_favourite(self) -> DeleteFavourite:
        return DeleteFavourite(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_templates(self) -> ListTemplates:
        return ListTemplates(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_template(self) -> GetTemplate:
        return GetTemplate(uow=self._uow(), clock=self.clock, ids=self.ids)

    def save_template(self) -> SaveTemplate:
        return SaveTemplate(uow=self._uow(), clock=self.clock, ids=self.ids)

    def delete_template(self) -> DeleteTemplate:
        return DeleteTemplate(uow=self._uow(), clock=self.clock, ids=self.ids)

    def suggest_medicines(self) -> SuggestMedicines:
        return SuggestMedicines(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_clinics(self) -> ListClinics:
        return ListClinics(uow=self._uow())

    def get_clinic_onboarding(self) -> GetClinicOnboarding:
        return GetClinicOnboarding(uow=self._uow())

    def messaging_costs(self) -> MessagingCosts:
        return MessagingCosts(uow=self._uow())

    def _uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)


def build_blob_storage(settings: AppSettings) -> BlobStoragePort:
    """ADR-0012: a local directory, or an S3-compatible bucket (credentials from the AWS chain)."""
    if settings.BLOB_STORAGE == "s3":
        import boto3  # only the s3 backend needs it loaded

        client = boto3.client(
            "s3",
            region_name=settings.S3_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL or None,
        )
        return S3BlobStorage(client, settings.S3_BUCKET)
    return LocalBlobStorage(settings.BLOB_LOCAL_DIR)


def build_password_hasher() -> PasswordHasher:
    """Production Argon2id parameters (also used by ``make seed``)."""
    return Argon2PasswordHasher()


GOOGLE_CALLBACK_PATH = "/api/v1/auth/google/callback"


def build_oidc(settings: AppSettings) -> OidcPort:
    """Google, or the fake that skips it (ADR-0015 decision 6), refused outside local and test."""
    if settings.GOOGLE_OIDC_PROVIDER == "google":
        return GoogleOidcProvider(
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
        )
    if settings.APP_ENV not in (AppEnv.LOCAL, AppEnv.TEST):
        raise ValueError(
            "GOOGLE_OIDC_PROVIDER=fake signs anyone in by email; "
            f"refused when APP_ENV={settings.APP_ENV.value}"
        )
    return FakeOidcProvider()


@dataclass(frozen=True, slots=True)
class SeedDependencies:
    uow: UnitOfWork
    clock: ClockPort
    ids: IdPort
    hasher: PasswordHasher


def build_seed_dependencies(settings: AppSettings) -> SeedDependencies:
    """Adapters for ``delivery/cli/seed.py``, chosen here like everything else."""
    configure_logging(settings)
    return SeedDependencies(
        uow=SqlAlchemyUnitOfWork(build_session_factory(build_engine(settings))),
        clock=SystemClock(),
        ids=Uuid7Generator(),
        hasher=build_password_hasher(),
    )


def build_support_uow(settings: AppSettings) -> UnitOfWork:
    """A unit of work for the support commands (``delivery/cli/dose_data.py``, M6b-P3b)."""
    configure_logging(settings)
    return SqlAlchemyUnitOfWork(build_session_factory(build_engine(settings)))


def _interruptible_sleep(stop: threading.Event) -> Callable[[float], None]:
    """Sleep that ends at once when the worker is told to stop."""

    def sleep(seconds: float) -> None:
        stop.wait(seconds)

    return sleep


def build_messaging(settings: AppSettings) -> MessagingPort:
    """The provider named by ``MESSAGING_PROVIDER`` (M5-P3); console is refused in production."""
    if settings.MESSAGING_PROVIDER == "whatsapp_cloud":
        return WhatsAppCloudAdapter(
            phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
            access_token=settings.WHATSAPP_ACCESS_TOKEN.get_secret_value(),
            api_version=settings.WHATSAPP_API_VERSION,
            graph_url=settings.WHATSAPP_GRAPH_URL,
        )
    if settings.APP_ENV is AppEnv.PRODUCTION:
        raise ValueError("MESSAGING_PROVIDER=console sends nothing; refused in production")
    return ConsoleMessagingAdapter()


def build_email(settings: AppSettings) -> EmailPort:
    """The email adapter (M6a-P4, ADR-0016); the console sends nothing, refused in production."""
    if settings.EMAIL_PROVIDER == "smtp":
        return SmtpEmailAdapter(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            security=settings.SMTP_SECURITY,
            sender=settings.EMAIL_FROM,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD.get_secret_value(),
        )
    if settings.APP_ENV is AppEnv.PRODUCTION:
        raise ValueError("EMAIL_PROVIDER=console sends nothing; refused in production")
    return ConsoleEmailAdapter()


def build_sms(settings: AppSettings) -> MessagingPort | None:
    """The SMS fallback's provider, or None while ``MESSAGING_SMS_FALLBACK_ENABLED`` is off (M5-P5).

    Only the console exists until L-03; it is refused in production, so the fallback cannot be
    turned on there and silently send nothing.
    """
    if not settings.MESSAGING_SMS_FALLBACK_ENABLED:
        return None
    if settings.APP_ENV is AppEnv.PRODUCTION:
        raise ValueError("SMS_PROVIDER=console sends nothing; the SMS fallback is refused")
    return ConsoleSmsAdapter()


def _messaging_handlers(
    settings: AppSettings,
    factory: sessionmaker[Session],
    clock: ClockPort,
    ids: IdPort,
) -> dict[str, JobHandler]:
    """The M5-P2 send jobs. Templates are loaded and checked here, so a bad file stops start-up."""
    messaging = build_messaging(settings)
    phones = FernetPhoneCipher(settings.messaging_phone_keys())
    templates = YamlTemplateCatalog.from_package()
    prices = load_price_table()
    sender = MessageSender(
        uow=SqlAlchemyUnitOfWork(factory),
        clock=clock,
        ids=ids,
        messaging=messaging,
        templates=templates,
        phones=phones,
        prices=prices,
    )
    sms = build_sms(settings)
    sms_sender = (
        MessageSender(
            uow=SqlAlchemyUnitOfWork(factory),
            clock=clock,
            ids=ids,
            messaging=sms,
            templates=templates,
            phones=phones,
            prices=prices,
        )
        if sms is not None
        else None
    )
    fallback = SmsFallback(ids=ids) if sms is not None else None
    return {
        WEBHOOK_KIND: ProcessWebhookEvent(
            uow=SqlAlchemyUnitOfWork(factory),
            clock=clock,
            parser=WhatsAppWebhookParser(phones),
            opt_outs=OptOutByReply(ids=ids, phones=phones),
            fallback=fallback,
            prices=prices,
            ids=ids,
        ),
        OPT_OUT_CONFIRMATION_KIND: SendOptOutConfirmation(sender=sender),
        SMS_FALLBACK_KIND: SendSmsFallback(sender=sms_sender, ids=ids),
        RECONCILE_KIND: ReconcileMessages(uow=SqlAlchemyUnitOfWork(factory), clock=clock, ids=ids),
        REMINDER_KIND: SendReminder(sender=sender, ids=ids, fallback=fallback),
        NO_SHOW_SWEEP_KIND: SweepNoShows(uow=SqlAlchemyUnitOfWork(factory), clock=clock, ids=ids),
        MARK_NO_SHOWS_KIND: MarkNoShows(uow=SqlAlchemyUnitOfWork(factory), clock=clock, ids=ids),
        BOOKING_CONFIRMATION_KIND: SendBookingConfirmation(sender=sender),
        # M6a-P8 (decision 7A): a visit the clinic cancelled.
        CANCELLATION_NOTICE_KIND: SendCancellationNotice(sender=sender),
        RX_LINK_KIND: SendRxLink(
            sender=sender,
            ids=ids,
            tokens=LinkTokens(HmacLinkSigner(settings.patient_link_keys())),
            public_base_url=settings.PUBLIC_BASE_URL,
            window=timedelta(hours=settings.RX_LINK_SEND_WINDOW_HOURS),
        ),
    }


def build_worker(settings: AppSettings, stop: threading.Event) -> Worker:
    """Compose the background worker (M5-P1): the same adapters as the API, no HTTP.

    ``stop`` is set by the process's signal handlers; the loop finishes the job in hand and exits.
    """
    configure_logging(settings)
    factory = build_session_factory(build_engine(settings))
    clock = SystemClock()
    ids = Uuid7Generator()
    store = SqlAlchemyJobStore(factory)
    # Jitter only spreads retries out; it needs no cryptographic randomness.
    rand = random.SystemRandom().random
    email = build_email(settings)
    handlers: dict[str, JobHandler] = {
        PURGE_KIND: PurgeExpired(uow=SqlAlchemyUnitOfWork(factory), clock=clock, ids=ids),
        AUTH_EMAIL_KIND: SendAuthEmail(
            uow=SqlAlchemyUnitOfWork(factory),
            clock=clock,
            ids=ids,
            secrets=Sha256RefreshTokenSecrets(),
            email=email,
            public_base_url=settings.PUBLIC_BASE_URL,
        ),
        # M6a-P5: an owner's emailed staff invitation (the same secret adapter as the API's).
        STAFF_INVITE_KIND: SendStaffInvite(
            uow=SqlAlchemyUnitOfWork(factory),
            clock=clock,
            secrets=Sha256RefreshTokenSecrets(),
            email=email,
            public_base_url=settings.PUBLIC_BASE_URL,
        ),
        **_messaging_handlers(settings, factory, clock, ids),
    }
    return Worker(
        worker_id=f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(3)}",
        store=store,
        run_job=RunJob(
            store=store,
            handlers=handlers,
            uow=SqlAlchemyUnitOfWork(factory),
            clock=clock,
            rand=rand,
        ),
        schedule=ScheduleRecurring(uow=SqlAlchemyUnitOfWork(factory), clock=clock, ids=ids),
        clock=clock,
        rand=rand,
        request_id=lambda: str(ULID()),
        beat=beat,
        sleep=_interruptible_sleep(stop),
        stopping=stop.is_set,
        batch_size=settings.WORKER_BATCH_SIZE,
        poll_seconds=settings.WORKER_POLL_SECONDS,
        renewer=LockRenewer(store, clock).hold,
    )


def create_app(
    settings: AppSettings,
    *,
    database_check: DatabaseCheck | None = None,
    password_hasher: PasswordHasher | None = None,
    clock: ClockPort | None = None,
    pdf_renderer: PdfRendererPort | None = None,
    blob_storage: BlobStoragePort | None = None,
    oidc: OidcPort | None = None,
) -> Flask:
    """Build and wire the Flask application from validated settings.

    The keyword arguments replace adapters in tests: a fake readiness check, a
    cheap password hasher, a fixed clock, a counting PDF renderer, another store
    or another OpenID Connect provider.
    Building the engine opens no connection, so this stays side-effect free.
    """
    configure_logging(settings)

    engine = build_engine(settings)
    if database_check is None:
        database_check = SqlAlchemyDatabaseCheck(engine)

    clock = clock or SystemClock()
    ids = Uuid7Generator()
    hasher = password_hasher or build_password_hasher()
    refresh_secrets = Sha256RefreshTokenSecrets()
    signing_key = settings.JWT_SIGNING_KEY.get_secret_value()
    access_ttl = timedelta(seconds=settings.ACCESS_TOKEN_TTL_SECONDS)
    refresh_ttl = timedelta(seconds=settings.REFRESH_TOKEN_TTL_SECONDS)
    access_tokens = JwtAccessTokenIssuer(signing_key=signing_key, ttl=access_ttl, ids=ids)
    # ADR-0015 decision 2: the same key, another audience; each verifier refuses the other's.
    portal_access_tokens = JwtAccessTokenIssuer(
        signing_key=signing_key, ttl=access_ttl, ids=ids, audience=PORTAL_AUDIENCE
    )
    use_cases = _UseCases(
        session_factory=build_session_factory(engine),
        clock=clock,
        ids=ids,
        hasher=hasher,
        refresh_secrets=refresh_secrets,
        invite_secrets=refresh_secrets,
        access_tokens=access_tokens,
        sessions=SessionIssuer(
            ids=ids,
            secrets=refresh_secrets,
            access_tokens=access_tokens,
            refresh_ttl=refresh_ttl,
        ),
        # One real hash of a random password, so unknown accounts cost the
        # same verification as real ones (spec R2).
        dummy_password_hash=hasher.hash(secrets.token_urlsafe(32)),
        pdf_renderer=pdf_renderer or WeasyPrintRenderer(),
        blob_storage=blob_storage or build_blob_storage(settings),
        link_tokens=LinkTokens(HmacLinkSigner(settings.patient_link_keys())),
        link_ttl_days=settings.PATIENT_LINK_TTL_DAYS,
        portal_access_tokens=portal_access_tokens,
        patient_sessions=PatientSessionIssuer(
            ids=ids,
            secrets=refresh_secrets,
            access_tokens=portal_access_tokens,
            refresh_ttl=refresh_ttl,
        ),
        oidc=oidc or build_oidc(settings),
        flow_sealer=JwtFlowSealer(signing_key=signing_key),
        google_redirect_uri=f"{settings.PUBLIC_BASE_URL}{GOOGLE_CALLBACK_PATH}",
        whatsapp_app_secret=settings.WHATSAPP_APP_SECRET.get_secret_value(),
        whatsapp_verify_token=settings.WHATSAPP_VERIFY_TOKEN.get_secret_value(),
        phones=FernetPhoneCipher(settings.messaging_phone_keys()),
    )

    # static_folder=None: the API serves JSON only, so there is no static route
    # to exempt from the access policy check below.
    app = Flask(__name__, static_folder=None)
    # Keep the validated settings on the app for handlers that need them later.
    app.config["SETTINGS"] = settings

    # Order matters: request context is bound first, then the request's ID and
    # IP fingerprint, then CSRF is checked (it costs no database call), then
    # each route's access policy decides who may continue; error handlers wrap
    # everything so failures still carry the request_id.
    register_request_middleware(app)
    register_request_info(app, HmacIpHasher(settings.AUDIT_IP_SALT.get_secret_value()))
    register_csrf_protection(app)
    register_access_control(app, use_cases)
    register_error_handlers(app)
    app.register_blueprint(create_platform_blueprint(database_check))
    app.register_blueprint(create_auth_blueprint(use_cases, cookie_secure=settings.COOKIE_SECURE))
    app.register_blueprint(create_google_blueprint(use_cases, cookie_secure=settings.COOKIE_SECURE))
    app.register_blueprint(create_portal_blueprint(use_cases, cookie_secure=settings.COOKIE_SECURE))
    app.register_blueprint(create_invite_blueprint(use_cases, cookie_secure=settings.COOKIE_SECURE))
    app.register_blueprint(create_me_blueprint())
    app.register_blueprint(
        create_clinic_blueprint(use_cases, public_base_url=settings.PUBLIC_BASE_URL)
    )
    app.register_blueprint(
        create_ops_blueprint(use_cases, public_base_url=settings.PUBLIC_BASE_URL)
    )
    app.register_blueprint(create_patients_blueprint(use_cases))
    app.register_blueprint(
        create_patient_portal_blueprint(use_cases, public_base_url=settings.PUBLIC_BASE_URL)
    )
    app.register_blueprint(create_portal_records_blueprint(use_cases))
    app.register_blueprint(create_my_patients_blueprint(use_cases))
    app.register_blueprint(create_scheduling_blueprint(use_cases))
    app.register_blueprint(create_appointments_blueprint(use_cases))
    app.register_blueprint(create_visits_blueprint(use_cases))
    app.register_blueprint(
        create_prescriptions_blueprint(use_cases, public_base_url=settings.PUBLIC_BASE_URL)
    )
    app.register_blueprint(create_public_links_blueprint(use_cases))
    app.register_blueprint(create_rx_library_blueprint(use_cases))
    app.register_blueprint(create_whatsapp_webhook_blueprint(use_cases))
    app.register_blueprint(create_reminders_blueprint(use_cases))
    app.register_blueprint(create_dashboard_blueprint(use_cases))
    app.register_blueprint(create_notifications_blueprint(use_cases))
    app.register_blueprint(create_audit_log_blueprint(use_cases))
    # Default deny: refuse to start with an undeclared route (spec R6-R10).
    check_every_route_has_policy(app)

    logger.info("app.created", app_env=settings.APP_ENV.value)
    return app
