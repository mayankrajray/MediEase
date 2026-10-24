"""Clinic endpoints for the staff of one clinic (FR-ORG-01..04, NFR-08).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/clinic`` | ``CLINIC_VIEW`` |
| ``PATCH /api/v1/clinic`` | ``CLINIC_MANAGE`` |
| ``GET /api/v1/clinic/doctors`` | ``DOCTORS_VIEW`` |
| ``POST /api/v1/clinic/doctors`` | ``CLINIC_MANAGE`` |
| ``GET /api/v1/clinic/doctors/{doctor_id}`` | ``DOCTORS_VIEW`` |
| ``PATCH /api/v1/clinic/doctors/{doctor_id}`` | ``CLINIC_MANAGE`` |
| ``GET /api/v1/clinic/staff`` | ``STAFF_MANAGE`` |
| ``POST /api/v1/clinic/staff`` | ``STAFF_MANAGE`` |
| ``PATCH /api/v1/clinic/staff/{membership_id}`` | ``STAFF_MANAGE`` |

The clinic is never a path or query parameter: it comes from the request
context the access hook resolved (spec R6), and every query runs through
repositories bound to it, so another clinic's doctor or member is a 404
(R8, AC3).

Lists are unpaginated by design: a clinic has a handful of doctors and staff,
so they return ``{"items": [...]}`` without a cursor. The paginated envelope
in docs/API.md arrives with the first list that can grow (patients, M2).

``PATCH`` on a membership carries the role, the status, or both: one endpoint
for "manage this membership", each field with its own audit action. There is
no way back from ``DEACTIVATED`` in M1 — invite the person again.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mediease_api.application.clinics.change_staff_role import (
    ChangeStaffRole,
    ChangeStaffRoleCommand,
)
from mediease_api.application.clinics.deactivate_staff import (
    DeactivateStaff,
    DeactivateStaffCommand,
)
from mediease_api.application.clinics.invite_staff import (
    InviteStaff,
    InviteStaffCommand,
    ResendStaffInvite,
)
from mediease_api.application.clinics.onboard_clinic import (
    AddDoctor,
    DoctorCommand,
    UpdateClinic,
    UpdateClinicCommand,
    UpdateDoctor,
)
from mediease_api.application.clinics.queries import GetClinic, GetDoctor, ListDoctors, ListStaff
from mediease_api.application.context import Actor
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import clinic_body, doctor_body, items_body, staff_body
from mediease_api.delivery.http.ops import team_invitation_body
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.clinics.clinic import PaperSize
from mediease_api.domain.identity.membership import MembershipStatus, Role
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import InvalidValue


class ClinicUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def get_clinic(self) -> GetClinic: ...
    def update_clinic(self) -> UpdateClinic: ...
    def list_doctors(self) -> ListDoctors: ...
    def get_doctor(self) -> GetDoctor: ...
    def add_doctor(self) -> AddDoctor: ...
    def update_doctor(self) -> UpdateDoctor: ...
    def list_staff(self) -> ListStaff: ...
    def invite_staff(self) -> InviteStaff: ...
    def resend_staff_invite(self) -> ResendStaffInvite: ...
    def change_staff_role(self) -> ChangeStaffRole: ...
    def deactivate_staff(self) -> DeactivateStaff: ...


class StaffMembershipRequest(BaseModel):
    """Change a member's role, their status, or both."""

    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    # DEACTIVATED only. Bringing a member back is a new invitation (POST /staff, M6a-P5), which
    # they must accept, so there is no status to PATCH back.
    status: MembershipStatus | None = None

    @model_validator(mode="after")
    def _at_least_one_change(self) -> StaffMembershipRequest:
        if self.role is None and self.status is None:
            raise ValueError("send a role, a status, or both")
        if self.status is not None and self.status is not MembershipStatus.DEACTIVATED:
            raise ValueError("status can only be set to DEACTIVATED")
        return self


class NewStaffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    role: Role
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=20)
    # M6a-P6: an owner who is also this doctor profile (Doctor 1).
    doctor_id: UUID | None = None


class NewClinicDoctorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    qualification: str = Field(min_length=1, max_length=200)
    registration_number: str = Field(min_length=1, max_length=50)
    registration_council: str = Field(min_length=1, max_length=200)
    specialty: str | None = Field(default=None, max_length=100)
    user_id: UUID | None = None


class UpdateDoctorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    qualification: str | None = Field(default=None, max_length=200)
    registration_number: str | None = Field(default=None, max_length=50)
    registration_council: str | None = Field(default=None, max_length=200)
    specialty: str | None = Field(default=None, max_length=100)
    user_id: UUID | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _at_least_one_change(self) -> UpdateDoctorRequest:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("send at least one field to change")
        return self


class UpdateClinicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    pincode: str | None = Field(default=None, max_length=6)
    specialties: list[str] | None = Field(default=None, max_length=20)
    # R19: refused while a current block lacks what the new mode needs.
    booking_mode: BookingMode | None = None
    # M4-P4 (decision 3A): applies to versions first rendered after the change.
    rx_paper_size: PaperSize | None = None
    # M6a-P8 (decision 3A): appointment reminders, for bookings made or moved from now on.
    reminder_evening_before: bool | None = None
    reminder_hours_before: int | None = Field(default=None, ge=0, le=6)

    @model_validator(mode="after")
    def _at_least_one_change(self) -> UpdateClinicRequest:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("send at least one field to change")
        return self


def create_clinic_blueprint(queries: ClinicUseCases, *, public_base_url: str) -> Blueprint:
    bp = Blueprint("clinic", __name__, url_prefix="/api/v1/clinic")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        # Clinic data is per-tenant and per-role: never cached by a proxy.
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.CLINIC_VIEW)
    def get_clinic() -> Response:
        return jsonify(clinic_body(queries.get_clinic().execute(current_context())))

    @bp.patch("")
    @clinic(Permission.CLINIC_MANAGE)
    def update_clinic() -> Response:
        body = parse_json(UpdateClinicRequest)
        ctx = current_context()
        clinic_row = queries.update_clinic().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            cmd=UpdateClinicCommand(
                name=body.name,
                timezone=body.timezone,
                phone=body.phone,
                address_line=body.address_line,
                city=body.city,
                state=body.state,
                pincode=body.pincode,
                specialties=tuple(body.specialties) if body.specialties is not None else None,
                booking_mode=body.booking_mode,
                rx_paper_size=body.rx_paper_size,
                reminder_evening_before=body.reminder_evening_before,
                reminder_hours_before=body.reminder_hours_before,
            ),
        )
        return jsonify(clinic_body(clinic_row))

    @bp.get("/doctors")
    @clinic(Permission.DOCTORS_VIEW)
    def list_doctors() -> Response:
        doctors = queries.list_doctors().execute(current_context())
        return jsonify(items_body(doctor_body(d) for d in doctors))

    @bp.post("/doctors")
    @clinic(Permission.CLINIC_MANAGE)
    def add_doctor() -> tuple[Response, int]:
        body = parse_json(NewClinicDoctorRequest)
        ctx = current_context()
        doctor = queries.add_doctor().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            cmd=DoctorCommand(**body.model_dump()),
        )
        return jsonify(doctor_body(doctor)), 201

    @bp.get("/doctors/<uuid:doctor_id>")
    @clinic(Permission.DOCTORS_VIEW)
    def get_doctor(doctor_id: UUID) -> Response:
        doctor = queries.get_doctor().execute(current_context(), doctor_id)
        return jsonify(doctor_body(doctor))

    @bp.patch("/doctors/<uuid:doctor_id>")
    @clinic(Permission.CLINIC_MANAGE)
    def update_doctor(doctor_id: UUID) -> Response:
        body = parse_json(UpdateDoctorRequest)
        ctx = current_context()
        doctor = queries.update_doctor().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            doctor_id=doctor_id,
            cmd=DoctorCommand(**body.model_dump()),
        )
        return jsonify(doctor_body(doctor))

    @bp.get("/staff")
    @clinic(Permission.STAFF_MANAGE)
    def list_staff() -> Response:
        staff = queries.list_staff().execute(current_context())
        return jsonify(items_body(staff_body(m) for m in staff))

    @bp.post("/staff")
    @clinic(Permission.STAFF_MANAGE)
    def invite_staff() -> tuple[Response, int]:
        body = parse_json(NewStaffRequest)
        ctx = current_context()
        invitation = queries.invite_staff().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            cmd=InviteStaffCommand(
                full_name=body.full_name,
                role=body.role,
                email=body.email,
                phone=body.phone,
                by_owner=True,
                doctor_id=body.doctor_id,
            ),
        )
        return jsonify(team_invitation_body(invitation, public_base_url)), 201

    @bp.post("/staff/<uuid:membership_id>/resend")
    @clinic(Permission.STAFF_MANAGE)
    def resend_invite(membership_id: UUID) -> Response:
        invitation = queries.resend_staff_invite().execute(current_context(), membership_id)
        return jsonify(team_invitation_body(invitation, public_base_url))

    @bp.patch("/staff/<uuid:membership_id>")
    @clinic(Permission.STAFF_MANAGE)
    def change_membership(membership_id: UUID) -> Response:
        body = parse_json(StaffMembershipRequest)
        ctx = current_context()
        member = None
        if body.role is not None:
            member = queries.change_staff_role().execute(
                ctx, ChangeStaffRoleCommand(membership_id=membership_id, role=body.role)
            )
        if body.status is MembershipStatus.DEACTIVATED:
            member = queries.deactivate_staff().execute(
                ctx, DeactivateStaffCommand(membership_id=membership_id)
            )
        if member is None:  # pragma: no cover - the request model requires one of the two
            raise InvalidValue("role", "send a role, a status, or both")
        return jsonify(staff_body(member))

    return bp
