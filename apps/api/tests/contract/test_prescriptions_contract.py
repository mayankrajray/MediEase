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


def test_adr_0008_printing_matches_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    """M4-P4: the PDF, the printable list, the paper size, and their refusals."""
    doctor, visit = _started(world)
    desk, owner = world.client_for(world.a.desk), world.client_for(world.a.owner)
    rx = _expect(openapi, _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions"), 201)
    one = f"/api/v1/prescriptions/{rx['id']}"
    _expect(openapi, _send(doctor, "PUT", one, {"revision": 1, "items": [SAMPLE_ITEM]}), 200)
    _expect(openapi, _send(desk, "GET", f"{one}/pdf"), 409)  # RX_NOT_ISSUED
    _expect(openapi, _send(doctor, "POST", f"{one}/issue", {"revision": 2}), 200)

    pdf = _send(desk, "GET", f"{one}/pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF-")
    _check(openapi, pdf)
    listed = _expect(
        openapi, _send(desk, "GET", f"/api/v1/patients/{visit['patient_id']}/prescriptions"), 200
    )
    assert [r["id"] for r in listed["items"]] == [rx["id"]]

    v2 = _expect(openapi, _send(doctor, "POST", f"{one}/revise"), 201)
    _send(doctor, "POST", f"/api/v1/prescriptions/{v2['id']}/issue", {"revision": 1})
    _expect(openapi, _send(desk, "GET", f"{one}/pdf"), 409)  # RX_NOT_LATEST

    clinic = _expect(openapi, _send(owner, "PATCH", "/api/v1/clinic", {"rx_paper_size": "A4"}), 200)
    assert clinic["rx_paper_size"] == "A4"
    # An invalid request is refused by the contract itself; the API agrees.
    assert _send(owner, "PATCH", "/api/v1/clinic", {"rx_paper_size": "B5"}).status_code == 422


def test_adr_0008_the_preview_and_the_queue_row_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    """M4-P6: the draft preview and the queue row's visit and prescription fields."""
    from tests.integration.test_prescriptions_http import _today

    doctor, visit = _started(world)
    rx = _expect(openapi, _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions"), 201)
    one = f"/api/v1/prescriptions/{rx['id']}"
    _expect(openapi, _send(doctor, "PUT", one, {"revision": 1, "items": [SAMPLE_ITEM]}), 200)
    _expect(openapi, _send(doctor, "GET", f"{one}/preview", query={"lang": "hi"}), 200)
    _expect(openapi, _send(doctor, "POST", f"{one}/issue", {"revision": 2}), 200)
    _expect(openapi, _send(doctor, "GET", f"{one}/preview"), 409)
    desk = world.client_for(world.a.desk)
    query = {"date": _today().isoformat(), "doctor_id": str(world.a.doctor.id)}
    queue = _expect(openapi, _send(desk, "GET", "/api/v1/queue", query=query), 200)
    rows = [a for s in queue["sessions"] for a in s["appointments"]]
    row = next(a for a in rows if a["id"] == visit["appointment_id"])
    assert row["prescription"]["id"] == rx["id"]
