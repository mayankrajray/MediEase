"""Reading appointments (FR-APT-05: history is retained and visible).

``GetAppointment``: one appointment with its session and status history.
``ListPatientAppointments``: a patient's appointments, newest first, capped like the patient lookup
(no cursor yet).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from mediease_api.application.appointments.common import load_appointment
from mediease_api.application.appointments.views import AppointmentDetail, AppointmentView
from mediease_api.application.context import RequestContext
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.unit_of_work import UnitOfWork

MAX_PATIENT_APPOINTMENTS = 50


class GetAppointment:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext, appointment_id: UUID) -> AppointmentDetail:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            appointment = load_appointment(tenant, ctx.clinic_id, appointment_id)
            session = tenant.sessions.get(appointment.session_id)
            assert session is not None  # the foreign key keeps it
            history = tuple(tenant.appointment_history.list_for_appointment(appointment.id))
            return AppointmentDetail(AppointmentView(appointment, session), history)


class ListPatientAppointments:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext, patient_id: UUID) -> Sequence[AppointmentView]:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            if tenant.patients.get(patient_id) is None:
                raise NotFound("patient")
            appointments = tenant.appointments.list_for_patient(
                patient_id, limit=MAX_PATIENT_APPOINTMENTS
            )
            sessions = {
                s.id: s for s in tenant.sessions.get_many({a.session_id for a in appointments})
            }
            return [AppointmentView(a, sessions[a.session_id]) for a in appointments]
