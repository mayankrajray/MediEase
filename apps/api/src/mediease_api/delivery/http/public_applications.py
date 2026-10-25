"""Applying to join MediEase (M6c-P1; FR-ONB-01, 07; spec clinic-onboarding R1-R18).

| Endpoint | Access |
|---|---|
| ``POST /api/v1/public/applications`` (multipart) | public |
| ``POST /api/v1/public/applications/confirm`` | public |

No session. The submission is ``multipart/form-data``: a part ``application`` (JSON) and one file
part ``certificate_<n>`` per doctor position ``n`` (1-based), at most 30 MB in all (413 before
parsing). Field errors name the field with 1-based doctor positions (``doctors.1.name``).
Never cached, never indexed. Both routes are CSRF-exempt: they carry no session's authority.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Protocol

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from werkzeug.exceptions import UnsupportedMediaType

from mediease_api.application.onboarding.submit import ConfirmApplication, SubmitApplication
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import RequestValidationFailed, parse_json
from mediease_api.domain.onboarding.application import (
    MAX_DOCTORS,
    ApplicationInput,
    ApplicationKind,
    DoctorInput,
)
from mediease_api.domain.onboarding.certificate import MAX_CERTIFICATE_BYTES

# R1: the whole request, files included.
MAX_SUBMISSION_BYTES = 30 * 1024 * 1024


class DoctorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    qualification: str = Field(max_length=200)
    council: str = Field(max_length=200)
    registration_number: str = Field(max_length=80)
    is_owner: bool = False


class ApplicationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["CLINIC", "SOLO_DOCTOR"]
    clinic_name: str = Field(max_length=200)
    address_line: str = Field(max_length=300)
    city: str = Field(max_length=100)
    state: str = Field(max_length=100)
    pincode: str = Field(max_length=6)
    clinic_phone: str = Field(max_length=20)
    specialties: list[str] = Field(max_length=10)
    owner_name: str = Field(max_length=200)
    owner_phone: str = Field(max_length=20)
    owner_email: str = Field(max_length=254)
    owner_practises: bool
    doctors: list[DoctorIn] = Field(min_length=1, max_length=MAX_DOCTORS)
    # R8: a field people never see or fill; anything in it marks a bot.
    website: str = Field(default="", max_length=200)


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=200)


class ApplicationUseCases(Protocol):
    def submit_application(self) -> SubmitApplication: ...
    def confirm_application(self) -> ConfirmApplication: ...


def _field(loc: tuple[int | str, ...]) -> str:
    """Pydantic's location with doctor positions counted from 1, as the form shows them."""
    parts = [
        str(p + 1) if i == 1 and loc[0] == "doctors" and isinstance(p, int) else str(p)
        for i, p in enumerate(loc)
    ]
    return ".".join(parts) or "application"


def _parse_application() -> ApplicationIn:
    raw = request.form.get("application")
    if raw is None:
        raise RequestValidationFailed([{"field": "application", "reason": "is required"}])
    try:
        body = json.loads(raw)
    except ValueError:
        raise RequestValidationFailed(
            [{"field": "application", "reason": "must be a JSON object"}]
        ) from None
    if not isinstance(body, dict):
        raise RequestValidationFailed([{"field": "application", "reason": "must be a JSON object"}])
    try:
        return ApplicationIn.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationFailed(
            [
                {"field": _field(tuple(err["loc"])), "reason": err["msg"]}
                for err in exc.errors(include_input=False, include_url=False)
            ]
        ) from None


def _files(count: int) -> dict[int, bytes]:
    """Each doctor's file, read to one byte past the limit so the domain can say "too large"."""
    files: dict[int, bytes] = {}
    for position in range(1, count + 1):
        part = request.files.get(f"certificate_{position}")
        if part is not None:
            files[position] = part.stream.read(MAX_CERTIFICATE_BYTES + 1)
    return files


def _input(body: ApplicationIn) -> ApplicationInput:
    return ApplicationInput(
        kind=ApplicationKind(body.kind),
        clinic_name=body.clinic_name,
        address_line=body.address_line,
        city=body.city,
        state=body.state,
        pincode=body.pincode,
        clinic_phone=body.clinic_phone,
        specialties=tuple(body.specialties),
        owner_name=body.owner_name,
        owner_phone=body.owner_phone,
        owner_email=body.owner_email,
        owner_practises=body.owner_practises,
        doctors=tuple(
            DoctorInput(
                name=d.name,
                qualification=d.qualification,
                council=d.council,
                registration_number=d.registration_number,
                is_owner=d.is_owner,
            )
            for d in body.doctors
        ),
    )


def receipt_body(reference: str, email_masked: str) -> dict[str, Any]:
    return {"reference": reference, "email_masked": email_masked}


def create_public_applications_blueprint(use_cases: ApplicationUseCases) -> Blueprint:
    bp = Blueprint("public_applications", __name__, url_prefix="/api/v1/public/applications")

    @bp.after_request
    def _private(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @bp.post("")
    @public
    def submit() -> tuple[Response, int]:
        request.max_content_length = MAX_SUBMISSION_BYTES
        if request.mimetype != "multipart/form-data":
            raise UnsupportedMediaType("Send the application as multipart/form-data.")
        body = _parse_application()
        receipt = use_cases.submit_application().execute(
            _input(body), _files(len(body.doctors)), request_info(), honeypot=body.website
        )
        return jsonify(receipt_body(receipt.reference, receipt.email_masked)), 202

    @bp.post("/confirm")
    @public
    def confirm() -> Response:
        body = parse_json(ConfirmIn)
        reference = use_cases.confirm_application().execute(body.token, request_info())
        return jsonify({"reference": reference})

    return bp
