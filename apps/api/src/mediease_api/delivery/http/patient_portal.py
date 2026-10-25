"""Linking and the patient's own records (M6b-P1; FR-PRT-02, 03, 06 b, c; NFR-18).

Patients (``@patient``, under ``/api/v1/portal``, the portal cookies):

| Endpoint | What |
|---|---|
| ``GET /links`` / ``DELETE /links/{link_id}`` | linked clinics (R10) / unlink (R8) |
| ``POST /links/prescription`` | link by a prescription link's last-4 check (R5, R6) |
| ``GET /invites/{token}`` / ``POST /invites/{token}/accept`` | an invite (R2, R3) |
| ``GET /appointments`` | grouped by clinic (R11) |
| ``GET /prescriptions`` / ``/{rx_id}`` / ``/{rx_id}/pdf`` | issued versions (R12) |
| ``GET /reminders`` | reminders with their visible status (R13) |
| ``GET /medicine-plan?date=`` / ``/medicine-plan/courses`` | the medicine plan (M6b-P3, R35) |
| ``PUT /medicine-plan/reminders`` | a reminder choice for one line and slot (R38) |
| ``POST`` / ``GET /booking-requests`` | ask a clinic for a time; the open requests (M6b-P4) |
| ``PUT`` / ``DELETE /medicine-plan/doses`` | mark a dose Taken or Skipped, or clear it (R45) |
| ``GET /medicine-plan/history?prescription_id=`` | a version's doses by day (R47, R49) |
| ``GET /notifications`` / ``/summary`` (ETag) | the bell and its count (M6b-P6, R67, R68) |
| ``POST /notifications/{id}/read`` / ``/read-all`` | read state (R68) |
| ``GET`` / ``PUT /notification-preferences`` | in-app and email switches (R62, R63) |
| ``GET /appointments/{id}/live-link`` | the live link of the account's appointment (R69) |

Staff (``PATIENTS_MANAGE``, under ``/api/v1/patients/{patient_id}``): ``POST /portal-invite``,
``GET /portal``, ``DELETE /portal-link`` (R1, R8, R14).

Every response is ``Cache-Control: no-store``. Bodies carry no clinical notes, no appointment
reason and no staff fields; staff never see the account's email or name.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from mediease_api.application.appointments.live import IssuePortalLiveLink
from mediease_api.application.booking.answers import AcceptProposal, DeclineProposal
from mediease_api.application.booking.requests import (
    BookingRequestCommand,
    CreateBookingRequest,
    ListMyBookingRequests,
    RequestItem,
)
from mediease_api.application.portal.doses import (
    ClearDose,
    DoseChoice,
    DoseHistory,
    DoseResult,
    GetDoseHistory,
    MarkDose,
)
from mediease_api.application.portal.linking import (
    AcceptPortalInvite,
    DescribePortalInvite,
    GetPortalStatus,
    InviteToPortal,
    LinkByPrescription,
    LinkedRecord,
    PatientPortalStatus,
    UnlinkPatient,
    UnlinkPortal,
)
from mediease_api.application.portal.medicines import (
    CourseView,
    DoseView,
    GetMedicinePlan,
    LineWords,
    ListMedicineCourses,
    MedicinePlan,
    PlanContext,
    PlanEntry,
    Reminder,
    ReminderChoice,
    SetMedicineReminder,
)
from mediease_api.application.portal.patient_notifications import (
    GetPatientNotificationSummary,
    GetPatientPreferences,
    ListPatientNotifications,
    MarkAllPatientNotificationsRead,
    MarkPatientNotificationRead,
    NoticeView,
    SetPatientPreference,
)
from mediease_api.application.portal.records import (
    GetPortalPrescription,
    ListPortalAppointments,
    ListPortalLinks,
    ListPortalPrescriptions,
    ListPortalReminders,
    PortalAppointment,
    PortalPrescriptionPdf,
)
from mediease_api.application.prescriptions.pdf import PDF_CONTENT_TYPE
from mediease_api.delivery.http.access import clinic, current_context, current_patient, patient
from mediease_api.delivery.http.bodies import items_body, patient_view_body
from mediease_api.delivery.http.etag import conditional_json
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.booking.request import RequestStatus
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.patients.patient import Language, Sex
from mediease_api.domain.portal.doses import DoseState
from mediease_api.domain.portal.notifications import PatientChannel, PatientNotificationKind
from mediease_api.domain.prescriptions.schedule import Slot
from mediease_api.domain.shared.errors import InvalidValue


class PortalRecordUseCases(Protocol):
    def list_portal_links(self) -> ListPortalLinks: ...
    def unlink_portal(self) -> UnlinkPortal: ...
    def link_by_prescription(self) -> LinkByPrescription: ...
    def describe_portal_invite(self) -> DescribePortalInvite: ...
    def accept_portal_invite(self) -> AcceptPortalInvite: ...
    def list_portal_appointments(self) -> ListPortalAppointments: ...
    def list_portal_prescriptions(self) -> ListPortalPrescriptions: ...
    def get_portal_prescription(self) -> GetPortalPrescription: ...
    def portal_prescription_pdf(self) -> PortalPrescriptionPdf: ...
    def list_portal_reminders(self) -> ListPortalReminders: ...
    def get_medicine_plan(self) -> GetMedicinePlan: ...
    def list_medicine_courses(self) -> ListMedicineCourses: ...
    def set_medicine_reminder(self) -> SetMedicineReminder: ...
    def create_booking_request(self) -> CreateBookingRequest: ...
    def list_my_booking_requests(self) -> ListMyBookingRequests: ...
    def accept_proposal(self) -> AcceptProposal: ...
    # M6b-P6: the bell, preferences and the live token link.
    def list_patient_notifications(self) -> ListPatientNotifications: ...
    def patient_notification_summary(self) -> GetPatientNotificationSummary: ...
    def mark_patient_notification_read(self) -> MarkPatientNotificationRead: ...
    def mark_all_patient_notifications_read(self) -> MarkAllPatientNotificationsRead: ...
    def get_patient_preferences(self) -> GetPatientPreferences: ...
    def set_patient_preference(self) -> SetPatientPreference: ...
    def issue_portal_live_link(self) -> IssuePortalLiveLink: ...
    def decline_proposal(self) -> DeclineProposal: ...
    def mark_dose(self) -> MarkDose: ...
    def clear_dose(self) -> ClearDose: ...
    def dose_history(self) -> GetDoseHistory: ...


class PatientPortalUseCases(Protocol):
    def invite_to_portal(self) -> InviteToPortal: ...
    def get_portal_status(self) -> GetPortalStatus: ...
    def unlink_patient(self) -> UnlinkPatient: ...


class PrescriptionLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
    phone_last4: str = Field(pattern=r"^[0-9]{4}$")


class ReminderRequest(BaseModel):
    """M6b-P3 (R38): ``remind_at`` null = the slot's own time."""

    model_config = ConfigDict(extra="forbid")

    prescription_id: UUID
    item_id: UUID
    slot: Slot
    enabled: bool
    remind_at: time | None = None


