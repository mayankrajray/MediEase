"""Prescriptions: real responses checked against contracts/openapi.yaml (ADR-0008, M4-P2)."""

from __future__ import annotations

from typing import Any

from openapi_core import OpenAPI

from tests.conftest import World
from tests.contract.test_scheduling_contract import _check, _send, openapi  # noqa: F401
from tests.integration.test_prescriptions_http import SAMPLE_ITEM
from tests.integration.test_visits_http import _started


def _expect(openapi: OpenAPI, resp: Any, status: int) -> Any:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    _check(openapi, resp)
    return resp.get_json() if status != 204 else None


def test_adr_0008_the_prescription_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    doctor, visit = _started(world)
    desk = world.client_for(world.a.desk)
    create = f"/api/v1/visits/{visit['id']}/prescriptions"
    rx = _expect(openapi, _send(doctor, "POST", create), 201)
    _expect(openapi, _send(doctor, "POST", create), 409)
    one = f"/api/v1/prescriptions/{rx['id']}"
    _expect(openapi, _send(doctor, "POST", f"{one}/issue", {"revision": 1}), 422)
    body = {
        "revision": 1,
        "items": [
            SAMPLE_ITEM,
            {
                "medicine_name": "Tab Y",
                "frequency": "CUSTOM",
                "frequency_text": "every 6 hours",
                "storage": [{"code": "DISCARD_AFTER_DAYS", "days": 7}],
            },
        ],
        "advice": {"diet": ["light food"], "return_if": ["fever above 102"], "notes": "rest"},
    }
    _expect(openapi, _send(doctor, "PUT", one, body), 200)
    _expect(openapi, _send(doctor, "PUT", one, body), 409)
    _expect(openapi, _send(desk, "GET", one), 403)
    issued = _expect(openapi, _send(doctor, "POST", f"{one}/issue", {"revision": 2}), 200)
    assert issued["status"] == "ISSUED"
    _expect(openapi, _send(doctor, "GET", one), 200)
    v2 = _expect(openapi, _send(doctor, "POST", f"{one}/revise"), 201)
    _expect(openapi, _send(doctor, "POST", f"{one}/revise"), 409)
    _expect(openapi, _send(doctor, "DELETE", f"/api/v1/prescriptions/{v2['id']}"), 204)
    view = _expect(openapi, _send(doctor, "GET", f"/api/v1/visits/{visit['id']}"), 200)
    assert [p["version"] for p in view["prescriptions"]] == [1]
