"""M7e-E2 (ADR-0025; spec web-push R10-R19): a person's devices for web push, over HTTP."""

from __future__ import annotations

import base64
from typing import Any

from flask.testing import FlaskClient
from sqlalchemy import text
from werkzeug.test import TestResponse

from mediease_api.application.push.subscriptions import GetPushConfig
from mediease_api.domain.push.subscription import MAX_DEVICES, SUBSCRIBES_PER_HOUR
from tests.conftest import UowFactory, World
from tests.integration.test_portal_http import portal_csrf
from tests.portal_helpers import portal_client, staff_csrf

PORTAL_DEVICES = "/api/v1/portal/push-subscriptions"
STAFF_DEVICES = "/api/v1/me/push-subscriptions"
ANDROID = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def subscription(n: int = 1, *, auth_byte: int = 0) -> dict[str, Any]:
    """What ``PushSubscription.toJSON()`` gives in a browser (synthetic endpoint and keys)."""
    return {
        "endpoint": f"https://fcm.googleapis.com/fcm/send/device-{n}:APA91b-test",
        "expirationTime": None,
        "keys": {
            "p256dh": _b64(b"\x04" + bytes([n % 256]) * 64),
            "auth": _b64(bytes([auth_byte]) * 16),
        },
    }


def subscribe(
    client: FlaskClient, url: str, csrf: dict[str, str], body: dict[str, Any]
) -> TestResponse:
    return client.post(url, json=body, headers={**csrf, "User-Agent": ANDROID})


def _rows(uow_factory: UowFactory) -> list[dict[str, Any]]:
    with uow_factory() as uow:
        result = uow._require_open().session.execute(
            text("SELECT * FROM push_subscriptions ORDER BY created_at")
        )
        return [dict(r._mapping) for r in result]


def _audit(uow_factory: UowFactory) -> list[tuple[str, str, dict[str, str]]]:
    with uow_factory() as uow:
        rows = uow._require_open().session.execute(
            text(
                "SELECT action, actor_type, metadata FROM audit_events"
                " WHERE action LIKE 'push_device.%' ORDER BY occurred_at, id"
            )
        )
        return [(r[0], r[1], r[2]) for r in rows]


# --- Config (R10) ---------------------------------------------------------------------------------


def test_r10_the_config_is_public_and_says_push_is_off_without_a_key(world: World) -> None:
    resp = world.anonymous().get("/api/v1/push/config")
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False, "public_key": None}
    assert resp.headers["Cache-Control"] == "no-store"


def test_r10_with_a_key_the_config_hands_it_to_browsers() -> None:
    key = _b64(b"\x04" + bytes(64))
    config = GetPushConfig(public_key=key).execute()
    assert (config.enabled, config.public_key) == (True, key)


# --- A patient's devices (R11-R17) ----------------------------------------------------------------


def test_r11_r15_a_patient_adds_this_browser_and_it_is_stored_encrypted(
    world: World, uow_factory: UowFactory
) -> None:
    me = portal_client(world, "push.patient@example.test")
    resp = subscribe(me, PORTAL_DEVICES, portal_csrf(me), subscription(1))
    assert resp.status_code == 201, resp.get_json()
    device = resp.get_json()
    assert device["label"] == "Chrome on Android"
    assert device["active"] is True and device["last_success_at"] is None
    assert resp.headers["Cache-Control"] == "no-store"
    [row] = _rows(uow_factory)
    assert row["account_id"] is not None and row["user_id"] is None
    # Nothing readable at rest: no endpoint host, no key, in any column.
    stored = " ".join(str(v) for v in row.values())
    assert "fcm.googleapis.com" not in stored
    assert subscription(1)["keys"]["p256dh"] not in stored
    assert _audit(uow_factory) == [
        (
            "push_device.added",
            "PATIENT",
            {"label": "Chrome on Android", "account_id": str(row["account_id"])},
        )
    ]


def test_r14_the_same_browser_again_refreshes_its_keys_and_adds_no_device(
    world: World, uow_factory: UowFactory
) -> None:
    me = portal_client(world, "push.again@example.test")
    first = subscribe(me, PORTAL_DEVICES, portal_csrf(me), subscription(1))
    again = subscribe(me, PORTAL_DEVICES, portal_csrf(me), subscription(1, auth_byte=7))
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.get_json()["id"] == first.get_json()["id"]
    [row] = _rows(uow_factory)
    assert row["updated_at"] >= row["created_at"]
    assert [a[0] for a in _audit(uow_factory)] == ["push_device.added"]


