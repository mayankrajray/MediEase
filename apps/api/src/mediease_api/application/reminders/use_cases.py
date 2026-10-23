"""Manual reminders and pending follow-ups (FR-REM-02, 07; spec R3, R17; M5-P4 decisions 5A, 6A).

Staff with ``REMINDERS_SCHEDULE`` (every role) schedule a follow-up reminder for a patient with a
doctor and a follow-up date; it is due like an automatic one (09:00 the day before, outside quiet
hours). Without consent: ``REM_NO_CONSENT``; a date not after today: ``REM_IN_PAST``; a clinic
with no phone: ``REM_CLINIC_PHONE_MISSING``. A scheduled reminder can be moved or cancelled;
anything else is ``REM_NOT_SCHEDULED``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import structlog

from mediease_api.application.context import RequestContext
from mediease_api.application.reminders.scheduling import audit, enqueue_send
from mediease_api.application.scheduling.schedules import load_clinic, load_doctor
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.messaging.message import Message
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.reminders.errors import ClinicPhoneMissing, InPast, NoConsent
from mediease_api.domain.reminders.reminder import Reminder, ReminderSource
from mediease_api.domain.reminders.rules import follow_up_due_at
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.reminders import PendingFollowUp, ReminderRead
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

LIST_LIMIT = 50
PENDING_MAX_LIMIT = 100


def _patient(tenant: TenantRepositories, clinic_id: UUID, patient_id: UUID) -> Patient:
    patient = tenant.patients.get(patient_id)
    if patient is None:
        logger.info(
            "tenancy.not_found",
            entity="patient",
            entity_id=str(patient_id),
            clinic_id=str(clinic_id),
        )
        raise NotFound("patient")
    return patient


class _UseCase:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids


@dataclass(frozen=True, slots=True)
class ScheduleCommand:
    doctor_id: UUID
    follow_up_date: date


class ScheduleReminder(_UseCase):
    def execute(
        self, ctx: RequestContext, *, patient_id: UUID, cmd: ScheduleCommand
    ) -> ReminderRead:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            patient = _patient(tenant, ctx.clinic_id, patient_id)
            doctor = load_doctor(tenant, ctx.clinic_id, cmd.doctor_id)
            if not doctor.is_active:
                raise InvalidValue("doctor_id", "is not an active doctor")
            now = self._clock.now()
            if cmd.follow_up_date <= local_date(now, clinic.timezone):
                raise InPast()
            if not patient.may_receive_whatsapp:
                raise NoConsent()
            if clinic.phone is None:
                raise ClinicPhoneMissing()
            reminder = Reminder.schedule(
                id=self._ids.new_id(),
                clinic_id=ctx.clinic_id,
                patient_id=patient.id,
                doctor_id=doctor.id,
                source=ReminderSource.MANUAL,
                source_id=None,
                follow_up_date=cmd.follow_up_date,
                due_at=follow_up_due_at(cmd.follow_up_date, clinic.timezone, now),
                created_by=ctx.user_id,
                now=now,
            )
            tenant.reminders.add(reminder)
            enqueue_send(uow, ids=self._ids, reminder=reminder, request_id=ctx.request_id, now=now)
            audit(
                uow,
                ids=self._ids,
                action=AuditAction.REMINDER_SCHEDULED,
                reminder=reminder,
                user_id=ctx.user_id,
                request_id=ctx.request_id,
                now=now,
            )
            uow.commit()
        logger.info("reminder.scheduled", reminder_id=str(reminder.id), source="MANUAL")
        return ReminderRead(reminder)


@dataclass(frozen=True, slots=True)
class ChangeCommand:
    """Exactly one: a new follow-up date, or cancel."""

    follow_up_date: date | None = None
    cancel: bool = False


class ChangeReminder(_UseCase):
    def execute(
        self, ctx: RequestContext, *, reminder_id: UUID, cmd: ChangeCommand
    ) -> ReminderRead:
        if (cmd.follow_up_date is None) == (not cmd.cancel):
            raise InvalidValue("body", "give either follow_up_date or cancel: true")
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            reminder = tenant.reminders.get(reminder_id, for_update=True)
            if reminder is None:
                logger.info(
                    "tenancy.not_found",
                    entity="reminder",
                    entity_id=str(reminder_id),
                    clinic_id=str(ctx.clinic_id),
                )
                raise NotFound("reminder")
            now = self._clock.now()
            if cmd.cancel:
                reminder.cancel(by=ctx.user_id, now=now)
                action = AuditAction.REMINDER_CANCELLED
            else:
                assert cmd.follow_up_date is not None
                if cmd.follow_up_date <= local_date(now, clinic.timezone):
                    raise InPast()
                reminder.move(
                    follow_up_date=cmd.follow_up_date,
                    due_at=follow_up_due_at(cmd.follow_up_date, clinic.timezone, now),
                    now=now,
                )
                enqueue_send(
                    uow, ids=self._ids, reminder=reminder, request_id=ctx.request_id, now=now
                )
                action = AuditAction.REMINDER_RESCHEDULED
            tenant.reminders.update(reminder)
            audit(
                uow,
                ids=self._ids,
                action=action,
                reminder=reminder,
                user_id=ctx.user_id,
                request_id=ctx.request_id,
                now=now,
            )
            uow.commit()
        logger.info(action.value, reminder_id=str(reminder.id))
        return ReminderRead(reminder)


class ListPatientReminders(_UseCase):
    def execute(self, ctx: RequestContext, *, patient_id: UUID) -> Sequence[ReminderRead]:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            _patient(tenant, ctx.clinic_id, patient_id)
            return tenant.reminders.list_for_patient(patient_id, limit=LIST_LIMIT)


class ListPatientMessages(_UseCase):
    """The patient's messages, newest first (M5-P6 decision 1A; R16; FR-MSG-04).

    The caller shows status only: what a message was about, its channel, status, error code and
    times. Its variables and number never leave the API.
    """

    def execute(self, ctx: RequestContext, *, patient_id: UUID) -> Sequence[Message]:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            _patient(tenant, ctx.clinic_id, patient_id)
            return tenant.messages.list_for_patient(patient_id, limit=LIST_LIMIT)


class ListPendingFollowUps(_UseCase):
    def execute(
        self, ctx: RequestContext, *, limit: int, offset: int, doctor_id: UUID | None = None
    ) -> Sequence[PendingFollowUp]:
        if not 1 <= limit <= PENDING_MAX_LIMIT:
            raise InvalidValue("limit", f"must be 1-{PENDING_MAX_LIMIT}")
        if offset < 0:
            raise InvalidValue("offset", "must not be negative")
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            today = local_date(self._clock.now(), clinic.timezone)
            return tenant.reminders.pending_follow_ups(
                today=today,
                timezone=clinic.timezone,
                limit=limit,
                offset=offset,
                doctor_id=doctor_id,
            )
