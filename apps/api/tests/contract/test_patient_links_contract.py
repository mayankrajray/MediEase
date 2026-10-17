"""Patient links: real responses against contracts/openapi.yaml (ADR-0008, M4-P5)."""

from __future__ import annotations

from typing import Any

from openapi_core import OpenAPI

from tests.conftest import World
from tests.contract.test_scheduling_contract import (  # noqa: F401
    _BASE_URL,
    _check,
    _send,
    openapi,
)
from tests.integration.test_patient_links_http import _last4, _token, _wrong
from tests.integration.test_prescriptions_http import _issued


def _expect(openapi: OpenAPI, resp: Any, status: int) -> Any:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    _check(openapi, resp)
    return resp.get_json()


def test_adr_0008_patient_links_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    _, visit, rx = _issued(world)
    desk, patient = world.client_for(world.a.desk), world.anonymous()
    staff = f"/api/v1/prescriptions/{rx['id']}/link"
    link = _expect(openapi, _send(desk, "GET", staff), 200)
    token = _token(link)
    base = f"/api/v1/public/links/{token}"
    _expect(openapi, _send(patient, "GET", base), 200)
    _expect(openapi, _send(patient, "GET", "/api/v1/public/links/not.a.token"), 404)
    right = _last4(world, visit["patient_id"])
    _expect(openapi, _send(patient, "POST", f"{base}/verify", {"phone_last4": _wrong(right)}), 401)
    _expect(openapi, _send(patient, "GET", f"{base}/prescription"), 401)
    view = _expect(openapi, _send(patient, "POST", f"{base}/verify", {"phone_last4": right}), 200)
    page = patient.get(
        f"{base}/prescription",
        query_string={"lang": "hi"},
        headers={"X-Link-View": view["view_token"]},
        base_url=_BASE_URL,
    )
    page.sent_body = b""  # type: ignore[attr-defined]
    _expect(openapi, page, 200)
    for _ in range(5):
        _send(patient, "POST", f"{base}/verify", {"phone_last4": _wrong(right)})
    _expect(openapi, _send(patient, "POST", f"{base}/verify", {"phone_last4": right}), 423)
    _expect(openapi, _send(desk, "POST", f"{staff}/reset"), 200)
    _expect(openapi, _send(desk, "POST", f"{staff}/reset"), 409)
    _expect(openapi, _send(desk, "POST", f"{staff}/replace"), 200)
    _expect(openapi, _send(patient, "GET", base), 410)
