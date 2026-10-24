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

Staff (``PATIENTS_MANAGE``, under ``/api/v1/patients/{patient_id}``): ``POST /portal-invite``,
``GET /portal``, ``DELETE /portal-link`` (R1, R8, R14).

Every response is ``Cache-Control: no-store``. Bodies carry no clinical notes, no appointment
reason and no staff fields; staff never see the account's email or name.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

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
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.patients.patient import Language
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


class PatientPortalUseCases(Protocol):
    def invite_to_portal(self) -> InviteToPortal: ...
    def get_portal_status(self) -> GetPortalStatus: ...
    def unlink_patient(self) -> UnlinkPatient: ...


class PrescriptionLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
    phone_last4: str = Field(pattern=r"^[0-9]{4}$")


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
