"""*Today*: real responses checked against contracts/openapi.yaml (ADR-0008, M6-P1)."""

from __future__ import annotations

from openapi_core import OpenAPI

from tests.conftest import World
from tests.contract.test_scheduling_contract import _check, _send, openapi  # noqa: F401
from tests.integration.test_appointments_http import _patient
from tests.sessions_now import running_session


def test_adr_0008_m6_p1_today_matches_the_contract_for_every_role(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    owner = world.client_for(world.a.owner)
    session = running_session(owner, world.a.doctor.id)
    booked = _send(
        owner,
        "POST",
        "/api/v1/appointments",
        {"session_id": session["id"], "patient_id": _patient(owner)},
    )
    assert booked.status_code == 201
    for user in (world.a.owner, world.a.doctor_user, world.a.desk):
        resp = _send(world.client_for(user), "GET", "/api/v1/dashboard/today")
        assert resp.status_code == 200, resp.get_json()
        _check(openapi, resp)

    first = _send(owner, "GET", "/api/v1/dashboard/today")
    owner.environ_base["HTTP_IF_NONE_MATCH"] = first.headers["ETag"]
    try:
        unchanged = _send(owner, "GET", "/api/v1/dashboard/today")
    finally:
        del owner.environ_base["HTTP_IF_NONE_MATCH"]
    assert unchanged.status_code == 304
    _check(openapi, unchanged)
