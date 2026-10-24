"""Telling a patient that the clinic cancelled their visit (M6a-P8; FR-APT-09; decision 7A).

Enqueued by the notification service in the cancellation's transaction when the reason is the
clinic's (``DOCTOR_UNAVAILABLE`` or ``CLINIC_REQUEST``) and the patient allows WhatsApp. Outside
the quiet hours: a cancellation at 22:00 is told at 08:00. At send time the appointment must still
be cancelled for that reason, consent is read again, and the clinic needs a phone (the message
asks the patient to call). At most one message per appointment (``appointment_cancelled:{id}``).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from mediease_api.application.messaging.sender import MessageSender, Send, Skip
from mediease_api.application.reminders.appointment import appointment_variables
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.status import AppointmentStatus, CancelReason
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.jobs.job import ClaimedJob, NewJob
from mediease_api.domain.messaging.errors import MSG_NO_CONSENT, MSG_NOT_APPLICABLE
from mediease_api.domain.messaging.jobs import (
    APPOINTMENT_CANCELLED,
    CANCELLATION_NOTICE_KIND,
    cancellation_notice_key,
)
from mediease_api.domain.messaging.message import SourceType
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.reminders.errors import REM_CLINIC_PHONE_MISSING
from mediease_api.domain.reminders.rules import outside_quiet_hours
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

# A patient who cancelled, a duplicate, OTHER and a reschedule are not told (decision 7A).
CLINIC_REASONS = frozenset({CancelReason.DOCTOR_UNAVAILABLE, CancelReason.CLINIC_REQUEST})


def enqueue_cancellation_notice(
    uow: UnitOfWork,
    *,
    ids: IdPort,
    clinic: Clinic,
    appointment: Appointment,
    patient: Patient,
    request_id: str | None,
    now: datetime,
) -> bool:
    if appointment.cancel_reason not in CLINIC_REASONS or not patient.may_receive_whatsapp:
        return False
    return uow.jobs.enqueue(
        NewJob.create(
            id=ids.new_id(),
            kind=CANCELLATION_NOTICE_KIND,
            now=now,
            clinic_id=appointment.clinic_id,
            payload={"appointment_id": str(appointment.id)},
            run_at=outside_quiet_hours(now, clinic.timezone),
            request_id=request_id,
            dedupe_key=cancellation_notice_key(appointment.id),
        )
    )


class SendCancellationNotice:
    def __init__(self, *, sender: MessageSender) -> None:
        self._sender = sender

    def __call__(self, job: ClaimedJob) -> None:
        appointment_id = UUID(str(job.payload["appointment_id"]))

        def plan(uow: UnitOfWork, tenant: TenantRepositories, now: datetime) -> Send | Skip:
            appointment = tenant.appointments.get(appointment_id)
            if (
                appointment is None
                or appointment.status is not AppointmentStatus.CANCELLED
                or appointment.cancel_reason not in CLINIC_REASONS
            ):
                return Skip("not_cancelled_by_clinic", MSG_NOT_APPLICABLE)
            patient = tenant.patients.get(appointment.patient_id)
            if patient is None or not patient.may_receive_whatsapp:
                return Skip("no_consent", MSG_NO_CONSENT)
            clinic = uow.clinics.get(tenant.clinic_id)
            session = tenant.sessions.get(appointment.session_id)
            doctor = tenant.doctors.get(appointment.doctor_id)
            assert clinic is not None and session is not None and doctor is not None
            if clinic.phone is None:
                return Skip("clinic_phone_missing", REM_CLINIC_PHONE_MISSING)
            return Send(
                patient=patient,
                template_key=APPOINTMENT_CANCELLED,
                variables=appointment_variables(clinic, doctor, appointment, session, patient),
                source_type=SourceType.APPOINTMENT,
                source_id=appointment.id,
            )

        self._sender.send(job, key=cancellation_notice_key(appointment_id), plan=plan)
