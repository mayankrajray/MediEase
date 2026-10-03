"""The ops console API: onboarding a clinic (FR-OPS-01, FR-OPS-04).

| Endpoint | Purpose |
|---|---|
| ``POST /api/v1/ops/clinics`` | Create a clinic in ``ONBOARDING`` |
| ``GET /api/v1/ops/clinics`` | Every clinic with its onboarding state |
| ``GET /api/v1/ops/clinics/{id}`` | One clinic: checklist, staff, doctor count |
| ``POST /api/v1/ops/clinics/{id}/doctors`` | Add a doctor |
| ``POST /api/v1/ops/clinics/{id}/staff-invites`` | Invite the owner (or any role) |

Every route is ``@ops``: platform staff only, and clinic staff are refused
even as owners (spec R10). Ops users have no membership, so the clinic is
named in the path — the use cases still reach tenant rows only through
``uow.tenant(clinic_id)``.

Ops never see clinical content: these endpoints return clinics, doctors,
staff names and timestamps. The clinic-health view (FR-OPS-03) arrives in
M6-P4 on top of ``v_clinic_activity``.

The response that creates an invitation contains the acceptance URL — the one
time the secret is visible anywhere.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.clinics.invite_staff import (
    InviteStaff,
    InviteStaffCommand,
    StaffInvitation,
)
from mediease_api.application.clinics.onboard_clinic import (
    AddDoctor,
    CreateClinic,
    CreateClinicCommand,
    DoctorCommand,
)
from mediease_api.application.context import Actor
from mediease_api.application.ops.queries import GetClinicOnboarding, ListClinics
from mediease_api.delivery.http.access import current_principal, ops
from mediease_api.delivery.http.bodies import (
    checklist_body,
    clinic_body,
    doctor_body,
    items_body,
    staff_body,
)
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.membership import Role


class OpsUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def create_clinic(self) -> CreateClinic: ...
    def list_clinics(self) -> ListClinics: ...
    def get_clinic_onboarding(self) -> GetClinicOnboarding: ...
    def add_doctor(self) -> AddDoctor: ...
    def invite_staff(self) -> InviteStaff: ...


class NewClinicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    # Lower-case URL segment; the domain validates the shape.
    slug: str = Field(min_length=3, max_length=63)
    timezone: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=6)
    specialties: list[str] = Field(default_factory=list, max_length=20)
    # 2-4 upper-case letters for patient codes (ME-0142); derived from the name when omitted.
    patient_code_prefix: str | None = Field(default=None, max_length=4)


class NewDoctorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    qualification: str = Field(min_length=1, max_length=200)
    registration_number: str = Field(min_length=1, max_length=50)
    registration_council: str = Field(min_length=1, max_length=200)
    specialty: str | None = Field(default=None, max_length=100)
    user_id: UUID | None = None


class NewInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    role: Role
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=20)


def create_ops_blueprint(use_cases: OpsUseCases, *, public_base_url: str) -> Blueprint:
    bp = Blueprint("ops", __name__, url_prefix="/api/v1/ops")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/clinics")
    @ops
    def create_clinic() -> tuple[Response, int]:
        body = parse_json(NewClinicRequest)
        clinic = use_cases.create_clinic().execute(
            _actor(),
            CreateClinicCommand(
                name=body.name,
                slug=body.slug,
                timezone=body.timezone,
                phone=body.phone,
                address_line=body.address_line,
                city=body.city,
                state=body.state,
                pincode=body.pincode,
                specialties=tuple(body.specialties),
                patient_code_prefix=body.patient_code_prefix,
            ),
        )
        return jsonify(clinic_body(clinic)), 201

    @bp.get("/clinics")
    @ops
    def list_clinics() -> Response:
        listed = use_cases.list_clinics().execute()
        return jsonify(
            items_body(
                {**clinic_body(entry.clinic), "onboarding": checklist_body(entry.checklist)}
                for entry in listed
            )
        )

    @bp.get("/clinics/<uuid:clinic_id>")
    @ops
    def get_clinic(clinic_id: UUID) -> Response:
        detail = use_cases.get_clinic_onboarding().execute(clinic_id)
        return jsonify(
            {
                **clinic_body(detail.clinic),
                "onboarding": checklist_body(detail.checklist),
                "doctor_count": detail.doctor_count,
                "staff": [staff_body(m) for m in detail.staff],
            }
        )

    @bp.post("/clinics/<uuid:clinic_id>/doctors")
    @ops
    def add_doctor(clinic_id: UUID) -> tuple[Response, int]:
        body = parse_json(NewDoctorRequest)
        doctor = use_cases.add_doctor().execute(
            clinic_id=clinic_id,
            actor=_actor(),
            cmd=DoctorCommand(**body.model_dump()),
        )
        return jsonify(doctor_body(doctor)), 201

    @bp.post("/clinics/<uuid:clinic_id>/staff-invites")
    @ops
    def invite_staff(clinic_id: UUID) -> tuple[Response, int]:
        body = parse_json(NewInviteRequest)
        invitation = use_cases.invite_staff().execute(
            clinic_id=clinic_id,
            actor=_actor(),
            cmd=InviteStaffCommand(
                full_name=body.full_name, role=body.role, email=body.email, phone=body.phone
            ),
        )
        return jsonify(invitation_body(invitation, public_base_url)), 201

    return bp


def _actor() -> Actor:
    return Actor.for_user(current_principal().user, request_info())


def invitation_body(invitation: StaffInvitation, public_base_url: str) -> dict[str, Any]:
    """The new member plus the acceptance URL — the only place the secret appears."""
    return {
        **staff_body(invitation.member),
        "accept_url": f"{public_base_url}/invite/{invitation.token}",
    }
