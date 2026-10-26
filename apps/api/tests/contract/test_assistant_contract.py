"""The assistant routes against contracts/openapi.yaml (ADR-0008, M7a)."""

from __future__ import annotations

from openapi_core import OpenAPI

from tests.conftest import World
from tests.contract.test_portal_linking_contract import _expect, _psend
from tests.contract.test_scheduling_contract import _send, openapi  # noqa: F401
from tests.integration.test_prescriptions_http import _issued
from tests.portal_helpers import PORTAL, link_by_invite, portal_client

TURNS = f"{PORTAL}/assistant/turns"


def _user(text: str) -> dict[str, str]:
    return {"role": "user", "content": text}


def test_adr_0008_the_assistant_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    _, visit, rx = _issued(world)
    patient = portal_client(world, "contract.assistant@example.test")
    link_by_invite(world.client_for(world.a.owner), patient, visit["patient_id"])
    context = {"prescription_id": rx["id"]}
    asked = {"messages": [_user("When do I take it?")], "context": context}
    _expect(openapi, _psend(patient, "POST", TURNS, asked), 200)
    _expect(
        openapi, _psend(patient, "POST", TURNS, {"messages": [_user("Is my sugar 180 high?")]}), 200
    )
    stranger = portal_client(world, "contract.stranger@example.test")
    _expect(openapi, _psend(stranger, "POST", TURNS, asked), 404)
    wrong = {"messages": [{"role": "assistant", "content": "x"}]}
    _expect(openapi, _psend(patient, "POST", TURNS, wrong), 422)
    _expect(
        openapi, _psend(patient, "POST", f"{PORTAL}/assistant/confirm", {"token": "x" * 40}), 404
    )

    desk = world.client_for(world.a.desk)
    queue = {"messages": [_user("show today's queue")]}
    _expect(openapi, _send(desk, "POST", "/api/v1/assistant/turns", queue), 200)
    _expect(openapi, _send(desk, "POST", "/api/v1/assistant/confirm", {"token": "y" * 40}), 404)
