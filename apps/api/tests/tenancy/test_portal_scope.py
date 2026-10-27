"""Cross-account isolation of the patient portal (M6b-P1 decision 6A; NFR-18; spec R9, AC4).

A permanent suite, like NFR-08's HTTP one. The scene: clinic A's doctor issues a prescription to
**Bina** (clinic A). Account *Bina* is linked to that record. Account *Asha* is linked to another
clinic-A record that shares Bina's phone, and to clinic B's record: every ``@patient`` route that
names an ID of Bina's must be 404 ``REQ_NOT_FOUND`` for Asha and work for Bina.

``test_every_portal_route_with_an_id_has_a_cross_account_case`` fails when a new ``@patient``
route takes an ID or token without a case here, so the guard cannot be forgotten.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from flask.testing import FlaskClient
from sqlalchemy import create_engine
from werkzeug.test import TestResponse

from mediease_api.delivery.http.access import Access, policy_of
from tests.booking_helpers import ask, ensure_schedule, offers, propose
from tests.conftest import World
from tests.integration.test_appointments_http import _book, _schedule, _session
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_prescriptions_http import _issued
from tests.integration.test_visits_http import _send
from tests.portal_helpers import (
    PORTAL,
    accept,
    invite_token,
    link_by_invite,
    portal_client,
    verify_email,
)


@dataclass(frozen=True)
class Scene:
    asha: FlaskClient
    bina: FlaskClient
    rx_id: str
    bina_link_id: str
    used_invite: str
    world: World
    bina_record: str
    bina_appointment: str
    bina_visit: str


def _bina_notice(scene: Scene) -> str:
    """M6b-P6: the desk books Bina's record again; her linked account is told (one notice)."""
    world = scene.world
    _schedule(world)
    desk = world.client_for(world.a.desk)
    booked = _book(desk, _session(desk, world)["id"], scene.bina_record)
    assert booked.status_code == 201, booked.get_json()
    items = scene.bina.get(f"{PORTAL}/notifications").get_json()["items"]
    assert items, "Bina should have been told of the booking"
    return str(items[0]["id"])


def _bina_proposal(scene: Scene) -> str:
    """M6b-P5: Bina asks clinic A for a time and the desk proposes another for her record."""
    world = scene.world
    engine = create_engine(world.app.config["SETTINGS"].DATABASE_URL)
    try:
        verify_email(engine, "bina.scope@example.test")
    finally:
        engine.dispose()
    ensure_schedule(world, world.a)
    first = offers(world, world.a)[0]
    made = ask(scene.bina, world.a, first)
    assert made.status_code == 201, made.get_json()
    request_id = str(made.get_json()["id"])
    resp = propose(world, world.a, request_id, first["starts_at"], patient_id=scene.bina_record)
    assert resp.status_code == 200, resp.get_json()
    return request_id


def _bina_bill(scene: Scene) -> str:
    """M6d-P4: the desk issues a bill for Bina's record."""
    desk = scene.world.client_for(scene.world.a.desk)
    drafted = _send(
        desk,
        "POST",
        "/api/v1/clinic/bills",
        {
            "patient_id": scene.bina_record,
            "lines": [{"description": "Consultation", "unit_price_paise": 50000}],
        },
    )
    assert drafted.status_code == 201, drafted.get_json()
    bill_id = str(drafted.get_json()["id"])
    issued = _send(desk, "POST", f"/api/v1/clinic/bills/{bill_id}/issue")
    assert issued.status_code == 200, issued.get_json()
    return bill_id


