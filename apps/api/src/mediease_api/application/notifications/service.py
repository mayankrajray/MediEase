"""The notification service (M6a-P7, ADR-0017; FR-NTF-02..06).

``publish(uow, ...)`` is called by a feature in the transaction of its change. The service, in that
same transaction:

1. reads what the event is about (the appointment, the patient, the doctor);
2. decides the recipients and channels (decision 2A):

   - **in-app** for staff: rows in ``notifications``, unique per recipient and event key, so a
     replayed event adds nothing. The member who caused the change is not told about it, and a
     member who turned the kind off gets nothing (decision 5A);
   - **WhatsApp** for the patient: the existing M5 send jobs (booking confirmation, prescription
     link), enqueued with their own keys. Their handlers re-check consent and the facts when they
     send, exactly as before (decision 3A).

So an event exists exactly when the change commits, and no feature calls WhatsApp itself.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from uuid import UUID

import structlog

from mediease_api.application.messaging.booking import enqueue_booking_confirmation
from mediease_api.application.messaging.cancellation import enqueue_cancellation_notice
from mediease_api.application.messaging.rx_link import enqueue_rx_link
from mediease_api.application.reminders.appointment import (
    cancel_appointment_reminders,
    schedule_appointment_reminders,
)
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.identity.membership import MembershipStatus, Role
from mediease_api.domain.notifications.events import (
    AppointmentBooked,
    AppointmentCancelled,
    AppointmentRescheduled,
    BookingsToMove,
    Event,
    MessageFailed,
    PatientArrived,
    PrescriptionIssued,
    StaffJoined,
)
from mediease_api.domain.notifications.notification import (
    BOOKINGS_TO_MOVE_LINK,
    Channel,
    Notification,
    NotificationKind,
    PatientRef,
    PersonName,
    Place,
    RoleLabel,
    arrived_title,
    booked_title,
    bookings_to_move_title,
    cancelled_title,
    message_failed_title,
    queue_link,
    rescheduled_title,
    staff_joined_title,
)
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ROLE_WORDS = {Role.OWNER: "an owner", Role.DOCTOR: "a doctor", Role.FRONT_DESK: "front desk"}

Title = Callable[[PatientRef, Place], str]
AppointmentEvent = (
    AppointmentBooked | AppointmentRescheduled | AppointmentCancelled | PatientArrived
)


def publish(
    uow: UnitOfWork,
    event: Event,
    *,
    clinic_id: UUID,
    ids: IdPort,
    now: datetime,
    request_id: str | None = None,
    actor_user_id: UUID | None = None,
) -> int:
    """Dispatch ``event`` in the caller's open transaction; returns the in-app rows written."""
    return NotificationService(ids=ids).dispatch(
        uow,
        event,
        clinic_id=clinic_id,
        now=now,
        request_id=request_id,
        actor_user_id=actor_user_id,
    )


