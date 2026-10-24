"""Cross-account isolation of the patient portal (M6b-P1 decision 6A; NFR-18; spec R9, AC4).

A permanent suite, like NFR-08's HTTP one. The scene: clinic A's doctor issues a prescription to
**Bina** (clinic A). Account *Bina* is linked to that record. Account *Asha* is linked to another
clinic-A record that shares Bina's phone, and to clinic B's record: every ``@patient`` route that
names an ID of Bina's must be 404 ``REQ_NOT_FOUND`` for Asha and work for Bina.

``test_every_portal_route_with_an_id_has_a_cross_account_case`` fails when a new ``@patient``
route takes an ID or token without a case here, so the guard cannot be forgotten.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mediease_api.delivery.http.access import Access, policy_of
from tests.conftest import World
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_prescriptions_http import _issued
from tests.integration.test_visits_http import _send
from tests.portal_helpers import PORTAL, accept, invite_token, link_by_invite, portal_client


@dataclass(frozen=True)
class Scene:
    asha: FlaskClient
    bina: FlaskClient
    rx_id: str
    bina_link_id: str
    used_invite: str


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
    return Scene(asha, bina, rx["id"], linked.get_json()["id"], used)


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
}

# Token routes have no owner to succeed for once used; Bina's own call is checked for ID routes.
_TOKEN_RULES = {"/api/v1/portal/invites/<token>", "/api/v1/portal/invites/<token>/accept"}


def _call(client: FlaskClient, method: str, url: str) -> TestResponse:
    headers = portal_csrf(client) if method != "GET" else {}
    return client.open(url, method=method, headers=headers)


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

    resp = _call(scene.asha, method, url)
    assert resp.status_code == 404, resp.get_json()
    assert resp.get_json()["error"]["code"] == code
    if rule not in _TOKEN_RULES:
        # The same URL works for the account it belongs to: the 404 is the scope, not the route.
        assert _call(scene.bina, method, url).status_code == 200


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
