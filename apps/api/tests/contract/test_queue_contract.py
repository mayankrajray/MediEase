"""The daily queue: real responses checked against contracts/openapi.yaml (ADR-0008, M3-P3)."""

from __future__ import annotations

from typing import Any

from openapi_core import OpenAPI

from tests.conftest import World
from tests.contract.test_scheduling_contract import _check, _send, openapi  # noqa: F401
from tests.sessions_now import running_session


def _expect(openapi: OpenAPI, resp: Any, status: int) -> Any:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    _check(openapi, resp)
    return resp.get_json()


def test_adr_0008_transitions_walk_ins_and_the_queue_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    owner = world.client_for(world.a.owner)
    session = running_session(owner, world.a.doctor.id)
    patients = [
        _expect(
            openapi,
            _send(
                owner,
                "POST",
                "/api/v1/patients",
                {
                    "full_name": name,
                    "phone": phone,
                    "sex": "FEMALE",
                    "date_of_birth": "1990-05-17",
                },
            ),
            201,
        )["id"]
        for name, phone in (("Asha Rao", "9000000401"), ("Bina Shah", "9000000402"))
    ]
    booked = _expect(
        openapi,
        _send(
            owner,
            "POST",
            "/api/v1/appointments",
            {"session_id": session["id"], "patient_id": patients[0]},
        ),
        201,
    )
    url = f"/api/v1/appointments/{booked['id']}/transitions"
    _expect(openapi, _send(owner, "POST", url, {"from": "BOOKED", "to": "ARRIVED"}), 200)
    _expect(openapi, _send(owner, "POST", url, {"from": "BOOKED", "to": "ARRIVED"}), 409)
    _expect(
        openapi,
        _send(
            owner,
            "POST",
            "/api/v1/queue/walk-ins",
            {"doctor_id": str(world.a.doctor.id), "patient_id": patients[1]},
        ),
        201,
    )
    queue = _expect(openapi, _send(owner, "GET", "/api/v1/queue"), 200)
    assert len(queue["sessions"][0]["appointments"]) == 2
    _expect(
        openapi,
        _send(owner, "GET", "/api/v1/queue", query={"include_cancelled": "true"}),
        200,
    )


def test_adr_0008_r12_the_queue_etag_and_304_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    owner = world.client_for(world.a.owner)
    running_session(owner, world.a.doctor.id)
    first = _send(owner, "GET", "/api/v1/queue")
    _expect(openapi, first, 200)
    tag = first.headers["ETag"]
    owner.environ_base["HTTP_IF_NONE_MATCH"] = tag
    try:
        unchanged = _send(owner, "GET", "/api/v1/queue")
    finally:
        del owner.environ_base["HTTP_IF_NONE_MATCH"]
    assert unchanged.status_code == 304 and unchanged.headers["ETag"] == tag
    _check(openapi, unchanged)
