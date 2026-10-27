"""Verified prescription uploads over HTTP (M7b-P6..P9; FR-UPL-01..05; spec prescription-uploads).

Under ``/api/v1/portal/prescription-uploads``, every route ``@patient``:

| Endpoint | What |
|---|---|
| ``POST ""`` | ``multipart/form-data`` with one part ``file``; 202, checked in the background |
| ``POST /by-code`` | ``{"code"}``: the printed code typed instead; 201, verified at once |
| ``GET /{upload_id}`` | the upload's state (polled while it is checked) |
| ``POST /{upload_id}/challenge`` | ``{"phone_last4"}``: the representative's check (R11, R12) |
| ``POST /{upload_id}/selection`` | ``{"choice": "UPLOADED" \\| "LATEST"}`` (R15) |
| ``DELETE /{upload_id}`` | withdraw: the file (if still held) and any grant go; 204 |

The request body is capped just above 10 MB before it is parsed (413). The response never holds
anything read from the file, and before verification nothing about the prescription (R11). An
upload is never served back: there is no file route, for the account or for staff (R17, D6).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field
from werkzeug.exceptions import UnsupportedMediaType

from mediease_api.application.uploads.intake import TypePrescriptionCode, UploadPrescription
from mediease_api.application.uploads.verify import (
    AnswerChallenge,
    ChooseVersion,
    GetUpload,
    UploadView,
    WithdrawUpload,
)
from mediease_api.delivery.http.access import current_patient, patient
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.uploads.upload import MAX_UPLOAD_BYTES, Choice

# R1: the file plus the multipart framing and a name; anything larger is refused unread.
MAX_UPLOAD_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024


class PrescriptionUploadUseCases(Protocol):
    def upload_prescription(self) -> UploadPrescription: ...
    def type_prescription_code(self) -> TypePrescriptionCode: ...
    def get_upload(self) -> GetUpload: ...
    def answer_upload_challenge(self) -> AnswerChallenge: ...
    def choose_upload_version(self) -> ChooseVersion: ...
    def withdraw_upload(self) -> WithdrawUpload: ...


class CodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80)


class ChallengeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_last4: str = Field(pattern=r"^[0-9]{4}$")


class SelectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: Literal["UPLOADED", "LATEST"]


def upload_body(view: UploadView) -> dict[str, Any]:
    v = view.verification
    return {
        "id": str(view.id),
        "state": view.state.value,
        "source": view.source,
        "rejection_code": view.rejection_code.value if view.rejection_code else None,
        "attempts_left": view.attempts_left,
        "created_at": view.created_at.isoformat(),
        "verification": (
            {
                "access": v.access.value,
                "clinic_name": v.clinic_name,
                "doctor_name": v.doctor_name,
                "version": v.version,
                "issued_at": v.issued_at.isoformat(),
                "superseded": v.superseded,
                "latest_version": v.latest_version,
                "latest_issued_at": v.latest_issued_at.isoformat() if v.latest_issued_at else None,
                "selected": v.selected.value if v.selected else None,
                "expires_at": v.expires_at.isoformat(),
            }
            if v
            else None
        ),
    }


def create_prescription_uploads_blueprint(use_cases: PrescriptionUploadUseCases) -> Blueprint:
    bp = Blueprint(
        "prescription_uploads", __name__, url_prefix="/api/v1/portal/prescription-uploads"
    )
    one = "/<uuid:upload_id>"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("")
    @patient
    def upload() -> tuple[Response, int]:
        request.max_content_length = MAX_UPLOAD_REQUEST_BYTES
        if request.mimetype != "multipart/form-data":
            raise UnsupportedMediaType("Send the prescription as multipart/form-data.")
        part = request.files.get("file")
        data = part.stream.read(MAX_UPLOAD_BYTES + 1) if part is not None else None
        view = use_cases.upload_prescription().execute(current_patient(), data, request_info())
        return jsonify(upload_body(view)), 202

    @bp.post("/by-code")
    @patient
    def by_code() -> tuple[Response, int]:
        body = parse_json(CodeIn)
        view = use_cases.type_prescription_code().execute(
            current_patient(), body.code, request_info()
        )
        return jsonify(upload_body(view)), 201

    @bp.get(one)
    @patient
    def get_upload(upload_id: UUID) -> Response:
        return jsonify(upload_body(use_cases.get_upload().execute(current_patient(), upload_id)))

    @bp.post(f"{one}/challenge")
    @patient
    def challenge(upload_id: UUID) -> Response:
        body = parse_json(ChallengeIn)
        view = use_cases.answer_upload_challenge().execute(
            current_patient(), upload_id, body.phone_last4, request_info()
        )
        return jsonify(upload_body(view))

    @bp.post(f"{one}/selection")
    @patient
    def selection(upload_id: UUID) -> Response:
        body = parse_json(SelectionIn)
        view = use_cases.choose_upload_version().execute(
            current_patient(), upload_id, Choice(body.choice)
        )
        return jsonify(upload_body(view))

    @bp.delete(one)
    @patient
    def withdraw(upload_id: UUID) -> tuple[str, int]:
        use_cases.withdraw_upload().execute(current_patient(), upload_id)
        return "", 204

    return bp
