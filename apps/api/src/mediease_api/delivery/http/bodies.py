"""Shared JSON bodies for clinics, doctors, staff and onboarding.

One place per resource, because the ops console and the clinic API return the
same shapes (``delivery/http/clinic.py``, ``delivery/http/ops.py``) and the
contract has one schema for each.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.access import StaffMember


def items_body(bodies: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Unpaginated list envelope; the cursor form arrives with patients (M2)."""
    return {"items": list(bodies)}


def clinic_body(clinic: Clinic) -> dict[str, Any]:
    return {
        "id": str(clinic.id),
        "name": clinic.name,
        "slug": clinic.slug,
        "timezone": clinic.timezone,
        "status": clinic.status.value,
        "phone_e164": clinic.phone.e164 if clinic.phone else None,
        "address_line": clinic.address_line,
        "city": clinic.city,
        "state": clinic.state,
        "pincode": clinic.pincode,
        "specialties": list(clinic.specialties),
    }


def doctor_body(doctor: Doctor) -> dict[str, Any]:
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


def staff_body(member: StaffMember) -> dict[str, Any]:
    return {
        "membership_id": str(member.membership_id),
        "user_id": str(member.user_id),
        "full_name": member.full_name,
        "role": member.role.value,
        "status": member.status.value,
    }


def checklist_body(checklist: OnboardingChecklist | None) -> dict[str, Any] | None:
    """Timestamps only: the raw material for goal G4 (FR-OPS-04)."""
    if checklist is None:
        return None
    body: dict[str, Any] = {"started_at": checklist.started_at.isoformat()}
    for step in OnboardingStep:
        recorded = checklist.at(step)
        body[step.value] = recorded.isoformat() if recorded else None
    return body
