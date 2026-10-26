"""Tenancy isolation over HTTP (NFR-08, spec R8, AC3).

The repository suite proves clinic A's scope cannot reach clinic B's rows.
This one proves the same through the whole stack, for the requests a browser
actually makes, and keeps itself honest: ``test_every_clinic_route_with_an_id``
fails when a new clinic endpoint takes a resource ID without a cross-clinic
case here, so the guard cannot be forgotten (CLAUDE.md "Tenancy isolation is a
permanent test suite").
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from uuid import uuid4

import pytest
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mediease_api.delivery.http.access import Access, policy_of
from tests.booking_helpers import offers, request_in, staff_session_after
from tests.conftest import World
from tests.integration.test_portal_http import portal_csrf
from tests.portal_helpers import portal_client
from tests.sessions_now import running_session

# A date well inside the 180-day horizon whatever day the suite runs (M3-P1 exceptions).
_FAR_DATE = (date.today() + timedelta(days=30)).isoformat()


# Rule -> a URL naming a resource of clinic B. Requested by clinic A's owner,
# each must answer 404 as if it did not exist.
CROSS_TENANT_CASES: dict[str, Callable[[World], str]] = {
    "/api/v1/clinic/doctors/<uuid:doctor_id>": lambda w: f"/api/v1/clinic/doctors/{w.b.doctor.id}",
    # M6c-P4 (R53): the owner's visibility switch.
    "/api/v1/clinic/listing/doctors/<uuid:doctor_id>": lambda w: (
        f"/api/v1/clinic/listing/doctors/{w.b.doctor.id}"
    ),
    # M6d-P1 (billing R7): the fee schedule, with clinic B's own service.
    "/api/v1/clinic/fees/services/<uuid:service_id>": lambda w: (
        f"/api/v1/clinic/fees/services/{_service_of_b(w)}"
    ),
    "/api/v1/clinic/fees/services/<uuid:service_id>/doctors/<uuid:doctor_id>": lambda w: (
        f"/api/v1/clinic/fees/services/{_service_of_b(w)}/doctors/{w.b.doctor.id}"
    ),
    "/api/v1/clinic/listing/doctors/<uuid:doctor_id>/profile": lambda w: (
        f"/api/v1/clinic/listing/doctors/{w.b.doctor.id}/profile"
    ),
    # M6d-P2 (billing R21): clinic B's bills.
    "/api/v1/clinic/bills/<uuid:bill_id>": lambda w: _bill_of_b(w),
    "/api/v1/clinic/bills/<uuid:bill_id>/issue": lambda w: f"{_bill_of_b(w)}/issue",
    "/api/v1/clinic/bills/<uuid:bill_id>/credit-notes": lambda w: (
        f"{_bill_of_b(w, issued=True)}/credit-notes"
    ),
    "/api/v1/clinic/staff/<uuid:membership_id>": lambda w: _staff_url(w),
    "/api/v1/clinic/staff/<uuid:membership_id>/resend": lambda w: _invited_staff_url(w),
    "/api/v1/patients/<uuid:patient_id>": lambda w: _patient_url(w),
    "/api/v1/patients/<uuid:patient_id>/consent": lambda w: f"{_patient_url(w)}/consent",
    "/api/v1/patients/<uuid:patient_id>/opt-out": lambda w: f"{_patient_url(w)}/opt-out",
    "/api/v1/patients/<uuid:patient_id>/opt-in": lambda w: f"{_opted_out_patient_url(w)}/opt-in",
    "/api/v1/clinic/doctors/<uuid:doctor_id>/schedule": lambda w: (
        f"/api/v1/clinic/doctors/{w.b.doctor.id}/schedule"
    ),
    "/api/v1/clinic/doctors/<uuid:doctor_id>/schedule-exceptions": lambda w: (
        f"/api/v1/clinic/doctors/{w.b.doctor.id}/schedule-exceptions"
    ),
    "/api/v1/clinic/doctors/<uuid:doctor_id>/schedule-exceptions/<uuid:exception_id>": lambda w: (
        _exception_url(w)
    ),
    "/api/v1/appointments/<uuid:appointment_id>": lambda w: _appointment_url(w),
    "/api/v1/appointments/<uuid:appointment_id>/cancel": lambda w: f"{_appointment_url(w)}/cancel",
    "/api/v1/appointments/<uuid:appointment_id>/reschedule": lambda w: (
        f"{_appointment_url(w)}/reschedule"
    ),
    "/api/v1/patients/<uuid:patient_id>/appointments": lambda w: f"{_patient_url(w)}/appointments",
    "/api/v1/appointments/<uuid:appointment_id>/transitions": lambda w: (
        f"{_appointment_url(w, today=True)}/transitions"
    ),
    "/api/v1/visits/<uuid:visit_id>": lambda w: _visit_url(w),
    "/api/v1/visits/<uuid:visit_id>/complete": lambda w: f"{_visit_url(w)}/complete",
    "/api/v1/visits/<uuid:visit_id>/addenda": lambda w: f"{_visit_url(w, completed=True)}/addenda",
    "/api/v1/patients/<uuid:patient_id>/visits": lambda w: f"{_patient_url(w)}/visits",
    "/api/v1/visits/<uuid:visit_id>/prescriptions": lambda w: f"{_visit_url(w)}/prescriptions",
    "/api/v1/prescriptions/<uuid:rx_id>": lambda w: _prescription_url(w),
    "/api/v1/prescriptions/<uuid:rx_id>/issue": lambda w: f"{_prescription_url(w)}/issue",
    "/api/v1/prescriptions/<uuid:rx_id>/preview": lambda w: f"{_prescription_url(w)}/preview",
    "/api/v1/prescriptions/<uuid:rx_id>/revise": lambda w: (
        f"{_prescription_url(w, issued=True)}/revise"
    ),
    "/api/v1/prescriptions/<uuid:rx_id>/pdf": lambda w: f"{_prescription_url(w, issued=True)}/pdf",
    "/api/v1/patients/<uuid:patient_id>/prescriptions": lambda w: (
        f"{_patient_url(w)}/prescriptions"
    ),
    "/api/v1/prescriptions/<uuid:rx_id>/link": lambda w: (
        f"{_prescription_url(w, issued=True)}/link"
    ),
    "/api/v1/prescriptions/<uuid:rx_id>/link/reset": lambda w: f"{_locked_link_url(w)}/reset",
    "/api/v1/prescriptions/<uuid:rx_id>/link/replace": lambda w: (
        f"{_prescription_url(w, issued=True)}/link/replace"
    ),
    "/api/v1/rx-favourites/<uuid:favourite_id>": lambda w: _library_url(w, "rx-favourites"),
    "/api/v1/rx-templates/<uuid:template_id>": lambda w: _library_url(w, "rx-templates"),
    # M5-P4: a patient's reminders and one reminder of clinic B.
    "/api/v1/patients/<uuid:patient_id>/reminders": lambda w: f"{_patient_url(w)}/reminders",
    # M5-P6: a patient's message history.
    "/api/v1/patients/<uuid:patient_id>/messages": lambda w: f"{_patient_url(w)}/messages",
    "/api/v1/reminders/<uuid:reminder_id>": lambda w: _reminder_url(w),
    # M6a-P7: one of clinic B's doctor's notifications.
    "/api/v1/notifications/<uuid:notification_id>/read": lambda w: _notification_url(w),
    # M6b-P1: a clinic B patient's portal invite, status and link.
    "/api/v1/patients/<uuid:patient_id>/portal-invite": lambda w: (
        f"{_patient_url(w)}/portal-invite"
    ),
    "/api/v1/patients/<uuid:patient_id>/portal": lambda w: f"{_patient_url(w)}/portal",
    "/api/v1/patients/<uuid:patient_id>/portal-link": lambda w: (
        f"{_linked_patient_url(w)}/portal-link"
    ),
    # M6b-P5: a booking request clinic B received; clinic A can neither see nor answer it.
    "/api/v1/booking-requests/<uuid:request_id>/candidates": lambda w: (
        f"{_request_url(w)}/candidates"
    ),
    "/api/v1/booking-requests/<uuid:request_id>/accept": lambda w: f"{_request_url(w)}/accept",
    "/api/v1/booking-requests/<uuid:request_id>/decline": lambda w: f"{_request_url(w)}/decline",
    "/api/v1/booking-requests/<uuid:request_id>/propose": lambda w: _proposable_url(w),
    # M6b-P6: clinic B's appointment's live token link.
    "/api/v1/appointments/<uuid:appointment_id>/live-link": lambda w: (
        f"{_appointment_url(w)}/live-link"
    ),
}

# Clinical writes need CLINICAL_WRITE and the visit's doctor (prescriptions spec §2), so these
# rules are tried by each clinic's doctor instead of its owner (an owner would get a 403 first).
AS_DOCTOR = {
    "/api/v1/visits/<uuid:visit_id>/complete",
    "/api/v1/visits/<uuid:visit_id>/addenda",
    "/api/v1/visits/<uuid:visit_id>/prescriptions",
    "/api/v1/prescriptions/<uuid:rx_id>/issue",
    "/api/v1/prescriptions/<uuid:rx_id>/revise",
    "/api/v1/rx-favourites/<uuid:favourite_id>",
    "/api/v1/rx-templates/<uuid:template_id>",
    # M6a-P7: a notification is its recipient's; B's doctor is told of the owner's booking.
    "/api/v1/notifications/<uuid:notification_id>/read",
}

# Methods a cross-tenant case must use (default GET), with the body to send: fixed, or built
# from clinic B's data after the URL (a reschedule needs another of B's sessions).
Body = dict[str, object] | Callable[[World], dict[str, object]]
CROSS_TENANT_WRITES: dict[str, tuple[str, Body]] = {
    "/api/v1/clinic/listing/doctors/<uuid:doctor_id>": ("PUT", {"visible": False}),
    "/api/v1/clinic/listing/doctors/<uuid:doctor_id>/profile": ("PUT", {"languages": []}),
    "/api/v1/clinic/fees/services/<uuid:service_id>": ("PATCH", {"default_price_paise": 100}),
    "/api/v1/clinic/bills/<uuid:bill_id>/issue": ("POST", {}),
    "/api/v1/clinic/bills/<uuid:bill_id>/credit-notes": ("POST", {"reason": "Wrong line"}),
    "/api/v1/clinic/fees/services/<uuid:service_id>/doctors/<uuid:doctor_id>": (
        "PUT",
        {"price_paise": 100},
    ),
    "/api/v1/appointments/<uuid:appointment_id>/cancel": ("POST", {"reason": "PATIENT_REQUEST"}),
    "/api/v1/appointments/<uuid:appointment_id>/transitions": (
        "POST",
        {"from": "BOOKED", "to": "ARRIVED"},
    ),
    "/api/v1/appointments/<uuid:appointment_id>/reschedule": (
        "POST",
        lambda w: {"session_id": _session_of_b(w, days=32)},
    ),
    "/api/v1/clinic/staff/<uuid:membership_id>": ("PATCH", {"role": "DOCTOR"}),
    "/api/v1/clinic/staff/<uuid:membership_id>/resend": ("POST", {}),
    "/api/v1/visits/<uuid:visit_id>/complete": ("POST", {}),
    "/api/v1/visits/<uuid:visit_id>/addenda": ("POST", {"body": "seen again"}),
    "/api/v1/visits/<uuid:visit_id>/prescriptions": ("POST", {}),
    "/api/v1/prescriptions/<uuid:rx_id>/issue": ("POST", {"revision": 2}),
    "/api/v1/prescriptions/<uuid:rx_id>/revise": ("POST", {}),
    "/api/v1/prescriptions/<uuid:rx_id>/link/reset": ("POST", {}),
    "/api/v1/prescriptions/<uuid:rx_id>/link/replace": ("POST", {}),
    "/api/v1/rx-favourites/<uuid:favourite_id>": (
        "PUT",
        {"revision": 1, "name": "Tab Y usual", "item": {"medicine_name": "Tab Y"}},
    ),
    "/api/v1/patients/<uuid:patient_id>/consent": ("PUT", {"whatsapp": True, "sms": False}),
    "/api/v1/patients/<uuid:patient_id>/opt-out": ("POST", {}),
    "/api/v1/patients/<uuid:patient_id>/opt-in": ("POST", {"whatsapp": True, "sms": False}),
    "/api/v1/clinic/doctors/<uuid:doctor_id>/schedule-exceptions": (
        "POST",
        {"kind": "LEAVE", "on_date": _FAR_DATE},
    ),
    "/api/v1/clinic/doctors/<uuid:doctor_id>/schedule-exceptions/<uuid:exception_id>": (
        "DELETE",
        {},
    ),
    "/api/v1/reminders/<uuid:reminder_id>": ("PATCH", {"cancel": True}),
    "/api/v1/notifications/<uuid:notification_id>/read": ("POST", {}),
    "/api/v1/patients/<uuid:patient_id>/portal-invite": ("POST", {}),
    "/api/v1/booking-requests/<uuid:request_id>/accept": (
        "POST",
        {"new_patient": {"sex": "FEMALE", "age_years": 30}},
    ),
    "/api/v1/booking-requests/<uuid:request_id>/decline": ("POST", {"reason": "PLEASE_CALL"}),
    "/api/v1/booking-requests/<uuid:request_id>/propose": ("POST", lambda w: _PROPOSALS[id(w)]),
    "/api/v1/patients/<uuid:patient_id>/portal-link": ("DELETE", {}),
}

# Patients have their own read and write cross-clinic cases in integration/test_patients_http.py;
# this suite reads one by ID so the "every route with an ID" guard below stays complete.


def _exception_url(world: World) -> str:
    """Clinic B's leave for its doctor, which clinic A must not be able to remove."""
    owner_of_b = world.client_for(world.b.owner)
    csrf = owner_of_b.get_cookie("me_csrf", path="/")
    assert csrf is not None
    base = f"/api/v1/clinic/doctors/{world.b.doctor.id}/schedule-exceptions"
    created = owner_of_b.post(
        base,
        json={"kind": "LEAVE", "on_date": (date.today() + timedelta(days=31)).isoformat()},
        headers={"X-CSRF-Token": csrf.value},
    )
    assert created.status_code == 201, created.get_json()
    return f"{base}/{created.get_json()['exception']['id']}"


