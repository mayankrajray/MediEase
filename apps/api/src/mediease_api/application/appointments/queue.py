"""The daily queue: transitions, walk-ins and the day's read (M3-P3; FR-QUE-01, 02, 04).

``TransitionAppointment`` moves one appointment along the state machine under the same lock order
as a booking (doctor ``FOR SHARE``, session ``FOR UPDATE``, then the appointment), so two tabs
making the same move get one 200 and one ``QUE_INVALID_TRANSITION`` (D18).

``AddWalkIn`` books into the doctor's session running now, else the next one today (D21), the
next token or the earliest free slot that has not ended (R11), source ``WALK_IN``, and marks it
``ARRIVED`` at once: two history rows, one ``appointment.booked`` audit row.

``GetQueue`` lists a date's sessions (generated as the session list does) with their
appointments by token or slot, the patient's code, name and age, and the wait so far.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.appointments.common import (
    ENTITY_TYPE,
    load_appointment,
    lock_sessions,
    place_metadata,
    record_history,
)
from mediease_api.application.appointments.views import AppointmentView
from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.patients.views import PatientView
from mediease_api.application.scheduling.generation import generate
from mediease_api.application.scheduling.schedules import load_clinic, load_doctor
from mediease_api.application.scheduling.sessions import sessions_for_date
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.errors import NoSession, SessionClosed, SessionFull
from mediease_api.domain.appointments.queue import first_free_slot, transition, wait_minutes
from mediease_api.domain.appointments.status import (
    AppointmentSource,
    AppointmentStatus,
)
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.repositories import RowLock
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TransitionCommand:
    seen: AppointmentStatus
    to: AppointmentStatus


class TransitionAppointment:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, *, clinic_id: UUID, actor: Actor, appointment_id: UUID, cmd: TransitionCommand
    ) -> AppointmentView:
        with self._uow as uow:
            clinic = load_clinic(uow, clinic_id)
            tenant = uow.tenant(clinic_id)
            seen = load_appointment(tenant, clinic_id, appointment_id)
            session = lock_sessions(tenant, clinic_id, [seen.session_id]).sessions[seen.session_id]
            appointment = load_appointment(tenant, clinic_id, appointment_id, for_update=True)
            now = self._clock.now()
            before = transition(
                appointment,
                session,
                seen=cmd.seen,
                to=cmd.to,
                now=now,
                today=local_date(now, clinic.timezone),
            )
            tenant.appointments.update(appointment)
            record_history(tenant, appointment, ids=self._ids, actor=actor, from_status=before)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.APPOINTMENT_STATUS_CHANGED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=appointment.id,
                metadata={
                    "from": before.value,
                    "to": cmd.to.value,
                    "session_id": str(session.id),
                    "doctor_id": str(session.doctor_id),
                },
            )
            uow.commit()

        logger.info(
            "appointment.status_changed",
            clinic_id=str(clinic_id),
            appointment_id=str(appointment_id),
            from_status=before.value,
            to_status=cmd.to.value,
        )
        return AppointmentView(appointment, session)


@dataclass(frozen=True, slots=True)
class WalkInCommand:
    doctor_id: UUID
    patient_id: UUID
    session_id: UUID | None = None
    slot_start: datetime | None = None
    reason: str | None = None


def _pick_session(sessions: Sequence[Session], now: datetime) -> Session:
    """D21: the open session running now, else the next one to start; none is QUE_NO_SESSION."""
    open_ones = [s for s in sessions if s.is_open and s.ends_at > now]
    running = [s for s in open_ones if s.starts_at <= now]
    if running:
        return running[0]
    upcoming = sorted((s for s in open_ones if s.starts_at > now), key=lambda s: s.starts_at)
    if not upcoming:
        raise NoSession()
    return upcoming[0]


class AddWalkIn:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, *, clinic_id: UUID, actor: Actor, cmd: WalkInCommand) -> AppointmentView:
        with self._uow as uow:
            clinic = load_clinic(uow, clinic_id)
            tenant = uow.tenant(clinic_id)
            if tenant.patients.get(cmd.patient_id) is None:
                raise NotFound("patient")
            now = self._clock.now()
            today = local_date(now, clinic.timezone)
            doctor = load_doctor(tenant, clinic_id, cmd.doctor_id, lock=RowLock.SHARE)
            if not doctor.is_active:
                raise SessionClosed()
            generate(tenant, clinic=clinic, doctor=doctor, on_date=today, ids=self._ids, now=now)
            # Today's sessions, plus last night's if it is still running (D19).
            todays = [
                s
                for s in tenant.sessions.list_for_doctor(
                    doctor.id, first=today - timedelta(days=1), last=today
                )
                if s.on_date == today or s.ends_at > now
            ]
            if cmd.session_id is not None:
                chosen = next((s for s in todays if s.id == cmd.session_id), None)
                if chosen is None or not chosen.is_open or chosen.ends_at <= now:
                    raise NoSession()
            else:
                chosen = _pick_session(todays, now)

            session = lock_sessions(tenant, clinic_id, [chosen.id]).sessions[chosen.id]
            active = tenant.appointments.list_active_for_sessions([session.id])
            slot_start = cmd.slot_start
            if session.mode is BookingMode.SLOTS and slot_start is None:
                slot_start = first_free_slot(
                    session, taken={a.slot_start for a in active if a.slot_start}, now=now
                )
                if slot_start is None:
                    raise SessionFull()
            appointment = Appointment.book(
                session,
                id=self._ids.new_id(),
                patient_id=cmd.patient_id,
                active=active,
                now=now,
                slot_start=slot_start if session.mode is BookingMode.SLOTS else None,
                source=AppointmentSource.WALK_IN,
                reason=cmd.reason,
                created_by=actor.user_id,
            )
            record = AppointmentView(appointment, session)
            tenant.sessions.update(session)
            tenant.appointments.add(appointment)
            record_history(tenant, appointment, ids=self._ids, actor=actor, from_status=None)
            transition(
                appointment,
                session,
                seen=AppointmentStatus.BOOKED,
                to=AppointmentStatus.ARRIVED,
                now=now,
                today=today,
            )
            tenant.appointments.update(appointment)
            record_history(
                tenant,
                appointment,
                ids=self._ids,
                actor=actor,
                from_status=AppointmentStatus.BOOKED,
            )
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.APPOINTMENT_BOOKED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=appointment.id,
                metadata=place_metadata(appointment, session),
            )
            uow.commit()

        logger.info(
            "appointment.walk_in",
            clinic_id=str(clinic_id),
            appointment_id=str(appointment.id),
            session_id=str(session.id),
        )
        return record


@dataclass(frozen=True, slots=True)
class QueueEntry:
    view: AppointmentView
    patient: PatientView
    wait_minutes: int | None


@dataclass(frozen=True, slots=True)
class QueueSession:
    session: Session
    entries: tuple[QueueEntry, ...]


@dataclass(frozen=True, slots=True)
class QueueView:
    on_date: date
    sessions: tuple[QueueSession, ...]


class GetQueue:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self,
        ctx: RequestContext,
        *,
        on_date: date | None = None,
        doctor_id: UUID | None = None,
        include_cancelled: bool = False,
    ) -> QueueView:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            now = self._clock.now()
            day = on_date or local_date(now, clinic.timezone)
            sessions, _ = sessions_for_date(
                tenant, clinic, day, doctor_id=doctor_id, ids=self._ids, now=now
            )
            ids = [s.id for s in sessions]
            appointments = (
                tenant.appointments.list_for_sessions(ids)
                if include_cancelled
                else tenant.appointments.list_active_for_sessions(ids)
            )
            patients = {
                p.id: PatientView.of(p, day)
                for p in tenant.patients.get_many({a.patient_id for a in appointments})
            }
            uow.commit()

        by_session: dict[UUID, list[QueueEntry]] = {s.id: [] for s in sessions}
        sessions_by_id = {s.id: s for s in sessions}
        for a in appointments:
            by_session[a.session_id].append(
                QueueEntry(
                    AppointmentView(a, sessions_by_id[a.session_id]),
                    patients[a.patient_id],
                    wait_minutes(a, now),
                )
            )
        ordered = tuple(
            QueueSession(
                s,
                tuple(
                    sorted(
                        by_session[s.id],
                        key=lambda e: (
                            e.view.appointment.token_number or 0,
                            e.view.appointment.slot_start or s.starts_at,
                        ),
                    )
                ),
            )
            for s in sessions
        )
        return QueueView(day, ordered)
