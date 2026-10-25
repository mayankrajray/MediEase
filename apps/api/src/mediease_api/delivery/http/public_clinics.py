"""The public clinic page and its availability (M6b-P4; FR-PUB-01, 04, FR-DIS-05, NFR-17, NFR-19).

| Endpoint | Access |
|---|---|
| ``GET /api/v1/public/clinics/{slug}`` | public |
| ``GET /api/v1/public/clinics/{slug}/availability?doctor_id=&from=`` | public |

No session. A clinic that is not ``has_public_page`` is exactly an unknown slug: the same 404. The
body is an **allow-list**: nothing but what a clinic publishes (a test fails on any other field).
Never cached, and ``noindex`` until M6c (FR-DIS-06).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request

from mediease_api.application.booking.public import (
    DayOffer,
    GetAvailability,
    GetPublicClinic,
    PublicClinic,
)
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.request_info import request_info
from mediease_api.domain.shared.errors import InvalidValue

# NFR-17: the only keys a public body may carry.
CLINIC_FIELDS = frozenset(
    {
        "name",
        "slug",
        "address_line",
        "city",
        "state",
        "pincode",
        "phone_e164",
        "timezone",
        "booking_mode",
        "map_url",
        "requires_age_sex",
        "doctors",
    }
)
DOCTOR_FIELDS = frozenset({"id", "display_name", "qualification", "specialty", "hours"})


class PublicClinicUseCases(Protocol):
    def get_public_clinic(self) -> GetPublicClinic: ...
    def get_availability(self) -> GetAvailability: ...


def _hhmm(value: Any) -> str:
    return str(value.strftime("%H:%M"))


def public_clinic_body(view: PublicClinic) -> dict[str, Any]:
    c = view.clinic
    return {
        "name": c.name,
        "slug": c.slug,
        "address_line": c.address_line,
        "city": c.city,
        "state": c.state,
        "pincode": c.pincode,
        "phone_e164": c.phone.e164 if c.phone else None,
        "timezone": c.timezone,
        "booking_mode": c.booking_mode.value,
        "map_url": view.map_url,
        "requires_age_sex": c.request_requires_age_sex,
        "doctors": [
            {
                "id": str(d.id),
                "display_name": d.display_name,
                "qualification": d.qualification,
                "specialty": d.specialty,
                "hours": [
                    {"weekday": h.weekday, "start": _hhmm(h.start), "end": _hhmm(h.end)}
                    for h in d.hours
                ],
            }
            for d in view.doctors
        ],
    }


def availability_body(days: list[DayOffer] | Any) -> dict[str, Any]:
    return {
        "days": [
            {
                "date": day.on_date.isoformat(),
                "sessions": [
                    {
                        "starts_at": s.starts_at.isoformat(),
                        "ends_at": s.ends_at.isoformat(),
                        "mode": s.mode.value,
                        "places_left": s.places_left,
                        "slots": [
                            {"starts_at": x.starts_at.isoformat(), "ends_at": x.ends_at.isoformat()}
                            for x in s.slots
                        ],
                    }
                    for s in day.sessions
                ],
            }
            for day in days
        ]
    }


def create_public_clinics_blueprint(use_cases: PublicClinicUseCases) -> Blueprint:
    bp = Blueprint("public_clinics", __name__, url_prefix="/api/v1/public/clinics")

    @bp.after_request
    def _private(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @bp.get("/<string(maxlength=63):slug>")
    @public
    def get_clinic(slug: str) -> Response:
        return jsonify(
            public_clinic_body(use_cases.get_public_clinic().execute(slug, request_info()))
        )

    @bp.get("/<string(maxlength=63):slug>/availability")
    @public
    def availability(slug: str) -> Response:
        try:
            doctor_id = UUID(request.args.get("doctor_id", ""))
        except ValueError:
            raise InvalidValue("doctor_id", "must be an ID") from None
        raw = request.args.get("from")
        try:
            first = date.fromisoformat(raw) if raw else None
        except ValueError:
            raise InvalidValue("from", "must be a date as YYYY-MM-DD") from None
        days = use_cases.get_availability().execute(slug, doctor_id, first, request_info())
        return jsonify(availability_body(list(days)))

    return bp
