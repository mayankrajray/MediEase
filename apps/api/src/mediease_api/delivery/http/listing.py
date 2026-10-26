"""The owner's directory listing (M6c-P4; FR-ONB-09, 10; spec R50-R55).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/clinic/listing`` | ``CLINIC_VIEW`` |
| ``PUT /api/v1/clinic/listing`` | ``CLINIC_MANAGE`` |
| ``PUT /api/v1/clinic/listing/doctors/{doctor_id}`` | ``CLINIC_MANAGE`` |

Each answers the whole listing: whether it is listed and discoverable, the problems in the way,
and each doctor's state with its own problems, so the screen never computes a rule.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict

from mediease_api.application.clinics.listing import (
    GetListing,
    Listing,
    SetDoctorVisibility,
    SetListing,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission


class ListedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listed: bool


class VisibleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible: bool


class ListingUseCases(Protocol):
    def get_listing(self) -> GetListing: ...
    def set_listing(self) -> SetListing: ...
    def set_doctor_visibility(self) -> SetDoctorVisibility: ...


def listing_body(listing: Listing) -> dict[str, Any]:
    c = listing.clinic
    return {
        "listed": c.listed,
        "listed_at": c.listed_at.isoformat() if c.listed_at else None,
        "verified": c.is_verified,
        "discoverable": listing.discoverable,
        "problems": [p.value for p in listing.problems],
        "doctors": [
            {
                "id": str(d.doctor.id),
                "display_name": d.doctor.display_name,
                "is_active": d.doctor.is_active,
                "verified": d.doctor.is_verified,
                "visible": d.doctor.visible,
                "has_schedule": d.has_schedule,
                "can_be_visible": d.can_be_visible,
                "problems": [p.value for p in d.problems],
            }
            for d in listing.doctors
        ],
    }


def create_listing_blueprint(use_cases: ListingUseCases) -> Blueprint:
    bp = Blueprint("listing", __name__, url_prefix="/api/v1/clinic/listing")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.CLINIC_VIEW)
    def get_listing() -> Response:
        return jsonify(listing_body(use_cases.get_listing().execute(current_context())))

    @bp.put("")
    @clinic(Permission.CLINIC_MANAGE)
    def set_listing() -> Response:
        body = parse_json(ListedIn)
        return jsonify(
            listing_body(use_cases.set_listing().execute(current_context(), body.listed))
        )

    @bp.put("/doctors/<uuid:doctor_id>")
    @clinic(Permission.CLINIC_MANAGE)
    def set_visibility(doctor_id: UUID) -> Response:
        body = parse_json(VisibleIn)
        listing = use_cases.set_doctor_visibility().execute(
            current_context(), doctor_id, body.visible
        )
        return jsonify(listing_body(listing))

    return bp
