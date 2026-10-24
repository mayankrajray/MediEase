"""Bookings to move (M6a-P8; FR-APT-09; decision 6A).

Leave over a booked day, or a changed weekly schedule, closes the sessions people are booked in
and cancels nothing (appointments spec R16, R17). This lists those bookings from today on, so the
front desk can reschedule or cancel each one: a derived list, not a table. ``reason`` is ``LEAVE``
when the doctor has leave that day, else ``SCHEDULE_CHANGED``. Who and where only: the patient's
code, first name and a masked phone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from mediease_api.application.context import RequestContext
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.scheduling.exceptions import ExceptionKind
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.unit_of_work import UnitOfWork

LIST_MAX = 200


class MoveReason(StrEnum):
    LEAVE = "LEAVE"
    SCHEDULE_CHANGED = "SCHEDULE_CHANGED"


@dataclass(frozen=True, slots=True)
class BookingToMove:
    appointment: Appointment
    session: Session
    patient: Patient
    reason: MoveReason


class ListBookingsToMove:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, ctx: RequestContext, *, doctor_id: UUID | None = None
    ) -> Sequence[BookingToMove]:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            today = local_date(self._clock.now(), clinic.timezone)
            found = tenant.appointments.list_to_move(
                from_date=today, doctor_id=doctor_id, limit=LIST_MAX
            )
            if not found:
                return []
            patients = {p.id: p for p in tenant.patients.get_many({a.patient_id for a, _ in found})}
            leave: set[tuple[UUID, object]] = set()
            for doctor in {a.doctor_id for a, _ in found}:
                days = [s.on_date for a, s in found if a.doctor_id == doctor]
                for exception in tenant.schedule_exceptions.list_for_doctor(
                    doctor, first=min(days), last=max(days)
                ):
                    if exception.kind is ExceptionKind.LEAVE:
                        leave.add((doctor, exception.on_date))
            return [
                BookingToMove(
                    appointment=appointment,
                    session=session,
                    patient=patients[appointment.patient_id],
                    reason=(
                        MoveReason.LEAVE
                        if (appointment.doctor_id, session.on_date) in leave
                        else MoveReason.SCHEDULE_CHANGED
                    ),
                )
                for appointment, session in found
                if appointment.patient_id in patients
            ]
