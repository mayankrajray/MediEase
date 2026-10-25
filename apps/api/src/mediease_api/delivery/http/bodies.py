"""Shared JSON bodies for clinics, doctors, staff and onboarding.

One place per resource, because the ops console and the clinic API return the
same shapes (``delivery/http/clinic.py``, ``delivery/http/ops.py``) and the
contract has one schema for each.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, time
from typing import Any

from mediease_api.application.appointments.queue import QueueView
from mediease_api.application.appointments.views import (
    AppointmentDetail,
    AppointmentView,
    HeldPlace,
)
from mediease_api.application.links.use_cases import LinkInfo
from mediease_api.application.patients.views import CandidateView, PatientView
from mediease_api.application.prescriptions.pdf import Printable
from mediease_api.application.prescriptions.use_cases import PrescriptionView
from mediease_api.application.scheduling.views import ScheduleView
from mediease_api.application.visits.use_cases import ConsultationView, VisitView
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.prescriptions.document import RxField
from mediease_api.domain.prescriptions.patient_view import PatientPage
from mediease_api.domain.prescriptions.plan import line_slots, line_warnings
from mediease_api.domain.prescriptions.prescription import Prescription, PrescriptionItem
from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock
from mediease_api.domain.scheduling.exceptions import ScheduleException
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.visits.visit import Visit, VisitAddendum


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
        "rx_paper_size": clinic.rx_paper_size.value,
        "reminder_evening_before": clinic.reminder_evening_before,
        "reminder_hours_before": clinic.reminder_hours_before,
        "request_hold_minutes": clinic.request_hold_minutes,
        "request_requires_age_sex": clinic.request_requires_age_sex,
        # M6c-P3, P4, P5: MediEase's verification, the directory listing and indexing.
        "verified_at": clinic.verified_at.isoformat() if clinic.verified_at else None,
        "verification_source": (
            clinic.verification_source.value if clinic.verification_source else None
        ),
        "listed": clinic.listed,
        "search_indexing": clinic.search_indexing,
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
        # M6c-P3, P4, P5: verification, directory visibility and the public profile.
        "verified_at": doctor.verified_at.isoformat() if doctor.verified_at else None,
        "verification_source": (
            doctor.verification_source.value if doctor.verification_source else None
        ),
        "visible": doctor.visible,
        "languages": list(doctor.languages),
        "fee_paise": doctor.fee_paise,
    }


def staff_body(member: StaffMember) -> dict[str, Any]:
    return {
        "membership_id": str(member.membership_id),
        "user_id": str(member.user_id),
        "full_name": member.full_name,
        "role": member.role.value,
        "status": member.status.value,
        # M6a-P5: the Team page. Owners only (STAFF_MANAGE); the ops answers carry them too.
        "email": member.email,
        "phone_e164": member.phone_e164,
        "invite_expires_at": (
            member.invite_expires_at.isoformat() if member.invite_expires_at else None
        ),
        "has_doctor_profile": member.has_doctor_profile,
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


def session_body(
    session: Session,
    taken: frozenset[datetime] | None = None,
    held: Sequence[HeldPlace] = (),
) -> dict[str, Any]:
    """A session; the slots in slot mode, the next token in token mode (R3, R4).

    ``taken`` (the listing passes it, M3-P2) marks each slot ``available`` or not; without it,
    as in a schedule change's ``kept_sessions``, slots carry their times only.
    """
    slots = session.mode is BookingMode.SLOTS

    def slot(start: datetime, end: datetime) -> dict[str, Any]:
        body: dict[str, Any] = {"starts_at": start.isoformat(), "ends_at": end.isoformat()}
        if taken is not None:
            body["available"] = start not in taken
        return body

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
        "slots": [slot(start, end) for start, end in session.slots()],
        # M6b-P4 (R23): places an online request holds for now; the requester is not named.
        "held": [{"slot_start": _iso(h.slot_start), "until": h.until.isoformat()} for h in held],
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def appointment_body(view: AppointmentView) -> dict[str, Any]:
    """An appointment and where it is. ``reason`` and ``cancel_note`` are for staff only."""
    a, session = view.appointment, view.session
    return {
        "id": str(a.id),
        "session_id": str(a.session_id),
        "doctor_id": str(a.doctor_id),
        "patient_id": str(a.patient_id),
        "on_date": session.on_date.isoformat(),
        "session_starts_at": session.starts_at.isoformat(),
        "session_ends_at": session.ends_at.isoformat(),
        "mode": session.mode.value,
        "slot_start": _iso(a.slot_start),
        "token_number": a.token_number,
        "status": a.status.value,
        "source": a.source.value,
        "reason": a.reason,
        "cancel_reason": a.cancel_reason.value if a.cancel_reason else None,
        "cancel_note": a.cancel_note,
        "cancelled_at": _iso(a.cancelled_at),
        "rescheduled_from_id": str(a.rescheduled_from_id) if a.rescheduled_from_id else None,
        "arrived_at": _iso(a.arrived_at),
        "started_at": _iso(a.started_at),
        "completed_at": _iso(a.completed_at),
        "created_by": str(a.created_by) if a.created_by else None,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }


def appointment_detail_body(detail: AppointmentDetail) -> dict[str, Any]:
    return {
        **appointment_body(detail.view),
        "history": [
            {
                "from_status": h.from_status.value if h.from_status else None,
                "to_status": h.to_status.value,
                "changed_by": str(h.changed_by) if h.changed_by else None,
                "changed_at": h.changed_at.isoformat(),
            }
            for h in detail.history
        ],
    }


def queue_body(queue: QueueView) -> dict[str, Any]:
    """The day's queue (FR-QUE-01): sessions with their appointments by token or slot."""
    return {
        "on_date": queue.on_date.isoformat(),
        "sessions": [
            {
                **session_body(q.session),
                "appointments": [
                    {
                        **appointment_body(e.view),
                        "patient": {
                            "id": str(e.patient.id),
                            "code": e.patient.code,
                            "full_name": e.patient.full_name,
                            "age_years": e.patient.age_years,
                            "sex": e.patient.sex.value,
                        },
                        "wait_minutes": e.wait_minutes,
                        # M4-P6 decision 4A: no content, only that a visit and an issued
                        # prescription exist, so front desk can print from the row.
                        "visit_id": str(e.visit_id) if e.visit_id else None,
                        "prescription": (
                            {
                                "id": str(e.prescription.id),
                                "version": e.prescription.version,
                                "issued_at": e.prescription.issued_at.isoformat(),
                            }
                            if e.prescription
                            else None
                        ),
                    }
                    for e in q.entries
                ],
            }
            for q in queue.sessions
        ],
    }


