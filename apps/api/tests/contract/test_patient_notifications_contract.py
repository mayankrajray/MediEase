"""Patient notifications and the live token link against contracts/openapi.yaml (M6b-P6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from flask.testing import FlaskClient
from openapi_core import OpenAPI
from werkzeug.test import TestResponse

from mediease_api.adapters.security.link_signer import HmacLinkSigner
from mediease_api.application.links.use_cases import LinkTokens
from mediease_api.domain.links.token import QueueClaims
from tests.booking_helpers import request_in, staff_post
from tests.conftest import World
from tests.contract.test_portal_linking_contract import _expect, _psend
from tests.contract.test_scheduling_contract import _check, _send, openapi  # noqa: F401
from tests.portal_helpers import PORTAL, link_by_invite
from tests.sessions_now import running_session

STAFF = "/api/v1/booking-requests"
NEW = {"new_patient": {"sex": "FEMALE", "age_years": 34}}


def _conditional(client: FlaskClient, path: str, tag: str) -> TestResponse:
    client.environ_base["HTTP_IF_NONE_MATCH"] = tag
    try:
        return _send(client, "GET", path)
    finally:
        del client.environ_base["HTTP_IF_NONE_MATCH"]


def test_adr_0008_portal_notifications_and_preferences_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    patient, rid = request_in(world, world.a, "contract.bell@example.test")
    accepted = staff_post(world.client_for(world.a.desk), f"{STAFF}/{rid}/accept", NEW)
    assert accepted.status_code == 201, accepted.get_json()

    listed = _expect(openapi, _psend(patient, "GET", f"{PORTAL}/notifications"), 200)
    first = _psend(patient, "GET", f"{PORTAL}/notifications/summary")
    _expect(openapi, first, 200)
    unchanged = _conditional(patient, f"{PORTAL}/notifications/summary", first.headers["ETag"])
    assert unchanged.status_code == 304
    _check(openapi, unchanged)

    notice = listed["items"][0]["id"]
    _expect(openapi, _psend(patient, "POST", f"{PORTAL}/notifications/{notice}/read"), 204)
    _expect(openapi, _psend(patient, "POST", f"{PORTAL}/notifications/{uuid4()}/read"), 404)
    _expect(openapi, _psend(patient, "POST", f"{PORTAL}/notifications/read-all"), 200)

    prefs = f"{PORTAL}/notification-preferences"
    _expect(openapi, _psend(patient, "GET", prefs), 200)
    off = {"kind": "booking.accepted", "channel": "EMAIL", "enabled": False}
    _expect(openapi, _psend(patient, "PUT", prefs, off), 200)
    refused = {"kind": "medicine.due", "channel": "EMAIL", "enabled": True}
    _expect(openapi, _psend(patient, "PUT", prefs, refused), 422)


def test_adr_0008_live_links_and_the_public_queue_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    from tests.booking_helpers import verified_client
    from tests.integration.test_appointments_http import _patient

    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    record = _patient(desk, "Contract Live")
    patient = verified_client(world, "contract.live@example.test")
    link_by_invite(owner, patient, record)
    booked = _expect(
        openapi,
        _send(
            desk,
            "POST",
            "/api/v1/appointments",
            {"session_id": session["id"], "patient_id": record},
        ),
        201,
    )
    other = _expect(
        openapi,
        _send(
            desk,
            "POST",
            "/api/v1/appointments",
            {"session_id": session["id"], "patient_id": _patient(desk, "Someone Else")},
        ),
        201,
    )

    staff = _expect(
        openapi, _send(desk, "GET", f"/api/v1/appointments/{booked['id']}/live-link"), 200
    )
    mine = f"{PORTAL}/appointments/{booked['id']}/live-link"
    _expect(openapi, _psend(patient, "GET", mine), 200)
    # Ownership: another patient's appointment does not exist for this account.
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/appointments/{other['id']}/live-link"), 404)

    anon = world.anonymous()
    path = "/api/v1/public/queue/" + staff["url"].rsplit("/q/", 1)[1]
    first = _send(anon, "GET", path)
    _expect(openapi, first, 200)
    unchanged = _conditional(anon, path, first.headers["ETag"])
    assert unchanged.status_code == 304
    _check(openapi, unchanged)

    now = datetime.now(UTC).replace(microsecond=0)
    tokens = LinkTokens(HmacLinkSigner(world.app.config["SETTINGS"].patient_link_keys()))
    old = tokens.queue_token(
        QueueClaims(
            cid=world.a.clinic.id,
            aid=UUID(booked["id"]),
            nbf=now - timedelta(days=2),
            exp=now - timedelta(days=1),
        )
    )
    _expect(openapi, _send(anon, "GET", f"/api/v1/public/queue/{old}"), 410)
    _expect(openapi, _send(anon, "GET", f"/api/v1/public/queue/{old[:-4]}AAAA"), 404)

    cancelled = _send(
        desk, "POST", f"/api/v1/appointments/{other['id']}/cancel", {"reason": "CLINIC_REQUEST"}
    )
    assert cancelled.status_code == 200, cancelled.get_json()
    _expect(openapi, _send(desk, "GET", f"/api/v1/appointments/{other['id']}/live-link"), 422)
