"""Shared JSON bodies for clinics, doctors, staff and onboarding.

One place per resource, because the ops console and the clinic API return the
same shapes (``delivery/http/clinic.py``, ``delivery/http/ops.py``) and the
contract has one schema for each.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import time
from typing import Any

from mediease_api.application.patients.views import CandidateView, PatientView
from mediease_api.application.scheduling.views import ScheduleView
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock
from mediease_api.domain.scheduling.exceptions import ScheduleException
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session


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
        "patient_code_prefix": clinic.patient_code_prefix,
        "booking_mode": clinic.booking_mode.value,
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


def patient_body(patient: PatientView) -> dict[str, Any]:
    """A patient as staff see them. Phone numbers are shown in full: staff must dial them."""
    return {
        "id": str(patient.id),
        "code": patient.code,
        "full_name": patient.full_name,
        "phone_e164": patient.phone_e164,
        "sex": patient.sex.value,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "age_years": patient.age_years,
        "age_is_estimated": patient.age_is_estimated,
        "is_minor": patient.is_minor,
        "guardian_name": patient.guardian_name,
        "language": patient.language.value,
        "whatsapp_consent": patient.whatsapp_consent,
        "sms_consent": patient.sms_consent,
        "opted_out": patient.opted_out,
        "opted_out_at": patient.opted_out_at.isoformat() if patient.opted_out_at else None,
        # One rule for the screens and M5's sender: consent given and not opted out (R6).
        "whatsapp_allowed": patient.whatsapp_allowed,
        "sms_allowed": patient.sms_allowed,
        "consent_recorded_at": (
            patient.consent_recorded_at.isoformat() if patient.consent_recorded_at else None
        ),
        "consent_recorded_by": (
            str(patient.consent_recorded_by) if patient.consent_recorded_by else None
        ),
        "created_at": patient.created_at.isoformat(),
        "updated_at": patient.updated_at.isoformat(),
    }


def candidate_body(candidate: CandidateView) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "code": candidate.code,
        "full_name": candidate.full_name,
        "age_years": candidate.age_years,
    }


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _shape_body(shape: BlockShape) -> dict[str, Any]:
    return {
        "start_time": _hhmm(shape.start_time),
        "end_time": _hhmm(shape.end_time),
        # True when the block ends the next day (decision D2).
        "overnight": shape.overnight,
        "slot_minutes": shape.slot_minutes,
        "capacity": shape.capacity,
    }


def block_body(block: WeeklyBlock) -> dict[str, Any]:
    return {"id": str(block.id), "weekday": block.weekday, **_shape_body(block.shape)}


def exception_body(exception: ScheduleException) -> dict[str, Any]:
    shape = (
        _shape_body(exception.shape)
        if exception.shape is not None
        else {
            "start_time": None,
            "end_time": None,
            "overnight": False,
            "slot_minutes": None,
            "capacity": None,
        }
    )
    return {
        "id": str(exception.id),
        "doctor_id": str(exception.doctor_id),
        "on_date": exception.on_date.isoformat(),
        "kind": exception.kind.value,
        "note": exception.note,
        **shape,
    }


def schedule_body(schedule: ScheduleView) -> dict[str, Any]:
    return {
        "doctor_id": str(schedule.doctor_id),
        "booking_mode": schedule.booking_mode.value,
        "blocks": [block_body(b) for b in schedule.blocks],
        "exceptions": [exception_body(e) for e in schedule.exceptions],
    }


def session_body(session: Session) -> dict[str, Any]:
    """A session; the slots in slot mode, the next token in token mode (R3, R4)."""
    slots = session.mode is BookingMode.SLOTS
    return {
        "id": str(session.id),
        "doctor_id": str(session.doctor_id),
        "on_date": session.on_date.isoformat(),
        "starts_at": session.starts_at.isoformat(),
        "ends_at": session.ends_at.isoformat(),
        "mode": session.mode.value,
        "status": session.status.value,
        "slot_minutes": session.slot_minutes,
        "capacity": session.capacity,
        "booked_count": session.booked_count,
        "available": session.available,
        "next_token": None if slots else session.next_token,
        "slots": [
            {"starts_at": start.isoformat(), "ends_at": end.isoformat()}
            for start, end in session.slots()
        ],
    }
