"""Read-only clinic endpoints for the staff of one clinic (FR-ORG-02..04, NFR-08).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/clinic`` | ``CLINIC_VIEW`` |
| ``GET /api/v1/clinic/doctors`` | ``DOCTORS_VIEW`` |
| ``GET /api/v1/clinic/doctors/{doctor_id}`` | ``DOCTORS_VIEW`` |
| ``GET /api/v1/clinic/staff`` | ``STAFF_MANAGE`` (owners) |

The clinic is never a path or query parameter: it comes from the request
context the access hook resolved (spec R6), and every query runs through
repositories bound to it, so another clinic's doctor is a 404 (R8, AC3).

Lists are unpaginated by design: a clinic has a handful of doctors and staff,
so they return ``{"items": [...]}`` without a cursor. The paginated envelope
in docs/API.md arrives with the first list that can grow (patients, M2).

Writes (invite, role change, deactivate) arrive in M1-P5, after the audit log.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify

from mediease_api.application.clinics.queries import GetClinic, GetDoctor, ListDoctors, ListStaff
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.identity.permissions import Permission


class ClinicQueries(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def get_clinic(self) -> GetClinic: ...
    def list_doctors(self) -> ListDoctors: ...
    def get_doctor(self) -> GetDoctor: ...
    def list_staff(self) -> ListStaff: ...


def create_clinic_blueprint(queries: ClinicQueries) -> Blueprint:
    bp = Blueprint("clinic", __name__, url_prefix="/api/v1/clinic")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        # Clinic data is per-tenant and per-role: never cached by a proxy.
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.CLINIC_VIEW)
    def get_clinic() -> Response:
        return jsonify(_clinic_body(queries.get_clinic().execute(current_context())))

    @bp.get("/doctors")
    @clinic(Permission.DOCTORS_VIEW)
    def list_doctors() -> Response:
        doctors = queries.list_doctors().execute(current_context())
        return jsonify(_items(_doctor_body(d) for d in doctors))

    @bp.get("/doctors/<uuid:doctor_id>")
    @clinic(Permission.DOCTORS_VIEW)
    def get_doctor(doctor_id: UUID) -> Response:
        doctor = queries.get_doctor().execute(current_context(), doctor_id)
        return jsonify(_doctor_body(doctor))

    @bp.get("/staff")
    @clinic(Permission.STAFF_MANAGE)
    def list_staff() -> Response:
        staff = queries.list_staff().execute(current_context())
        return jsonify(_items(_staff_body(m) for m in staff))

    return bp


def _items(bodies: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {"items": list(bodies)}


def _clinic_body(clinic_row: Clinic) -> dict[str, Any]:
    return {
        "id": str(clinic_row.id),
        "name": clinic_row.name,
        "slug": clinic_row.slug,
        "timezone": clinic_row.timezone,
        "status": clinic_row.status.value,
        "phone_e164": clinic_row.phone.e164 if clinic_row.phone else None,
        "address_line": clinic_row.address_line,
        "city": clinic_row.city,
        "state": clinic_row.state,
        "pincode": clinic_row.pincode,
        "specialties": list(clinic_row.specialties),
    }


def _doctor_body(doctor: Doctor) -> dict[str, Any]:
    return {
        "id": str(doctor.id),
        "user_id": str(doctor.user_id) if doctor.user_id else None,
        "display_name": doctor.display_name,
        "qualification": doctor.qualification,
        "registration_number": doctor.registration_number,
        "registration_council": doctor.registration_council,
        "specialty": doctor.specialty,
        "is_active": doctor.is_active,
    }


def _staff_body(member: StaffMember) -> dict[str, Any]:
    return {
        "membership_id": str(member.membership_id),
        "user_id": str(member.user_id),
        "full_name": member.full_name,
        "role": member.role.value,
        "status": member.status.value,
    }