class BookingRequestBody(BaseModel):
    """M6b-P4 (booking-requests R9, R12): the session is named by its start (it may not exist
    yet); age and sex are optional unless the clinic requires them."""

    model_config = ConfigDict(extra="forbid")

    clinic_slug: str = Field(min_length=3, max_length=63)
    doctor_id: UUID
    session_start: AwareDatetime
    slot_start: AwareDatetime | None = None
    contact_phone: str = Field(min_length=1, max_length=20)
    age_years: int | None = Field(default=None, ge=0, le=120)
    sex: Sex | None = None
    reason: str | None = Field(default=None, max_length=200)
    not_emergency_ack: bool


# M6b-P5 (R48, R49): the patient's words for each state; a pending request is "Requested".
_PATIENT_STATUS = {
    RequestStatus.PENDING: "REQUESTED",
    RequestStatus.PROPOSED: "PROPOSED",
    RequestStatus.ACCEPTED: "ACCEPTED",
    RequestStatus.DECLINED: "DECLINED",
    RequestStatus.EXPIRED: "EXPIRED",
}


def request_item_body(r: RequestItem) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "status": _PATIENT_STATUS[r.status],
        "original_starts_at": r.original_starts_at.isoformat() if r.original_starts_at else None,
        "decline_reason": r.decline_reason.value if r.decline_reason else None,
        "respond_by": r.respond_by.isoformat() if r.respond_by else None,
        "clinic_id": str(r.clinic_id),
        "clinic_name": r.clinic_name,
        "clinic_slug": r.clinic_slug,
        "clinic_phone_e164": r.clinic_phone_e164,
        "timezone": r.timezone,
        "doctor_name": r.doctor_name,
        "mode": r.mode.value,
        "starts_at": r.starts_at.isoformat(),
        "created_at": r.created_at.isoformat(),
    }