def _bina_report(scene: Scene) -> str:
    """M6d-P6: the doctor attaches a report to Bina's visit and shares it with her portal."""
    doctor = scene.world.client_for(scene.world.a.doctor_user)
    csrf = doctor.get_cookie("me_csrf", path="/")
    assert csrf is not None
    url = f"/api/v1/visits/{scene.bina_visit}/attachments"
    added = doctor.post(
        url,
        data={"file": (io.BytesIO(b"%PDF-1.7 synthetic report"), "cbc.pdf")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf.value},
    )
    assert added.status_code == 201, added.get_json()
    report = str(added.get_json()["id"])
    shared = _send(doctor, "PUT", f"{url}/{report}/share", {"shared": True})
    assert shared.status_code == 200, shared.get_json()
    return report


def _bina_upload(scene: Scene) -> str:
    """M7b: Bina verifies her own prescription by its printed code."""
    made = scene.bina.post(
        f"{PORTAL}/prescription-uploads/by-code",
        json={"code": scene.rx_id},
        headers=portal_csrf(scene.bina),
    )
    assert made.status_code == 201 and made.get_json()["state"] == "VERIFIED", made.get_json()
    return str(made.get_json()["id"])


def _bina_pending_upload(scene: Scene) -> str:
    """M7b: an upload of Bina's waiting for the last-4 check (both accounts verified)."""
    engine = create_engine(scene.world.app.config["SETTINGS"].DATABASE_URL)
    try:
        for email in ("asha.scope@example.test", "bina.scope@example.test"):
            verify_email(engine, email)
    finally:
        engine.dispose()
    made = scene.bina.post(
        f"{PORTAL}/prescription-uploads/by-code",
        json={"code": "00000000-0000-7000-8000-000000000042"},
        headers=portal_csrf(scene.bina),
    )
    assert made.get_json()["state"] == "NEEDS_CHALLENGE", made.get_json()
    return str(made.get_json()["id"])


def _scene(world: World) -> Scene:
    _, visit, rx = _issued(world)
    owner_a = world.client_for(world.a.owner)
    bina_record = visit["patient_id"]
    phone = owner_a.get(f"/api/v1/patients/{bina_record}").get_json()["phone_e164"]
    asha_record = _send(
        owner_a,
        "POST",
        "/api/v1/patients",
        {
            "full_name": "Asha Rao",
            "phone": phone,
            "sex": "UNDISCLOSED",
            "date_of_birth": "1992-01-02",
            "confirm_new": True,
        },
    )
    assert asha_record.status_code == 201, asha_record.get_json()
    owner_b = world.client_for(world.b.owner)
    beta_record = _send(
        owner_b,
        "POST",
        "/api/v1/patients",
        {"full_name": "Asha Rao", "phone": phone, "sex": "UNDISCLOSED", "age_years": 34},
    )
    assert beta_record.status_code == 201, beta_record.get_json()

    asha = portal_client(world, "asha.scope@example.test", name="Asha Rao")
    link_by_invite(owner_a, asha, asha_record.get_json()["id"])
    link_by_invite(owner_b, asha, beta_record.get_json()["id"])
    bina = portal_client(world, "bina.scope@example.test", name="Bina Shah")
    used = invite_token(owner_a, bina_record)
    linked = accept(bina, used)
    assert linked.status_code == 201, linked.get_json()
    return Scene(
        asha,
        bina,
        rx["id"],
        linked.get_json()["id"],
        used,
        world,
        bina_record,
        str(visit["appointment_id"]),
        str(visit["id"]),
    )


Case = tuple[str, Callable[[Scene], str], str]

