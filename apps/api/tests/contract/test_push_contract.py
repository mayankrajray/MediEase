"""M7e-E2 (ADR-0008, ADR-0025): the push routes answer as contracts/openapi.yaml says."""

from __future__ import annotations

from openapi_core import OpenAPI
from werkzeug.test import TestResponse

from tests.conftest import World
from tests.contract.test_portal_linking_contract import _psend
from tests.contract.test_scheduling_contract import _BASE_URL, _check, _send, openapi  # noqa: F401
from tests.integration.test_push_http import subscription
from tests.portal_helpers import portal_client


def _expect(openapi: OpenAPI, resp: TestResponse, status: int) -> None:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    _check(openapi, resp)


def test_the_config_matches_the_contract(openapi: OpenAPI, world: World) -> None:  # noqa: F811
    _expect(openapi, _send(world.anonymous(), "GET", "/api/v1/push/config"), 200)


def test_a_patients_devices_match_the_contract(openapi: OpenAPI, world: World) -> None:  # noqa: F811
    me = portal_client(world, "push.contract@example.test")
    url = "/api/v1/portal/push-subscriptions"
    added = _psend(me, "POST", url, subscription(1))
    _expect(openapi, added, 201)
    _expect(openapi, _psend(me, "POST", url, subscription(1)), 200)
    _expect(openapi, _psend(me, "GET", url), 200)
    bad = {**subscription(2), "endpoint": "https://x.example/"}
    _expect(openapi, _psend(me, "POST", url, bad), 422)
    device = added.get_json()["id"]
    _expect(openapi, _psend(me, "DELETE", f"{url}/{device}"), 204)
    _expect(openapi, _psend(me, "DELETE", f"{url}/{device}"), 404)


def test_a_staff_members_devices_match_the_contract(openapi: OpenAPI, world: World) -> None:  # noqa: F811
    desk = world.client_for(world.a.desk)
    url = "/api/v1/me/push-subscriptions"
    added = _send(desk, "POST", url, subscription(3))
    _expect(openapi, added, 201)
    _expect(openapi, _send(desk, "GET", url), 200)
    _expect(openapi, _send(desk, "DELETE", f"{url}/{added.get_json()['id']}"), 204)


def test_the_preferences_with_push_match_the_contract(openapi: OpenAPI, world: World) -> None:  # noqa: F811
    me = portal_client(world, "push.prefs.contract@example.test")
    url = "/api/v1/portal/notification-preferences"
    _expect(openapi, _psend(me, "GET", url), 200)
    change = {"kind": "medicine.due", "channel": "PUSH", "enabled": False}
    _expect(openapi, _psend(me, "PUT", url, change), 200)
    desk = world.client_for(world.a.desk)
    staff = "/api/v1/notifications/preferences"
    _expect(openapi, _send(desk, "GET", staff), 200)
    body = {"items": [{"kind": "appointment.booked", "channel": "PUSH", "enabled": False}]}
    _expect(openapi, _send(desk, "PUT", staff, body), 200)