class PreferenceRequest(BaseModel):
    """M6b-P6 (R62, R63): one switch; email only for the four booking kinds."""

    model_config = ConfigDict(extra="forbid")

    kind: PatientNotificationKind
    channel: PatientChannel
    enabled: bool


def notice_body(n: NoticeView) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "kind": n.kind.value,
        "title": n.title,
        "link": n.link,
        "created_at": n.created_at.isoformat(),
        "read_at": n.read_at.isoformat() if n.read_at else None,
    }


class DoseRequest(BaseModel):
    """M6b-P3b (R45): one scheduled dose and what the patient marks it."""

    model_config = ConfigDict(extra="forbid")

    prescription_id: UUID
    item_id: UUID
    on_date: date
    slot: Slot
    state: DoseState


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def dose_body(d: DoseView | DoseResult) -> dict[str, Any]:
    """R45-R47: the state in a word, the time marked, and whether it can still be changed."""
    return {"status": d.status.value, "marked_at": _iso(d.marked_at), "markable": d.markable}


def history_body(h: DoseHistory) -> dict[str, Any]:
    return {
        "prescription_id": str(h.prescription_id),
        "version": h.version,
        "clinic_name": h.clinic_name,
        "clinic_phone_e164": h.clinic_phone_e164,
        "timezone": h.timezone,
        "starts_on": h.starts_on.isoformat(),
        "counts": {k.value: v for k, v in h.counts.items()},
        "days": [
            {
                "date": d.on_date.isoformat(),
                "doses": [
                    {
                        "item_id": str(x.item_id),
                        "medicine_name": x.medicine_name,
                        "dose": x.dose,
                        "slot": x.slot.value,
                        "status": x.status.value,
                        "marked_at": _iso(x.marked_at),
                    }
                    for x in d.doses
                ],
            }
            for d in h.days
        ],
        "versions": [
            {
                "prescription_id": str(v.prescription_id),
                "version": v.version,
                "status": v.status.value,
            }
            for v in h.versions
        ],
    }


def _uuid_arg(name: str) -> UUID:
    try:
        return UUID(request.args[name])
    except (KeyError, ValueError):
        raise InvalidValue(name, "must be an ID") from None


