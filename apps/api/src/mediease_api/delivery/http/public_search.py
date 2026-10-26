"""Directory search (M6c-P6; FR-DIS-01, 02, 04, 05; spec discovery R1-R10; ADR-0021).

| Endpoint | Access |
|---|---|
| ``GET /api/v1/public/search/clinics?q=&city=&pincode=&specialty=&language=&available=`` | public |
| ``GET /api/v1/public/search/doctors?...`` (the same filters) | public |

No session, rate limited per caller like the public page. The bodies are **allow-lists** of what
a clinic publishes (a test fails on any other key). Never cached by a proxy, ``noindex``.
"""

from __future__ import annotations

from typing import Any, Protocol

from flask import Blueprint, Response, jsonify, request

from mediease_api.application.discovery.search import (
    ClinicHit,
    DoctorHit,
    SearchClinics,
    SearchDoctors,
    SearchOptions,
    SearchQuery,
)
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.request_info import request_info
from mediease_api.domain.shared.errors import InvalidValue

CLINIC_HIT_FIELDS = frozenset(
    {
        "slug",
        "name",
        "address_line",
        "city",
        "state",
        "pincode",
        "specialties",
        "doctors",
        "next_available",
    }
)
CLINIC_HIT_DOCTOR_FIELDS = frozenset({"id", "display_name", "specialty"})
DOCTOR_HIT_FIELDS = frozenset(
    {
        "id",
        "display_name",
        "qualification",
        "specialty",
        "languages",
        "fee_paise",
        "next_available",
        "clinic",
    }
)
DOCTOR_HIT_CLINIC_FIELDS = frozenset({"slug", "name", "city", "state", "pincode"})


class SearchUseCases(Protocol):
    def search_clinics(self) -> SearchClinics: ...
    def search_doctors(self) -> SearchDoctors: ...


def _query() -> SearchQuery:
    args = request.args
    available = args.get("available", "false").lower()
    if available not in {"true", "false", "1", "0"}:
        raise InvalidValue("available", "must be true or false")
    return SearchQuery(
        q=args.get("q", ""),
        city=args.get("city"),
        pincode=args.get("pincode"),
        specialty=args.get("specialty"),
        language=args.get("language"),
        available=available in {"true", "1"},
    )


def _options() -> dict[str, Any]:
    options = SearchOptions()
    return {"specialties": list(options.specialties), "languages": list(options.languages)}


def clinic_hit_body(hit: ClinicHit) -> dict[str, Any]:
    c = hit.clinic
    return {
        "slug": c.slug,
        "name": c.name,
        "address_line": c.address_line,
        "city": c.city,
        "state": c.state,
        "pincode": c.pincode,
        "specialties": list(c.specialties),
        "doctors": [
            {"id": str(d.id), "display_name": d.display_name, "specialty": d.specialty}
            for d in hit.doctors
        ],
        "next_available": hit.next_available.isoformat() if hit.next_available else None,
    }


def doctor_hit_body(hit: DoctorHit) -> dict[str, Any]:
    d, c = hit.doctor, hit.clinic
    return {
        "id": str(d.id),
        "display_name": d.display_name,
        "qualification": d.qualification,
        "specialty": d.specialty,
        "languages": list(d.languages),
        "fee_paise": d.fee_paise,
        "next_available": hit.next_available.isoformat() if hit.next_available else None,
        "clinic": {
            "slug": c.slug,
            "name": c.name,
            "city": c.city,
            "state": c.state,
            "pincode": c.pincode,
        },
    }


def create_public_search_blueprint(use_cases: SearchUseCases) -> Blueprint:
    bp = Blueprint("public_search", __name__, url_prefix="/api/v1/public/search")

    @bp.after_request
    def _private(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @bp.get("/clinics")
    @public
    def clinics() -> Response:
        hits = use_cases.search_clinics().execute(_query(), request_info())
        return jsonify({"items": [clinic_hit_body(h) for h in hits], "options": _options()})

    @bp.get("/doctors")
    @public
    def doctors() -> Response:
        hits = use_cases.search_doctors().execute(_query(), request_info())
        return jsonify({"items": [doctor_hit_body(h) for h in hits], "options": _options()})

    return bp