def _reminder_url(world: World) -> str:
    """A scheduled reminder of clinic B's patient (consent recorded first)."""
    url = _patient_url(world)
    owner_of_b, headers = _owner_of_b(world)
    consent = owner_of_b.put(
        f"{url}/consent", json={"whatsapp": True, "sms": False}, headers=headers
    )
    assert consent.status_code == 200, consent.get_json()
    created = owner_of_b.post(
        f"{url}/reminders",
        json={
            "doctor_id": str(world.b.doctor.id),
            "follow_up_date": (date.today() + timedelta(days=10)).isoformat(),
        },
        headers=headers,
    )
    assert created.status_code == 201, created.get_json()
    return f"/api/v1/reminders/{created.get_json()['id']}"


def _notification_url(world: World) -> str:
    """The notification B's doctor gets when B's owner books with them (M6a-P7)."""
    _appointment_url(world)
    items = world.client_for(world.b.doctor_user).get("/api/v1/notifications").get_json()["items"]
    assert items, "the doctor should have been told of the booking"
    return f"/api/v1/notifications/{items[0]['id']}/read"


def _owner_of_b(world: World) -> tuple[FlaskClient, dict[str, str]]:
    client = world.client_for(world.b.owner)
    csrf = client.get_cookie("me_csrf", path="/")
    assert csrf is not None
    return client, {"X-CSRF-Token": csrf.value}


