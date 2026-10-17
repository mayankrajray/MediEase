"""Visits: start, read, edit, complete, addenda, a patient's history (M4-P1; FR-VIS-01..03, 05).

| Endpoint | Permission |
|---|---|
| ``POST /api/v1/visits`` | ``CLINICAL_WRITE`` (and the appointment's doctor) |
| ``GET /api/v1/visits/{visit_id}`` | ``CLINICAL_VIEW`` |
| ``PATCH /api/v1/visits/{visit_id}`` | ``CLINICAL_WRITE`` (and the visit's doctor) |
| ``POST /api/v1/visits/{visit_id}/complete`` | ``CLINICAL_WRITE`` (and the visit's doctor) |
| ``POST /api/v1/visits/{visit_id}/addenda`` | ``CLINICAL_WRITE`` (and the visit's doctor) |
| ``GET /api/v1/patients/{patient_id}/visits`` | ``CLINICAL_VIEW`` |

Front desk holds neither permission, so every route here is a 403 for them before anything is
read (spec §2). Clinical content: never logged, never cached (``no-store``), and validation errors
name the field, never the value (R17).
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.visits.use_cases import (
    DEFAULT_PAGE,
    MAX_PAGE,
    AddAddendum,
    CompleteVisit,
    GetConsultation,
    ListPatientVisits,
    StartVisit,
    UpdateVisit,
    VisitChanges,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import (
    addendum_body,
    consultation_body,
    visit_body,
    visit_summary_body,
)
from mediease_api.delivery.http.scheduling import _uuid_arg
from mediease_api.delivery.http.validation import RequestValidationFailed, parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.visits.visit import ADDENDUM_MAX, TEXT_LIMITS
from mediease_api.domain.visits.vitals import Vitals


class VisitUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def start_visit(self) -> StartVisit: ...
    def get_consultation(self) -> GetConsultation: ...
    def update_visit(self) -> UpdateVisit: ...
    def complete_visit(self) -> CompleteVisit: ...
    def add_addendum(self) -> AddAddendum: ...
    def list_patient_visits(self) -> ListPatientVisits: ...


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: UUID


class VitalsInput(BaseModel):
    """Numbers only; units and bounds are the domain's (``domain/visits/vitals.py``)."""

    model_config = ConfigDict(extra="forbid")

    bp_systolic: float | None = None
    bp_diastolic: float | None = None
    pulse: float | None = None
    temp_c: float | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    spo2: float | None = None
    resp_rate: float | None = None


class UpdateRequest(BaseModel):
    """Only the fields sent change; ``null`` clears one. ``revision`` is the one the screen has."""

    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    chief_complaint: str | None = Field(default=None, max_length=TEXT_LIMITS["chief_complaint"])
    findings: str | None = Field(default=None, max_length=TEXT_LIMITS["findings"])
    diagnosis: str | None = Field(default=None, max_length=TEXT_LIMITS["diagnosis"])
    notes: str | None = Field(default=None, max_length=TEXT_LIMITS["notes"])
    vitals: VitalsInput | None = None


class AddendumRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=ADDENDUM_MAX)


def _limit_arg() -> int:
    raw = request.args.get("limit")
    if raw is None or raw == "":
        return DEFAULT_PAGE
    try:
        return int(raw)
    except ValueError:
        raise RequestValidationFailed(
            [{"field": "limit", "reason": f"must be a number from 1 to {MAX_PAGE}"}]
        ) from None


def create_visits_blueprint(use_cases: VisitUseCases) -> Blueprint:
    bp = Blueprint("visits", __name__, url_prefix="/api/v1")
    one = "/visits/<uuid:visit_id>"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/visits")
    @clinic(Permission.CLINICAL_WRITE)
    def start_visit() -> tuple[Response, int]:
        body = parse_json(StartRequest)
        view = use_cases.start_visit().execute(
            current_context(), appointment_id=body.appointment_id
        )
        return jsonify(visit_body(view)), 201

    @bp.get(one)
    @clinic(Permission.CLINICAL_VIEW)
    def get_visit(visit_id: UUID) -> Response:
        view = use_cases.get_consultation().execute(current_context(), visit_id=visit_id)
        return jsonify(consultation_body(view))

    @bp.patch(one)
    @clinic(Permission.CLINICAL_WRITE)
    def update_visit(visit_id: UUID) -> Response:
        body = parse_json(UpdateRequest)
        sent = body.model_dump(exclude_unset=True)
        fields: dict[str, Any] = {k: v for k, v in sent.items() if k not in ("revision", "vitals")}
        if "vitals" in sent:
            fields["vitals"] = Vitals.parse(sent["vitals"] or {})
        view = use_cases.update_visit().execute(
            current_context(),
            visit_id=visit_id,
            changes=VisitChanges(seen_revision=body.revision, fields=fields),
        )
        return jsonify(visit_body(view))

    @bp.post(f"{one}/complete")
    @clinic(Permission.CLINICAL_WRITE)
    def complete_visit(visit_id: UUID) -> Response:
        view = use_cases.complete_visit().execute(current_context(), visit_id=visit_id)
        return jsonify(visit_body(view))

    @bp.post(f"{one}/addenda")
    @clinic(Permission.CLINICAL_WRITE)
    def add_addendum(visit_id: UUID) -> tuple[Response, int]:
        body = parse_json(AddendumRequest)
        addendum = use_cases.add_addendum().execute(
            current_context(), visit_id=visit_id, body=body.body
        )
        return jsonify(addendum_body(addendum)), 201

    @bp.get("/patients/<uuid:patient_id>/visits")
    @clinic(Permission.CLINICAL_VIEW)
    def list_patient_visits(patient_id: UUID) -> Response:
        page = use_cases.list_patient_visits().execute(
            current_context(),
            patient_id=patient_id,
            limit=_limit_arg(),
            before=_uuid_arg("before"),
        )
        return jsonify(
            {
                "items": [visit_summary_body(v) for v in page.items],
                "next_before": str(page.next_before) if page.next_before else None,
            }
        )

    return bp
