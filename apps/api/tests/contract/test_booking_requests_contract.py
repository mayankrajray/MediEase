"""The public page, booking requests and the hold: real responses against the contract (ADR-0008).

M6b-P4. Every status the contract declares for these paths is produced once and validated.
"""

from __future__ import annotations

from collections.abc import Iterator
from json import dumps
from typing import Any

import pytest
from flask.testing import FlaskClient
from openapi_core import OpenAPI
from sqlalchemy import Engine, create_engine
from werkzeug.test import TestResponse

from tests.booking_helpers import offers, request_in, staff_session_after
from tests.conftest import World
from tests.contract.test_scheduling_contract import _check, _send, openapi  # noqa: F401
from tests.integration.test_appointments_http import MONDAY, _schedule
from tests.integration.test_appointments_http import _patient as _register
from tests.integration.test_booking_requests_http import _form, _slug
from tests.portal_helpers import portal_client, verify_email

BASE = "http://localhost:8000"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _portal(
    client: FlaskClient, method: str, path: str, body: dict[str, Any] | None = None
) -> TestResponse:
    csrf = client.get_cookie("me_pt_csrf", domain="localhost", path="/")
    headers = {"X-CSRF-Token": csrf.value} if csrf is not None else {}
    resp = client.open(path, method=method, base_url=BASE, json=body, headers=headers)
    resp.sent_body = b"" if body is None else dumps(body).encode()  # type: ignore[attr-defined]
    return resp


def test_adr_0008_the_public_page_and_availability_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    _schedule(world, capacity=2)
    anon = world.anonymous()
    page = anon.get(f"/api/v1/public/clinics/{_slug(world)}", base_url=BASE)
    assert page.status_code == 200
    _check(openapi, page)

    offers = anon.get(
        f"/api/v1/public/clinics/{_slug(world)}/availability",
        query_string={"doctor_id": str(world.a.doctor.id), "from": MONDAY.isoformat()},
        base_url=BASE,
    )
    assert offers.status_code == 200
    _check(openapi, offers)

    for url in (
        "/api/v1/public/clinics/no-such-clinic",
        f"/api/v1/public/clinics/no-such-clinic/availability?doctor_id={world.a.doctor.id}",
    ):
        missing = anon.get(url, base_url=BASE)
        assert missing.status_code == 404
        _check(openapi, missing)


def test_adr_0008_requests_holds_and_overrides_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
    db: Engine,
) -> None:
    _schedule(world, capacity=1)
    me = portal_client(world, "contract.requester@example.test")
    unverified = _portal(me, "POST", "/api/v1/portal/booking-requests", _form(world))
    assert unverified.status_code == 403
    _check(openapi, unverified)

    verify_email(db, "contract.requester@example.test")
    made = _portal(me, "POST", "/api/v1/portal/booking-requests", _form(world))
    assert made.status_code == 201, made.get_json()
    _check(openapi, made)

    again = _portal(me, "POST", "/api/v1/portal/booking-requests", _form(world))
    assert again.status_code == 409
    _check(openapi, again)

    bad = _portal(
        me, "POST", "/api/v1/portal/booking-requests", _form(world, not_emergency_ack=False)
    )
    assert bad.status_code == 422
    _check(openapi, bad)

    listed = _portal(me, "GET", "/api/v1/portal/booking-requests")
    assert listed.status_code == 200
    _check(openapi, listed)

    desk = world.client_for(world.a.desk)
    staff = _send(desk, "GET", "/api/v1/booking-requests")
    assert staff.status_code == 200
    _check(openapi, staff)

    monday = MONDAY.isoformat()
    sessions = _send(
        desk,
        "GET",
        "/api/v1/sessions",
        query={"date": monday, "doctor_id": str(world.a.doctor.id)},
    )
    assert sessions.status_code == 200
    assert len(sessions.get_json()["items"][0]["held"]) == 1
    _check(openapi, sessions)
    session_id = sessions.get_json()["items"][0]["id"]

    patient = _register(desk)
    held = _send(
        desk, "POST", "/api/v1/appointments", {"session_id": session_id, "patient_id": patient}
    )
    assert held.status_code == 409
    assert held.get_json()["error"]["code"] == "APT_SLOT_HELD"
    _check(openapi, held)

    forced = _send(
        desk,
        "POST",
        "/api/v1/appointments",
        {"session_id": session_id, "patient_id": patient, "override_hold": True},
    )
    assert forced.status_code == 201, forced.get_json()
    _check(openapi, forced)

    owner = world.client_for(world.a.owner)
    settings = _send(
        owner,
        "PATCH",
        "/api/v1/clinic",
        {"request_hold_minutes": 60, "request_requires_age_sex": True},
    )
    assert settings.status_code == 200
    _check(openapi, settings)