def _service_of_b(world: World) -> str:
    """M6d-P1: one of clinic B's services, added by B's owner if it has none."""
    client, headers = _owner_of_b(world)
    services = client.get("/api/v1/clinic/fees").get_json()["services"]
    if not services:
        resp = client.post(
            "/api/v1/clinic/fees/services",
            json={"name": "Consultation", "kind": "CONSULTATION", "default_price_paise": 50000},
            headers=headers,
        )
        assert resp.status_code == 201, resp.get_json()
        services = resp.get_json()["services"]
    return str(services[0]["id"])


def _bill_of_b(world: World, *, issued: bool = False) -> str:
    """M6d-P2: a draft (or issued) bill of clinic B's patient, by B's owner."""
    client, headers = _owner_of_b(world)
    patient_id = _patient_url(world).rsplit("/", 1)[1]
    drafted = client.post(
        "/api/v1/clinic/bills",
        json={
            "patient_id": patient_id,
            "lines": [{"description": "Dressing", "unit_price_paise": 20000}],
        },
        headers=headers,
    )
    assert drafted.status_code == 201, drafted.get_json()
    url = f"/api/v1/clinic/bills/{drafted.get_json()['id']}"
    if issued:
        assert client.post(f"{url}/issue", headers=headers).status_code == 200
    return url