# Rule -> (method, a URL naming Bina's resource, the error Asha gets).
PORTAL_ID_CASES: dict[str, Case] = {
    "/api/v1/portal/prescriptions/<uuid:rx_id>": (
        "GET",
        lambda s: f"{PORTAL}/prescriptions/{s.rx_id}",
        "REQ_NOT_FOUND",
    ),
    "/api/v1/portal/prescriptions/<uuid:rx_id>/pdf": (
        "GET",
        lambda s: f"{PORTAL}/prescriptions/{s.rx_id}/pdf",
        "REQ_NOT_FOUND",
    ),
    # M6d-P4 (billing R52): an issued bill of Bina's record.
    "/api/v1/portal/bills/<uuid:bill_id>/receipt.pdf": (
        "GET",
        lambda s: f"{PORTAL}/bills/{_bina_bill(s)}/receipt.pdf",
        "REQ_NOT_FOUND",
    ),
    # M6d-P6 (visit-attachments R12): a report shared with Bina.
    "/api/v1/portal/attachments/<uuid:attachment_id>/file": (
        "GET",
        lambda s: f"{PORTAL}/attachments/{_bina_report(s)}/file",
        "REQ_NOT_FOUND",
    ),
    "/api/v1/portal/links/<uuid:link_id>": (
        "DELETE",
        lambda s: f"{PORTAL}/links/{s.bina_link_id}",
        "REQ_NOT_FOUND",
    ),
    # Tokens: an invite already used by Bina says nothing to Asha (R2).
    "/api/v1/portal/invites/<token>": (
        "GET",
        lambda s: f"{PORTAL}/invites/{s.used_invite}",
        "PRT_INVITE_INVALID",
    ),
    "/api/v1/portal/invites/<token>/accept": (
        "POST",
        lambda s: f"{PORTAL}/invites/{s.used_invite}/accept",
        "PRT_INVITE_INVALID",
    ),
    # M6b-P6: Bina's notice and her appointment's live link; Asha reaches neither.
    "/api/v1/portal/notifications/<uuid:notification_id>/read": (
        "POST",
        lambda s: f"{PORTAL}/notifications/{_bina_notice(s)}/read",
        "REQ_NOT_FOUND",
    ),
    "/api/v1/portal/appointments/<uuid:appointment_id>/live-link": (
        "GET",
        lambda s: f"{PORTAL}/appointments/{s.bina_appointment}/live-link",
        "REQ_NOT_FOUND",
    ),
    # M6b-P5: Bina's proposal; Asha cannot take or refuse it.
    "/api/v1/portal/booking-requests/<uuid:request_id>/accept-proposal": (
        "POST",
        lambda s: f"{PORTAL}/booking-requests/{_bina_proposal(s)}/accept-proposal",
        "REQ_NOT_FOUND",
    ),
    "/api/v1/portal/booking-requests/<uuid:request_id>/decline-proposal": (
        "POST",
        lambda s: f"{PORTAL}/booking-requests/{_bina_proposal(s)}/decline-proposal",
        "REQ_NOT_FOUND",
    ),
    # M7b: Bina's uploads; Asha can neither read, choose for, answer for nor withdraw them.
    "/api/v1/portal/prescription-uploads/<uuid:upload_id>": (
        "GET",
        lambda s: f"{PORTAL}/prescription-uploads/{_bina_upload(s)}",
        "REQ_NOT_FOUND",
    ),
    "/api/v1/portal/prescription-uploads/<uuid:upload_id>/selection": (
        "POST",
        lambda s: f"{PORTAL}/prescription-uploads/{_bina_upload(s)}/selection",
        "REQ_NOT_FOUND",
    ),
    "/api/v1/portal/prescription-uploads/<uuid:upload_id>/challenge": (
        "POST",
        lambda s: f"{PORTAL}/prescription-uploads/{_bina_pending_upload(s)}/challenge",
        "REQ_NOT_FOUND",
    ),
}

# POST bodies the routes validate before they look anything up.
_BODIES = {
    "/api/v1/portal/prescription-uploads/<uuid:upload_id>/selection": {"choice": "UPLOADED"},
    "/api/v1/portal/prescription-uploads/<uuid:upload_id>/challenge": {"phone_last4": "0000"},
}
# Bina's own answer to a check on an unknown code is a failed check, not a 404.
_OWN_STATUS = {"/api/v1/portal/prescription-uploads/<uuid:upload_id>/challenge": 401}

