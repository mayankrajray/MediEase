"""M7e-E3 (ADR-0025; spec web-push R30-R37): push delivery from a notice to a person's devices.

Real PostgreSQL and the real composition root; the push service is a fake port, so the tests see
exactly what would leave and can answer as a push service would (accepted, gone, busy, refused).
"""

from __future__ import annotations

import base64
import dataclasses
import json
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.security.text_cipher import FernetTextCipher
from mediease_api.application.notifications.service import publish
from mediease_api.application.push.delivery import SendPush
from mediease_api.domain.jobs.job import PUSH_KIND, ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.notifications.events import BookingRequestAnswered
from mediease_api.ports.push import PushFailed, PushFailure, PushTarget
from tests.booking_helpers import request_in, staff_post
from tests.conftest import UowFactory, World
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_push_http import (
    PORTAL_DEVICES,
    STAFF_DEVICES,
    subscribe,
    subscription,
)
from tests.portal_helpers import staff_csrf

NEW = {"new_patient": {"sex": "FEMALE", "age_years": 34}}
PREFS = "/api/v1/portal/notification-preferences"


class FakePush:
    """A push service: records what it was handed, or answers with ``failure``."""

    provider = "test"

    def __init__(self, failure: PushFailure | None = None, status: int | None = None) -> None:
        self.sent: list[tuple[PushTarget, dict[str, Any], int]] = []
        self._failure = failure
        self._status = status

    def send(self, target: PushTarget, data: str, *, ttl: int) -> None:
        if self._failure is not None:
            raise PushFailed(self._failure, status=self._status)
        self.sent.append((target, json.loads(data), ttl))


def _jobs(uow_factory: UowFactory) -> list[ClaimedJob]:
    with uow_factory() as uow:
        rows = uow._require_open().session.execute(
            text(
                "SELECT id, clinic_id, payload, dedupe_key FROM jobs WHERE kind = :k"
                " ORDER BY created_at, id"
            ),
            {"k": PUSH_KIND},
        )
        return [
            ClaimedJob(
                id=r.id,
                kind=PUSH_KIND,
                clinic_id=r.clinic_id,
                payload=r.payload,
                attempts=1,
                max_attempts=5,
                request_id=None,
                locked_by="test",
                dedupe_key=r.dedupe_key,
            )
            for r in rows
        ]


def _devices(uow_factory: UowFactory) -> dict[str, dict[str, Any]]:
    with uow_factory() as uow:
        rows = uow._require_open().session.execute(text("SELECT * FROM push_subscriptions"))
        return {str(r.id): dict(r._mapping) for r in rows}


def _handler(world: World, uow_factory: UowFactory, push: FakePush) -> SendPush:
    keys = world.app.config["SETTINGS"].messaging_phone_keys()
    return SendPush(
        uow=uow_factory(), clock=SystemClock(), push=push, cipher=FernetTextCipher(keys)
    )


def _answered(world: World) -> tuple[Any, str, list[str]]:
    """A patient with two devices whose booking request the desk accepts."""
    patient, rid = request_in(world, world.a, "push.told@example.test")
    devices = [
        subscribe(patient, PORTAL_DEVICES, portal_csrf(patient), subscription(n)).get_json()["id"]
        for n in (1, 2)
    ]
    accepted = staff_post(
        world.client_for(world.a.desk), f"/api/v1/booking-requests/{rid}/accept", NEW
    )
    assert accepted.status_code == 201, accepted.get_json()
    return patient, rid, devices


# --- A patient's notice (R30-R33) -----------------------------------------------------------------


def test_r30_r31_one_push_per_device_and_a_replay_enqueues_nothing(
    world: World, uow_factory: UowFactory
) -> None:
    _, rid, devices = _answered(world)
    jobs = _jobs(uow_factory)
    assert sorted(str(j.payload["device_id"]) for j in jobs) == sorted(devices)
    for job in jobs:
        assert job.clinic_id == world.a.clinic.id
        # R32: the job holds IDs, the kind and the path; nothing about the person or the visit.
        assert set(job.payload) == {"owner_kind", "owner_id", "device_id", "notice", "link"}
        assert (job.payload["notice"], job.payload["link"]) == (
            "booking.accepted",
            "/portal/appointments",
        )

    with uow_factory() as uow:  # R31: the same event again
        publish(
            uow,
            BookingRequestAnswered(UUID(rid)),
            clinic_id=world.a.clinic.id,
            ids=Uuid7Generator(),
            now=SystemClock().now(),
        )
        uow.commit()
    assert len(_jobs(uow_factory)) == 2


