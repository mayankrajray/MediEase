"""Patients: register, look up, read and correct (M2-P2; FR-PAT-01..04, spec patients R1-R10).

| Endpoint | Permission |
|---|---|
| ``POST /api/v1/patients`` | ``PATIENTS_MANAGE`` |
| ``GET /api/v1/patients?q=`` | ``PATIENTS_MANAGE`` |
| ``GET /api/v1/patients/{patient_id}`` | ``PATIENTS_MANAGE`` |
| ``PATCH /api/v1/patients/{patient_id}`` | ``PATIENTS_MANAGE`` |

Every clinic role holds ``PATIENTS_MANAGE`` (PRD §8.1); ops users are refused on clinic routes
(spec identity-and-tenancy R10). The clinic comes from the request context, never from the
client, so another clinic's patient is a 404 (NFR-08).

Responses carry personal data and are never cached. The lookup returns ``{"items": [...]}``
capped at 20, so it needs no cursor yet.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mediease_api.application.patients.consent import (
    ConsentCommand,
    OptIn,
    OptOut,
    RecordConsent,
)
from mediease_api.application.patients.queries import GetPatient, LookupPatients
from mediease_api.application.patients.register_patient import (
    RegisterPatient,
    RegisterPatientCommand,
)
from mediease_api.application.patients.update_patient import UpdatePatient, UpdatePatientCommand
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import items_body, patient_body
from mediease_api.delivery.http.validation import RequestValidationFailed, parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.patients.patient import Language, Sex

MAX_QUERY_LENGTH = 100


class PatientUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def register_patient(self) -> RegisterPatient: ...
    def update_patient(self) -> UpdatePatient: ...
    def get_patient(self) -> GetPatient: ...
    def lookup_patients(self) -> LookupPatients: ...
    def record_consent(self) -> RecordConsent: ...
    def opt_out(self) -> OptOut: ...
    def opt_in(self) -> OptIn: ...


class NewPatientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    # The contact of record: the guardian's number for a patient under 18 (spec D1).
    phone: str = Field(min_length=1, max_length=20)
    sex: Sex
    # Exactly one of these two; the domain enforces it (I1) and names the field.
    date_of_birth: date | None = None
    age_years: int | None = Field(default=None, ge=0, le=120)
    guardian_name: str | None = Field(default=None, max_length=200)
    language: Language = Language.EN
    confirm_new: bool = False


class UpdatePatientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    sex: Sex | None = None
    date_of_birth: date | None = None
    age_years: int | None = Field(default=None, ge=0, le=120)
    # Blank clears it (refused for a minor); absent or null leaves it alone.
    guardian_name: str | None = Field(default=None, max_length=200)
    language: Language | None = None

    @model_validator(mode="after")
    def _at_least_one_change(self) -> UpdatePatientRequest:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("send at least one field to change")
        return self


class ConsentRequest(BaseModel):
    """The answer to "may we message you on WhatsApp, on SMS?"; both are required."""

    model_config = ConfigDict(extra="forbid", strict=True)

    whatsapp: bool
    sms: bool


def create_patients_blueprint(use_cases: PatientUseCases) -> Blueprint:
    bp = Blueprint("patients", __name__, url_prefix="/api/v1/patients")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        # Patient data is personal data: never cached by a browser or a proxy.
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("")
    @clinic(Permission.PATIENTS_MANAGE)
    def register_patient() -> tuple[Response, int]:
        body = parse_json(NewPatientRequest)
        patient = use_cases.register_patient().execute(
            current_context(),
            RegisterPatientCommand(
                full_name=body.full_name,
                phone=body.phone,
                sex=body.sex,
                date_of_birth=body.date_of_birth,
                age_years=body.age_years,
                guardian_name=body.guardian_name,
                language=body.language,
                confirm_new=body.confirm_new,
            ),
        )
        return jsonify(patient_body(patient)), 201

    @bp.get("")
    @clinic(Permission.PATIENTS_MANAGE)
    def lookup_patients() -> Response:
        text = request.args.get("q")
        if text is None:
            raise RequestValidationFailed([{"field": "q", "reason": "is required"}])
        if len(text) > MAX_QUERY_LENGTH:
            raise RequestValidationFailed(
                [{"field": "q", "reason": f"must be at most {MAX_QUERY_LENGTH} characters"}]
            )
        found = use_cases.lookup_patients().execute(current_context(), text)
        return jsonify(items_body(patient_body(p) for p in found))

    @bp.get("/<uuid:patient_id>")
    @clinic(Permission.PATIENTS_MANAGE)
    def get_patient(patient_id: UUID) -> Response:
        patient = use_cases.get_patient().execute(current_context(), patient_id)
        return jsonify(patient_body(patient))

    @bp.patch("/<uuid:patient_id>")
    @clinic(Permission.PATIENTS_MANAGE)
    def update_patient(patient_id: UUID) -> Response:
        body = parse_json(UpdatePatientRequest)
        patient = use_cases.update_patient().execute(
            current_context(),
            UpdatePatientCommand(
                patient_id=patient_id,
                full_name=body.full_name,
                phone=body.phone,
                sex=body.sex,
                date_of_birth=body.date_of_birth,
                age_years=body.age_years,
                guardian_name=body.guardian_name,
                language=body.language,
            ),
        )
        return jsonify(patient_body(patient))

    @bp.put("/<uuid:patient_id>/consent")
    @clinic(Permission.PATIENTS_MANAGE)
    def record_consent(patient_id: UUID) -> Response:
        body = parse_json(ConsentRequest)
        patient = use_cases.record_consent().execute(
            current_context(),
            ConsentCommand(patient_id=patient_id, whatsapp=body.whatsapp, sms=body.sms),
        )
        return jsonify(patient_body(patient))

    @bp.post("/<uuid:patient_id>/opt-out")
    @clinic(Permission.PATIENTS_MANAGE)
    def opt_out(patient_id: UUID) -> Response:
        return jsonify(patient_body(use_cases.opt_out().execute(current_context(), patient_id)))

    @bp.post("/<uuid:patient_id>/opt-in")
    @clinic(Permission.PATIENTS_MANAGE)
    def opt_in(patient_id: UUID) -> Response:
        body = parse_json(ConsentRequest)
        patient = use_cases.opt_in().execute(
            current_context(),
            ConsentCommand(patient_id=patient_id, whatsapp=body.whatsapp, sms=body.sms),
        )
        return jsonify(patient_body(patient))

    return bp
