"""The reviewer's routes for clinic applications (M6c-P2; FR-ONB-03, 05; spec R24-R41).

| Endpoint | Access |
|---|---|
| ``GET /api/v1/ops/applications?queue=waiting|review|decided`` | ``@reviewer`` |
| ``GET /api/v1/ops/applications/{id}`` | ``@reviewer`` (audited) |
| ``GET /api/v1/ops/applications/{id}/doctors/{doctor_id}/certificate`` | ``@reviewer`` (audited) |
| ``POST /api/v1/ops/applications/{id}/take`` | ``@reviewer`` |
| ``PUT /api/v1/ops/applications/{id}/doctors/{doctor_id}/check`` | ``@reviewer`` |
| ``POST /api/v1/ops/applications/{id}/reject`` | ``@reviewer`` |
| ``POST /api/v1/ops/applications/{id}/approve`` (P3) | ``@reviewer`` |

Never cached. A certificate is streamed with its stored type, ``inline``, ``nosniff`` and a
sandboxing CSP, never by a public or pre-signed URL.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.context import Actor
from mediease_api.application.onboarding.approve import (
    ApproveApplication,
    ApproveCommand,
    VerifyClinic,
    VerifyDoctor,
)
from mediease_api.application.onboarding.review import (
    QUEUES,
    ApplicationDetail,
    CheckCommand,
    CheckDoctor,
    GetApplication,
    GetCertificate,
    ListReviewQueue,
    RejectApplication,
    TakeApplication,
)
from mediease_api.delivery.http.access import current_principal, reviewer
from mediease_api.delivery.http.bodies import clinic_body
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.onboarding.application import CheckResult, RejectReason
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.ports.onboarding import ApplicationSummary


class CheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    register_checked: bool
    certificate_matches: bool
    result: Literal["VERIFIED", "NOT_VERIFIED"]
    note: str | None = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal[
        "REGISTRATION_NOT_FOUND",
        "CERTIFICATE_UNCLEAR",
        "DETAILS_DO_NOT_MATCH",
        "NOT_ELIGIBLE",
        "DUPLICATE",
        "OTHER",
    ]
    message: str | None = Field(default=None, max_length=500)


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=3, max_length=63)
    booking_mode: BookingMode = BookingMode.TOKENS
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    clinic_name: str | None = Field(default=None, max_length=200)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=6)


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    register_checked: bool
    certificate_matches: bool


class ReviewUseCases(Protocol):
    def list_review_queue(self) -> ListReviewQueue: ...
    def get_application(self) -> GetApplication: ...
    def get_application_certificate(self) -> GetCertificate: ...
    def take_application(self) -> TakeApplication: ...
    def check_application_doctor(self) -> CheckDoctor: ...
    def reject_application(self) -> RejectApplication: ...
    def approve_application(self) -> ApproveApplication: ...
    def verify_clinic_doctor(self) -> VerifyDoctor: ...
    def verify_clinic(self) -> VerifyClinic: ...


def _actor() -> Actor:
    return Actor.for_user(current_principal().user, request_info())


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def summary_body(a: ApplicationSummary) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "reference": a.reference,
        "kind": a.kind.value,
        "status": a.status.value,
        "clinic_name": a.clinic_name,
        "city": a.city,
        "doctors": a.doctors,
        "submitted_at": a.submitted_at.isoformat(),
        "email_verified_at": a.email_verified_at.isoformat(),
        "taken_at": _iso(a.taken_at),
        "decided_at": _iso(a.decided_at),
        "possible_duplicate": a.possible_duplicate,
    }


def detail_body(detail: ApplicationDetail) -> dict[str, Any]:
    a = detail.application
    doctors = []
    for d in a.doctors:
        assert d.id is not None and d.certificate is not None
        check = detail.checks.get(d.id)
        doctors.append(
            {
                "id": str(d.id),
                "position": d.position,
                "name": d.name,
                "qualification": d.qualification,
                "council": d.council,
                "registration_number": d.registration_number,
                "is_owner": d.is_owner,
                "certificate": {
                    "content_type": d.certificate.content_type,
                    "size": d.certificate.size,
                },
                "check": None
                if check is None
                else {
                    "register_checked": check.register_checked,
                    "certificate_matches": check.certificate_matches,
                    "result": check.result.value,
                    "note": check.note,
                    "checked_at": check.checked_at.isoformat(),
                    "checked_by": str(check.checked_by),
                },
            }
        )
    return {
        "id": str(a.id),
        "reference": a.reference,
        "kind": a.kind.value,
        "status": a.status.value,
        "clinic_name": a.clinic_name,
        "address_line": a.address_line,
        "city": a.city,
        "state": a.state,
        "pincode": a.pincode,
        "clinic_phone_e164": a.clinic_phone.e164,
        "specialties": list(a.specialties),
        "owner_name": a.owner_name,
        "owner_phone_e164": a.owner_phone.e164,
        "owner_email": a.owner_email.value,
        "owner_practises": a.owner_practises,
        "submitted_at": a.submitted_at.isoformat(),
        "email_verified_at": _iso(a.email_verified_at),
        "taken_by": str(a.taken_by) if a.taken_by else None,
        "taken_at": _iso(a.taken_at),
        "decided_at": _iso(a.decided_at),
        "decision_reason": a.decision_reason.value if a.decision_reason else None,
        "decision_message": a.decision_message,
        "duplicate_of": list(a.duplicate_of),
        "clinic_id": str(a.clinic_id) if a.clinic_id else None,
        "all_verified": detail.all_verified,
        "doctors": doctors,
    }


def create_ops_applications_blueprint(use_cases: ReviewUseCases) -> Blueprint:
    bp = Blueprint("ops_applications", __name__, url_prefix="/api/v1/ops/applications")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @reviewer
    def list_applications() -> Response:
        queue = request.args.get("queue")
        if queue is not None and queue not in QUEUES:
            raise InvalidValue("queue", "must be waiting, review or decided")
        items = use_cases.list_review_queue().execute(queue)
        return jsonify({"items": [summary_body(a) for a in items]})

    @bp.get("/<uuid:application_id>")
    @reviewer
    def get_application(application_id: UUID) -> Response:
        return jsonify(detail_body(use_cases.get_application().execute(_actor(), application_id)))

    @bp.get("/<uuid:application_id>/doctors/<uuid:doctor_id>/certificate")
    @reviewer
    def certificate(application_id: UUID, doctor_id: UUID) -> Response:
        data, content_type = use_cases.get_application_certificate().execute(
            _actor(), application_id, doctor_id
        )
        response = Response(data, mimetype=content_type)
        response.headers["Content-Disposition"] = "inline"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return response

    @bp.post("/<uuid:application_id>/take")
    @reviewer
    def take(application_id: UUID) -> Response:
        return jsonify(detail_body(use_cases.take_application().execute(_actor(), application_id)))

    @bp.put("/<uuid:application_id>/doctors/<uuid:doctor_id>/check")
    @reviewer
    def check(application_id: UUID, doctor_id: UUID) -> Response:
        body = parse_json(CheckIn)
        detail = use_cases.check_application_doctor().execute(
            _actor(),
            application_id,
            doctor_id,
            CheckCommand(
                register_checked=body.register_checked,
                certificate_matches=body.certificate_matches,
                result=CheckResult(body.result),
                note=body.note,
            ),
        )
        return jsonify(detail_body(detail))

    @bp.post("/<uuid:application_id>/reject")
    @reviewer
    def reject(application_id: UUID) -> Response:
        body = parse_json(RejectIn)
        detail = use_cases.reject_application().execute(
            _actor(), application_id, RejectReason(body.reason), body.message
        )
        return jsonify(detail_body(detail))

    @bp.post("/<uuid:application_id>/approve")
    @reviewer
    def approve(application_id: UUID) -> tuple[Response, int]:
        # M6c-P3 (R41, R42): creates the clinic through the one creation path.
        body = parse_json(ApproveIn)
        approval = use_cases.approve_application().execute(
            _actor(),
            application_id,
            ApproveCommand(
                slug=body.slug,
                booking_mode=body.booking_mode,
                timezone=body.timezone,
                clinic_name=body.clinic_name,
                address_line=body.address_line,
                city=body.city,
                state=body.state,
                pincode=body.pincode,
            ),
        )
        return jsonify(
            {
                "application": detail_body(approval.detail),
                "clinic": clinic_body(approval.clinic),
                "invitation_delivery": approval.delivery.value,
            }
        ), 201

    return bp


def create_ops_verification_blueprint(use_cases: ReviewUseCases) -> Blueprint:
    """M6c-P3 (R45, FR-ONB-06): a reviewer verifies an ops-created clinic and its doctors."""
    bp = Blueprint("ops_verification", __name__, url_prefix="/api/v1/ops/clinics")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/<uuid:clinic_id>/doctors/<uuid:doctor_id>/verify")
    @reviewer
    def verify_doctor(clinic_id: UUID, doctor_id: UUID) -> Response:
        body = parse_json(VerifyIn)
        changed = use_cases.verify_clinic_doctor().execute(
            _actor(),
            clinic_id,
            doctor_id,
            register_checked=body.register_checked,
            certificate_matches=body.certificate_matches,
        )
        return jsonify({"verified": True, "changed": changed})

    @bp.post("/<uuid:clinic_id>/verify")
    @reviewer
    def verify_clinic(clinic_id: UUID) -> Response:
        return jsonify(clinic_body(use_cases.verify_clinic().execute(_actor(), clinic_id)))

    return bp