def test_r38_a_push_at_night_waits_for_eight_and_a_medicine_reminder_does_not(
    world: World, uow_factory: UowFactory
) -> None:
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from mediease_api.application.portal.patient_notifications import notify_patient
    from mediease_api.domain.portal.notifications import PatientNotificationKind

    patient, _ = request_in(world, world.a, "push.night@example.test")
    subscribe(patient, PORTAL_DEVICES, portal_csrf(patient), subscription(5))
    with uow_factory() as uow:
        account = (
            uow._require_open()
            .session.execute(
                text("SELECT id FROM patient_accounts WHERE email = 'push.night@example.test'")
            )
            .scalar_one()
        )
    zone = ZoneInfo(world.a.clinic.timezone)
    night = datetime(2026, 11, 12, 23, 30, tzinfo=zone).astimezone(UTC)
    kinds = (PatientNotificationKind.APPOINTMENT_CANCELLED, PatientNotificationKind.MEDICINE_DUE)
    with uow_factory() as uow:
        for kind in kinds:
            notify_patient(
                uow,
                uow.tenant(world.a.clinic.id),
                ids=Uuid7Generator(),
                account_id=account,
                kind=kind,
                event_key=f"{kind.value}:night-test",
                entity=("appointment", account),
                link="/portal",
                params={},
                now=night,
            )
        uow.commit()
    with uow_factory() as uow:
        rows = uow._require_open().session.execute(
            text("SELECT payload->>'notice' AS notice, run_at FROM jobs WHERE kind = :k"),
            {"k": PUSH_KIND},
        )
        run_at = {r.notice: r.run_at.astimezone(zone) for r in rows}
    assert run_at["appointment.cancelled"] == datetime(2026, 11, 13, 8, 0, tzinfo=zone)
    assert run_at["medicine.due"] == night.astimezone(zone)


def test_r32_r33_the_push_is_generic_and_records_the_success(
    world: World, uow_factory: UowFactory
) -> None:
    _, _, devices = _answered(world)
    push = FakePush()
    for job in _jobs(uow_factory):
        _handler(world, uow_factory, push)(job)
    assert len(push.sent) == 2
    endpoints = {target.endpoint for target, _, _ in push.sent}
    assert endpoints == {subscription(1)["endpoint"], subscription(2)["endpoint"]}
    for _, body, ttl in push.sent:
        assert body == {
            "title": "Booking accepted",
            "body": "Your booking request was accepted. Open MediEase to see it.",
            "url": "/portal/appointments",
            "tag": "booking.accepted",
        }
        assert ttl == 86_400
        sent = json.dumps(body, ensure_ascii=False)
        for leak in (world.a.clinic.name, world.a.doctor.display_name, "Asha"):
            assert leak not in sent
    rows = _devices(uow_factory)
    assert all(rows[d]["last_success_at"] is not None for d in devices)


def test_r32_a_hindi_account_gets_the_hindi_text(world: World, uow_factory: UowFactory) -> None:
    patient, rid = request_in(world, world.a, "push.hindi@example.test")
    lang = patient.patch("/api/v1/portal/me", json={"language": "hi"}, headers=portal_csrf(patient))
    assert lang.status_code == 200, lang.get_json()
    subscribe(patient, PORTAL_DEVICES, portal_csrf(patient), subscription(3))
    staff_post(world.client_for(world.a.desk), f"/api/v1/booking-requests/{rid}/accept", NEW)
    push = FakePush()
    [job] = _jobs(uow_factory)
    _handler(world, uow_factory, push)(job)
    [(_, body, _)] = push.sent
    assert body["title"] == "बुकिंग स्वीकार हुई"
    assert body["body"].endswith("देखने के लिए MediEase खोलें।")


def test_r20_r30_push_has_its_own_switch(world: World, uow_factory: UowFactory) -> None:
    patient, rid = request_in(world, world.a, "push.switch@example.test")
    subscribe(patient, PORTAL_DEVICES, portal_csrf(patient), subscription(1))
    for channel, enabled in (("PUSH", False), ("IN_APP", True)):
        resp = patient.put(
            PREFS,
            json={"kind": "booking.accepted", "channel": channel, "enabled": enabled},
            headers=portal_csrf(patient),
        )
        assert resp.status_code == 200
    staff_post(world.client_for(world.a.desk), f"/api/v1/booking-requests/{rid}/accept", NEW)
    assert _jobs(uow_factory) == []


def test_r20_push_still_goes_with_the_in_app_notice_off(
    world: World, uow_factory: UowFactory
) -> None:
    patient, rid = request_in(world, world.a, "push.only@example.test")
    subscribe(patient, PORTAL_DEVICES, portal_csrf(patient), subscription(1))
    patient.put(
        PREFS,
        json={"kind": "booking.accepted", "channel": "IN_APP", "enabled": False},
        headers=portal_csrf(patient),
    )
    staff_post(world.client_for(world.a.desk), f"/api/v1/booking-requests/{rid}/accept", NEW)
    assert len(_jobs(uow_factory)) == 1


def test_r35_turned_off_or_removed_after_the_notice_sends_nothing(
    world: World, uow_factory: UowFactory
) -> None:
    patient, _, devices = _answered(world)
    first, second = _jobs(uow_factory)
    removed = patient.delete(
        f"{PORTAL_DEVICES}/{first.payload['device_id']}", headers=portal_csrf(patient)
    )
    assert removed.status_code == 204
    patient.put(
        PREFS,
        json={"kind": "booking.accepted", "channel": "PUSH", "enabled": False},
        headers=portal_csrf(patient),
    )
    push = FakePush()
    for job in (first, second):
        _handler(world, uow_factory, push)(job)
    assert push.sent == []
    assert len(devices) == 2


