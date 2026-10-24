"""The SMS fallback for reminders (M5-P5; FR-REM-06; decision 4A).

Off unless ``MESSAGING_SMS_FALLBACK_ENABLED``. When on, a reminder's WhatsApp message that ends
``FAILED`` with a definite non-delivery (``domain/messaging/sms.py``) — either when the send fails
or when a webhook later reports the failure — enqueues one ``send_sms_fallback`` job, in the
transaction that records the failure. The job, at send time:

- does nothing unless the reminder is still ``SENT`` and its WhatsApp message still failed so;
- inside the quiet hours, enqueues a fresh job for the next 08:00 (as P4 decision 2A);
- without SMS consent (or opted out), sends nothing (``MSG_NO_CONSENT``);
- otherwise sends ``follow_up_due``'s SMS wording as a second message row on channel ``SMS``,
  keyed ``sms:<reminder_id>``: at most one SMS per reminder. The reminder then shows that
  message's status (P4 decision 3A: its latest message).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.messaging.sender import MessageSender, Send, Skip
from mediease_api.application.reminders.appointment import (
    appointment_variables,
    still_applies,
    visit_start,
)
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.jobs.job import ClaimedJob, NewJob
from mediease_api.domain.messaging.errors import MSG_NO_CONSENT, MSG_NOT_APPLICABLE
from mediease_api.domain.messaging.formatting import follow_up_date_text
from mediease_api.domain.messaging.jobs import (
    APPOINTMENT_REMINDER,
    FOLLOW_UP_DUE,
    SMS_FALLBACK_KIND,
    reminder_message_key,
    sms_fallback_job_key,
    sms_fallback_key,
)
from mediease_api.domain.messaging.message import Message, SourceType
from mediease_api.domain.messaging.sms import falls_back_to_sms
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.reminders.errors import REM_CLINIC_PHONE_MISSING
from mediease_api.domain.reminders.reminder import Reminder, ReminderStatus
from mediease_api.domain.reminders.rules import in_quiet_hours, outside_quiet_hours
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

MSG_QUIET_HOURS_DEFERRED = "MSG_QUIET_HOURS_DEFERRED"


def follow_up_variables(
    clinic: Clinic, doctor: Doctor, reminder: Reminder, patient: Patient
) -> dict[str, str]:
    """``follow_up_due``'s values; the caller has checked the clinic has a phone (6A)."""
    assert clinic.phone is not None
    return {
        "clinic_name": clinic.name,
        "doctor_name": doctor.display_name,
        "follow_up_date": follow_up_date_text(reminder.follow_up_date, patient.language),
        "clinic_phone": clinic.phone.e164,
    }


def _job(
    ids: IdPort,
    clinic_id: UUID,
    reminder_id: UUID,
    *,
    deferrals: int,
    request_id: str | None,
    now: datetime,
    run_at: datetime | None = None,
) -> NewJob:
    return NewJob.create(
        id=ids.new_id(),
        kind=SMS_FALLBACK_KIND,
        now=now,
        clinic_id=clinic_id,
        payload={"reminder_id": str(reminder_id), "deferrals": deferrals},
        run_at=run_at,
        request_id=request_id,
        dedupe_key=sms_fallback_job_key(reminder_id, deferrals),
    )


class SmsFallback:
    """Enqueues the fallback for a failed reminder message; built only when the flag is on."""

    def __init__(self, *, ids: IdPort) -> None:
        self._ids = ids

    def enqueue(
        self, uow: UnitOfWork, message: Message, *, request_id: str | None, now: datetime
    ) -> bool:
        if not falls_back_to_sms(message):
            return False
        added = uow.jobs.enqueue(
            _job(
                self._ids,
                message.clinic_id,
                message.source_id,
                deferrals=0,
                request_id=request_id,
                now=now,
            )
        )
        if added:
            logger.info(
                "reminder.sms_fallback_enqueued",
                reminder_id=str(message.source_id),
                error_code=message.error_code,
            )
        return added


class SendSmsFallback:
    """The ``send_sms_fallback`` job. ``sender`` is the SMS sender; None while the flag is off."""

    def __init__(self, *, sender: MessageSender | None, ids: IdPort) -> None:
        self._sender = sender
        self._ids = ids

    def __call__(self, job: ClaimedJob) -> None:
        reminder_id = UUID(str(job.payload["reminder_id"]))
        deferrals = int(str(job.payload.get("deferrals", 0)))
        if self._sender is None:
            # Enqueued while the flag was on, run after it was turned off.
            logger.info("reminder.sms_fallback_disabled", reminder_id=str(reminder_id))
            return

        def plan(uow: UnitOfWork, tenant: TenantRepositories, now: datetime) -> Send | Skip:
            reminder = tenant.reminders.get(reminder_id, for_update=True)
            if reminder is None or reminder.status is not ReminderStatus.SENT:
                return Skip("not_current", MSG_NOT_APPLICABLE)
            first = tenant.messages.get_by_key(reminder_message_key(reminder_id))
            if first is None or not falls_back_to_sms(first):
                return Skip("not_failed", MSG_NOT_APPLICABLE)
            clinic = uow.clinics.get(tenant.clinic_id)
            assert clinic is not None
            if in_quiet_hours(now, clinic.timezone):
                uow.jobs.enqueue(
                    _job(
                        self._ids,
                        tenant.clinic_id,
                        reminder_id,
                        deferrals=deferrals + 1,
                        request_id=job.request_id,
                        now=now,
                        run_at=outside_quiet_hours(now, clinic.timezone),
                    )
                )
                logger.info(
                    "reminder.sms_fallback_deferred",
                    reminder_id=str(reminder_id),
                    code=MSG_QUIET_HOURS_DEFERRED,
                )
                return Skip("quiet_hours", MSG_QUIET_HOURS_DEFERRED, close=False)
            patient = tenant.patients.get(reminder.patient_id)
            assert patient is not None
            if not patient.may_receive_sms:
                logger.info("reminder.sms_fallback_no_consent", reminder_id=str(reminder_id))
                return Skip("no_consent", MSG_NO_CONSENT)
            if clinic.phone is None:
                return Skip("clinic_phone_missing", REM_CLINIC_PHONE_MISSING)
            doctor = tenant.doctors.get(reminder.doctor_id)
            assert doctor is not None
            if reminder.follows_appointment:
                # M6a-P8: the SMS of an appointment reminder, only while the visit still stands.
                assert reminder.appointment_id is not None
                appointment = tenant.appointments.get(reminder.appointment_id)
                session = tenant.sessions.get(appointment.session_id) if appointment else None
                if not still_applies(appointment, session):
                    return Skip("appointment_changed", MSG_NOT_APPLICABLE)
                assert appointment is not None and session is not None
                if now >= visit_start(appointment, session):
                    return Skip("too_late", MSG_NOT_APPLICABLE)
                return Send(
                    patient=patient,
                    template_key=APPOINTMENT_REMINDER,
                    variables=appointment_variables(clinic, doctor, appointment, session, patient),
                    source_type=SourceType.REMINDER,
                    source_id=reminder.id,
                )
            return Send(
                patient=patient,
                template_key=FOLLOW_UP_DUE,
                variables=follow_up_variables(clinic, doctor, reminder, patient),
                source_type=SourceType.REMINDER,
                source_id=reminder.id,
            )

        self._sender.send(job, key=sms_fallback_key(reminder_id), plan=plan)
