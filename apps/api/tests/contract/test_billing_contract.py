"""Fees, bills and credit notes against contracts/openapi.yaml (ADR-0008, M6d-P1, P2)."""

from __future__ import annotations

from typing import Any

from openapi_core import OpenAPI

from tests.conftest import UowFactory, World
from tests.contract.test_scheduling_contract import _check, _send, openapi  # noqa: F401
from tests.integration.test_appointments_http import _patient
from tests.integration.test_visits_http import _past_visit

FEES = "/api/v1/clinic/fees"
BILLS = "/api/v1/clinic/bills"


def _expect(openapi: OpenAPI, resp: Any, status: int) -> Any:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    _check(openapi, resp)
    return resp.get_json() if status != 204 else None


def test_adr_0008_the_fee_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    owner = world.client_for(world.a.owner)
    added = _expect(
        openapi,
        _send(
            owner,
            "POST",
            f"{FEES}/services",
            {"name": "Consultation", "kind": "CONSULTATION", "default_price_paise": 50000},
        ),
        201,
    )
    service = added["services"][0]["id"]
    _expect(
        openapi,
        _send(owner, "POST", f"{FEES}/services", {"name": "consultation", "kind": "OTHER"}),
        409,
    )
    _expect(
        openapi,
        _send(owner, "PATCH", f"{FEES}/services/{service}", {"default_price_paise": None}),
        200,
    )
    _expect(
        openapi,
        _send(
            owner,
            "PUT",
            f"{FEES}/services/{service}/doctors/{world.a.doctor.id}",
            {"price_paise": 60000},
        ),
        200,
    )
    _expect(openapi, _send(owner, "GET", FEES), 200)
    _expect(
        openapi,
        _send(
            world.client_for(world.a.desk),
            "POST",
            f"{FEES}/services",
            {"name": "X", "kind": "OTHER"},
        ),
        403,
    )
    _expect(openapi, _send(owner, "GET", "/api/v1/clinic/listing"), 200)


def test_adr_0008_the_bill_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
    uow_factory: UowFactory,
) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    _send(
        owner,
        "POST",
        f"{FEES}/services",
        {"name": "Consultation", "kind": "CONSULTATION", "default_price_paise": 50000},
    )
    patient = _patient(desk)
    visit = _past_visit(uow_factory, world, patient, days_ago=0)
    bill = _expect(
        openapi, _send(desk, "POST", BILLS, {"patient_id": patient, "visit_id": str(visit)}), 201
    )
    url = f"{BILLS}/{bill['id']}"
    _expect(
        openapi,
        _send(
            desk,
            "PUT",
            url,
            {
                "lines": [
                    {"description": "Consultation", "unit_price_paise": 50000},
                    {
                        "description": "Dressing",
                        "unit_price_paise": 20000,
                        "discount": {"kind": "PERCENT", "value": 1000},
                    },
                ],
                "discount": {"kind": "AMOUNT", "value": 1000},
                "notes": "Paid at the desk",
            },
        ),
        200,
    )
    issued = _expect(openapi, _send(desk, "POST", f"{url}/issue"), 200)
    _expect(openapi, _send(desk, "PUT", url, {"lines": []}), 409)
    _expect(
        openapi,
        _send(
            desk,
            "POST",
            f"{url}/credit-notes",
            {"line_ids": [issued["lines"][1]["id"]], "reason": "Not done"},
        ),
        201,
    )
    paid = _expect(
        openapi,
        _send(
            desk,
            "POST",
            f"{url}/payments",
            {"mode": "UPI", "amount_paise": 1000, "reference": "UPI-1"},
        ),
        201,
    )
    _expect(
        openapi,
        _send(desk, "POST", f"{url}/payments", {"mode": "CASH", "amount_paise": 99_999_999}),
        409,
    )
    _expect(
        openapi,
        _send(
            desk, "POST", f"{url}/payments/{paid['payments'][0]['id']}/void", {"reason": "Wrong"}
        ),
        200,
    )
    _expect(openapi, _send(desk, "GET", "/api/v1/clinic/dues"), 200)
    _expect(openapi, _send(desk, "GET", "/api/v1/queue"), 200)
    _expect(openapi, _send(desk, "GET", url), 200)
    _expect(openapi, _send(desk, "GET", f"{BILLS}?patient_id={patient}"), 200)
    draft = _expect(openapi, _send(desk, "POST", BILLS, {"patient_id": patient, "lines": []}), 201)
    _expect(openapi, _send(desk, "DELETE", f"{BILLS}/{draft['id']}"), 204)
    _expect(openapi, _send(desk, "GET", f"{BILLS}/{draft['id']}"), 404)