# --- Answers from the push service (R34, R36) -----------------------------------------------------


@pytest.mark.parametrize("status", [404, 410])
def test_r34_a_gone_browser_disables_the_device_and_gets_no_more_jobs(
    world: World, uow_factory: UowFactory, status: int
) -> None:
    patient, _, devices = _answered(world)
    jobs = _jobs(uow_factory)
    handler = _handler(world, uow_factory, FakePush(PushFailure.GONE, status))
    for job in jobs:
        handler(job)  # the job succeeds: there is nothing to retry
    rows = _devices(uow_factory)
    for device in devices:
        assert rows[device]["disabled_at"] is not None
        assert rows[device]["disabled_reason"] == "EXPIRED"
    listed = patient.get(PORTAL_DEVICES).get_json()["items"]
    assert {d["active"] for d in listed} == {False}

    # The next notice goes to no device.
    _, rid2 = request_in(world, world.a, "push.told.again@example.test")
    before = len(_jobs(uow_factory))
    staff_post(world.client_for(world.a.desk), f"/api/v1/booking-requests/{rid2}/accept", NEW)
    assert len(_jobs(uow_factory)) == before


@pytest.mark.parametrize(
    ("failure", "status", "retryable"),
    [
        (PushFailure.RATE_LIMITED, 429, True),
        (PushFailure.UNAVAILABLE, 503, True),
        (PushFailure.UNAVAILABLE, None, True),
        (PushFailure.REFUSED, 403, False),
    ],
)
def test_r36_busy_is_retried_and_refused_is_not(
    world: World,
    uow_factory: UowFactory,
    json_logs: Any,
    failure: PushFailure,
    status: int | None,
    retryable: bool,
) -> None:
    _answered(world)
    job = _jobs(uow_factory)[0]
    with pytest.raises(JobFailure) as raised:
        _handler(world, uow_factory, FakePush(failure, status))(job)
    assert (raised.value.code, raised.value.retryable) == (failure.value, retryable)
    rows = _devices(uow_factory)
    assert rows[str(job.payload["device_id"])]["disabled_at"] is None
    # R37: the log names the device, never its endpoint.
    logs = json.dumps(json_logs())
    assert "fcm.googleapis.com" not in logs and "push.failed" in logs


# --- Staff (R30) ----------------------------------------------------------------------------------


def test_r30_a_staff_member_is_pushed_a_new_booking_request(
    world: World, uow_factory: UowFactory
) -> None:
    desk = world.client_for(world.a.desk)
    device = subscribe(desk, STAFF_DEVICES, staff_csrf(desk), subscription(9)).get_json()["id"]
    request_in(world, world.a, "push.asks@example.test")
    [job] = _jobs(uow_factory)
    assert job.payload["owner_kind"] == "STAFF" and job.payload["device_id"] == device
    push = FakePush()
    _handler(world, uow_factory, push)(job)
    [(_, body, _)] = push.sent
    assert body == {
        "title": "New booking request",
        "body": "A patient asked for an appointment. Open MediEase to see it.",
        "url": "/booking-requests",
        "tag": "booking.requested",
    }


def test_r30_r35_staff_push_off_or_no_longer_a_member_sends_nothing(
    world: World, uow_factory: UowFactory
) -> None:
    desk = world.client_for(world.a.desk)
    subscribe(desk, STAFF_DEVICES, staff_csrf(desk), subscription(9))
    off = desk.put(
        "/api/v1/notifications/preferences",
        json={"items": [{"kind": "booking.requested", "channel": "PUSH", "enabled": False}]},
        headers=staff_csrf(desk),
    )
    assert off.status_code == 200
    request_in(world, world.a, "push.asks.quiet@example.test")
    assert _jobs(uow_factory) == []


def test_a_malformed_job_is_dead_and_an_unreadable_device_is_skipped(
    world: World, uow_factory: UowFactory
) -> None:
    _answered(world)
    job = _jobs(uow_factory)[0]
    push = FakePush()
    for broken in ({**job.payload, "notice": "nope"}, {**job.payload, "owner_kind": "CLINIC"}):
        bad = dataclasses.replace(job, payload=broken)
        with pytest.raises(JobFailure) as raised:
            _handler(world, uow_factory, push)(bad)
        assert (raised.value.code, raised.value.retryable) == ("JOB_HANDLER_ERROR", False)
    # A key no longer configured: the device cannot be read, so nothing is sent.
    other = FernetTextCipher([base64.urlsafe_b64encode(b"another-push-test-key-32-bytes!!")])
    SendPush(uow=uow_factory(), clock=SystemClock(), push=push, cipher=other)(job)
    assert push.sent == []
