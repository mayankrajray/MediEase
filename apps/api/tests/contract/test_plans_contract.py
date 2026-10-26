"""Plans and the trial against contracts/openapi.yaml (ADR-0008, M6d-P7)."""

from __future__ import annotations

from typing import Any

from openapi_core import OpenAPI

from tests.conftest import World
from tests.contract.test_scheduling_contract import _check, _send, openapi  # noqa: F401

OPS_CLINICS = "/api/v1/ops/clinics"


def _expect(openapi: OpenAPI, resp: Any, status: int) -> Any:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    _check(openapi, resp)
    return resp.get_json()


def test_adr_0008_the_plan_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    ops = world.client_for(world.ops)
    clinic = _expect(
        openapi,
        _send(
            ops,
            "POST",
            OPS_CLINICS,
            {"name": "Contract Plan Clinic", "slug": "contract-plan", "plan": "SOLO"},
        ),
        201,
    )["id"]
    _expect(openapi, _send(ops, "GET", OPS_CLINICS), 200)
    doctor = {
        "display_name": "Dr. Contract",
        "qualification": "MBBS",
        "registration_council": "Sample State Medical Council",
    }
    doctors = f"{OPS_CLINICS}/{clinic}/doctors"
    _expect(openapi, _send(ops, "POST", doctors, {**doctor, "registration_number": "CP-1"}), 201)
    _expect(openapi, _send(ops, "POST", doctors, {**doctor, "registration_number": "CP-2"}), 409)

    plan = f"{OPS_CLINICS}/{clinic}/plan"
    _expect(openapi, _send(ops, "PUT", plan, {"plan": "PLUS"}), 200)
    _expect(openapi, _send(ops, "POST", doctors, {**doctor, "registration_number": "CP-2"}), 201)
    _expect(openapi, _send(ops, "PUT", plan, {"plan": "SOLO"}), 409)

    _expect(
        openapi, _send(world.client_for(world.a.owner), "GET", "/api/v1/clinic/subscription"), 200
    )
    _expect(
        openapi, _send(world.client_for(world.a.desk), "GET", "/api/v1/clinic/subscription"), 403
    )
