"""Booking confirmations (FR-APT-06; appointments spec D16; M5-P2 decision 6A).

Enqueued with the booking or the reschedule, in its transaction, when the patient allows WhatsApp
at that moment. At send time the appointment must still be booked and not over, and consent is
read again (R5).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from mediease_api.application.messaging.sender import MessageSender, Send, Skip
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.jobs.job import ClaimedJob, NewJob
from mediease_api.domain.messaging.errors import MSG_NO_CONSENT, MSG_NOT_APPLICABLE
from mediease_api.domain.messaging.formatting import appointment_when
from mediease_api.domain.messaging.jobs import (
    BOOKING_CONFIRMATION_KIND,
    BOOKING_CONFIRMED,
    booking_confirmation_key,
)
from mediease_api.domain.messaging.message import SourceType
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork


def enqueue_booking_confirmation(
    uow: UnitOfWork,
    *,
    ids: IdPort,
    appointment: Appointment,
    patient: Patient,
    request_id: str | None,
    now: datetime,
) -> bool:
    """In the booking's transaction (the outbox); nothing for a patient who cannot be messaged."""
    if not patient.may_receive_whatsapp:
        return False
    return uow.jobs.enqueue(
        NewJob.create(
            id=ids.new_id(),
            kind=BOOKING_CONFIRMATION_KIND,
            now=now,
            clinic_id=appointment.clinic_id,
            payload={"appointment_id": str(appointment.id)},
            request_id=request_id,
            dedupe_key=booking_confirmation_key(appointment.id),
        )
    )


class SendBookingConfirmation:
    def __init__(self, *, sender: MessageSender) -> None:
        self._sender = sender

    def __call__(self, job: ClaimedJob) -> None:
        appointment_id = UUID(str(job.payload["appointment_id"]))

        def plan(uow: UnitOfWork, tenant: TenantRepositories, now: datetime) -> Send | Skip:
            appointment = tenant.appointments.get(appointment_id)
            if appointment is None or appointment.status is not AppointmentStatus.BOOKED:
                return Skip("not_booked", MSG_NOT_APPLICABLE)
            session = tenant.sessions.get(appointment.session_id)
            if session is None or session.ends_at <= now:
                return Skip("session_over", MSG_NOT_APPLICABLE)
            patient = tenant.patients.get(appointment.patient_id)
            if patient is None or not patient.may_receive_whatsapp:
                return Skip("no_consent", MSG_NO_CONSENT)
            clinic = uow.clinics.get(tenant.clinic_id)
            doctor = tenant.doctors.get(appointment.doctor_id)
            assert clinic is not None and doctor is not None  # foreign keys keep them
            tokens = session.mode is BookingMode.TOKENS
            when = appointment_when(
                starts_at=appointment.slot_start or session.starts_at,
                token_number=appointment.token_number if tokens else None,
                timezone=clinic.timezone,
                language=patient.language,
            )
            return Send(
                patient=patient,
                template_key=BOOKING_CONFIRMED,
                variables={
                    "clinic_name": clinic.name,
                    "doctor_name": doctor.display_name,
                    "date_time_or_token": when,
                },
                source_type=SourceType.APPOINTMENT,
                source_id=appointment.id,
            )

        self._sender.send(job, key=booking_confirmation_key(appointment_id), plan=plan)
