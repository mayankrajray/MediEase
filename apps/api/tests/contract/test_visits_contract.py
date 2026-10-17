"""Visits: real responses checked against contracts/openapi.yaml (ADR-0008, M4-P1)."""

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


def test_adr_0008_the_visit_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    session = running_session(owner, world.a.doctor.id)
    patient = _expect(
        openapi,
        _send(
            desk,
            "POST",
            "/api/v1/patients",
            {
                "full_name": "Asha Rao",
                "phone": "9000000501",
                "sex": "FEMALE",
                "date_of_birth": "1990-05-17",
            },
        ),
        201,
    )["id"]
    appointment = _expect(
        openapi,
        _send(
            desk,
            "POST",
            "/api/v1/appointments",
            {"session_id": session["id"], "patient_id": patient},
        ),
        201,
    )["id"]
    early = _send(doctor, "POST", "/api/v1/visits", {"appointment_id": appointment})
    _expect(openapi, early, 409)
    moves = f"/api/v1/appointments/{appointment}/transitions"
    for seen, to in (("BOOKED", "ARRIVED"), ("ARRIVED", "IN_CONSULTATION")):
        _expect(openapi, _send(desk, "POST", moves, {"from": seen, "to": to}), 200)

    visit = _expect(
        openapi, _send(doctor, "POST", "/api/v1/visits", {"appointment_id": appointment}), 201
    )
    one = f"/api/v1/visits/{visit['id']}"
    _expect(
        openapi,
        _send(
            doctor,
            "PATCH",
            one,
            {"revision": 1, "chief_complaint": "fever", "vitals": {"temp_c": 38.2, "pulse": 90}},
        ),
        200,
    )
    _expect(openapi, _send(doctor, "PATCH", one, {"revision": 1, "notes": "stale"}), 409)
    _expect(openapi, _send(doctor, "PATCH", one, {"revision": 2, "vitals": {"pulse": 72.5}}), 422)
    _expect(openapi, _send(desk, "GET", one), 403)
    _expect(openapi, _send(doctor, "POST", f"{one}/complete"), 200)
    _expect(openapi, _send(doctor, "POST", f"{one}/addenda", {"body": "reviewed"}), 201)
    consultation = _expect(openapi, _send(doctor, "GET", one), 200)
    assert consultation["visit"]["addenda"][0]["body"] == "reviewed"
    page = _expect(openapi, _send(owner, "GET", f"/api/v1/patients/{patient}/visits"), 200)
    assert [v["id"] for v in page["items"]] == [visit["id"]]
