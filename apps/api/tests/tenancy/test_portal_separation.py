"""Patient and staff sessions never cross (M6a-P3; ADR-0015 decisions 1, 2; NFR-18).

A permanent suite, like tenancy isolation: it enumerates every route, so a new staff or clinic
endpoint is covered the day it is added.

- A portal session is 401 on every staff, clinic and ops route, even when its token is copied
  into the staff cookie (the audience differs).
- A staff session is 401 on every ``@patient`` route, even copied into the portal cookie.
- A patient account never appears among a clinic's staff, even with a staff member's email.
"""

from __future__ import annotations

import re
import uuid

from flask import Flask
from flask.testing import FlaskClient

from mediease_api.delivery.http.access import Access, policy_of
from tests.conftest import DEMO_PASSWORD, World
from tests.integration.test_portal_http import PASSWORD, sign_up

_PARAM = re.compile(r"<(?:(\w+):)?(\w+)>")
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _concrete(rule: str) -> str:
    def fill(match: re.Match[str]) -> str:
        return str(uuid.uuid4()) if match.group(1) == "uuid" else "x"

    return _PARAM.sub(fill, rule)


def _routes(app: Flask, *, patient: bool) -> list[tuple[str, str]]:
    found = []
    for rule in app.url_map.iter_rules():
        policy = policy_of(app.view_functions[rule.endpoint])
        assert policy is not None
        if policy.access is Access.PUBLIC or (policy.access is Access.PATIENT) is not patient:
            continue
        for method in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
            found.append((method, _concrete(rule.rule)))
    return found


def _call(client: FlaskClient, method: str, url: str) -> int:
    headers = {"X-CSRF-Token": "forged-but-matching"} if method in _UNSAFE else {}
    return client.open(
        url, method=method, json={} if method in _UNSAFE else None, headers=headers
    ).status_code


def _portal_client(world: World, email: str = "asha.patient@example.test") -> FlaskClient:
    client = world.anonymous()
    assert sign_up(client, email=email).status_code == 201
    return client


def test_nfr_18_a_portal_session_is_refused_on_every_staff_route(world: World) -> None:
    client = _portal_client(world)
    token = client.get_cookie("me_pt_access", path="/api/v1/portal")
    assert token is not None
    # Copy the portal token into the staff cookie too: the staff verifier must refuse it.
    client.set_cookie("me_access", token.value, path="/api")
    client.set_cookie("me_csrf", "forged-but-matching", path="/")

    routes = _routes(world.app, patient=False)
    assert len(routes) > 50  # the whole staff surface, not an empty loop
    refused = {(m, u): _call(client, m, u) for m, u in routes}
    assert set(refused.values()) == {401}, {k: v for k, v in refused.items() if v != 401}


def test_nfr_18_a_staff_session_is_refused_on_every_patient_route(world: World) -> None:
    staff = world.client_for(world.a.owner)
    token = staff.get_cookie("me_access", path="/api")
    assert token is not None
    staff.set_cookie("me_pt_access", token.value, path="/api/v1/portal")
    staff.set_cookie("me_pt_csrf", "forged-but-matching", path="/")

    routes = _routes(world.app, patient=True)
    assert routes  # GET /api/v1/portal/me at least
    for method, url in routes:
        assert _call(staff, method, url) == 401, (method, url)


def test_adr_0015_a_patient_account_is_never_staff_even_with_a_staff_email(world: World) -> None:
    desk_email = world.a.desk.email
    assert desk_email is not None
    owner = world.client_for(world.a.owner)
    before = owner.get("/api/v1/clinic/staff").get_json()["items"]

    patient = _portal_client(world, email=desk_email.value)
    assert patient.get("/api/v1/me").status_code == 401

    assert owner.get("/api/v1/clinic/staff").get_json()["items"] == before
    # Both sign-ins keep working, each with its own password and its own cookies.
    staff = world.anonymous()
    signed_in = staff.post(
        "/api/v1/auth/sign-in", json={"identifier": desk_email.value, "password": DEMO_PASSWORD}
    )
    assert signed_in.status_code == 200
    portal = world.anonymous().post(
        "/api/v1/portal/auth/sign-in", json={"email": desk_email.value, "password": PASSWORD}
    )
    assert portal.status_code == 200
    assert staff.get_cookie("me_pt_access", path="/api/v1/portal") is None
