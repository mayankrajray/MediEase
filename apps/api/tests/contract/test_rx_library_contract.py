"""Favourites, templates, suggestions against contracts/openapi.yaml (ADR-0008, M4-P3)."""

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


def test_adr_0008_the_rx_library_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    doctor, visit = _started(world)
    fav = _expect(
        openapi,
        _send(doctor, "POST", "/api/v1/rx-favourites", {"name": "Fever", "item": SAMPLE_ITEM}),
        201,
    )
    _expect(
        openapi,
        _send(doctor, "POST", "/api/v1/rx-favourites", {"name": "fever", "item": SAMPLE_ITEM}),
        409,
    )
    one = f"/api/v1/rx-favourites/{fav['id']}"
    _expect(
        openapi,
        _send(doctor, "PUT", one, {"name": "Fever", "item": SAMPLE_ITEM, "revision": 1}),
        200,
    )
    _expect(openapi, _send(doctor, "GET", "/api/v1/rx-favourites"), 200)
    template = _expect(
        openapi,
        _send(
            doctor,
            "POST",
            "/api/v1/rx-templates",
            {
                "name": "Viral",
                "items": [SAMPLE_ITEM],
                "advice": {"diet": ["fluids"]},
                "follow_up_days": 3,
            },
        ),
        201,
    )
    tpl = f"/api/v1/rx-templates/{template['id']}"
    _expect(openapi, _send(doctor, "GET", tpl), 200)
    _expect(
        openapi,
        _send(doctor, "PUT", tpl, {"name": "Viral", "revision": 9, "items": [SAMPLE_ITEM]}),
        409,
    )
    _expect(openapi, _send(doctor, "GET", "/api/v1/rx-templates"), 200)

    rx = _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions").get_json()
    saved = _expect(
        openapi,
        _send(
            doctor,
            "PUT",
            f"/api/v1/prescriptions/{rx['id']}",
            {
                "revision": 1,
                "items": [{**SAMPLE_ITEM, "favourite_id": fav["id"]}],
                "template_id": template["id"],
            },
        ),
        200,
    )
    assert saved["template_id"] == template["id"]
    _expect(
        openapi,
        _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2}),
        200,
    )
    found = _expect(
        openapi, _send(doctor, "GET", "/api/v1/medicine-suggestions", query={"q": "syr"}), 200
    )
    assert found["items"][0]["source"] == "FAVOURITE"
    _expect(openapi, _send(doctor, "GET", "/api/v1/medicine-suggestions", query={"q": "  "}), 422)
    _expect(openapi, _send(doctor, "DELETE", one), 204)
    _expect(openapi, _send(doctor, "DELETE", tpl), 204)