def _session_of_b(world: World, *, days: int) -> str:
    """A token session of clinic B's doctor ``days`` ahead (every weekday has a block)."""
    client, headers = _owner_of_b(world)
    schedule = client.get(f"/api/v1/clinic/doctors/{world.b.doctor.id}/schedule").get_json()
    if not schedule["blocks"]:
        blocks = [
            {"weekday": d, "start_time": "10:00", "end_time": "13:00", "capacity": 12}
            for d in range(7)
        ]
        resp = client.put(
            f"/api/v1/clinic/doctors/{world.b.doctor.id}/schedule",
            json={"blocks": blocks},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_json()
    on_date = (date.today() + timedelta(days=days)).isoformat()
    sessions = client.get(f"/api/v1/sessions?date={on_date}&doctor_id={world.b.doctor.id}")
    return str(sessions.get_json()["items"][0]["id"])


def _appointment_url(world: World, *, today: bool = False) -> str:
    """Clinic B's booked appointment for its own patient, which clinic A must not reach."""
    client, headers = _owner_of_b(world)
    patient_id = _patient_url(world).rsplit("/", 1)[1]
    # Today's queue needs a session running now (tests/sessions_now.py).
    session_id = (
        running_session(client, world.b.doctor.id)["id"] if today else _session_of_b(world, days=30)
    )
    booked = client.post(
        "/api/v1/appointments",
        json={"session_id": session_id, "patient_id": patient_id},
        headers=headers,
    )
    assert booked.status_code == 201, booked.get_json()
    return f"/api/v1/appointments/{booked.get_json()['id']}"


def _visit_url(world: World, *, completed: bool = False) -> str:
    """Clinic B's visit, started by B's doctor in a session running now."""
    client, headers = _owner_of_b(world)
    appointment = _appointment_url(world, today=True)
    for seen, to in (("BOOKED", "ARRIVED"), ("ARRIVED", "IN_CONSULTATION")):
        moved = client.post(
            f"{appointment}/transitions", json={"from": seen, "to": to}, headers=headers
        )
        assert moved.status_code == 200, moved.get_json()
    doctor = world.client_for(world.b.doctor_user)
    csrf = doctor.get_cookie("me_csrf", path="/")
    assert csrf is not None
    doctor_headers = {"X-CSRF-Token": csrf.value}
    started = doctor.post(
        "/api/v1/visits",
        json={"appointment_id": appointment.rsplit("/", 1)[1]},
        headers=doctor_headers,
    )
    assert started.status_code == 201, started.get_json()
    url = f"/api/v1/visits/{started.get_json()['id']}"
    if completed:
        assert doctor.post(f"{url}/complete", headers=doctor_headers).status_code == 200
    return url


def _prescription_url(world: World, *, issued: bool = False) -> str:
    """Clinic B's draft (one medicine, revision 2), or issued, by B's doctor."""
    visit = _visit_url(world)
    doctor = world.client_for(world.b.doctor_user)
    csrf = doctor.get_cookie("me_csrf", path="/")
    assert csrf is not None
    headers = {"X-CSRF-Token": csrf.value}
    created = doctor.post(f"{visit}/prescriptions", headers=headers)
    assert created.status_code == 201, created.get_json()
    url = f"/api/v1/prescriptions/{created.get_json()['id']}"
    body = {"revision": 1, "items": [{"medicine_name": "Tab Y"}]}
    assert doctor.put(url, json=body, headers=headers).status_code == 200
    if issued:
        resp = doctor.post(f"{url}/issue", json={"revision": 2}, headers=headers)
        assert resp.status_code == 200, resp.get_json()
    return url


def _locked_link_url(world: World) -> str:
    """Clinic B's prescription link after five wrong answers, so a reset is valid for B."""
    rx = _prescription_url(world, issued=True)
    client, _ = _owner_of_b(world)
    url = f"{rx}/link"
    token = client.get(url).get_json()["url"].rsplit("/p/", 1)[1]
    for _ in range(5):
        world.anonymous().post(f"/api/v1/public/links/{token}/verify", json={"phone_last4": "0000"})
    assert client.get(url).get_json()["locked"] is True
    return url


def _library_url(world: World, kind: str) -> str:
    """Clinic B's doctor's favourite or template."""
    doctor = world.client_for(world.b.doctor_user)
    csrf = doctor.get_cookie("me_csrf", path="/")
    assert csrf is not None
    body: dict[str, object] = {"name": "Tab Y usual"}
    body.update(
        {"item": {"medicine_name": "Tab Y"}}
        if kind == "rx-favourites"
        else {"items": [{"medicine_name": "Tab Y"}]}
    )
    created = doctor.post(f"/api/v1/{kind}", json=body, headers={"X-CSRF-Token": csrf.value})
    assert created.status_code == 201, created.get_json()
    return f"/api/v1/{kind}/{created.get_json()['id']}"


def _staff_url(world: World) -> str:
    """Clinic B's front-desk membership, which clinic A must not be able to reach."""
    owner_of_b = world.client_for(world.b.owner)
    staff = owner_of_b.get("/api/v1/clinic/staff").get_json()["items"]
    membership_id = next(m["membership_id"] for m in staff if m["full_name"] == "Beta Front_Desk")
    return f"/api/v1/clinic/staff/{membership_id}"


def _invited_staff_url(world: World) -> str:
    """The resend URL of somebody clinic B has invited by phone (M6a-P5: resend needs INVITED)."""
    owner_of_b = world.client_for(world.b.owner)
    csrf = owner_of_b.get_cookie("me_csrf", path="/")
    assert csrf is not None
    invited = owner_of_b.post(
        "/api/v1/clinic/staff",
        json={"full_name": "Beta Invitee", "role": "FRONT_DESK", "phone": "9000066001"},
        headers={"X-CSRF-Token": csrf.value},
    )
    assert invited.status_code == 201, invited.get_json()
    return f"/api/v1/clinic/staff/{invited.get_json()['membership_id']}/resend"


def _patient_url(world: World) -> str:
    """A patient of clinic B, registered by B's owner, which clinic A must not be able to reach."""
    owner_of_b = world.client_for(world.b.owner)
    csrf = owner_of_b.get_cookie("me_csrf", path="/")
    assert csrf is not None
    created = owner_of_b.post(
        "/api/v1/patients",
        json={
            "full_name": "Beta Patient",
            "phone": "9000000042",
            "sex": "UNDISCLOSED",
            "date_of_birth": "1990-05-17",
        },
        headers={"X-CSRF-Token": csrf.value},
    )
    assert created.status_code == 201, created.get_json()
    return f"/api/v1/patients/{created.get_json()['id']}"


def _linked_patient_url(world: World) -> str:
    """Clinic B's patient linked to a portal account by an invite (M6b-P1)."""
    url = _patient_url(world)
    owner_of_b, headers = _owner_of_b(world)
    invite = owner_of_b.post(f"{url}/portal-invite", headers=headers)
    assert invite.status_code == 201, invite.get_json()
    token = invite.get_json()["url"].rsplit("/portal/link/", 1)[1]
    patient = portal_client(world, email="beta.patient@example.test")
    accepted = patient.post(f"/api/v1/portal/invites/{token}/accept", headers=portal_csrf(patient))
    assert accepted.status_code == 201, accepted.get_json()
    return url


def _opted_out_patient_url(world: World) -> str:
    """Clinic B's patient after an opt-out, so opting in is a valid request for clinic B."""
    url = _patient_url(world)
    owner_of_b = world.client_for(world.b.owner)
    csrf = owner_of_b.get_cookie("me_csrf", path="/")
    assert csrf is not None
    assert (
        owner_of_b.post(f"{url}/opt-out", headers={"X-CSRF-Token": csrf.value}).status_code == 200
    )
    return url


# A proposal's body names one of clinic B's sessions, found when its URL is built (per world).
_PROPOSALS: dict[int, dict[str, object]] = {}


def _request_url(world: World) -> str:
    """An open booking request of clinic B from a fresh verified account (M6b-P5)."""
    _, request_id = request_in(world, world.b, f"beta.req.{uuid4().hex[:10]}@example.test")
    return f"/api/v1/booking-requests/{request_id}"


def _proposable_url(world: World) -> str:
    """Clinic B's request and, kept on the world for the body, a later session of B to offer."""
    url = _request_url(world)
    first = offers(world, world.b)[0]
    target = staff_session_after(world, world.b, first["starts_at"])
    body: dict[str, object] = {
        "session_id": target["id"],
        "new_patient": {"sex": "FEMALE", "age_years": 30},
    }
    if target["slots"]:
        body["slot_start"] = target["slots"][0]["starts_at"]
    _PROPOSALS[id(world)] = body
    return f"{url}/propose"


def _clinic_rules_with_an_id(world: World) -> set[str]:
    return {
        rule.rule
        for rule in world.app.url_map.iter_rules()
        if "<" in rule.rule
        and (policy := policy_of(world.app.view_functions[rule.endpoint])) is not None
        and policy.access is Access.CLINIC
    }


def test_nfr_08_every_clinic_route_with_an_id_has_a_cross_tenant_case(world: World) -> None:
    assert _clinic_rules_with_an_id(world) == set(CROSS_TENANT_CASES)


@pytest.mark.parametrize("rule", sorted(CROSS_TENANT_CASES))
def test_ac3_nfr_08_another_clinics_resource_is_404(world: World, rule: str) -> None:
    url = CROSS_TENANT_CASES[rule](world)
    doctor = rule in AS_DOCTOR
    owner_of_a = world.client_for(world.a.doctor_user if doctor else world.a.owner)
    method, wanted = CROSS_TENANT_WRITES.get(rule, ("GET", {}))
    body = wanted(world) if callable(wanted) else wanted

    resp = _call(owner_of_a, method, url, body)
    assert resp.status_code == 404, resp.get_json()
    assert resp.get_json()["error"]["code"] == "REQ_NOT_FOUND"
    # The same URL works for its own clinic, so the 404 is the scope, not the route.
    own = world.client_for(world.b.doctor_user if doctor else world.b.owner)
    assert _call(own, method, url, body).status_code in (200, 201)


def _call(client: FlaskClient, method: str, url: str, body: dict[str, object]) -> TestResponse:
    if method == "GET":
        return client.get(url)
    csrf = client.get_cookie("me_csrf", path="/")
    assert csrf is not None
    return client.open(url, method=method, json=body, headers={"X-CSRF-Token": csrf.value})


def test_ac3_nfr_08_no_other_clinics_rows_appear_in_any_list(world: World) -> None:
    owner_of_a = world.client_for(world.a.owner)

    doctors = owner_of_a.get("/api/v1/clinic/doctors").get_json()["items"]
    assert [d["id"] for d in doctors] == [str(world.a.doctor.id)]
    assert str(world.b.doctor.id) not in owner_of_a.get("/api/v1/clinic/doctors").text

    staff = owner_of_a.get("/api/v1/clinic/staff").get_json()["items"]
    assert str(world.b.owner.id) not in {m["user_id"] for m in staff}
    assert all(name.startswith(("Alpha", "Multi")) for name in (m["full_name"] for m in staff))


def test_ac3_nfr_08_the_clinic_endpoint_never_returns_another_clinic(world: World) -> None:
    body = world.client_for(world.a.owner).get("/api/v1/clinic").get_json()
    assert body["id"] == str(world.a.clinic.id)
    assert body["name"] == "Alpha Sample Clinic"


def test_r8_a_cross_clinic_read_is_logged_as_tenancy_not_found(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    client = world.client_for(world.a.owner)
    capsys.readouterr()
    client.get(f"/api/v1/clinic/doctors/{world.b.doctor.id}")
    out = capsys.readouterr().out
    assert "tenancy.not_found" in out
    assert str(world.a.clinic.id) in out  # the scope that refused, for monitoring


def test_nfr_08_fr_aud_03_an_owner_reads_only_their_own_clinics_audit_log(world: World) -> None:
    """M6a-P8: clinic B's owner changes B's clinic; it is in B's log and never in A's."""
    owner_of_b, headers = _owner_of_b(world)
    changed = owner_of_b.patch("/api/v1/clinic", json={"city": "Beta City"}, headers=headers)
    assert changed.status_code == 200, changed.get_json()

    def updates(client: FlaskClient) -> set[str]:
        items = client.get("/api/v1/audit-events?category=SETTINGS").get_json()["items"]
        return {i["entity_id"] for i in items if i["action"] == "clinic.updated"}

    assert str(world.b.clinic.id) in updates(owner_of_b)
    assert updates(world.client_for(world.a.owner)) == set()