def test_r14_another_person_subscribing_the_same_browser_takes_the_device_over(
    world: World, uow_factory: UowFactory
) -> None:
    asha = portal_client(world, "push.asha@example.test")
    ravi = portal_client(world, "push.ravi@example.test", name="Ravi Patient")
    subscribe(asha, PORTAL_DEVICES, portal_csrf(asha), subscription(1))
    taken = subscribe(ravi, PORTAL_DEVICES, portal_csrf(ravi), subscription(1))
    assert taken.status_code == 201
    assert asha.get(PORTAL_DEVICES).get_json()["items"] == []
    assert [d["id"] for d in ravi.get(PORTAL_DEVICES).get_json()["items"]] == [
        taken.get_json()["id"]
    ]
    assert len(_rows(uow_factory)) == 1


def test_r16_r17_a_patient_lists_and_removes_their_own_devices_only(
    world: World, uow_factory: UowFactory
) -> None:
    me = portal_client(world, "push.mine@example.test")
    other = portal_client(world, "push.other@example.test", name="Other Patient")
    mine = [
        subscribe(me, PORTAL_DEVICES, portal_csrf(me), subscription(n)).get_json()["id"]
        for n in (1, 2)
    ]
    theirs = subscribe(other, PORTAL_DEVICES, portal_csrf(other), subscription(3)).get_json()["id"]
    listed = me.get(PORTAL_DEVICES)
    assert listed.status_code == 200
    assert [d["id"] for d in listed.get_json()["items"]] == list(reversed(mine))
    # Another account's device is not found, and stays.
    assert me.delete(f"{PORTAL_DEVICES}/{theirs}", headers=portal_csrf(me)).status_code == 404
    assert me.delete(f"{PORTAL_DEVICES}/{mine[0]}", headers=portal_csrf(me)).status_code == 204
    assert [d["id"] for d in me.get(PORTAL_DEVICES).get_json()["items"]] == [mine[1]]
    assert len(other.get(PORTAL_DEVICES).get_json()["items"]) == 1
    assert [a[0] for a in _audit(uow_factory)][-1] == "push_device.removed"


def test_r12_r13_a_bad_endpoint_or_key_is_refused_without_echoing_it(world: World) -> None:
    me = portal_client(world, "push.bad@example.test")
    for change in (
        {"endpoint": "https://169.254.169.254/latest/meta-data"},
        {"endpoint": "http://fcm.googleapis.com/fcm/send/x"},
        {"keys": {"p256dh": "short", "auth": _b64(bytes(16))}},
        {"unexpected": 1},
    ):
        resp = subscribe(me, PORTAL_DEVICES, portal_csrf(me), {**subscription(1), **change})
        assert resp.status_code == 422, change
        assert resp.get_json()["error"]["code"] == "REQ_VALIDATION_FAILED"
        assert "169.254" not in resp.get_data(as_text=True)


def test_r18_the_csrf_token_is_needed_and_a_staff_session_cannot_use_the_portal_routes(
    world: World,
) -> None:
    me = portal_client(world, "push.csrf@example.test")
    no_token = me.post(PORTAL_DEVICES, json=subscription(1))
    assert no_token.status_code == 403
    assert no_token.get_json()["error"]["code"] == "AUTH_CSRF_INVALID"
    staff = world.client_for(world.a.desk)
    assert staff.get(PORTAL_DEVICES).status_code == 401
    assert world.anonymous().get(PORTAL_DEVICES).status_code == 401


def test_r19_at_most_ten_devices_and_thirty_subscribes_an_hour(world: World) -> None:
    me = portal_client(world, "push.many@example.test")
    for n in range(MAX_DEVICES):
        assert (
            subscribe(me, PORTAL_DEVICES, portal_csrf(me), subscription(n + 1)).status_code == 201
        )
    full = subscribe(me, PORTAL_DEVICES, portal_csrf(me), subscription(99))
    assert full.status_code == 409
    assert full.get_json()["error"]["code"] == "PSH_TOO_MANY_DEVICES"
    for _ in range(SUBSCRIBES_PER_HOUR - MAX_DEVICES - 1):
        subscribe(me, PORTAL_DEVICES, portal_csrf(me), subscription(1))
    limited = subscribe(me, PORTAL_DEVICES, portal_csrf(me), subscription(1))
    assert limited.status_code == 429
    assert limited.get_json()["error"]["code"] == "PSH_RATE_LIMITED"
    assert 1 <= int(limited.headers["Retry-After"]) <= 3600


