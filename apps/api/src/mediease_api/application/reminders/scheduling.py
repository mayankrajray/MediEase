"""Scheduling a reminder's send job, and keeping a prescription's reminder in step (R1, R2).

Every move enqueues a new ``send_reminder`` job for the new revision, in the change's own
transaction (the outbox); the job of an older revision finds the reminder moved on and does
nothing (decision 1A).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

import structlog

from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.jobs.job import NewJob
from mediease_api.domain.messaging.jobs import REMINDER_KIND, reminder_job_key
from mediease_api.domain.prescriptions.prescription import Prescription
from mediease_api.domain.reminders.reminder import Reminder, ReminderSource
from mediease_api.domain.reminders.rules import follow_up_due_at
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "reminder"


def enqueue_send(
    uow: UnitOfWork, *, ids: IdPort, reminder: Reminder, request_id: str | None, now: datetime
) -> None:
    uow.jobs.enqueue(
        NewJob.create(
            id=ids.new_id(),
            kind=REMINDER_KIND,
            now=now,
            clinic_id=reminder.clinic_id,
            payload={"reminder_id": str(reminder.id), "revision": reminder.revision},
            run_at=max(reminder.due_at, now),
            request_id=request_id,
            dedupe_key=reminder_job_key(reminder.id, reminder.revision),
        )
    )


def reminder_metadata(reminder: Reminder) -> dict[str, str]:
    """IDs, the source, the date and the revision: nothing clinical."""
    return {
        "patient_id": str(reminder.patient_id),
        "doctor_id": str(reminder.doctor_id),
        "source": reminder.source.value,
        "follow_up_date": reminder.follow_up_date.isoformat(),
        "revision": str(reminder.revision),
    }


def audit(
    uow: UnitOfWork,
    *,
    ids: IdPort,
    action: AuditAction,
    reminder: Reminder,
    user_id: UUID | None,
    request_id: str | None,
    now: datetime,
) -> None:
    uow.audit.record(
        AuditEvent.record(
            id=ids.new_id(),
            action=action,
            actor_type=ActorType.STAFF if user_id else ActorType.SYSTEM,
            actor_user_id=user_id,
            clinic_id=reminder.clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=reminder.id,
            request_id=request_id,
            metadata=reminder_metadata(reminder),
            now=now,
        )
    )


def sync_prescription_reminder(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    *,
    ids: IdPort,
    rx: Prescription,
    chain_id: UUID,
    timezone: str,
    user_id: UUID,
    request_id: str | None,
    now: datetime,
) -> Reminder | None:
    """R1, R2: the chain's reminder follows the issued version's follow-up date.

    A new date moves the scheduled reminder (or creates one); no date cancels it. A reminder
    already sent for the same date is not repeated; a sent one is never changed.
    """
    scheduled = tenant.reminders.scheduled_for_chain(chain_id, for_update=True)
    follow_up: date | None = rx.follow_up_date
    if follow_up is None:
        if scheduled is not None:
            scheduled.cancel(by=user_id, now=now)
            tenant.reminders.update(scheduled)
            audit(
                uow,
                ids=ids,
                action=AuditAction.REMINDER_CANCELLED,
                reminder=scheduled,
                user_id=user_id,
                request_id=request_id,
                now=now,
            )
            logger.info("reminder.cancelled", reminder_id=str(scheduled.id), reason="revision")
        return None
    due = follow_up_due_at(follow_up, timezone, now)
    if scheduled is not None:
        if scheduled.follow_up_date == follow_up and scheduled.doctor_id == rx.doctor_id:
            return scheduled
        scheduled.move(follow_up_date=follow_up, due_at=due, now=now)
        tenant.reminders.update(scheduled)
        enqueue_send(uow, ids=ids, reminder=scheduled, request_id=request_id, now=now)
        audit(
            uow,
            ids=ids,
            action=AuditAction.REMINDER_RESCHEDULED,
            reminder=scheduled,
            user_id=user_id,
            request_id=request_id,
            now=now,
        )
        logger.info("reminder.rescheduled", reminder_id=str(scheduled.id))
        return scheduled
    if tenant.reminders.sent_for_chain(chain_id, follow_up):
        return None
    reminder = Reminder.schedule(
        id=ids.new_id(),
        clinic_id=rx.clinic_id,
        patient_id=rx.patient_id,
        doctor_id=rx.doctor_id,
        source=ReminderSource.PRESCRIPTION,
        source_id=chain_id,
        follow_up_date=follow_up,
        due_at=due,
        created_by=user_id,
        now=now,
    )
    tenant.reminders.add(reminder)
    enqueue_send(uow, ids=ids, reminder=reminder, request_id=request_id, now=now)
    audit(
        uow,
        ids=ids,
        action=AuditAction.REMINDER_SCHEDULED,
        reminder=reminder,
        user_id=user_id,
        request_id=request_id,
        now=now,
    )
    logger.info("reminder.scheduled", reminder_id=str(reminder.id), source="PRESCRIPTION")
    return reminder
