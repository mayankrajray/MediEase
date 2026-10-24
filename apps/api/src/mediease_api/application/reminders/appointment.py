"""Appointment reminders (M6a-P8; FR-APT-08; decisions 1A, 2A, 4A, 5A).

Scheduled and cancelled by the notification service, in the transaction of the booking, the
reschedule or the cancellation that raised the event; each is a ``reminders`` row with its own
send job, like a follow-up. A walk-in gets none, nor does a patient who cannot be messaged on
WhatsApp at booking time (the send job reads consent again). Each change is audited as SYSTEM.

At send time (``send.py``) the reminder applies only while its appointment is ``BOOKED`` in an
``OPEN`` session and the visit has not started; otherwise the system cancels it
(``REM_APPOINTMENT_CHANGED`` or ``REM_TOO_LATE``).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.reminders.scheduling import audit, enqueue_send
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.status import AppointmentSource, AppointmentStatus
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.messaging.formatting import appointment_when
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.reminders.reminder import Reminder
from mediease_api.domain.reminders.rules import appointment_reminder_times
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)


def visit_start(appointment: Appointment, session: Session) -> datetime:
    """The slot's start, or the session's in token mode."""
    return appointment.slot_start or session.starts_at


def schedule_appointment_reminders(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    *,
    ids: IdPort,
    clinic: Clinic,
    appointment: Appointment,
    session: Session,
    patient: Patient,
    created_by: UUID | None,
    request_id: str | None,
    now: datetime,
) -> list[Reminder]:
    if appointment.source is AppointmentSource.WALK_IN or not patient.may_receive_whatsapp:
        return []
    times = appointment_reminder_times(
        starts_at=visit_start(appointment, session),
        timezone=clinic.timezone,
        now=now,
        evening_before=clinic.reminder_evening_before,
        hours_before=clinic.reminder_hours_before,
    )
    made = []
    for due_at in times:
        reminder = Reminder.for_appointment(
            id=ids.new_id(),
            clinic_id=tenant.clinic_id,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            appointment_id=appointment.id,
            visit_date=session.on_date,
            due_at=due_at,
            created_by=created_by,
            now=now,
        )
        tenant.reminders.add(reminder)
        enqueue_send(uow, ids=ids, reminder=reminder, request_id=request_id, now=now)
        audit(
            uow,
            ids=ids,
            action=AuditAction.REMINDER_SCHEDULED,
            reminder=reminder,
            user_id=None,
            request_id=request_id,
            now=now,
        )
        made.append(reminder)
    if made:
        logger.info(
            "reminder.scheduled",
            source="APPOINTMENT",
            appointment_id=str(appointment.id),
            count=len(made),
        )
    return made


def cancel_appointment_reminders(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    *,
    ids: IdPort,
    appointment_id: UUID,
    request_id: str | None,
    now: datetime,
    code: str | None = None,
) -> int:
    """The appointment's reminders still to go are cancelled by the system; returns how many."""
    cancelled = 0
    for reminder in tenant.reminders.scheduled_for_appointment(appointment_id):
        cancel_reminder(
            uow, tenant, ids=ids, reminder=reminder, request_id=request_id, now=now, code=code
        )
        cancelled += 1
    return cancelled


def cancel_reminder(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    *,
    ids: IdPort,
    reminder: Reminder,
    request_id: str | None,
    now: datetime,
    code: str | None,
) -> None:
    reminder.cancel(by=None, now=now, code=code)
    tenant.reminders.update(reminder)
    audit(
        uow,
        ids=ids,
        action=AuditAction.REMINDER_CANCELLED,
        reminder=reminder,
        user_id=None,
        request_id=request_id,
        now=now,
    )
    logger.info("reminder.cancelled", reminder_id=str(reminder.id), reason=code or "appointment")


def still_applies(appointment: Appointment | None, session: Session | None) -> bool:
    """Decision 4A: booked, in a session that still exists as planned."""
    return (
        appointment is not None
        and appointment.status is AppointmentStatus.BOOKED
        and session is not None
        and session.is_open
    )


def appointment_variables(
    clinic: Clinic,
    doctor: Doctor,
    appointment: Appointment,
    session: Session,
    patient: Patient,
) -> dict[str, str]:
    """``appointment_reminder``'s and ``appointment_cancelled``'s values (decisions 5A, 7A).

    The caller has checked that the clinic has a phone.
    """
    assert clinic.phone is not None
    tokens = session.mode is BookingMode.TOKENS
    return {
        "clinic_name": clinic.name,
        "doctor_name": doctor.display_name,
        "date_time_or_token": appointment_when(
            starts_at=visit_start(appointment, session),
            token_number=appointment.token_number if tokens else None,
            timezone=clinic.timezone,
            language=patient.language,
        ),
        "clinic_phone": clinic.phone.e164,
    }
