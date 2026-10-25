"""The public live-queue page's data (M6b-P6; FR-QUE-06; portal spec R70, R71; ADR-0019).

``GET /api/v1/public/queue/{token}``: no sign-in. The body is the clinic, the doctor, the mode,
the patient's own token or slot, ``ahead``, what is being seen now and a state; never a name,
phone, reason or age. ETag (304 when unchanged), never cached, ``noindex``; an invalid token is
404 ``LINK_INVALID``, an expired one 410 ``LINK_EXPIRED``, too many reads 429 with Retry-After.
"""

from __future__ import annotations

from typing import Any, Protocol

from flask import Blueprint, Response

from mediease_api.application.appointments.live import GetLiveQueue, LiveQueue
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.etag import conditional_json
from mediease_api.delivery.http.request_info import request_info

# R70: the only keys the public body may carry (a test fails on any other).
LIVE_FIELDS = frozenset(
    {
        "clinic_name",
        "doctor_name",
        "timezone",
        "mode",
        "state",
        "token_number",
        "slot_start",
        "ahead",
        "now_seeing_token",
        "now_seeing_slot",
        "session_starts_at",
    }
)


class PublicQueueUseCases(Protocol):
    def get_live_queue(self) -> GetLiveQueue: ...


def live_body(q: LiveQueue) -> dict[str, Any]:
    v = q.view
    return {
        "clinic_name": q.clinic_name,
        "doctor_name": q.doctor_name,
        "timezone": q.timezone,
        "mode": q.mode.value,
        "state": v.state.value,
        "token_number": v.token_number,
        "slot_start": v.slot_start.isoformat() if v.slot_start else None,
        "ahead": v.ahead,
        "now_seeing_token": v.now_seeing_token,
        "now_seeing_slot": v.now_seeing_slot.isoformat() if v.now_seeing_slot else None,
        "session_starts_at": q.session_starts_at.isoformat(),
    }


def create_public_queue_blueprint(use_cases: PublicQueueUseCases) -> Blueprint:
    bp = Blueprint("public_queue", __name__, url_prefix="/api/v1/public/queue")

    @bp.after_request
    def _private(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @bp.get("/<string(maxlength=200):token>")
    @public
    def live_queue(token: str) -> Response:
        return conditional_json(
            live_body(use_cases.get_live_queue().execute(token, request_info()))
        )

    return bp