def _hhmm(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value is not None else None


def reminder_body(r: Reminder) -> dict[str, Any]:
    return {"enabled": r.enabled, "remind_at": _hhmm(r.remind_at)}


def _context_body(c: PlanContext) -> dict[str, Any]:
    return {
        "prescription_id": str(c.prescription_id),
        "version": c.version,
        "clinic_id": str(c.clinic_id),
        "clinic_name": c.clinic_name,
        "clinic_phone_e164": c.clinic_phone_e164,
        "doctor_name": c.doctor_name,
        "starts_on": c.starts_on.isoformat(),
        "timezone": c.timezone,
    }


def _line_body(w: LineWords) -> dict[str, Any]:
    return {
        "item_id": str(w.item_id),
        "medicine_name": w.medicine_name,
        "form_strength": w.form_strength,
        "dose": w.dose,
        "as_written": w.as_written,
        "timing": w.timing,
        "how": w.how,
        "duration": w.duration,
    }


def _entry_body(e: PlanEntry) -> dict[str, Any]:
    return {
        **_context_body(e.context),
        **_line_body(e.line),
        "day": e.day,
        "days_total": e.days_total,
        "reminder": reminder_body(e.reminder) if e.reminder else None,
        # M6b-P3b: the patient's mark (``dose`` above is the doctor's dose, as written).
        "mark": dose_body(e.dose) if e.dose else None,
    }


def medicine_plan_body(p: MedicinePlan) -> dict[str, Any]:
    """R35, R36: words in the account's language; the doctor's text as written."""
    return {
        "date": p.on_date.isoformat(),
        "today": p.today.isoformat(),
        "language": p.language.value,
        "has_prescriptions": p.has_prescriptions,
        "slots": [
            {
                "slot": s.slot.value,
                "label": s.label,
                "time": _hhmm(s.time),
                "entries": [_entry_body(e) for e in s.entries],
            }
            for s in p.slots
        ],
        "as_written": [_entry_body(e) for e in p.as_written],
    }


def course_body(c: CourseView) -> dict[str, Any]:
    return {
        **_context_body(c.context),
        "revised": c.revised,
        "reminders_set": c.reminders_set,
        "ends_on": c.ends_on.isoformat() if c.ends_on else None,
        "lines": [
            {
                **_line_body(line.line),
                "ends_on": line.ends_on.isoformat() if line.ends_on else None,
                "slots": [
                    {
                        "slot": s.slot.value,
                        "label": s.label,
                        "time": _hhmm(s.time),
                        "reminder": reminder_body(s.reminder),
                    }
                    for s in line.slots
                ],
            }
            for line in c.lines
        ],
    }


def _plan_date() -> date | None:
    raw = request.args.get("date")
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise InvalidValue("date", "must be a date as YYYY-MM-DD") from None


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


def status_body(s: PatientPortalStatus) -> dict[str, Any]:
    """R14: never the account's email or name."""
    return {
        "status": s.status.value,
        "method": s.method.value if s.method else None,
        "linked_at": s.linked_at.isoformat() if s.linked_at else None,
        "invite_expires_at": s.invite_expires_at.isoformat() if s.invite_expires_at else None,
    }


def linked_body(r: LinkedRecord) -> dict[str, Any]:
    return {
        "id": str(r.link_id),
        "clinic_id": str(r.clinic_id),
        "clinic_name": r.clinic_name,
        "patient_first_name": r.patient_first_name,
        "patient_code": r.patient_code,
        "method": r.method.value,
        "linked_at": r.linked_at.isoformat(),
    }


def portal_appointment_body(p: PortalAppointment) -> dict[str, Any]:
    a, s = p.appointment, p.session
    return {
        "id": str(a.id),
        "doctor_name": p.doctor_name,
        "on_date": s.on_date.isoformat(),
        "starts_at": p.starts_at.isoformat(),
        "session_starts_at": s.starts_at.isoformat(),
        "session_ends_at": s.ends_at.isoformat(),
        "mode": s.mode.value,
        "slot_start": a.slot_start.isoformat() if a.slot_start else None,
        "token_number": a.token_number,
        "status": a.status.value,
    }


def _items(bodies: Iterable[dict[str, Any]]) -> Response:
    return jsonify(items_body(bodies))


def _language() -> Language | None:
    raw = request.args.get("lang")
    if raw is None:
        return None
    try:
        return Language(raw)
    except ValueError:
        raise InvalidValue("lang", "must be en or hi") from None


def create_portal_records_blueprint(use_cases: PortalRecordUseCases) -> Blueprint:
    bp = Blueprint("portal_records", __name__, url_prefix="/api/v1/portal")
    bp.after_request(_no_store)

    @bp.get("/links")
    @patient
    def list_links() -> Response:
        return _items(
            {
                "id": str(v.link_id),
                "clinic": {
                    "id": str(v.clinic_id),
                    "name": v.clinic_name,
                    "phone_e164": v.clinic_phone_e164,
                    "address_line": v.clinic_address_line,
                    "city": v.clinic_city,
                    "timezone": v.clinic_timezone,
                },
                "patient_first_name": v.patient_first_name,
                "patient_code": v.patient_code,
                "method": v.method.value,
                "linked_at": v.linked_at.isoformat(),
            }
            for v in use_cases.list_portal_links().execute(current_patient())
        )

    @bp.delete("/links/<uuid:link_id>")
    @patient
    def unlink(link_id: UUID) -> Response:
        revoked_at = use_cases.unlink_portal().execute(current_patient(), link_id, request_info())
        return jsonify({"id": str(link_id), "revoked_at": revoked_at.isoformat()})

    @bp.post("/links/prescription")
    @patient
    def link_by_prescription() -> tuple[Response, int]:
        body = parse_json(PrescriptionLinkRequest)
        record = use_cases.link_by_prescription().execute(
            current_patient(), body.token, body.phone_last4, request_info()
        )
        return jsonify(linked_body(record)), 201

    @bp.get("/invites/<token>")
    @patient
    def describe_invite(token: str) -> Response:
        summary = use_cases.describe_portal_invite().execute(current_patient(), token)
        return jsonify(
            {
                "clinic_name": summary.clinic_name,
                "patient_first_name": summary.patient_first_name,
                "patient_code": summary.patient_code,
            }
        )

    @bp.post("/invites/<token>/accept")
    @patient
    def accept_invite(token: str) -> tuple[Response, int]:
        record = use_cases.accept_portal_invite().execute(current_patient(), token, request_info())
        return jsonify(linked_body(record)), 201

    @bp.get("/appointments")
    @patient
    def list_appointments() -> Response:
        return _items(
            {
                "clinic_id": str(g.clinic_id),
                "clinic_name": g.clinic_name,
                "timezone": g.clinic_timezone,
                "phone_e164": g.clinic_phone_e164,
                "appointments": [portal_appointment_body(a) for a in g.appointments],
            }
            for g in use_cases.list_portal_appointments().execute(current_patient())
        )

    @bp.get("/prescriptions")
    @patient
    def list_prescriptions() -> Response:
        return _items(
            {
                "id": str(p.id),
                "clinic_id": str(p.clinic_id),
                "clinic_name": p.clinic_name,
                "doctor_name": p.doctor_name,
                "version": p.version,
                "issued_at": p.issued_at.isoformat(),
            }
            for p in use_cases.list_portal_prescriptions().execute(current_patient())
        )

    @bp.get("/prescriptions/<uuid:rx_id>")
    @patient
    def get_prescription(rx_id: UUID) -> Response:
        page = use_cases.get_portal_prescription().execute(current_patient(), rx_id, _language())
        return jsonify(patient_view_body(page))

    @bp.get("/prescriptions/<uuid:rx_id>/pdf")
    @patient
    def prescription_pdf(rx_id: UUID) -> Response:
        pdf = use_cases.portal_prescription_pdf().execute(current_patient(), rx_id)
        response = Response(pdf.data, mimetype=PDF_CONTENT_TYPE)
        response.headers["Content-Disposition"] = f'inline; filename="{pdf.filename}"'
        return response

    @bp.get("/reminders")
    @patient
    def list_reminders() -> Response:
        return _items(
            {
                "id": str(r.id),
                "clinic_id": str(r.clinic_id),
                "clinic_name": r.clinic_name,
                "kind": r.kind,
                "follow_up_date": r.follow_up_date.isoformat(),
                "due_at": r.due_at.isoformat(),
                "status": r.status,
            }
            for r in use_cases.list_portal_reminders().execute(current_patient())
        )

    @bp.get("/medicine-plan")
    @patient
    def medicine_plan() -> Response:
        plan = use_cases.get_medicine_plan().execute(current_patient(), _plan_date())
        return jsonify(medicine_plan_body(plan))

    @bp.get("/medicine-plan/courses")
    @patient
    def medicine_courses() -> Response:
        return _items(
            course_body(c) for c in use_cases.list_medicine_courses().execute(current_patient())
        )

    @bp.put("/medicine-plan/reminders")
    @patient
    def set_medicine_reminder() -> Response:
        body = parse_json(ReminderRequest)
        reminder = use_cases.set_medicine_reminder().execute(
            current_patient(),
            ReminderChoice(
                body.prescription_id, body.item_id, body.slot, body.enabled, body.remind_at
            ),
        )
        return jsonify(reminder_body(reminder))

    @bp.post("/booking-requests")
    @patient
    def create_booking_request() -> tuple[Response, int]:
        body = parse_json(BookingRequestBody)
        item = use_cases.create_booking_request().execute(
            current_patient(),
            BookingRequestCommand(
                clinic_slug=body.clinic_slug,
                doctor_id=body.doctor_id,
                session_start=body.session_start.astimezone(UTC),
                slot_start=body.slot_start.astimezone(UTC) if body.slot_start else None,
                contact_phone=body.contact_phone,
                age_years=body.age_years,
                sex=body.sex,
                reason=body.reason,
                not_emergency_ack=body.not_emergency_ack,
            ),
            request_info(),
        )
        return jsonify(request_item_body(item)), 201

    # --- M6b-P6: the notification centre (R67, R68) and the live token link (R69) -------------

    @bp.get("/notifications")
    @patient
    def list_notifications() -> Response:
        return jsonify(
            items_body(
                notice_body(n)
                for n in use_cases.list_patient_notifications().execute(current_patient())
            )
        )

    @bp.get("/notifications/summary")
    @patient
    def notification_summary() -> Response:
        summary = use_cases.patient_notification_summary().execute(current_patient())
        return conditional_json(
            {
                "unread": summary.unread,
                "latest_id": str(summary.latest_id) if summary.latest_id else None,
            }
        )

    @bp.post("/notifications/<uuid:notification_id>/read")
    @patient
    def read_notification(notification_id: UUID) -> tuple[Response, int]:
        use_cases.mark_patient_notification_read().execute(current_patient(), notification_id)
        return Response(status=204), 204

    @bp.post("/notifications/read-all")
    @patient
    def read_all_notifications() -> Response:
        marked = use_cases.mark_all_patient_notifications_read().execute(current_patient())
        return jsonify({"marked": marked})

    @bp.get("/notification-preferences")
    @patient
    def notification_preferences() -> Response:
        return jsonify(
            items_body(
                {"kind": p.kind.value, "in_app": p.in_app, "email": p.email}
                for p in use_cases.get_patient_preferences().execute(current_patient())
            )
        )

    @bp.put("/notification-preferences")
    @patient
    def set_notification_preference() -> Response:
        body = parse_json(PreferenceRequest)
        principal = current_patient()
        use_cases.set_patient_preference().execute(principal, body.kind, body.channel, body.enabled)
        return jsonify(
            items_body(
                {"kind": p.kind.value, "in_app": p.in_app, "email": p.email}
                for p in use_cases.get_patient_preferences().execute(principal)
            )
        )

    @bp.get("/appointments/<uuid:appointment_id>/live-link")
    @patient
    def live_link(appointment_id: UUID) -> Response:
        link = use_cases.issue_portal_live_link().execute(current_patient(), appointment_id)
        return jsonify({"url": link.url, "expires_at": link.expires_at.isoformat()})

    @bp.post("/booking-requests/<uuid:request_id>/accept-proposal")
    @patient
    def accept_proposal(request_id: UUID) -> Response:
        result = use_cases.accept_proposal().execute(current_patient(), request_id, request_info())
        return jsonify({"id": str(result.request_id), "status": result.status.value})

    @bp.post("/booking-requests/<uuid:request_id>/decline-proposal")
    @patient
    def decline_proposal(request_id: UUID) -> Response:
        result = use_cases.decline_proposal().execute(current_patient(), request_id, request_info())
        return jsonify({"id": str(result.request_id), "status": result.status.value})

    @bp.get("/booking-requests")
    @patient
    def list_booking_requests() -> Response:
        return _items(
            request_item_body(i)
            for i in use_cases.list_my_booking_requests().execute(current_patient())
        )

    @bp.put("/medicine-plan/doses")
    @patient
    def mark_dose() -> Response:
        body = parse_json(DoseRequest)
        result = use_cases.mark_dose().execute(
            current_patient(),
            DoseChoice(body.prescription_id, body.item_id, body.on_date, body.slot),
            body.state,
        )
        return jsonify(dose_body(result))

    @bp.delete("/medicine-plan/doses")
    @patient
    def clear_dose() -> Response:
        try:
            on_date = date.fromisoformat(request.args.get("on_date", ""))
            slot = Slot(request.args.get("slot", ""))
        except ValueError:
            raise InvalidValue("on_date", "send on_date (YYYY-MM-DD) and slot") from None
        choice = DoseChoice(_uuid_arg("prescription_id"), _uuid_arg("item_id"), on_date, slot)
        return jsonify(dose_body(use_cases.clear_dose().execute(current_patient(), choice)))

    @bp.get("/medicine-plan/history")
    @patient
    def dose_history() -> Response:
        history = use_cases.dose_history().execute(current_patient(), _uuid_arg("prescription_id"))
        return jsonify(history_body(history))

    return bp


def create_patient_portal_blueprint(
    use_cases: PatientPortalUseCases, *, public_base_url: str
) -> Blueprint:
    bp = Blueprint("patient_portal", __name__, url_prefix="/api/v1/patients")
    bp.after_request(_no_store)

    @bp.post("/<uuid:patient_id>/portal-invite")
    @clinic(Permission.PATIENTS_MANAGE)
    def invite(patient_id: UUID) -> tuple[Response, int]:
        invitation = use_cases.invite_to_portal().execute(current_context(), patient_id)
        # R1: the only place the secret appears.
        return jsonify(
            {
                "url": f"{public_base_url}/portal/link/{invitation.token}",
                "expires_at": invitation.expires_at.isoformat(),
            }
        ), 201

    @bp.get("/<uuid:patient_id>/portal")
    @clinic(Permission.PATIENTS_MANAGE)
    def status(patient_id: UUID) -> Response:
        return jsonify(
            status_body(use_cases.get_portal_status().execute(current_context(), patient_id))
        )

    @bp.delete("/<uuid:patient_id>/portal-link")
    @clinic(Permission.PATIENTS_MANAGE)
    def unlink(patient_id: UUID) -> Response:
        use_cases.unlink_patient().execute(current_context(), patient_id)
        return jsonify(
            status_body(use_cases.get_portal_status().execute(current_context(), patient_id))
        )

    return bp
