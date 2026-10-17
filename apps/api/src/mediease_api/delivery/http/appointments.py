"""Appointments: book, read, cancel, reschedule (M3-P2; FR-APT-03..05, FR-APT-07; spec R3-R8).

| Endpoint | Permission |
|---|---|
| ``POST /api/v1/appointments`` | ``APPOINTMENTS_MANAGE`` |
| ``GET /api/v1/appointments/{appointment_id}`` | ``APPOINTMENTS_MANAGE`` |
| ``POST /api/v1/appointments/{appointment_id}/cancel`` | ``APPOINTMENTS_MANAGE`` |
| ``POST /api/v1/appointments/{appointment_id}/reschedule`` | ``APPOINTMENTS_MANAGE`` |
| ``GET /api/v1/patients/{patient_id}/appointments`` | ``APPOINTMENTS_MANAGE`` |

Every role books (spec §2). The clinic comes from the request context, so another clinic's
appointment, session or patient is a 404 (NFR-08). ``reason`` is a short non-clinical note and is
never logged or audited.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from mediease_api.application.appointments.book import BookAppointment, BookCommand
from mediease_api.application.appointments.cancel import CancelAppointment, CancelCommand
from mediease_api.application.appointments.queries import GetAppointment, ListPatientAppointments
from mediease_api.application.appointments.reschedule import (
    RescheduleAppointment,
    RescheduleCommand,
)
from mediease_api.application.context import Actor
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import (
    appointment_body,
    appointment_detail_body,
    items_body,
)
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.appointments.appointment import CANCEL_NOTE_MAX, REASON_MAX
from mediease_api.domain.appointments.status import (
    STAFF_CANCEL_REASONS,
    STAFF_SOURCES,
    AppointmentSource,
    CancelReason,
)
from mediease_api.domain.identity.permissions import Permission


class AppointmentUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def book_appointment(self) -> BookAppointment: ...
    def get_appointment(self) -> GetAppointment: ...
    def cancel_appointment(self) -> CancelAppointment: ...
    def reschedule_appointment(self) -> RescheduleAppointment: ...
    def list_patient_appointments(self) -> ListPatientAppointments: ...


def _as_utc(value: datetime | None) -> datetime | None:
    """Any offset is accepted at the edge (``+05:30`` from the screen) and compared in UTC."""
    return value.astimezone(UTC) if value is not None else None


class BookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    patient_id: UUID
    # Slot mode only: one of the session's slot starts, with an offset.
    slot_start: AwareDatetime | None = None
    source: AppointmentSource = AppointmentSource.FRONT_DESK
    reason: str | None = Field(default=None, max_length=REASON_MAX)

    @field_validator("source")
    @classmethod
    def _staff_source(cls, value: AppointmentSource) -> AppointmentSource:
        if value not in STAFF_SOURCES:
            raise ValueError("walk-ins and public bookings have their own routes")
        return value


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: CancelReason
    note: str | None = Field(default=None, max_length=CANCEL_NOTE_MAX)

    @field_validator("reason")
    @classmethod
    def _staff_reason(cls, value: CancelReason) -> CancelReason:
        if value not in STAFF_CANCEL_REASONS:
            raise ValueError("RESCHEDULED is set by a reschedule")
        return value


class RescheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    slot_start: AwareDatetime | None = None


def create_appointments_blueprint(use_cases: AppointmentUseCases) -> Blueprint:
    bp = Blueprint("appointments", __name__, url_prefix="/api/v1")
    one = "/appointments/<uuid:appointment_id>"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/appointments")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def book_appointment() -> tuple[Response, int]:
        body = parse_json(BookRequest)
        ctx = current_context()
        view = use_cases.book_appointment().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            cmd=BookCommand(
                session_id=body.session_id,
                patient_id=body.patient_id,
                slot_start=_as_utc(body.slot_start),
                source=body.source,
                reason=body.reason,
            ),
        )
        return jsonify(appointment_body(view)), 201

    @bp.get(one)
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def get_appointment(appointment_id: UUID) -> Response:
        detail = use_cases.get_appointment().execute(current_context(), appointment_id)
        return jsonify(appointment_detail_body(detail))

    @bp.post(f"{one}/cancel")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def cancel_appointment(appointment_id: UUID) -> Response:
        body = parse_json(CancelRequest)
        ctx = current_context()
        view = use_cases.cancel_appointment().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            appointment_id=appointment_id,
            cmd=CancelCommand(reason=body.reason, note=body.note),
        )
        return jsonify(appointment_body(view))

    @bp.post(f"{one}/reschedule")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def reschedule_appointment(appointment_id: UUID) -> tuple[Response, int]:
        body = parse_json(RescheduleRequest)
        ctx = current_context()
        view = use_cases.reschedule_appointment().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            appointment_id=appointment_id,
            cmd=RescheduleCommand(session_id=body.session_id, slot_start=_as_utc(body.slot_start)),
        )
        return jsonify(appointment_body(view)), 201

    @bp.get("/patients/<uuid:patient_id>/appointments")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def list_patient_appointments(patient_id: UUID) -> Response:
        views = use_cases.list_patient_appointments().execute(current_context(), patient_id)
        return jsonify(items_body(appointment_body(v) for v in views))

    return bp
