"""Linking and the portal's reads: real responses against contracts/openapi.yaml (M6b-P1)."""

from __future__ import annotations

import json
from typing import Any

from flask.testing import FlaskClient
from openapi_core import OpenAPI
from sqlalchemy import create_engine
from werkzeug.test import TestResponse

from tests.conftest import World
from tests.contract.test_scheduling_contract import (  # noqa: F401
    _BASE_URL,
    _check,
    _send,
    openapi,
)
from tests.integration.test_patient_links_http import _last4, _token, _wrong
from tests.integration.test_prescriptions_http import _issued
from tests.portal_helpers import PORTAL, portal_client, verify_email


def _expect(openapi: OpenAPI, resp: Any, status: int) -> Any:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    _check(openapi, resp)
    return resp.get_json() if resp.mimetype == "application/json" else None


def _psend(
    client: FlaskClient, method: str, path: str, body: dict[str, Any] | None = None
) -> TestResponse:
    """A portal request: the portal CSRF cookie, not the staff one."""
    headers = {}
    csrf = client.get_cookie("me_pt_csrf", domain="localhost", path="/")
    if csrf is not None and method != "GET":
        headers["X-CSRF-Token"] = csrf.value
    resp = client.open(path, method=method, base_url=_BASE_URL, json=body, headers=headers)
    resp.sent_body = b"" if body is None else json.dumps(body).encode()  # type: ignore[attr-defined]
    return resp


def test_adr_0008_linking_and_the_portal_reads_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
    migrated_database_url: str,
) -> None:
    _, visit, rx = _issued(world)
    owner = world.client_for(world.a.owner)
    patient_id = visit["patient_id"]
    staff = f"/api/v1/patients/{patient_id}"

    _expect(openapi, _send(owner, "GET", f"{staff}/portal"), 200)
    invite = _expect(openapi, _send(owner, "POST", f"{staff}/portal-invite"), 201)
    token = invite["url"].rsplit("/portal/link/", 1)[1]
    _expect(openapi, _send(owner, "GET", f"{staff}/portal"), 200)

    patient = portal_client(world, "contract.patient@example.test")
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/invites/{token}"), 200)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/invites/{'x' * 43}"), 404)
    linked = _expect(openapi, _psend(patient, "POST", f"{PORTAL}/invites/{token}/accept"), 201)
    _expect(openapi, _psend(patient, "POST", f"{PORTAL}/invites/{token}/accept"), 404)
    _expect(openapi, _send(owner, "POST", f"{staff}/portal-invite"), 409)

    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/links"), 200)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/appointments"), 200)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/prescriptions"), 200)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/prescriptions/{rx['id']}"), 200)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/prescriptions/{rx['id']}/pdf"), 200)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/reminders"), 200)
    _expect(openapi, _psend(patient, "DELETE", f"{PORTAL}/links/{linked['id']}"), 200)
    _expect(openapi, _psend(patient, "DELETE", f"{PORTAL}/links/{linked['id']}"), 404)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/prescriptions/{rx['id']}"), 404)

    # The prescription route: unverified, wrong digits, linked; then staff unlink.
    desk = world.client_for(world.a.desk)
    rx_token = _token(_send(desk, "GET", f"/api/v1/prescriptions/{rx['id']}/link").get_json())
    right = _last4(world, patient_id)
    by_rx = f"{PORTAL}/links/prescription"
    other = portal_client(world, "contract.rx@example.test")
    body = {"token": rx_token, "phone_last4": right}
    _expect(openapi, _psend(other, "POST", by_rx, body), 403)
    engine = create_engine(migrated_database_url)
    try:
        verify_email(engine, "contract.rx@example.test")
    finally:
        engine.dispose()
    wrong = {"token": rx_token, "phone_last4": _wrong(right)}
    _expect(openapi, _psend(other, "POST", by_rx, wrong), 401)
    _expect(openapi, _psend(other, "POST", by_rx, body), 201)
    _expect(openapi, _send(owner, "DELETE", f"{staff}/portal-link"), 200)
    _expect(openapi, _send(owner, "DELETE", f"{staff}/portal-link"), 404)
