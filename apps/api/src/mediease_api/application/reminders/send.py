"""Send a follow-up reminder (spec R4, R5; FR-REM-01, 04; M5-P4 decisions 1A, 2A, 3A, 6A).

The job names the reminder and the revision it was made for. At send time, in the sender's first
transaction:

- a newer revision, or a reminder no longer ``SCHEDULED`` / ``SENT`` (cancelled, skipped): nothing;
- inside the quiet hours (R4): the reminder is deferred to the next 08:00 under a new revision and
  a fresh job is enqueued for it (2A); this job succeeds (``MSG_QUIET_HOURS_DEFERRED``);
- no consent (R5): ``SKIPPED_NO_CONSENT``, no message row;
- no clinic phone (6A): ``FAILED`` with ``REM_CLINIC_PHONE_MISSING``;
- otherwise ``follow_up_due`` with the clinic name, doctor, date and the clinic's phone; the
  reminder becomes ``SENT`` with the message row, and from then on shows the message's status (3A);
- M5-P5: a final failure that WhatsApp could not deliver enqueues the SMS fallback when it is on
  (``fallback.py``; FR-REM-06).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.messaging.sender import MessageSender, Send, Skip
from mediease_api.application.reminders.fallback import (
    MSG_QUIET_HOURS_DEFERRED,
    SmsFallback,
    follow_up_variables,
)
from mediease_api.application.reminders.scheduling import enqueue_send
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.messaging.errors import MSG_NO_CONSENT, MSG_NOT_APPLICABLE
from mediease_api.domain.messaging.jobs import FOLLOW_UP_DUE, reminder_message_key
from mediease_api.domain.messaging.message import Message, SourceType
from mediease_api.domain.reminders.errors import REM_CLINIC_PHONE_MISSING
from mediease_api.domain.reminders.reminder import ReminderStatus
from mediease_api.domain.reminders.rules import in_quiet_hours, outside_quiet_hours
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

__all__ = ["MSG_QUIET_HOURS_DEFERRED", "SendReminder"]


class SendReminder:
    def __init__(
        self, *, sender: MessageSender, ids: IdPort, fallback: SmsFallback | None = None
    ) -> None:
        self._sender = sender
        self._ids = ids
        self._fallback = fallback

    def __call__(self, job: ClaimedJob) -> None:
        reminder_id = UUID(str(job.payload["reminder_id"]))
        revision = int(str(job.payload["revision"]))

        def plan(uow: UnitOfWork, tenant: TenantRepositories, now: datetime) -> Send | Skip:
            reminder = tenant.reminders.get(reminder_id, for_update=True)
            live = (ReminderStatus.SCHEDULED, ReminderStatus.SENT)
            if reminder is None or reminder.status not in live or reminder.revision != revision:
                return Skip("not_current", MSG_NOT_APPLICABLE)
            clinic = uow.clinics.get(tenant.clinic_id)
            assert clinic is not None
            if reminder.is_scheduled and in_quiet_hours(now, clinic.timezone):
                reminder.defer(outside_quiet_hours(now, clinic.timezone), now)
                tenant.reminders.update(reminder)
                enqueue_send(
                    uow, ids=self._ids, reminder=reminder, request_id=job.request_id, now=now
                )
                logger.info(
                    "reminder.deferred",
                    reminder_id=str(reminder.id),
                    code=MSG_QUIET_HOURS_DEFERRED,
                    due_at=reminder.due_at.isoformat(),
                )
                return Skip("quiet_hours", MSG_QUIET_HOURS_DEFERRED, close=False)
            patient = tenant.patients.get(reminder.patient_id)
            assert patient is not None
            if not patient.may_receive_whatsapp:
                if reminder.is_scheduled:
                    reminder.skipped_no_consent(now)
                    tenant.reminders.update(reminder)
                logger.info("reminder.skipped_no_consent", reminder_id=str(reminder.id))
                return Skip("no_consent", MSG_NO_CONSENT)
            if clinic.phone is None:
                if reminder.is_scheduled:
                    reminder.failed(REM_CLINIC_PHONE_MISSING, now)
                    tenant.reminders.update(reminder)
                logger.warning(
                    "reminder.failed",
                    reminder_id=str(reminder.id),
                    error_code=REM_CLINIC_PHONE_MISSING,
                )
                return Skip("clinic_phone_missing", REM_CLINIC_PHONE_MISSING)
            doctor = tenant.doctors.get(reminder.doctor_id)
            assert doctor is not None
            reminder.handed_off(now)
            tenant.reminders.update(reminder)
            return Send(
                patient=patient,
                template_key=FOLLOW_UP_DUE,
                variables=follow_up_variables(clinic, doctor, reminder, patient),
                source_type=SourceType.REMINDER,
                source_id=reminder.id,
            )

        after_failed = None
        if self._fallback is not None:
            fallback = self._fallback

            def after_failed(
                uow: UnitOfWork, tenant: TenantRepositories, message: Message, now: datetime
            ) -> None:
                fallback.enqueue(uow, message, request_id=job.request_id, now=now)

        self._sender.send(
            job, key=reminder_message_key(reminder_id), plan=plan, after_failed=after_failed
        )
