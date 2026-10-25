"""The clinic's inbox of online booking requests (M6b-P4, P5; spec booking-requests R22, R31-R47).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/booking-requests?state=open|answered`` | ``APPOINTMENTS_MANAGE`` |
| ``GET /api/v1/booking-requests/{id}/candidates`` | ``APPOINTMENTS_MANAGE`` |
| ``POST /api/v1/booking-requests/{id}/accept`` | ``APPOINTMENTS_MANAGE`` (+ new record: patients) |
| ``POST /api/v1/booking-requests/{id}/decline`` | ``APPOINTMENTS_MANAGE`` |
| ``POST /api/v1/booking-requests/{id}/propose`` | ``APPOINTMENTS_MANAGE`` (+ new record: ditto) |

The reason and the staff note are clinical or internal text for this clinic's staff only; never
logged or notified. A second answer to the same request is 409 ``BKG_ALREADY_ANSWERED``.
"""

from __future__ import annotations

from datetime import UTC, date
from typing import Any, Literal, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from mediease_api.application.auth.errors import PermissionDenied
from mediease_api.application.booking.answers import (
    AcceptBookingRequest,
    AnswerResult,
    CandidateList,
    DeclineBookingRequest,
    ListRequestCandidates,
    NewRecord,
    ProposeBookingTime,
    RecordChoice,
)
from mediease_api.application.booking.requests import (
    ListBookingRequests,
    StaffRequestItem,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.booking.request import DeclineReason
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.patients.patient import Sex
from mediease_api.domain.shared.errors import InvalidValue


class BookingRequestUseCases(Protocol):
    def list_booking_requests(self) -> ListBookingRequests: ...
    def accept_booking_request(self) -> AcceptBookingRequest: ...
    def decline_booking_request(self) -> DeclineBookingRequest: ...
    def propose_booking_time(self) -> ProposeBookingTime: ...
    def list_request_candidates(self) -> ListRequestCandidates: ...


StaffReason = Literal[
    "TIME_UNAVAILABLE", "DOCTOR_UNAVAILABLE", "PLEASE_CALL", "NOT_ONLINE", "DUPLICATE", "OTHER"
]


class NewRecordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sex: Sex | None = None
    age_years: int | None = Field(default=None, ge=0, le=120)
    date_of_birth: date | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=200)


class RecordBody(BaseModel):
    """Exactly one of ``patient_id`` and ``new_patient`` (R36, R37)."""

    model_config = ConfigDict(extra="forbid")

    patient_id: UUID | None = None
    new_patient: NewRecordBody | None = None


class DeclineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: StaffReason
    note: str | None = Field(default=None, max_length=200)


class ProposeBody(RecordBody):
    session_id: UUID
    slot_start: AwareDatetime | None = None


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def staff_request_body(r: StaffRequestItem) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "status": r.status.value,
        "full_name": r.full_name,
        "age_years": r.age_years,
        "sex": r.sex.value if r.sex else None,
        "phone_e164": r.phone_e164,
        "reason": r.reason,
        "doctor_id": str(r.doctor_id) if r.doctor_id else None,
        "doctor_name": r.doctor_name,
        "mode": r.mode.value,
        "session_id": str(r.session_id) if r.session_id else None,
        "starts_at": r.starts_at.isoformat(),
        "original_starts_at": _iso(r.original_starts_at),
        "created_at": r.created_at.isoformat(),
        "hold_expires_at": r.hold_expires_at.isoformat(),
        "holding": r.holding,
        "hold_overridden": r.hold_overridden,
        "respond_by": r.respond_by.isoformat(),
        "patient_id": str(r.patient_id) if r.patient_id else None,
        "patient_code": r.patient_code,
        "appointment_id": str(r.appointment_id) if r.appointment_id else None,
        "answered_at": _iso(r.answered_at),
        "answered_by_name": r.answered_by_name,
        "decided_at": _iso(r.decided_at),
        "decided_by": r.decided_by.value if r.decided_by else None,
        "decline_reason": r.decline_reason.value if r.decline_reason else None,
        "decline_note": r.decline_note,
    }


def answer_body(result: AnswerResult) -> dict[str, Any]:
    return {
        "id": str(result.request_id),
        "status": result.status.value,
        "patient_id": str(result.patient_id) if result.patient_id else None,
        "appointment_id": str(result.appointment_id) if result.appointment_id else None,
    }


def candidates_body(c: CandidateList) -> dict[str, Any]:
    return {
        "linked": c.linked,
        "items": [
            {
                "id": str(i.id),
                "code": i.code,
                "full_name": i.full_name,
                "age_years": i.age_years,
                "no_shows": i.no_shows,
            }
            for i in c.items
        ],
        "suggested": {
            "full_name": c.suggested_name,
            "age_years": c.suggested_age_years,
            "sex": c.suggested_sex.value if c.suggested_sex else None,
        },
    }


def _choice(body: RecordBody) -> RecordChoice:
    if body.new_patient is not None:
        # R34, R40: creating a record needs the permission registration needs.
        ctx = current_context()
        if Permission.PATIENTS_MANAGE not in ctx.permissions:
            raise PermissionDenied(permission=Permission.PATIENTS_MANAGE.value, role=ctx.role.value)
        n = body.new_patient
        if n.date_of_birth is not None and n.age_years is not None:
            raise InvalidValue("new_patient", "give an age or a date of birth, not both")
        return RecordChoice(
            new=NewRecord(
                sex=n.sex,
                age_years=n.age_years,
                date_of_birth=n.date_of_birth,
                full_name=n.full_name,
            )
        )
    return RecordChoice(patient_id=body.patient_id)


def create_booking_requests_blueprint(use_cases: BookingRequestUseCases) -> Blueprint:
    bp = Blueprint("booking_requests", __name__, url_prefix="/api/v1/booking-requests")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def list_booking_requests() -> Response:
        state = request.args.get("state", "open")
        if state not in ("open", "answered"):
            raise InvalidValue("state", "must be open or answered")
        inbox = use_cases.list_booking_requests().execute(current_context(), state)
        return jsonify(
            {
                "items": [staff_request_body(r) for r in inbox.items],
                "open_count": inbox.open_count,
                "expired_7d": inbox.expired_7d,
            }
        )

    @bp.get("/<uuid:request_id>/candidates")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def candidates(request_id: UUID) -> Response:
        return jsonify(
            candidates_body(
                use_cases.list_request_candidates().execute(current_context(), request_id)
            )
        )

    @bp.post("/<uuid:request_id>/accept")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def accept(request_id: UUID) -> tuple[Response, int]:
        body = parse_json(RecordBody)
        result = use_cases.accept_booking_request().execute(
            current_context(), request_id, _choice(body)
        )
        return jsonify(answer_body(result)), 201

    @bp.post("/<uuid:request_id>/decline")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def decline(request_id: UUID) -> Response:
        body = parse_json(DeclineBody)
        result = use_cases.decline_booking_request().execute(
            current_context(), request_id, DeclineReason(body.reason), body.note
        )
        return jsonify(answer_body(result))

    @bp.post("/<uuid:request_id>/propose")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def propose(request_id: UUID) -> Response:
        body = parse_json(ProposeBody)
        result = use_cases.propose_booking_time().execute(
            current_context(),
            request_id,
            session_id=body.session_id,
            slot_start=body.slot_start.astimezone(UTC) if body.slot_start else None,
            choice=_choice(body),
        )
        return jsonify(answer_body(result))

    return bp
