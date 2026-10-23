"""The ops console API: onboarding a clinic (FR-OPS-01, FR-OPS-04).

| Endpoint | Purpose |
|---|---|
| ``POST /api/v1/ops/clinics`` | Create a clinic in ``ONBOARDING`` |
| ``GET /api/v1/ops/clinics`` | Every clinic with its onboarding state |
| ``GET /api/v1/ops/clinics/{id}`` | One clinic: checklist, staff, doctor count |
| ``POST /api/v1/ops/clinics/{id}/doctors`` | Add a doctor |
| ``POST /api/v1/ops/clinics/{id}/staff-invites`` | Invite the owner (or any role) |
| ``POST /api/v1/ops/clinics/{id}/patient-imports`` | CSV patient import, dry run by default |
| ``PUT /api/v1/ops/clinics/{id}/doctors/{doctor_id}/schedule`` | Weekly schedule (D5) |
| ``GET /api/v1/ops/messaging-costs?month=YYYY-MM`` | Messages and their cost per clinic (M5-P5) |

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

import re
from datetime import date
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field
from werkzeug.exceptions import UnsupportedMediaType

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
from mediease_api.application.ops.queries import (
    ClinicMessagingCost,
    GetClinicOnboarding,
    ListClinics,
    MessagingCosts,
    paise,
)
from mediease_api.application.patients.import_patients import (
    ImportPatients,
    ImportPatientsCommand,
    ImportReport,
    RowDuplicate,
)
from mediease_api.application.scheduling.schedules import ReplaceSchedule
from mediease_api.delivery.http.access import current_principal, ops
from mediease_api.delivery.http.bodies import (
    checklist_body,
    clinic_body,
    doctor_body,
    items_body,
    staff_body,
)
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.scheduling import ScheduleRequest, schedule_change_body
from mediease_api.delivery.http.validation import RequestValidationFailed, parse_json
from mediease_api.domain.clinics.clinic import PaperSize
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.scheduling.mode import BookingMode

# The patient import's body limit (M2-P4): 5,000 rows fit with room to spare.
MAX_IMPORT_BYTES = 2 * 1024 * 1024


class OpsUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def create_clinic(self) -> CreateClinic: ...
    def list_clinics(self) -> ListClinics: ...
    def get_clinic_onboarding(self) -> GetClinicOnboarding: ...
    def add_doctor(self) -> AddDoctor: ...
    def invite_staff(self) -> InviteStaff: ...
    def import_patients(self) -> ImportPatients: ...
    def replace_schedule(self) -> ReplaceSchedule: ...
    def messaging_costs(self) -> MessagingCosts: ...


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
    booking_mode: BookingMode = BookingMode.TOKENS
    rx_paper_size: PaperSize = PaperSize.A5


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
    # M6a-P6 (decision 8A): the owner also practises here, as this doctor profile (Doctor 1).
    doctor_id: UUID | None = None


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
                booking_mode=body.booking_mode,
                rx_paper_size=body.rx_paper_size,
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

    @bp.put("/clinics/<uuid:clinic_id>/doctors/<uuid:doctor_id>/schedule")
    @ops
    def replace_schedule(clinic_id: UUID, doctor_id: UUID) -> Response:
        body = parse_json(ScheduleRequest)
        change = use_cases.replace_schedule().execute(
            clinic_id=clinic_id,
            actor=_actor(),
            doctor_id=doctor_id,
            blocks=[b.command() for b in body.blocks],
        )
        return jsonify(schedule_change_body(change))

    @bp.post("/clinics/<uuid:clinic_id>/staff-invites")
    @ops
    def invite_staff(clinic_id: UUID) -> tuple[Response, int]:
        body = parse_json(NewInviteRequest)
        invitation = use_cases.invite_staff().execute(
            clinic_id=clinic_id,
            actor=_actor(),
            cmd=InviteStaffCommand(
                full_name=body.full_name,
                role=body.role,
                email=body.email,
                phone=body.phone,
                doctor_id=body.doctor_id,
            ),
        )
        return jsonify(invitation_body(invitation, public_base_url)), 201

    @bp.post("/clinics/<uuid:clinic_id>/patient-imports")
    @ops
    def import_patients(clinic_id: UUID) -> Response:
        dry_run = _dry_run_flag()
        report = use_cases.import_patients().execute(
            clinic_id=clinic_id,
            actor=_actor(),
            cmd=ImportPatientsCommand(data=_csv_body(), dry_run=dry_run),
        )
        return jsonify(import_report_body(report))

    @bp.get("/messaging-costs")
    @ops
    def messaging_costs() -> Response:
        month = _month()
        clinics = use_cases.messaging_costs().execute(month)
        return jsonify(
            {
                "month": month.strftime("%Y-%m"),
                "clinics": [clinic_cost_body(c) for c in clinics],
                "cost_paise": paise(sum(c.cost_millipaise for c in clinics)),
            }
        )

    return bp


_MONTH = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")


def _month() -> date:
    """``month=YYYY-MM``, required: a total is always for a named month."""
    match = _MONTH.fullmatch(request.args.get("month", "").strip())
    if match is None:
        raise RequestValidationFailed([{"field": "month", "reason": "must be YYYY-MM"}])
    return date(int(match.group(1)), int(match.group(2)), 1)


def clinic_cost_body(clinic: ClinicMessagingCost) -> dict[str, Any]:
    """Counts and money only (R18); paise rounded at each total from exact millipaise."""
    return {
        "clinic_id": str(clinic.clinic_id),
        "clinic_name": clinic.clinic_name,
        "messages": clinic.messages,
        "unpriced": clinic.unpriced,
        "cost_paise": paise(clinic.cost_millipaise),
        "channels": [
            {
                "channel": c.channel.value,
                "messages": c.messages,
                "priced": c.priced,
                "unpriced": c.unpriced,
                "cost_paise": paise(c.cost_millipaise),
            }
            for c in clinic.channels
        ],
    }


def _dry_run_flag() -> bool:
    """``dry_run`` defaults to true: a call that forgets the flag never writes (M2-P4)."""
    raw = request.args.get("dry_run", "true").strip().lower()
    if raw not in ("true", "false"):
        raise RequestValidationFailed([{"field": "dry_run", "reason": "must be true or false"}])
    return raw == "true"


def _csv_body() -> bytes:
    """The raw CSV, ``text/csv`` only, at most ``MAX_IMPORT_BYTES`` (413 beyond)."""
    if request.mimetype != "text/csv":
        raise UnsupportedMediaType("Send the file as text/csv.")
    # Per request, so only this route accepts a body this large; Werkzeug refuses
    # a longer Content-Length up front and stops reading a chunked body at the limit.
    request.max_content_length = MAX_IMPORT_BYTES
    return request.get_data(cache=False)


def _actor() -> Actor:
    return Actor.for_user(current_principal().user, request_info())


def invitation_body(invitation: StaffInvitation, public_base_url: str) -> dict[str, Any]:
    """The new member plus the acceptance URL — the only place the secret appears.

    Ops invitations are always shown as a link (until M6c, FR-ONB-08).
    """
    if invitation.token is None:  # pragma: no cover - ops never ask for email delivery
        raise ValueError("an ops invitation is always a link")
    return {
        **staff_body(invitation.member),
        "accept_url": f"{public_base_url}/invite/{invitation.token}",
    }


def team_invitation_body(invitation: StaffInvitation, public_base_url: str) -> dict[str, Any]:
    """An owner's invitation (M6a-P5): emailed (masked address) or a link shown once."""
    return {
        **staff_body(invitation.member),
        "delivery": invitation.delivery.value,
        "email_masked": invitation.email_masked,
        "accept_url": (
            f"{public_base_url}/invite/{invitation.token}" if invitation.token is not None else None
        ),
    }


def import_report_body(report: ImportReport) -> dict[str, Any]:
    """Row numbers, counts, columns and new codes: nothing from the file (M2-P4)."""
    return {
        "dry_run": report.dry_run,
        "rows": report.rows,
        "valid": report.valid,
        "invalid": report.invalid,
        "possible_duplicates": report.possible_duplicates,
        "already_registered": report.already_registered,
        "imported": report.imported,
        "codes": list(report.codes),
        "errors": [{"row": e.row, "field": e.field, "reason": e.reason} for e in report.errors],
        "duplicates": [_duplicate_body(d) for d in report.duplicates],
        "errors_truncated": report.errors_truncated,
        "duplicates_truncated": report.duplicates_truncated,
    }


def _duplicate_body(duplicate: RowDuplicate) -> dict[str, Any]:
    body: dict[str, Any] = {"row": duplicate.row, "kind": duplicate.kind.value}
    if duplicate.matches is not None:
        body["matches"] = duplicate.matches
    if duplicate.same_as_row is not None:
        body["same_as_row"] = duplicate.same_as_row
    return body
