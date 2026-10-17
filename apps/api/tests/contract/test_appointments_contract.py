"""Appointments: real responses checked against contracts/openapi.yaml (ADR-0008, M3-P2)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from openapi_core import OpenAPI

from tests.conftest import World
from tests.contract.test_scheduling_contract import _check, _monday, _send, openapi  # noqa: F401


def _expect(openapi: OpenAPI, resp: Any, status: int) -> Any:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    _check(openapi, resp)
    return resp.get_json()


def test_adr_0008_booking_cancel_reschedule_and_reads_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    owner = world.client_for(world.a.owner)
    doctor = f"/api/v1/clinic/doctors/{world.a.doctor.id}"
    monday = _monday()
    blocks = [
        {
            "weekday": d,
            "start_time": "10:00",
            "end_time": "13:00",
            "slot_minutes": 60,
            "capacity": 4,
        }
        for d in (0, 1)
    ]
    _expect(openapi, _send(owner, "PUT", f"{doctor}/schedule", {"blocks": blocks}), 200)
    patient = _expect(
        openapi,
        _send(
            owner,
            "POST",
            "/api/v1/patients",
            {
                "full_name": "Asha Rao",
                "phone": "9000000301",
                "sex": "FEMALE",
                "date_of_birth": "1990-05-17",
            },
        ),
        201,
    )["id"]

    def session_on(day: Any) -> str:
        listed = _expect(
            openapi,
            _send(
                owner,
                "GET",
                "/api/v1/sessions",
                query={"date": day.isoformat(), "doctor_id": str(world.a.doctor.id)},
            ),
            200,
        )
        return str(listed["items"][0]["id"])

    first, second = session_on(monday), session_on(monday + timedelta(days=1))
    booked = _expect(
        openapi,
        _send(
            owner,
            "POST",
            "/api/v1/appointments",
            {"session_id": first, "patient_id": patient, "source": "PHONE", "reason": "follow-up"},
        ),
        201,
    )
    assert booked["token_number"] == 1
    _expect(
        openapi,
        _send(owner, "POST", "/api/v1/appointments", {"session_id": first, "patient_id": patient}),
        409,
    )
    moved = _expect(
        openapi,
        _send(
            owner, "POST", f"/api/v1/appointments/{booked['id']}/reschedule", {"session_id": second}
        ),
        201,
    )
    _expect(openapi, _send(owner, "GET", f"/api/v1/appointments/{booked['id']}"), 200)
    _expect(
        openapi,
        _send(
            owner,
            "POST",
            f"/api/v1/appointments/{moved['id']}/cancel",
            {"reason": "OTHER", "note": "moved city"},
        ),
        200,
    )
    _expect(
        openapi,
        _send(owner, "POST", f"/api/v1/appointments/{moved['id']}/cancel", {"reason": "DUPLICATE"}),
        409,
    )
    listed = _expect(openapi, _send(owner, "GET", f"/api/v1/patients/{patient}/appointments"), 200)
    assert len(listed["items"]) == 2


def test_adr_0008_slot_mode_sessions_mark_taken_slots(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    owner = world.client_for(world.a.owner)
    _expect(openapi, _send(owner, "PATCH", "/api/v1/clinic", {"booking_mode": "SLOTS"}), 200)
    block = {"weekday": 0, "start_time": "10:00", "end_time": "12:00", "slot_minutes": 60}
    _expect(
        openapi,
        _send(
            owner,
            "PUT",
            f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule",
            {"blocks": [block]},
        ),
        200,
    )
    query = {"date": _monday().isoformat()}
    session = _expect(openapi, _send(owner, "GET", "/api/v1/sessions", query=query), 200)["items"][
        0
    ]
    patient = _expect(
        openapi,
        _send(
            owner,
            "POST",
            "/api/v1/patients",
            {
                "full_name": "Bina Shah",
                "phone": "9000000302",
                "sex": "FEMALE",
                "date_of_birth": "1980-01-01",
            },
        ),
        201,
    )["id"]
    _expect(
        openapi,
        _send(
            owner,
            "POST",
            "/api/v1/appointments",
            {
                "session_id": session["id"],
                "patient_id": patient,
                "slot_start": session["slots"][1]["starts_at"],
            },
        ),
        201,
    )
    after = _expect(openapi, _send(owner, "GET", "/api/v1/sessions", query=query), 200)["items"][0]
    assert [s["available"] for s in after["slots"]] == [True, False]
    _expect(
        openapi,
        _send(
            owner,
            "POST",
            "/api/v1/appointments",
            {"session_id": session["id"], "patient_id": patient},
        ),
        422,
    )
