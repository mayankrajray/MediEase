"""The public clinic page and its availability (M6b-P4; FR-PUB-01, 04, FR-DIS-05, NFR-17, NFR-19).

| Endpoint | Access |
|---|---|
| ``GET /api/v1/public/clinics/{slug}`` | public |
| ``GET /api/v1/public/clinics/{slug}/availability?doctor_id=&from=`` | public |
| ``GET /api/v1/public/sitemap`` (M6c-P5) | public |

No session. A clinic that is not ``has_public_page`` is exactly an unknown slug: the same 404. The
body is an **allow-list**: nothing but what a clinic publishes (a test fails on any other field).
Never cached. The JSON is ``noindex``; the web page is indexable only when ``indexable`` is
true (M6c-P5, FR-DIS-06: discoverable and not opted out).
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
    GetSitemap,
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
        # M6c-P5 (FR-DIS-03, 06).
        "specialties",
        "indexable",
    }
)
DOCTOR_FIELDS = frozenset(
    {"id", "display_name", "qualification", "specialty", "hours", "languages", "fee_paise"}
)


class PublicClinicUseCases(Protocol):
    def get_public_clinic(self) -> GetPublicClinic: ...
    def get_availability(self) -> GetAvailability: ...
    def get_sitemap(self) -> GetSitemap: ...


def _via_directory() -> bool:
    """M6c-P7 (discovery R11): ``via=directory`` asks for the discoverability rule too."""
    via = request.args.get("via")
    if via not in (None, "directory"):
        raise InvalidValue("via", "must be directory")
    return via == "directory"


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
        "specialties": list(c.specialties),
        "indexable": view.indexable,
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
                "languages": list(d.languages),
                "fee_paise": d.fee_paise,
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
        view = use_cases.get_public_clinic().execute(
            slug, request_info(), via_directory=_via_directory()
        )
        return jsonify(public_clinic_body(view))

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
        days = use_cases.get_availability().execute(
            slug, doctor_id, first, request_info(), via_directory=_via_directory()
        )
        return jsonify(availability_body(list(days)))

    return bp


def create_public_sitemap_blueprint(
    use_cases: PublicClinicUseCases, *, public_base_url: str
) -> Blueprint:
    """M6c-P5 (R63): the indexable profiles as absolute URLs, for the web app's sitemap.xml."""
    bp = Blueprint("public_sitemap", __name__, url_prefix="/api/v1/public/sitemap")
    base = public_base_url.rstrip("/")

    @bp.after_request
    def _private(response: Response) -> Response:
        response.headers["Cache-Control"] = "public, max-age=3600"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @bp.get("")
    @public
    def sitemap() -> Response:
        items = []
        for entry in use_cases.get_sitemap().execute():
            clinic_url = f"{base}/c/{entry.slug}"
            items.append({"loc": clinic_url, "lastmod": entry.updated_at.isoformat()})
            items.extend(
                {"loc": f"{clinic_url}/doctors/{d}", "lastmod": entry.updated_at.isoformat()}
                for d in entry.doctor_ids
            )
        return jsonify({"base_url": base, "items": items})

    return bp
