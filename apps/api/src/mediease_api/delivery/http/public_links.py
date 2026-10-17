"""Public patient link routes (M4-P5; FR-RX-07, 08; spec prescriptions R9-R13, R19).

| Endpoint | Access |
|---|---|
| ``GET /api/v1/public/links/{token}`` | public |
| ``POST /api/v1/public/links/{token}/verify`` | public (last 4 digits) |
| ``GET /api/v1/public/links/{token}/prescription`` | public + ``X-Link-View`` from verify |

No session and no cookie here: the patient page's server (apps/web) keeps the view token in its
own HttpOnly cookie scoped to the page (decision 3A) and sends it as ``X-Link-View``. Responses
are never cached or indexed. The token is in the path, which the access log never records (it
logs the route template).
"""

from __future__ import annotations

from typing import Protocol

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.links.use_cases import DescribeLink, VerifyChallenge, ViewPrescription
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.bodies import patient_view_body
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import InvalidValue

VIEW_HEADER = "X-Link-View"


class PublicLinkUseCases(Protocol):
    def describe_link(self) -> DescribeLink: ...
    def verify_link(self) -> VerifyChallenge: ...
    def view_link_prescription(self) -> ViewPrescription: ...


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_last4: str = Field(pattern=r"^[0-9]{4}$")


def _language() -> Language | None:
    raw = request.args.get("lang")
    if raw is None:
        return None
    try:
        return Language(raw)
    except ValueError:
        raise InvalidValue("lang", "must be en or hi") from None


def create_public_links_blueprint(use_cases: PublicLinkUseCases) -> Blueprint:
    bp = Blueprint("public_links", __name__, url_prefix="/api/v1/public/links")

    @bp.after_request
    def _private(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @bp.get("/<token>")
    @public
    def describe_link(token: str) -> Response:
        summary = use_cases.describe_link().execute(token, request_info())
        return jsonify(
            {
                "clinic_name": summary.clinic_name,
                "language": summary.language.value,
                "locked": summary.locked,
                "challenge_required": True,
            }
        )

    @bp.post("/<token>/verify")
    @public
    def verify_link(token: str) -> Response:
        body = parse_json(VerifyRequest)
        opened = use_cases.verify_link().execute(token, body.phone_last4, request_info())
        return jsonify(
            {"view_token": opened.token, "view_expires_at": opened.expires_at.isoformat()}
        )

    @bp.get("/<token>/prescription")
    @public
    def view_link_prescription(token: str) -> Response:
        page = use_cases.view_link_prescription().execute(
            token, request.headers.get(VIEW_HEADER), _language(), request_info()
        )
        return jsonify(patient_view_body(page))

    return bp
