"""The live queue over HTTP on PostgreSQL (M3-P4; FR-QUE-03; spec R12, D23-D26).

A screen polls ``GET /api/v1/queue`` with the last ``ETag`` and gets ``304`` until something it
would show changes. Today's sessions come from ``tests/sessions_now.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mediease_api.adapters.clock.system import SystemClock
from tests.conftest import World
from tests.integration.test_appointments_http import _patient
from tests.sessions_now import running_session


def _send(client: FlaskClient, method: str, url: str, body: Any = None) -> TestResponse:
    csrf = client.get_cookie("me_csrf", path="/")
    headers = {"X-CSRF-Token": csrf.value} if csrf is not None else {}
    return client.open(url, method=method, json=body, headers=headers)


def _poll(client: FlaskClient, tag: str | None = None, query: str = "") -> TestResponse:
    headers = {"If-None-Match": f'"{tag}"'} if tag else {}
    return client.get(f"/api/v1/queue{query}", headers=headers)


def _tag(resp: TestResponse) -> str:
    tag, weak = resp.get_etag()
    assert tag is not None and not weak
    return tag


def _book(client: FlaskClient, session_id: str, patient_id: str) -> str:
    resp = _send(
        client, "POST", "/api/v1/appointments", {"session_id": session_id, "patient_id": patient_id}
    )
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["id"])


def test_r12_an_unchanged_queue_is_a_304_with_the_same_headers(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    _book(desk, session["id"], _patient(desk))

    first = _poll(desk)
    assert first.status_code == 200
    tag = _tag(first)

    again = _poll(desk, tag)
    assert again.status_code == 304
    assert again.get_data() == b""
    assert again.headers["ETag"] == f'"{tag}"'
    assert again.headers["Cache-Control"] == "no-store"  # D26: names are never cached
    assert again.headers["X-Request-ID"]
    # Another screen of the same clinic, same filters: the same tag.
    assert _poll(world.client_for(world.a.doctor_user), tag).status_code == 304


def test_fr_que_03_every_visible_change_changes_the_tag(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    patient = _patient(desk)
    tag = _tag(_poll(desk))

    def changed() -> str:
        nonlocal tag
        resp = _poll(desk, tag)
        assert resp.status_code == 200, "the change was not visible to a polling screen"
        tag = _tag(resp)
        return tag

    appointment = _book(desk, session["id"], patient)
    changed()  # a booking
    moved = _send(
        desk,
        "POST",
        f"/api/v1/appointments/{appointment}/transitions",
        {"from": "BOOKED", "to": "ARRIVED"},
    )
    assert moved.status_code == 200
    changed()  # a status
    renamed = _send(desk, "PATCH", f"/api/v1/patients/{patient}", {"full_name": "Asha R. Rao"})
    assert renamed.status_code == 200, renamed.get_json()
    changed()  # a corrected name
    cancelled = _send(
        desk, "POST", f"/api/v1/appointments/{appointment}/cancel", {"reason": "DUPLICATE"}
    )
    assert cancelled.status_code == 200
    changed()  # a cancellation leaves the queue
    assert _poll(desk, tag).status_code == 304


def test_d24_a_waiting_patient_changes_the_tag_once_a_minute(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    appointment = _book(desk, session["id"], _patient(desk))
    arrived = _send(
        desk,
        "POST",
        f"/api/v1/appointments/{appointment}/transitions",
        {"from": "BOOKED", "to": "ARRIVED"},
    )
    assert arrived.status_code == 200
    first = _poll(desk)
    tag = _tag(first)

    real_now = SystemClock.now
    later = real_now(SystemClock()) + timedelta(minutes=1, seconds=5)
    monkeypatch.setattr(SystemClock, "now", lambda self: later.astimezone(UTC))
    ticked = _poll(desk, tag)

    assert ticked.status_code == 200
    waits = [a["wait_minutes"] for a in ticked.get_json()["sessions"][0]["appointments"]]
    assert waits[0] >= 1


def test_d23_other_filters_and_other_clinics_get_their_own_body(world: World) -> None:
    owner_a, owner_b = world.client_for(world.a.owner), world.client_for(world.b.owner)
    running_session(owner_a, world.a.doctor.id)
    tag_a = _tag(_poll(owner_a))

    filtered = _poll(owner_a, tag_a, f"?doctor_id={world.b.doctor.id}")
    assert filtered.status_code == 404  # another clinic's doctor, never a 304
    tomorrow = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    assert _poll(owner_a, tag_a, f"?date={tomorrow}").status_code == 200
    assert _poll(owner_b, tag_a).status_code == 200