# Token routes have no owner to succeed for once used; Bina's own call is checked for ID routes.
_TOKEN_RULES = {"/api/v1/portal/invites/<token>", "/api/v1/portal/invites/<token>/accept"}


def _call(
    client: FlaskClient, method: str, url: str, body: dict[str, str] | None = None
) -> TestResponse:
    headers = portal_csrf(client) if method != "GET" else {}
    return client.open(url, method=method, headers=headers, json=body)


def test_every_portal_route_with_an_id_has_a_cross_account_case(world: World) -> None:
    rules = {
        rule.rule
        for rule in world.app.url_map.iter_rules()
        if "<" in rule.rule
        and (policy := policy_of(world.app.view_functions[rule.endpoint])) is not None
        and policy.access is Access.PATIENT
    }
    assert rules == set(PORTAL_ID_CASES)


@pytest.mark.parametrize("rule", sorted(PORTAL_ID_CASES))
def test_ac4_nfr_18_another_accounts_resource_is_not_found(world: World, rule: str) -> None:
    scene = _scene(world)
    method, url_of, code = PORTAL_ID_CASES[rule]
    url = url_of(scene)

    body = _BODIES.get(rule)
    resp = _call(scene.asha, method, url, body)
    assert resp.status_code == 404, resp.get_json()
    assert resp.get_json()["error"]["code"] == code
    if rule not in _TOKEN_RULES:
        # The same URL works for the account it belongs to: the 404 is the scope, not the route.
        own = _call(scene.bina, method, url, body).status_code
        assert own in ((_OWN_STATUS[rule],) if rule in _OWN_STATUS else (200, 204))


def test_ac4_ac5_lists_hold_only_the_accounts_own_records(world: World) -> None:
    scene = _scene(world)
    links = scene.asha.get(f"{PORTAL}/links").get_json()["items"]
    assert sorted(i["clinic"]["name"] for i in links) == [
        "Alpha Sample Clinic",
        "Beta Sample Clinic",
    ]
    assert {i["patient_first_name"] for i in links} == {"Asha"}
    assert scene.asha.get(f"{PORTAL}/prescriptions").get_json()["items"] == []
    for group in scene.asha.get(f"{PORTAL}/appointments").get_json()["items"]:
        assert group["appointments"] == []
    assert scene.asha.get(f"{PORTAL}/reminders").get_json()["items"] == []

    bina = scene.bina.get(f"{PORTAL}/prescriptions").get_json()["items"]
    assert [p["id"] for p in bina] == [scene.rx_id]
    assert len(scene.bina.get(f"{PORTAL}/appointments").get_json()["items"][0]["appointments"]) == 1


def test_m6b_p3_the_plan_and_reminder_choices_hold_only_the_accounts_own_records(
    world: World,
) -> None:
    """R35, R38: Bina's medicine is never in Asha's plan, and Asha cannot set its reminder."""
    scene = _scene(world)
    plan = scene.asha.get(f"{PORTAL}/medicine-plan").get_json()
    assert (plan["has_prescriptions"], plan["slots"], plan["as_written"]) == (False, [], [])
    assert scene.asha.get(f"{PORTAL}/medicine-plan/courses").get_json()["items"] == []

    [course] = scene.bina.get(f"{PORTAL}/medicine-plan/courses").get_json()["items"]
    assert course["prescription_id"] == scene.rx_id
    line = course["lines"][0]
    choice = {
        "prescription_id": scene.rx_id,
        "item_id": line["item_id"],
        "slot": line["slots"][0]["slot"],
        "enabled": True,
    }
    url = f"{PORTAL}/medicine-plan/reminders"
    refused = scene.asha.put(url, json=choice, headers=portal_csrf(scene.asha))
    assert (refused.status_code, refused.get_json()["error"]["code"]) == (404, "REQ_NOT_FOUND")
    assert scene.bina.put(url, json=choice, headers=portal_csrf(scene.bina)).status_code == 200