class NotificationService:
    def __init__(self, *, ids: IdPort) -> None:
        self._ids = ids

    def dispatch(
        self,
        uow: UnitOfWork,
        event: Event,
        *,
        clinic_id: UUID,
        now: datetime,
        request_id: str | None,
        actor_user_id: UUID | None,
    ) -> int:
        tenant = uow.tenant(clinic_id)
        appointment_events: dict[type, tuple[NotificationKind, Title, bool]] = {
            AppointmentBooked: (NotificationKind.APPOINTMENT_BOOKED, booked_title, True),
            AppointmentRescheduled: (
                NotificationKind.APPOINTMENT_RESCHEDULED,
                rescheduled_title,
                True,
            ),
            AppointmentCancelled: (NotificationKind.APPOINTMENT_CANCELLED, cancelled_title, False),
            PatientArrived: (NotificationKind.PATIENT_ARRIVED, arrived_title, False),
        }
        match event:
            case (
                AppointmentBooked()
                | AppointmentRescheduled()
                | AppointmentCancelled()
                | (PatientArrived())
            ):
                kind, title, confirm = appointment_events[type(event)]
                return self._appointment(
                    uow,
                    tenant,
                    event,
                    kind,
                    title,
                    confirm=confirm,
                    now=now,
                    request_id=request_id,
                    actor=actor_user_id,
                )
            case PrescriptionIssued(prescription_id=prescription_id):
                rx = tenant.prescriptions.get(prescription_id)
                if rx is not None:
                    enqueue_rx_link(uow, ids=self._ids, rx=rx, request_id=request_id, now=now)
                return 0
            case MessageFailed(message_id=message_id, patient_id=patient_id):
                patient = tenant.patients.get(patient_id)
                if patient is None:  # pragma: no cover - a foreign key keeps it
                    return 0
                return self._in_app(
                    tenant,
                    NotificationKind.MESSAGE_FAILED,
                    self._members(tenant, {Role.OWNER, Role.FRONT_DESK}),
                    event_key=f"message.failed:{message_id}",
                    title=message_failed_title(PatientRef.of(patient.full_name, patient.code)),
                    link=f"/patients/{patient.id}",
                    entity=("message", message_id),
                    now=now,
                    actor=actor_user_id,
                )
            case StaffJoined(membership_id=membership_id):
                membership = tenant.memberships.get(membership_id)
                user = uow.users.get(membership.user_id) if membership is not None else None
                if membership is None or user is None:  # pragma: no cover - foreign keys
                    return 0
                joined = membership.invite_accepted_at or now
                return self._in_app(
                    tenant,
                    NotificationKind.STAFF_JOINED,
                    [u for u in self._members(tenant, {Role.OWNER}) if u != user.id],
                    event_key=f"staff.joined:{membership.id}:{joined.isoformat()}",
                    title=staff_joined_title(
                        PersonName(user.full_name), RoleLabel(ROLE_WORDS[membership.role])
                    ),
                    link="/team",
                    entity=("clinic_membership", membership.id),
                    now=now,
                    actor=actor_user_id,
                )
            case BookingsToMove(doctor_id=doctor_id, change_id=change_id, on_date=on_date):
                return self._bookings_to_move(
                    uow, tenant, doctor_id, change_id, on_date, now=now, actor=actor_user_id
                )
        return 0  # pragma: no cover - every event is matched above

    # --- events about an appointment ------------------------------------------------------------

    def _appointment(
        self,
        uow: UnitOfWork,
        tenant: TenantRepositories,
        event: AppointmentEvent,
        kind: NotificationKind,
        title: Title,
        *,
        confirm: bool,
        now: datetime,
        request_id: str | None,
        actor: UUID | None,
    ) -> int:
        appointment = tenant.appointments.get(event.appointment_id)
        if appointment is None:  # pragma: no cover - published in the change's transaction
            return 0
        session = tenant.sessions.get(appointment.session_id)
        patient = tenant.patients.get(appointment.patient_id)
        doctor = tenant.doctors.get(appointment.doctor_id)
        clinic = uow.clinics.get(tenant.clinic_id)
        if session is None or patient is None or doctor is None or clinic is None:
            return 0  # pragma: no cover - foreign keys keep them
        if confirm:
            # WhatsApp channel (FR-APT-06, M5-P2): the same job and key as before P7.
            enqueue_booking_confirmation(
                uow,
                ids=self._ids,
                appointment=appointment,
                patient=patient,
                request_id=request_id,
                now=now,
            )
        self._reminders(
            uow,
            tenant,
            event,
            clinic=clinic,
            appointment=appointment,
            session=session,
            patient=patient,
            now=now,
            request_id=request_id,
            actor=actor,
        )
        place = Place.of(
            starts_at=appointment.slot_start or session.starts_at,
            token_number=appointment.token_number if session.mode is BookingMode.TOKENS else None,
            timezone=clinic.timezone,
        )
        return self._in_app(
            tenant,
            kind,
            self._doctor_user(tenant, doctor.user_id),
            event_key=_appointment_key(kind, appointment),
            title=title(PatientRef.of(patient.full_name, patient.code), place),
            link=queue_link(session.on_date),
            entity=("appointment", appointment.id),
            now=now,
            actor=actor,
        )

    def _reminders(
        self,
        uow: UnitOfWork,
        tenant: TenantRepositories,
        event: AppointmentEvent,
        *,
        clinic: Clinic,
        appointment: Appointment,
        session: Session,
        patient: Patient,
        now: datetime,
        request_id: str | None,
        actor: UUID | None,
    ) -> None:
        """M6a-P8: the patient's reminders follow the booking (4A); a clinic cancellation is told
        to the patient (7A)."""
        if isinstance(event, AppointmentRescheduled):
            cancel_appointment_reminders(
                uow,
                tenant,
                ids=self._ids,
                appointment_id=event.from_appointment_id,
                request_id=request_id,
                now=now,
            )
        if isinstance(event, AppointmentBooked | AppointmentRescheduled):
            schedule_appointment_reminders(
                uow,
                tenant,
                ids=self._ids,
                clinic=clinic,
                appointment=appointment,
                session=session,
                patient=patient,
                created_by=actor,
                request_id=request_id,
                now=now,
            )
        elif isinstance(event, AppointmentCancelled):
            cancel_appointment_reminders(
                uow,
                tenant,
                ids=self._ids,
                appointment_id=appointment.id,
                request_id=request_id,
                now=now,
            )
            enqueue_cancellation_notice(
                uow,
                ids=self._ids,
                clinic=clinic,
                appointment=appointment,
                patient=patient,
                request_id=request_id,
                now=now,
            )

    def _bookings_to_move(
        self,
        uow: UnitOfWork,
        tenant: TenantRepositories,
        doctor_id: UUID,
        change_id: UUID,
        on_date: date | None,
        *,
        now: datetime,
        actor: UUID | None,
    ) -> int:
        """M6a-P8 (FR-APT-09, decision 6A): the desk and the owners hear what needs moving."""
        clinic = uow.clinics.get(tenant.clinic_id)
        doctor = tenant.doctors.get(doctor_id)
        if clinic is None or doctor is None:  # pragma: no cover - foreign keys keep them
            return 0
        count = tenant.appointments.count_to_move(
            from_date=local_date(now, clinic.timezone), doctor_id=doctor_id
        )
        if count == 0:
            return 0
        return self._in_app(
            tenant,
            NotificationKind.BOOKINGS_TO_MOVE,
            self._members(tenant, {Role.OWNER, Role.FRONT_DESK}),
            event_key=f"{NotificationKind.BOOKINGS_TO_MOVE.value}:{change_id}",
            title=bookings_to_move_title(PersonName(doctor.display_name), count, on_date),
            link=BOOKINGS_TO_MOVE_LINK,
            entity=("doctor", doctor_id),
            now=now,
            actor=actor,
        )

    # --- recipients and the in-app channel ------------------------------------------------------

    @staticmethod
    def _members(tenant: TenantRepositories, roles: set[Role]) -> list[UUID]:
        return [
            m.user_id
            for m in tenant.memberships.list()
            if m.status is MembershipStatus.ACTIVE and m.role in roles
        ]

    @staticmethod
    def _doctor_user(tenant: TenantRepositories, user_id: UUID | None) -> list[UUID]:
        if user_id is None:
            return []
        membership = tenant.memberships.get_for_user(user_id)
        if membership is None or membership.status is not MembershipStatus.ACTIVE:
            return []
        return [user_id]

    def _in_app(
        self,
        tenant: TenantRepositories,
        kind: NotificationKind,
        recipients: Sequence[UUID],
        *,
        event_key: str,
        title: str,
        link: str,
        entity: tuple[str, UUID],
        now: datetime,
        actor: UUID | None,
    ) -> int:
        wanted = [u for u in dict.fromkeys(recipients) if u != actor]
        if not wanted:
            return 0
        off = tenant.notification_preferences.disabled_among(wanted, kind, Channel.IN_APP)
        rows = [
            Notification.create(
                id=self._ids.new_id(),
                clinic_id=tenant.clinic_id,
                recipient_user_id=user_id,
                kind=kind,
                event_key=event_key,
                title=title,
                link=link,
                entity_type=entity[0],
                entity_id=entity[1],
                now=now,
            )
            for user_id in wanted
            if user_id not in off
        ]
        written = tenant.notifications.add_many(rows)
        logger.info(
            "notification.dispatched",
            kind=kind.value,
            recipients=len(rows),
            written=written,
            muted=len(off),
        )
        return written


def _appointment_key(kind: NotificationKind, appointment: Appointment) -> str:
    return f"{kind.value}:{appointment.id}"