# --- Visits (M4-P1). Clinical content: CLINICAL_VIEW routes only, never logged. ------------------


def addendum_body(addendum: VisitAddendum) -> dict[str, Any]:
    return {
        "id": str(addendum.id),
        "visit_id": str(addendum.visit_id),
        "author_user_id": str(addendum.author_user_id),
        "body": addendum.body,
        "created_at": addendum.created_at.isoformat(),
    }


def visit_body(view: VisitView) -> dict[str, Any]:
    """The full record; ``is_locked`` is as of the response (R3)."""
    v = view.visit
    return {
        "id": str(v.id),
        "patient_id": str(v.patient_id),
        "doctor_id": str(v.doctor_id),
        "appointment_id": str(v.appointment_id),
        "status": v.status.value,
        "chief_complaint": v.chief_complaint,
        "findings": v.findings,
        "diagnosis": v.diagnosis,
        "notes": v.notes,
        "vitals": v.vitals.as_json(),
        "revision": v.revision,
        "started_at": v.started_at.isoformat(),
        "completed_at": _iso(v.completed_at),
        "locked_at": _iso(v.locked_at),
        "is_locked": view.is_locked,
        "addenda": [addendum_body(a) for a in view.addenda],
        "created_at": v.created_at.isoformat(),
        "updated_at": v.updated_at.isoformat(),
    }


def visit_summary_body(visit: Visit, prescription: Prescription | None = None) -> dict[str, Any]:
    """One line of a patient's history (R2): when, who, why, what was found and what was given."""
    return {
        "id": str(visit.id),
        "doctor_id": str(visit.doctor_id),
        "appointment_id": str(visit.appointment_id),
        "status": visit.status.value,
        "started_at": visit.started_at.isoformat(),
        "completed_at": _iso(visit.completed_at),
        "chief_complaint": visit.chief_complaint,
        "diagnosis": visit.diagnosis,
        "prescription": prescription_summary_body(prescription) if prescription else None,
    }


def consultation_body(view: ConsultationView) -> dict[str, Any]:
    """The consultation screen in one response (R16: one read, one audit row)."""
    return {
        "visit": visit_body(view.visit),
        "patient": patient_body(view.patient),
        "history": [
            visit_summary_body(v, view.history_prescriptions.get(v.id)) for v in view.history
        ],
        "prescriptions": [prescription_body(PrescriptionView(rx)) for rx in view.prescriptions],
    }


# --- Prescriptions (M4-P2). Clinical content: CLINICAL_VIEW routes only, never logged. -----------


def item_body(item: PrescriptionItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "position": item.position,
        "medicine_name": item.medicine_name,
        "form": item.form,
        "strength": item.strength,
        "dose": item.dose,
        "frequency": item.frequency.value if item.frequency else None,
        "frequency_text": item.frequency_text,
        "timing": item.timing.value if item.timing else None,
        "duration_days": item.duration_days,
        "duration_kind": item.duration_kind.value if item.duration_kind else None,
        # M6b-P3 (R21, R22): the slots the pattern marks, from the one engine, and the
        # non-blocking warnings for the doctor.
        "slots": [s.value for s in line_slots(item)],
        "line_warnings": [w.value for w in line_warnings(item)],
        "quantity": item.quantity,
        "preparation": [p.as_json() for p in item.preparation],
        "storage": [s.as_json() for s in item.storage],
        "warnings": item.warnings,
        "notes": item.notes,
        "favourite_id": str(item.favourite_id) if item.favourite_id else None,
    }


