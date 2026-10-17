"""Visit use cases (M4-P1; FR-VIS-01..03, 05; spec prescriptions R1-R3, R16, R17).

Who may do what (spec §2; M4-P1 decisions 1A-6A):

- Writing needs ``CLINICAL_WRITE`` (checked by the route) **and** being the visit's doctor: the
  doctor profile linked to the caller's user (``VIS_NOT_YOURS`` otherwise).
- Reading needs ``CLINICAL_VIEW`` (doctors and owners, never front desk).

Lock order, the same as the queue's (``application/appointments/common.py``): the doctor
``FOR SHARE``, the session ``FOR UPDATE``, the appointment, then the visit. Starting a visit and
completing it take the whole chain, so they serialise with queue moves on the same appointment;
editing and addenda lock the visit row only, which cannot form a cycle with them.

Audit (R16): every write has its own action; every read that returns clinical content writes one
row for the whole view, never one per visit in it. Metadata and logs carry IDs, counts and field
names only (R17).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.appointments.common import (
    ENTITY_TYPE as APPOINTMENT_ENTITY,
)
from mediease_api.application.appointments.common import (
    load_appointment,
    lock_sessions,
    record_history,
)
from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.patients.views import PatientView
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.domain.appointments.queue import is_session_day, transition
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.domain.visits.errors import VisitAlreadyExists, VisitNotYours
from mediease_api.domain.visits.visit import Visit, VisitAddendum
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "visit"
HISTORY_SIZE = 10  # R2: the consultation screen shows the last 10 visits
DEFAULT_PAGE = 10
MAX_PAGE = 50


@dataclass(frozen=True, slots=True)
class VisitView:
    """A visit, its addenda (oldest first) and whether it is locked at the time of the read."""

    visit: Visit
    addenda: tuple[VisitAddendum, ...]
    is_locked: bool


@dataclass(frozen=True, slots=True)
class ConsultationView:
    """Everything the consultation screen shows, from one read (R16)."""

    visit: VisitView
    patient: PatientView
    history: tuple[Visit, ...]


@dataclass(frozen=True, slots=True)
class VisitPage:
    items: tuple[Visit, ...]
    # The last item's ID when there may be more; pass it back as ``before``.
    next_before: UUID | None


def _load_visit(
    tenant: TenantRepositories, clinic_id: UUID, visit_id: UUID, *, for_update: bool = False
) -> Visit:
    visit = tenant.visits.get(visit_id, for_update=for_update)
    if visit is None:
        logger.info(
            "tenancy.not_found", entity="visit", entity_id=str(visit_id), clinic_id=str(clinic_id)
        )
        raise NotFound("visit")
    return visit


def _callers_doctor_id(tenant: TenantRepositories, ctx: RequestContext) -> UUID:
    """The doctor profile of the signed-in user; without one, nobody's visits are theirs."""
    doctor = tenant.doctors.get_for_user(ctx.user_id)
    if doctor is None or not doctor.is_active:
        raise VisitNotYours()
    return doctor.id


def _view(tenant: TenantRepositories, visit: Visit, *, locked: bool) -> VisitView:
    return VisitView(visit, tuple(tenant.visit_addenda.list_for_visit(visit.id)), locked)


class StartVisit:
    """R1, decision 1A: the doctor opens the record after the queue's *Start*."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, *, appointment_id: UUID) -> VisitView:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            doctor_id = _callers_doctor_id(tenant, ctx)
            seen = load_appointment(tenant, ctx.clinic_id, appointment_id)
            lock_sessions(tenant, ctx.clinic_id, [seen.session_id])
            appointment = load_appointment(tenant, ctx.clinic_id, appointment_id, for_update=True)
            if doctor_id != appointment.doctor_id:
                raise VisitNotYours()  # before saying whether a visit exists
            # Under the session lock two starts for one appointment serialise; the unique index
            # on visits.appointment_id is the backstop.
            existing = tenant.visits.get_for_appointment(appointment.id)
            if existing is not None:
                raise VisitAlreadyExists(existing.id)
            now = self._clock.now()
            visit = Visit.start(
                appointment,
                id=self._ids.new_id(),
                doctor_id=doctor_id,
                created_by=ctx.user_id,
                now=now,
            )
            tenant.visits.add(visit)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.VISIT_STARTED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=visit.id,
                metadata={
                    "appointment_id": str(appointment.id),
                    "patient_id": str(visit.patient_id),
                    "doctor_id": str(visit.doctor_id),
                },
            )
            uow.commit()

        logger.info("visit.started", visit_id=str(visit.id), appointment_id=str(appointment.id))
        return VisitView(visit, (), False)


@dataclass(frozen=True, slots=True)
class VisitChanges:
    """Only the fields the caller sent; ``vitals`` already parsed."""

    seen_revision: int
    fields: Mapping[str, object]


class UpdateVisit:
    """FR-VIS-02: clinical fields and vitals, by the visit's doctor, until the lock (R3)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, *, visit_id: UUID, changes: VisitChanges) -> VisitView:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            visit = _load_visit(tenant, ctx.clinic_id, visit_id, for_update=True)
            visit.check_writer(_callers_doctor_id(tenant, ctx))
            now = self._clock.now()
            changed = visit.edit(changes.fields, seen_revision=changes.seen_revision, now=now)
            if changed:
                tenant.visits.update(visit)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.VISIT_UPDATED,
                    actor=Actor.staff(ctx),
                    now=now,
                    clinic_id=ctx.clinic_id,
                    entity_type=ENTITY_TYPE,
                    entity_id=visit.id,
                    metadata={"fields": ",".join(changed), "revision": str(visit.revision)},
                )
            view = _view(tenant, visit, locked=visit.is_locked(now))
            uow.commit()

        logger.info("visit.updated", visit_id=str(visit_id), fields=list(changed))
        return view


