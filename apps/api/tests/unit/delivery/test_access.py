"""Default deny: every route declares an access policy (FR-AUTH-03, spec R6-R10).

These are the structural guards. Who may actually call what is proved end to
end in ``tests/integration/test_authorization_http.py``.
"""

from __future__ import annotations

import pytest
from flask import Flask

from mediease_api.delivery.http.access import (
    Access,
    MissingAccessPolicy,
    check_every_route_has_policy,
    current_context,
    current_principal,
    policy_of,
)
from mediease_api.domain.identity.permissions import Permission

# The whole HTTP surface after M3-P1, and the policy each route carries.
EXPECTED_POLICIES = {
    "platform.health": (Access.PUBLIC, None),
    "platform.ready": (Access.PUBLIC, None),
    "auth.sign_in": (Access.PUBLIC, None),
    "auth.refresh": (Access.PUBLIC, None),
    "auth.sign_out": (Access.PUBLIC, None),
    # M6a-P3: Google sign-in (the authority is the flow cookie and Google's ID token) and the
    # patient portal, whose only non-public route takes a portal session.
    "google.start": (Access.PUBLIC, None),
    "google.callback": (Access.PUBLIC, None),
    "portal.sign_up": (Access.PUBLIC, None),
    "portal.sign_in": (Access.PUBLIC, None),
    "portal.refresh": (Access.PUBLIC, None),
    "portal.sign_out": (Access.PUBLIC, None),
    "portal.me": (Access.PATIENT, None),
    "portal.update_me": (Access.PATIENT, None),
    # M6b-P1: linking and the patient's own records.
    "portal_records.list_links": (Access.PATIENT, None),
    "portal_records.unlink": (Access.PATIENT, None),
    "portal_records.link_by_prescription": (Access.PATIENT, None),
    "portal_records.describe_invite": (Access.PATIENT, None),
    "portal_records.accept_invite": (Access.PATIENT, None),
    "portal_records.list_appointments": (Access.PATIENT, None),
    "portal_records.list_prescriptions": (Access.PATIENT, None),
    "portal_records.get_prescription": (Access.PATIENT, None),
    "portal_records.prescription_pdf": (Access.PATIENT, None),
    "portal_records.list_reminders": (Access.PATIENT, None),
    # M6b-P3: the medicine plan and the person's reminder choices.
    "portal_records.medicine_plan": (Access.PATIENT, None),
    "portal_records.medicine_courses": (Access.PATIENT, None),
    "portal_records.set_medicine_reminder": (Access.PATIENT, None),
    # M6b-P3b: the patient's own dose marks; no staff or ops route reaches them.
    "portal_records.mark_dose": (Access.PATIENT, None),
    "portal_records.clear_dose": (Access.PATIENT, None),
    "portal_records.dose_history": (Access.PATIENT, None),
    "patient_portal.invite": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "patient_portal.status": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "patient_portal.unlink": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    # M6a-P4: the emailed links' endpoints are public (the token is the authority); the resend
    # is the signed-in patient's.
    "auth.request_password_reset": (Access.PUBLIC, None),
    "auth.complete_password_reset": (Access.PUBLIC, None),
    "portal.request_password_reset": (Access.PUBLIC, None),
    "portal.complete_password_reset": (Access.PUBLIC, None),
    "portal.verify_email": (Access.PUBLIC, None),
    "portal.resend_verification": (Access.PATIENT, None),
    # The authority is the invitation secret in the URL, not a session.
    "invites.describe_invite": (Access.PUBLIC, None),
    "invites.accept_invite": (Access.PUBLIC, None),
    "me.me": (Access.AUTHENTICATED, None),
    "clinic.get_clinic": (Access.CLINIC, Permission.CLINIC_VIEW),
    "clinic.update_clinic": (Access.CLINIC, Permission.CLINIC_MANAGE),
    "clinic.list_doctors": (Access.CLINIC, Permission.DOCTORS_VIEW),
    "clinic.add_doctor": (Access.CLINIC, Permission.CLINIC_MANAGE),
    "clinic.get_doctor": (Access.CLINIC, Permission.DOCTORS_VIEW),
    "clinic.update_doctor": (Access.CLINIC, Permission.CLINIC_MANAGE),
    "clinic.list_staff": (Access.CLINIC, Permission.STAFF_MANAGE),
    "clinic.invite_staff": (Access.CLINIC, Permission.STAFF_MANAGE),
    "clinic.change_membership": (Access.CLINIC, Permission.STAFF_MANAGE),
    "clinic.resend_invite": (Access.CLINIC, Permission.STAFF_MANAGE),
    "patients.register_patient": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "my_patients.list_my_patients": (Access.CLINIC, Permission.CLINICAL_VIEW),
    "notifications.list_notifications": (Access.CLINIC, Permission.CLINIC_VIEW),
    "notifications.notification_summary": (Access.CLINIC, Permission.CLINIC_VIEW),
    "notifications.read_notification": (Access.CLINIC, Permission.CLINIC_VIEW),
    "notifications.read_all_notifications": (Access.CLINIC, Permission.CLINIC_VIEW),
    "notifications.notification_preferences": (Access.CLINIC, Permission.CLINIC_VIEW),
    "notifications.set_notification_preferences": (Access.CLINIC, Permission.CLINIC_VIEW),
    # M6a-P8: bookings to move, and the owner's audit log.
    "appointments.list_bookings_to_move": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "audit_log.list_audit_events": (Access.CLINIC, Permission.AUDIT_VIEW),
    "audit_log.export_audit_events": (Access.CLINIC, Permission.AUDIT_VIEW),
    "patients.lookup_patients": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "patients.get_patient": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "patients.update_patient": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "patients.record_consent": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "patients.opt_out": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "patients.opt_in": (Access.CLINIC, Permission.PATIENTS_MANAGE),
    "scheduling.get_schedule": (Access.CLINIC, Permission.DOCTORS_VIEW),
    "scheduling.replace_schedule": (Access.CLINIC, Permission.SCHEDULES_MANAGE),
    "scheduling.add_exception": (Access.CLINIC, Permission.SCHEDULES_MANAGE),
    "scheduling.remove_exception": (Access.CLINIC, Permission.SCHEDULES_MANAGE),
    "scheduling.list_sessions": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "appointments.book_appointment": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "appointments.get_appointment": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "appointments.cancel_appointment": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "appointments.reschedule_appointment": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "appointments.list_patient_appointments": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "appointments.transition_appointment": (Access.CLINIC, Permission.QUEUE_MOVE),
    "appointments.add_walk_in": (Access.CLINIC, Permission.QUEUE_MOVE),
    "appointments.get_queue": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "visits.start_visit": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "visits.get_visit": (Access.CLINIC, Permission.CLINICAL_VIEW),
    "visits.update_visit": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "visits.complete_visit": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "visits.add_addendum": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "visits.list_patient_visits": (Access.CLINIC, Permission.CLINICAL_VIEW),
    "prescriptions.create_prescription": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "prescriptions.get_prescription": (Access.CLINIC, Permission.CLINICAL_VIEW),
    "prescriptions.replace_prescription": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "prescriptions.discard_prescription": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "prescriptions.issue_prescription": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "prescriptions.revise_prescription": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "prescriptions.preview_prescription": (Access.CLINIC, Permission.CLINICAL_VIEW),
    "prescriptions.prescription_pdf": (Access.CLINIC, Permission.RX_PRINT),
    "prescriptions.list_printable": (Access.CLINIC, Permission.RX_PRINT),
    "prescriptions.get_patient_link": (Access.CLINIC, Permission.RX_PRINT),
    "prescriptions.reset_patient_link": (Access.CLINIC, Permission.RX_PRINT),
    "prescriptions.replace_patient_link": (Access.CLINIC, Permission.RX_PRINT),
    # M6b-P4: the public clinic page and its availability; a clinic that is not public is a 404.
    "public_clinics.get_clinic": (Access.PUBLIC, None),
    "public_clinics.availability": (Access.PUBLIC, None),
    "booking_requests.list_booking_requests": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    # M6b-P5: answering requests (a new record also needs PATIENTS_MANAGE, checked in the route).
    "booking_requests.candidates": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "booking_requests.accept": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "booking_requests.decline": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "booking_requests.propose": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "portal_records.accept_proposal": (Access.PATIENT, None),
    # M6b-P6: the bell, preferences and live links; the public live-queue page.
    "portal_records.list_notifications": (Access.PATIENT, None),
    "portal_records.notification_summary": (Access.PATIENT, None),
    "portal_records.read_notification": (Access.PATIENT, None),
    "portal_records.read_all_notifications": (Access.PATIENT, None),
    "portal_records.notification_preferences": (Access.PATIENT, None),
    "portal_records.set_notification_preference": (Access.PATIENT, None),
    "portal_records.live_link": (Access.PATIENT, None),
    "appointments.live_link": (Access.CLINIC, Permission.APPOINTMENTS_MANAGE),
    "public_queue.live_queue": (Access.PUBLIC, None),
    "portal_records.decline_proposal": (Access.PATIENT, None),
    "portal_records.create_booking_request": (Access.PATIENT, None),
    "portal_records.list_booking_requests": (Access.PATIENT, None),
    "public_links.describe_link": (Access.PUBLIC, None),
    "public_links.verify_link": (Access.PUBLIC, None),
    "public_links.view_link_prescription": (Access.PUBLIC, None),
    # M5-P3: Meta's webhook; the challenge needs our verify token, the body our signature.
    "whatsapp_webhook.verify_whatsapp_subscription": (Access.PUBLIC, None),
    "whatsapp_webhook.receive_whatsapp_webhook": (Access.PUBLIC, None),
    "reminders.list_patient_reminders": (Access.CLINIC, Permission.REMINDERS_SCHEDULE),
    "reminders.schedule_reminder": (Access.CLINIC, Permission.REMINDERS_SCHEDULE),
    "reminders.change_reminder": (Access.CLINIC, Permission.REMINDERS_SCHEDULE),
    "reminders.list_pending_follow_ups": (Access.CLINIC, Permission.REMINDERS_SCHEDULE),
    "reminders.list_patient_messages": (Access.CLINIC, Permission.REMINDERS_SCHEDULE),
    # M6-P1: Today, for every clinic role (the 7-day strip is shaped inside, not refused).
    "dashboard.get_today": (Access.CLINIC, Permission.CLINIC_VIEW),
    "rx_library.list_favourites": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.create_favourite": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.replace_favourite": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.delete_favourite": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.list_templates": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.create_template": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.get_template": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.replace_template": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.delete_template": (Access.CLINIC, Permission.CLINICAL_WRITE),
    "rx_library.suggest_medicines": (Access.CLINIC, Permission.CLINICAL_WRITE),
    # M6b-P3: the engine's slot sets and codes, for the editor; no clinic data.
    "rx_library.rx_vocabulary": (Access.CLINIC, Permission.CLINICAL_VIEW),
    "ops.replace_schedule": (Access.OPS, None),
    "ops.create_clinic": (Access.OPS, None),
    "ops.list_clinics": (Access.OPS, None),
    "ops.get_clinic": (Access.OPS, None),
    "ops.add_doctor": (Access.OPS, None),
    "ops.invite_staff": (Access.OPS, None),
    # M5-P5 (R18): counts and money per clinic, platform staff only.
    "ops.messaging_costs": (Access.OPS, None),
    # M6c-P1 (clinic-onboarding R1, R12, R18): applying, confirming, and the ops list.
    # M6c-P2 (R24): the reviewer's routes (OPS policy with the OPS_REVIEWER role).
    "ops_applications.list_applications": (Access.OPS, None),
    "ops_applications.get_application": (Access.OPS, None),
    "ops_applications.certificate": (Access.OPS, None),
    "ops_applications.take": (Access.OPS, None),
    "ops_applications.check": (Access.OPS, None),
    "ops_applications.reject": (Access.OPS, None),
    # M6c-P3 (R41, R45): approval and the verification of ops-created clinics.
    "ops_applications.approve": (Access.OPS, None),
    "ops_verification.verify_doctor": (Access.OPS, None),
    "ops_verification.verify_clinic": (Access.OPS, None),
    # M6c-P4 (R50-R58): suspension (OPS_ADMIN) and the owner's listing.
    "ops_suspension.suspend": (Access.OPS, None),
    "ops_suspension.reactivate": (Access.OPS, None),
    "listing.get_listing": (Access.CLINIC, Permission.CLINIC_VIEW),
    "listing.set_listing": (Access.CLINIC, Permission.CLINIC_MANAGE),
    "listing.set_visibility": (Access.CLINIC, Permission.CLINIC_MANAGE),
    # M6c-P5 (R61, R63): a doctor's public profile and the sitemap.
    "listing.set_profile": (Access.CLINIC, Permission.CLINIC_MANAGE),
    # M6d-P1 (billing R6): the fee schedule.
    "fees.get_fees": (Access.CLINIC, Permission.BILLING_MANAGE),
    "fees.add_service": (Access.CLINIC, Permission.FEES_MANAGE),
    "fees.change_service": (Access.CLINIC, Permission.FEES_MANAGE),
    "fees.set_doctor_price": (Access.CLINIC, Permission.FEES_MANAGE),
    "public_sitemap.sitemap": (Access.PUBLIC, None),
    # M6c-P6 (discovery R1-R10): directory search.
    "public_search.clinics": (Access.PUBLIC, None),
    "public_search.doctors": (Access.PUBLIC, None),
    "public_applications.submit": (Access.PUBLIC, None),
    "public_applications.confirm": (Access.PUBLIC, None),
    # Ops imports patients but cannot browse them (spec patients §2, M2-P4).
    "ops.import_patients": (Access.OPS, None),
}