def prescription_body(view: PrescriptionView) -> dict[str, Any]:
    """One version in full; ``versions`` lists the chain when the read had it."""
    rx = view.prescription
    return {
        "id": str(rx.id),
        "visit_id": str(rx.visit_id),
        "patient_id": str(rx.patient_id),
        "doctor_id": str(rx.doctor_id),
        "version": rx.version,
        "supersedes_id": str(rx.supersedes_id) if rx.supersedes_id else None,
        "status": rx.status.value,
        "revision": rx.revision,
        "items": [item_body(i) for i in rx.items],
        "advice": rx.advice.as_json(),
        "follow_up_date": rx.follow_up_date.isoformat() if rx.follow_up_date else None,
        "starts_on": rx.starts_on.isoformat() if rx.starts_on else None,
        "previous_starts_on": view.previous_start.isoformat() if view.previous_start else None,
        "language": rx.language.value if rx.language else None,
        "issued_at": _iso(rx.issued_at),
        "doctor_snapshot": rx.doctor_snapshot.as_json() if rx.doctor_snapshot else None,
        "clinic_snapshot": rx.clinic_snapshot.as_json() if rx.clinic_snapshot else None,
        "link_delivery": rx.link_delivery.value if rx.link_delivery else None,
        "template_id": str(rx.template_id) if rx.template_id else None,
        "versions": [
            {
                "id": str(v.id),
                "version": v.version,
                "status": v.status.value,
                "issued_at": _iso(v.issued_at),
            }
            for v in view.chain
        ],
        "created_at": rx.created_at.isoformat(),
        "updated_at": rx.updated_at.isoformat(),
    }


def _field(f: RxField) -> dict[str, str]:
    return {"label": f.label, "value": f.value}


def patient_view_body(v: PatientPage) -> dict[str, Any]:
    """M4-P5: the patient page; labels translated, the doctor's text as written."""
    return {
        "language": v.language.value,
        "version": v.version,
        "clinic_name": v.clinic_name,
        "clinic_phone_e164": v.clinic_phone_e164,
        "call_label": v.call_label,
        "doctor_name": v.doctor_name,
        "doctor_lines": list(v.doctor_lines),
        "issued_on": _field(v.issued_on),
        "updated_note": v.updated_note,
        "medicines_heading": v.medicines_heading,
        "medicines": [
            {
                "number": m.number,
                "name": m.name,
                "form_strength": m.form_strength,
                "fields": [_field(f) for f in m.fields],
            }
            for m in v.medicines
        ],
        "advice_heading": v.advice_heading,
        "advice": [{"heading": a.heading, "entries": list(a.entries)} for a in v.advice],
        "advice_notes": _field(v.advice_notes) if v.advice_notes else None,
        "follow_up": _field(v.follow_up) if v.follow_up else None,
        # M6b-P3 (prescriptions R25): the Medicine schedule, from the one engine.
        "schedule_heading": v.schedule_heading,
        "schedule_columns": list(v.schedule_columns),
        "schedule_as_written": v.schedule_as_written,
        "schedule": [
            {
                "number": r.number,
                "name": r.name,
                "dose": r.dose,
                "marks": list(r.marks),
                "as_written": r.as_written,
                "timing": r.timing,
                "how": r.how,
                "duration": r.duration,
            }
            for r in v.schedule
        ],
    }


def patient_link_body(info: LinkInfo, public_base_url: str) -> dict[str, Any]:
    """M4-P5 decision 6A: what the clinic sees about a link; no content, no digits."""
    link = info.link
    return {
        "id": str(link.id),
        "url": f"{public_base_url}/p/{info.token}",
        "expires_at": link.expires_at.isoformat(),
        "locked": link.is_locked,
        "open_count": link.open_count,
        "last_opened_at": _iso(link.last_opened_at),
    }


def printable_body(p: Printable) -> dict[str, Any]:
    """M4-P4 decision 2A: what front desk may print. IDs, version, date, doctor; no content."""
    return {
        "id": str(p.prescription_id),
        "visit_id": str(p.visit_id),
        "version": p.version,
        "issued_at": p.issued_at.isoformat(),
        "doctor_display_name": p.doctor_display_name,
    }


def prescription_summary_body(rx: Prescription) -> dict[str, Any]:
    """A history line's prescription: the medicines and how they were taken (R2)."""
    return {
        "id": str(rx.id),
        "version": rx.version,
        "issued_at": _iso(rx.issued_at),
        "items": [
            {
                "medicine_name": i.medicine_name,
                "dose": i.dose,
                "frequency": i.frequency.value if i.frequency else None,
                "frequency_text": i.frequency_text,
                "timing": i.timing.value if i.timing else None,
                "duration_days": i.duration_days,
                "duration_kind": i.duration_kind.value if i.duration_kind else None,
            }
            for i in rx.items
        ],
    }