def test_adr_0008_answering_requests_matches_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
    db: Engine,
) -> None:
    """M6b-P5: candidates, accept, decline, propose, the patient's answers and the lists."""
    desk = world.client_for(world.a.desk)
    patient, first = request_in(world, world.a, "contract.answer.1@example.test")

    candidates = _send(desk, "GET", f"/api/v1/booking-requests/{first}/candidates")
    assert candidates.status_code == 200
    _check(openapi, candidates)

    bad = _send(desk, "POST", f"/api/v1/booking-requests/{first}/accept", {})
    assert bad.status_code == 422
    _check(openapi, bad)

    accepted = _send(
        desk,
        "POST",
        f"/api/v1/booking-requests/{first}/accept",
        {"new_patient": {"sex": "FEMALE", "age_years": 30}},
    )
    assert accepted.status_code == 201, accepted.get_json()
    _check(openapi, accepted)

    again = _send(desk, "POST", f"/api/v1/booking-requests/{first}/decline", {"reason": "OTHER"})
    assert again.status_code == 409
    _check(openapi, again)

    _, second = request_in(world, world.a, "contract.answer.2@example.test", phone="9000000801")
    declined = _send(
        desk,
        "POST",
        f"/api/v1/booking-requests/{second}/decline",
        {"reason": "PLEASE_CALL", "note": "staff only"},
    )
    assert declined.status_code == 200
    _check(openapi, declined)

    third_client, third = request_in(
        world, world.a, "contract.answer.3@example.test", phone="9000000802"
    )
    starts = offers(world, world.a)[0]["starts_at"]
    target = staff_session_after(world, world.a, starts)
    body: dict[str, Any] = {
        "session_id": target["id"],
        "new_patient": {"sex": "MALE", "age_years": 41},
    }
    if target["slots"]:
        body["slot_start"] = target["slots"][0]["starts_at"]
    proposed = _send(desk, "POST", f"/api/v1/booking-requests/{third}/propose", body)
    assert proposed.status_code == 200, proposed.get_json()
    _check(openapi, proposed)

    mine = _portal(third_client, "GET", "/api/v1/portal/booking-requests")
    assert mine.get_json()["items"][0]["status"] == "PROPOSED"
    _check(openapi, mine)
    taken = _portal(
        third_client, "POST", f"/api/v1/portal/booking-requests/{third}/accept-proposal"
    )
    assert taken.status_code == 200, taken.get_json()
    _check(openapi, taken)
    refused = _portal(
        third_client, "POST", f"/api/v1/portal/booking-requests/{third}/decline-proposal"
    )
    assert refused.status_code == 409
    _check(openapi, refused)

    for state in ("open", "answered"):
        listed = _send(desk, "GET", "/api/v1/booking-requests", query={"state": state})
        assert listed.status_code == 200
        _check(openapi, listed)
    today = _send(world.client_for(world.a.owner), "GET", "/api/v1/dashboard/today")
    assert today.status_code == 200
    _check(openapi, today)
    assert patient is not None
