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

from flask import Blueprint, Response, jsonify, request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from mediease_api.application.appointments.book import BookAppointment, BookCommand
from mediease_api.application.appointments.cancel import CancelAppointment, CancelCommand
from mediease_api.application.appointments.live import IssueStaffLiveLink
from mediease_api.application.appointments.queries import GetAppointment, ListPatientAppointments
from mediease_api.application.appointments.queue import (
    AddWalkIn,
    GetQueue,
    TransitionAppointment,
    TransitionCommand,
    WalkInCommand,
)
from mediease_api.application.appointments.reschedule import (
    RescheduleAppointment,
    RescheduleCommand,
)
from mediease_api.application.appointments.to_move import BookingToMove, ListBookingsToMove
from mediease_api.application.context import Actor
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import (
    appointment_body,
    appointment_detail_body,
    items_body,
    queue_body,
)
from mediease_api.delivery.http.etag import conditional_json
from mediease_api.delivery.http.scheduling import _date_arg_optional, _uuid_arg
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.appointments.appointment import CANCEL_NOTE_MAX, REASON_MAX
from mediease_api.domain.appointments.status import (
    STAFF_CANCEL_REASONS,
    STAFF_SOURCES,
    AppointmentSource,
    AppointmentStatus,
    CancelReason,
)
from mediease_api.domain.identity.permissions import Permission


class AppointmentUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def book_appointment(self) -> BookAppointment: ...
    def get_appointment(self) -> GetAppointment: ...
    def issue_staff_live_link(self) -> IssueStaffLiveLink: ...
    def cancel_appointment(self) -> CancelAppointment: ...
    def reschedule_appointment(self) -> RescheduleAppointment: ...
    def list_patient_appointments(self) -> ListPatientAppointments: ...
    def transition_appointment(self) -> TransitionAppointment: ...
    def add_walk_in(self) -> AddWalkIn: ...
    def get_queue(self) -> GetQueue: ...
    def list_bookings_to_move(self) -> ListBookingsToMove: ...


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
    # M6b-P4 (R18a): book over an online request's hold; ends the hold and is audited.
    override_hold: bool = False

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
    # M6b-P4 (R18a): the confirmed "Book anyway" action over an online request's hold.
    override_hold: bool = False


class TransitionRequest(BaseModel):
    """D18: the status the screen showed and the one wanted."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    seen: AppointmentStatus = Field(alias="from")
    to: AppointmentStatus


class WalkInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: UUID
    patient_id: UUID
    # Another of today's sessions than the one running or next (D21).
    session_id: UUID | None = None
    # Slot mode: a free slot; without it the earliest free one that has not ended.
    slot_start: AwareDatetime | None = None
    reason: str | None = Field(default=None, max_length=REASON_MAX)


def booking_to_move_body(item: BookingToMove) -> dict[str, object]:
    """Who and where (decision 6A): code, first name and a masked phone; nothing clinical."""
    a, s, p = item.appointment, item.session, item.patient
    return {
        "id": str(a.id),
        "status": a.status.value,
        "doctor_id": str(a.doctor_id),
        "session_id": str(s.id),
        "on_date": s.on_date.isoformat(),
        "starts_at": (a.slot_start or s.starts_at).isoformat(),
        "slot_start": a.slot_start.isoformat() if a.slot_start else None,
        "token_number": a.token_number,
        "reason": item.reason.value,
        "patient": {
            "id": str(p.id),
            "code": p.code,
            "first_name": (p.full_name.split() or ["Patient"])[0],
            "phone_masked": p.phone.masked(),
        },
    }


def create_appointments_blueprint(use_cases: AppointmentUseCases) -> Blueprint:
    bp = Blueprint("appointments", __name__, url_prefix="/api/v1")
    one = "/appointments/<uuid:appointment_id>"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("/appointments/to-move")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def list_bookings_to_move() -> Response:
        """M6a-P8 (FR-APT-09): live bookings in sessions a schedule change closed."""
        items = use_cases.list_bookings_to_move().execute(
            current_context(), doctor_id=_uuid_arg("doctor_id")
        )
        return jsonify(items_body(booking_to_move_body(i) for i in items))

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
                override_hold=body.override_hold,
            ),
        )
        return jsonify(appointment_body(view)), 201

    @bp.get(one)
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def get_appointment(appointment_id: UUID) -> Response:
        detail = use_cases.get_appointment().execute(current_context(), appointment_id)
        return jsonify(appointment_detail_body(detail))

    @bp.get(f"{one}/live-link")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def live_link(appointment_id: UUID) -> Response:
        """M6b-P6 (R69): the patient's live token link, for staff to send by hand."""
        link = use_cases.issue_staff_live_link().execute(current_context(), appointment_id)
        return jsonify({"url": link.url, "expires_at": link.expires_at.isoformat()})

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
            cmd=RescheduleCommand(
                session_id=body.session_id,
                slot_start=_as_utc(body.slot_start),
                override_hold=body.override_hold,
            ),
        )
        return jsonify(appointment_body(view)), 201

    @bp.get("/patients/<uuid:patient_id>/appointments")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def list_patient_appointments(patient_id: UUID) -> Response:
        views = use_cases.list_patient_appointments().execute(current_context(), patient_id)
        return jsonify(items_body(appointment_body(v) for v in views))

    @bp.post(f"{one}/transitions")
    @clinic(Permission.QUEUE_MOVE)
    def transition_appointment(appointment_id: UUID) -> Response:
        body = parse_json(TransitionRequest)
        ctx = current_context()
        view = use_cases.transition_appointment().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            appointment_id=appointment_id,
            cmd=TransitionCommand(seen=body.seen, to=body.to),
        )
        return jsonify(appointment_body(view))

    @bp.post("/queue/walk-ins")
    @clinic(Permission.QUEUE_MOVE)
    def add_walk_in() -> tuple[Response, int]:
        body = parse_json(WalkInRequest)
        ctx = current_context()
        view = use_cases.add_walk_in().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            cmd=WalkInCommand(
                doctor_id=body.doctor_id,
                patient_id=body.patient_id,
                session_id=body.session_id,
                slot_start=_as_utc(body.slot_start),
                reason=body.reason,
            ),
        )
        return jsonify(appointment_body(view)), 201

    @bp.get("/queue")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def get_queue() -> Response:
        queue = use_cases.get_queue().execute(
            current_context(),
            on_date=_date_arg_optional("date"),
            doctor_id=_uuid_arg("doctor_id"),
            include_cancelled=request.args.get("include_cancelled") == "true",
        )
        # R12, D23: screens poll with If-None-Match and get 304 while nothing changed.
        return conditional_json(queue_body(queue))

    return bp