# --- A staff member's devices (R11, R16, R17) ----------------------------------------------------


def test_r11_staff_devices_belong_to_the_user_in_every_clinic(
    world: World, uow_factory: UowFactory
) -> None:
    desk = world.client_for(world.a.desk)
    resp = subscribe(desk, STAFF_DEVICES, staff_csrf(desk), subscription(5))
    assert resp.status_code == 201, resp.get_json()
    [row] = _rows(uow_factory)
    assert row["user_id"] == world.a.desk.id and row["account_id"] is None
    # No clinic header needed: the device is the person's, not a clinic's.
    assert [d["id"] for d in desk.get(STAFF_DEVICES).get_json()["items"]] == [resp.get_json()["id"]]
    action, actor, metadata = _audit(uow_factory)[0]
    assert (action, actor, metadata) == (
        "push_device.added",
        "STAFF",
        {"label": "Chrome on Android"},
    )


def test_r17_another_users_device_is_not_found_and_a_patient_cannot_use_the_staff_routes(
    world: World,
) -> None:
    desk = world.client_for(world.a.desk)
    owner_b = world.client_for(world.b.owner)
    device = subscribe(desk, STAFF_DEVICES, staff_csrf(desk), subscription(6)).get_json()["id"]
    assert (
        owner_b.delete(f"{STAFF_DEVICES}/{device}", headers=staff_csrf(owner_b)).status_code == 404
    )
    assert owner_b.get(STAFF_DEVICES).get_json()["items"] == []
    me = portal_client(world, "push.notstaff@example.test")
    assert me.get(STAFF_DEVICES).status_code == 401
    assert desk.delete(f"{STAFF_DEVICES}/{device}", headers=staff_csrf(desk)).status_code == 204


# --- The PUSH preference channel (R20) -----------------------------------------------------------


def test_r20_a_patient_turns_push_off_for_one_kind(world: World) -> None:
    me = portal_client(world, "push.prefs@example.test")
    before = me.get("/api/v1/portal/notification-preferences").get_json()["items"]
    assert all(item["push"] is True for item in before)
    resp = me.put(
        "/api/v1/portal/notification-preferences",
        json={"kind": "medicine.due", "channel": "PUSH", "enabled": False},
        headers=portal_csrf(me),
    )
    assert resp.status_code == 200, resp.get_json()
    after = {item["kind"]: item for item in resp.get_json()["items"]}
    assert after["medicine.due"]["push"] is False
    assert after["medicine.due"]["in_app"] is True


def test_r20_staff_preferences_list_push_beside_in_app_and_audit_the_change(
    world: World, uow_factory: UowFactory
) -> None:
    desk = world.client_for(world.a.desk)
    items = desk.get("/api/v1/notifications/preferences").get_json()["items"]
    channels = {i["channel"] for i in items}
    assert channels == {"IN_APP", "PUSH"}
    assert len([i for i in items if i["channel"] == "PUSH"]) == len(
        [i for i in items if i["channel"] == "IN_APP"]
    )
    resp = desk.put(
        "/api/v1/notifications/preferences",
        json={"items": [{"kind": "appointment.booked", "channel": "PUSH", "enabled": False}]},
        headers=staff_csrf(desk),
    )
    assert resp.status_code == 200, resp.get_json()
    chosen = {(i["kind"], i["channel"]): i["enabled"] for i in resp.get_json()["items"]}
    assert chosen[("appointment.booked", "PUSH")] is False
    assert chosen[("appointment.booked", "IN_APP")] is True
    with uow_factory() as uow:
        metadata = (
            uow._require_open()
            .session.execute(
                text(
                    "SELECT metadata FROM audit_events"
                    " WHERE action = 'notification.preferences_changed' ORDER BY occurred_at DESC"
                )
            )
            .scalar_one()
        )
    assert metadata == {"on": "", "off": "appointment.booked:PUSH"}
    for channel in ("WHATSAPP", "EMAIL", "SMS"):
        refused = desk.put(
            "/api/v1/notifications/preferences",
            json={"items": [{"kind": "appointment.booked", "channel": channel, "enabled": False}]},
            headers=staff_csrf(desk),
        )
        assert refused.status_code == 409, channel