def test_fr_auth_03_every_route_declares_the_expected_policy(app: Flask) -> None:
    """A new endpoint must appear here — and in the authorisation tests — on purpose."""
    actual = {}
    for endpoint, view in app.view_functions.items():
        policy = policy_of(view)
        assert policy is not None, endpoint
        actual[endpoint] = (policy.access, policy.permission)
    assert actual == EXPECTED_POLICIES


def test_fr_auth_03_an_app_with_an_undeclared_route_does_not_start(app: Flask) -> None:
    @app.get("/forgotten")
    def _forgotten() -> str:
        return "no policy"

    with pytest.raises(MissingAccessPolicy, match="_forgotten"):
        check_every_route_has_policy(app)


def test_fr_auth_03_calling_an_undeclared_route_is_refused_not_served(app: Flask) -> None:
    """Belt and braces: a route registered after start-up is never served either."""

    @app.get("/forgotten")
    def _forgotten() -> str:
        return "no policy"

    resp = app.test_client().get("/forgotten")
    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "SYS_UNEXPECTED"
    assert "no policy" not in resp.get_data(as_text=True)


def test_context_accessors_fail_loudly_on_the_wrong_policy(app: Flask) -> None:
    @app.get("/public-route")
    def _public_route() -> str:
        return "ok"

    with app.test_request_context("/public-route"):
        with pytest.raises(RuntimeError, match="@authenticated"):
            current_principal()
        with pytest.raises(RuntimeError, match="@clinic"):
            current_context()