class CompleteVisit:
    """R3, decision 2A: completes the visit and, while it is still there, its appointment."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, *, visit_id: UUID) -> VisitView:
        actor = Actor.staff(ctx)
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            seen = _load_visit(tenant, ctx.clinic_id, visit_id)
            seen.check_writer(_callers_doctor_id(tenant, ctx))
            appointment = load_appointment(tenant, ctx.clinic_id, seen.appointment_id)
            session = lock_sessions(tenant, ctx.clinic_id, [appointment.session_id]).sessions[
                appointment.session_id
            ]
            appointment = load_appointment(tenant, ctx.clinic_id, appointment.id, for_update=True)
            visit = _load_visit(tenant, ctx.clinic_id, visit_id, for_update=True)
            now = self._clock.now()
            moved = False
            if visit.complete(now):
                tenant.visits.update(visit)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.VISIT_COMPLETED,
                    actor=actor,
                    now=now,
                    clinic_id=ctx.clinic_id,
                    entity_type=ENTITY_TYPE,
                    entity_id=visit.id,
                    metadata={"appointment_id": str(appointment.id)},
                )
                # The board follows the doctor; a queue move already made (or a later day,
                # D19) leaves the appointment as it is.
                today = local_date(now, clinic.timezone)
                if appointment.status is AppointmentStatus.IN_CONSULTATION and is_session_day(
                    session, now=now, today=today
                ):
                    before = transition(
                        appointment,
                        session,
                        seen=AppointmentStatus.IN_CONSULTATION,
                        to=AppointmentStatus.COMPLETED,
                        now=now,
                        today=today,
                    )
                    tenant.appointments.update(appointment)
                    record_history(
                        tenant, appointment, ids=self._ids, actor=actor, from_status=before
                    )
                    record_event(
                        uow,
                        event_id=self._ids.new_id(),
                        action=AuditAction.APPOINTMENT_STATUS_CHANGED,
                        actor=actor,
                        now=now,
                        clinic_id=ctx.clinic_id,
                        entity_type=APPOINTMENT_ENTITY,
                        entity_id=appointment.id,
                        metadata={
                            "from": before.value,
                            "to": AppointmentStatus.COMPLETED.value,
                            "session_id": str(session.id),
                            "doctor_id": str(session.doctor_id),
                            "by": "visit.completed",
                        },
                    )
                    moved = True
            view = _view(tenant, visit, locked=visit.is_locked(now))
            uow.commit()

        logger.info("visit.completed", visit_id=str(visit_id), appointment_moved=moved)
        return view


class AddAddendum:
    """R3, decision 3A: a later note on a completed visit, by its doctor; never changed."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, *, visit_id: UUID, body: str) -> VisitAddendum:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            visit = _load_visit(tenant, ctx.clinic_id, visit_id, for_update=True)
            visit.check_writer(_callers_doctor_id(tenant, ctx))
            now = self._clock.now()
            addendum = visit.addendum(
                id=self._ids.new_id(), author_user_id=ctx.user_id, body=body, now=now
            )
            tenant.visit_addenda.add(addendum)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.VISIT_ADDENDUM_ADDED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=visit.id,
                metadata={
                    "addendum_id": str(addendum.id),
                    "after_lock": "true" if visit.is_locked(now) else "false",
                },
            )
            uow.commit()

        logger.info("visit.addendum_added", visit_id=str(visit_id), addendum_id=str(addendum.id))
        return addendum


class GetConsultation:
    """R2, R16, AC9: the visit, its addenda, the patient and their last 10 visits; one audit row."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, *, visit_id: UUID) -> ConsultationView:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            visit = _load_visit(tenant, ctx.clinic_id, visit_id)
            patient = tenant.patients.get(visit.patient_id)
            assert patient is not None  # the foreign key keeps it
            # Previous visits only: this one is shown in full.
            history = tuple(
                v
                for v in tenant.visits.list_for_patient(visit.patient_id, limit=HISTORY_SIZE + 1)
                if v.id != visit.id
            )[:HISTORY_SIZE]
            now = self._clock.now()
            view = ConsultationView(
                _view(tenant, visit, locked=visit.is_locked(now)),
                PatientView.of(patient, local_date(now, clinic.timezone)),
                history,
            )
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.VISIT_VIEWED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=visit.id,
                metadata={"patient_id": str(visit.patient_id), "history": str(len(history))},
            )
            uow.commit()
        return view


class ListPatientVisits:
    """FR-VIS-03: a patient's visits, newest first, in pages; one audit row per page (R16)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self,
        ctx: RequestContext,
        *,
        patient_id: UUID,
        limit: int = DEFAULT_PAGE,
        before: UUID | None = None,
    ) -> VisitPage:
        if not 1 <= limit <= MAX_PAGE:
            raise InvalidValue("limit", f"must be between 1 and {MAX_PAGE}")
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            if tenant.patients.get(patient_id) is None:
                raise NotFound("patient")
            position = None
            if before is not None:
                anchor = tenant.visits.get(before)
                if anchor is None or anchor.patient_id != patient_id:
                    raise InvalidValue("before", "must be one of this patient's visits")
                position = (anchor.started_at, anchor.id)
            found: Sequence[Visit] = tenant.visits.list_for_patient(
                patient_id, limit=limit + 1, before=position
            )
            items = tuple(found[:limit])
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.PATIENT_VISITS_VIEWED,
                actor=Actor.staff(ctx),
                now=self._clock.now(),
                clinic_id=ctx.clinic_id,
                entity_type="patient",
                entity_id=patient_id,
                metadata={"count": str(len(items))},
            )
            uow.commit()
        return VisitPage(items, items[-1].id if len(found) > limit else None)
