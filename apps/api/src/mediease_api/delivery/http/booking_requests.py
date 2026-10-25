"""Staff view of the clinic's online booking requests (M6b-P4; spec booking-requests R22).

``GET /api/v1/booking-requests`` (``APPOINTMENTS_MANAGE``): the open requests, oldest first, so
front desk can match or create the patient. Read-only here; accept, decline and propose are P5.
The reason is clinical text (C3) shown only to staff of this clinic; never logged or notified.
"""

from __future__ import annotations

from typing import Any, Protocol

from flask import Blueprint, Response, jsonify

from mediease_api.application.booking.requests import ListBookingRequests, StaffRequestItem
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import items_body
from mediease_api.domain.identity.permissions import Permission


class BookingRequestUseCases(Protocol):
    def list_booking_requests(self) -> ListBookingRequests: ...


def staff_request_body(r: StaffRequestItem) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "full_name": r.full_name,
        "age_years": r.age_years,
        "sex": r.sex.value if r.sex else None,
        "phone_e164": r.phone_e164,
        "reason": r.reason,
        "doctor_name": r.doctor_name,
        "mode": r.mode.value,
        "starts_at": r.starts_at.isoformat(),
        "created_at": r.created_at.isoformat(),
        "hold_expires_at": r.hold_expires_at.isoformat(),
        "holding": r.holding,
        "hold_overridden": r.hold_overridden,
        "respond_by": r.respond_by.isoformat(),
    }


def create_booking_requests_blueprint(use_cases: BookingRequestUseCases) -> Blueprint:
    bp = Blueprint("booking_requests", __name__, url_prefix="/api/v1/booking-requests")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def list_booking_requests() -> Response:
        return jsonify(
            items_body(
                staff_request_body(r)
                for r in use_cases.list_booking_requests().execute(current_context())
            )
        )

    return bp
