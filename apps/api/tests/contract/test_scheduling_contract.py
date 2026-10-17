"""Schedules and sessions: real responses checked against contracts/openapi.yaml (ADR-0008)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from json import dumps
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from openapi_core import OpenAPI
from openapi_core.contrib.werkzeug import WerkzeugOpenAPIRequest, WerkzeugOpenAPIResponse
from werkzeug.test import EnvironBuilder, TestResponse
from werkzeug.wrappers import Request

from tests.conftest import World

_SPEC_PATH = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
_BASE_URL = "http://localhost:8000"


def _monday() -> date:
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return today + timedelta(days=7 + (7 - today.weekday()) % 7)


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    return OpenAPI.from_file_path(str(_SPEC_PATH))


def _check(openapi: OpenAPI, resp: TestResponse) -> None:
    sent = resp.request
    request = WerkzeugOpenAPIRequest(
        Request(
            EnvironBuilder(
                base_url=_BASE_URL,
                path=sent.path,
                query_string=sent.query_string.decode(),
                method=sent.method,
                headers=dict(sent.headers),
                data=getattr(resp, "sent_body", b""),
            ).get_environ()
        )
    )
    openapi.validate_request(request)
    openapi.validate_response(request, WerkzeugOpenAPIResponse(resp))


def _send(
    client: FlaskClient,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
) -> TestResponse:
    headers = {}
    csrf = client.get_cookie("me_csrf", domain="localhost", path="/")
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf.value
    resp = client.open(
        path, method=method, base_url=_BASE_URL, json=body, headers=headers, query_string=query
    )
    resp.sent_body = b"" if body is None else dumps(body).encode()  # type: ignore[attr-defined]
    return resp


def test_adr_0008_schedule_exceptions_and_sessions_match_the_contract(
    openapi: OpenAPI, world: World
) -> None:
    owner = world.client_for(world.a.owner)
    doctor = f"/api/v1/clinic/doctors/{world.a.doctor.id}"
    monday = _monday().isoformat()

    for resp, status in (
        (
            _send(
                owner,
                "PUT",
                f"{doctor}/schedule",
                {
                    "blocks": [
                        {"weekday": 0, "start_time": "10:00", "end_time": "13:00", "capacity": 12},
                        {"weekday": 6, "start_time": "23:00", "end_time": "01:00", "capacity": 4},
                    ]
                },
            ),
            200,
        ),
        (_send(owner, "GET", f"{doctor}/schedule"), 200),
        (_send(owner, "GET", "/api/v1/sessions", query={"date": monday}), 200),
        (_send(owner, "PATCH", "/api/v1/clinic", {"booking_mode": "TOKENS"}), 200),
    ):
        assert resp.status_code == status, resp.get_json()
        _check(openapi, resp)

    extra = _send(
        owner,
        "POST",
        f"{doctor}/schedule-exceptions",
        {
            "kind": "EXTRA",
            "on_date": monday,
            "start_time": "18:00",
            "end_time": "19:00",
            "capacity": 5,
        },
    )
    assert extra.status_code == 201
    _check(openapi, extra)
    leave = _send(
        owner, "POST", f"{doctor}/schedule-exceptions", {"kind": "LEAVE", "on_date": monday}
    )
    assert leave.status_code == 201
    _check(openapi, leave)
    removed = _send(
        owner, "DELETE", f"{doctor}/schedule-exceptions/{leave.get_json()['exception']['id']}"
    )
    assert removed.status_code == 200
    _check(openapi, removed)


def test_adr_0008_slot_sessions_and_the_ops_route_match_the_contract(
    openapi: OpenAPI, world: World
) -> None:
    owner = world.client_for(world.a.owner)
    assert _send(owner, "PATCH", "/api/v1/clinic", {"booking_mode": "SLOTS"}).status_code == 200
    ops = world.client_for(world.ops)
    url = f"/api/v1/ops/clinics/{world.a.clinic.id}/doctors/{world.a.doctor.id}/schedule"

    put = _send(
        ops,
        "PUT",
        url,
        {
            "blocks": [
                {"weekday": 0, "start_time": "10:00", "end_time": "11:00", "slot_minutes": 15}
            ]
        },
    )
    assert put.status_code == 200
    _check(openapi, put)
    sessions = _send(owner, "GET", "/api/v1/sessions", query={"date": _monday().isoformat()})
    assert len(sessions.get_json()["items"][0]["slots"]) == 4
    _check(openapi, sessions)


def test_adr_0008_scheduling_errors_match_the_contract(openapi: OpenAPI, world: World) -> None:
    owner = world.client_for(world.a.owner)
    doctor = f"/api/v1/clinic/doctors/{world.a.doctor.id}"
    monday = _monday().isoformat()
    _send(owner, "POST", f"{doctor}/schedule-exceptions", {"kind": "LEAVE", "on_date": monday})

    for resp, status in (
        (
            _send(
                owner,
                "PUT",
                f"{doctor}/schedule",
                {
                    "blocks": [
                        {"weekday": 0, "start_time": "13:00", "end_time": "10:00", "capacity": 3}
                    ]
                },
            ),
            422,
        ),
        (
            _send(
                owner,
                "PUT",
                f"{doctor}/schedule",
                {
                    "blocks": [
                        {"weekday": 0, "start_time": "10:00", "end_time": "12:00", "capacity": 3},
                        {"weekday": 0, "start_time": "11:00", "end_time": "13:00", "capacity": 3},
                    ]
                },
            ),
            409,
        ),
        (
            _send(
                owner, "POST", f"{doctor}/schedule-exceptions", {"kind": "LEAVE", "on_date": monday}
            ),
            409,
        ),
        (_send(world.client_for(world.a.desk), "PUT", f"{doctor}/schedule", {"blocks": []}), 403),
        (_send(owner, "GET", f"/api/v1/clinic/doctors/{world.b.doctor.id}/schedule"), 404),
    ):
        assert resp.status_code == status, resp.get_json()
        _check(openapi, resp)
