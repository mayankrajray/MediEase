"""The public clinic page, booking requests and the soft hold over HTTP (M6b-P4).

Spec booking-requests R1-R30 and AC1-AC7; ADR-0018. Real PostgreSQL, the real composition root.
Dates are the Monday at least a week ahead in the clinic's timezone, so the 2-hour lead and the
4-hour response window never get in the way; hold expiry is moved in the database instead of
waiting.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from mediease_api.delivery.http.public_clinics import CLINIC_FIELDS, DOCTOR_FIELDS
from tests.conftest import World
from tests.integration.test_appointments_http import (
    ELEVEN,
    MONDAY,
    TEN,
    _book,
    _code,
    _in_parallel,
    _patient,
    _schedule,
    _send,
    _session,
)
from tests.integration.test_portal_http import portal_csrf
from tests.portal_helpers import PORTAL, portal_client, verify_email

PUBLIC = "/api/v1/public/clinics"
REASON = "synthetic-reason-marker-xyz"
PHONE = "9000000501"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _slug(world: World) -> str:
    return world.a.clinic.slug


def _verified(world: World, db: Engine, n: int = 1) -> FlaskClient:
    email = f"requester{n}@example.test"
    client = portal_client(world, email, name=f"Requester Number{n}")
    verify_email(db, email)
    return client


def _form(world: World, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "clinic_slug": _slug(world),
        "doctor_id": str(world.a.doctor.id),
        "session_start": TEN,
        "contact_phone": PHONE,
        "reason": REASON,
        "not_emergency_ack": True,
    }
    body.update(over)
    return body


def _ask(client: FlaskClient, body: dict[str, Any]) -> TestResponse:
    return client.post(f"{PORTAL}/booking-requests", json=body, headers=portal_csrf(client))


def _scalar(db: Engine, sql: str, **params: object) -> Any:
    with db.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _lapse(db: Engine) -> None:
    """End every hold now, as two hours passing would."""
    with db.begin() as conn:
        conn.execute(
            text("UPDATE booking_requests SET hold_expires_at = now() - interval '1 minute'")
        )


def _held(world: World, client: FlaskClient) -> list[dict[str, Any]]:
    return list(_session(client, world).get("held", []))


# --- The public page (R1-R4, AC2, AC3) -----------------------------------------------------------


def test_ac3_nfr_17_the_public_body_is_an_allow_list(world: World) -> None:
    _schedule(world)
    resp = world.anonymous().get(f"{PUBLIC}/{_slug(world)}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == CLINIC_FIELDS
    assert body["slug"] == _slug(world)
    [doctor] = body["doctors"]
    assert set(doctor) == DOCTOR_FIELDS
    assert {h["weekday"] for h in doctor["hours"]} == {0, 1}
    assert resp.headers["Cache-Control"] == "no-store"
    assert "noindex" in resp.headers["X-Robots-Tag"]


def test_ac2_unknown_onboarding_and_suspended_clinics_give_the_same_404(
    world: World, db: Engine
) -> None:
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinics SET status = 'ONBOARDING' WHERE slug = :s"),
            {"s": world.b.clinic.slug},
        )
    anon = world.anonymous()
    seen = [
        anon.get(f"{PUBLIC}/{slug}")
        for slug in ("no-such-clinic", world.b.clinic.slug, world.suspended_clinic.slug)
    ]
    assert {r.status_code for r in seen} == {404}
    assert len({json.dumps(r.get_json()["error"]["code"]) for r in seen}) == 1
    assert seen[0].get_json()["error"]["code"] == "REQ_NOT_FOUND"
    assert (
        anon.get(
            f"{PUBLIC}/{world.b.clinic.slug}/availability?doctor_id={world.b.doctor.id}"
        ).status_code
        == 404
    )


# --- Availability and the hold (R5-R8, AC4) ------------------------------------------------------


def _offers(world: World, client: FlaskClient | None = None) -> list[dict[str, Any]]:
    c = client or world.anonymous()
    resp = c.get(
        f"{PUBLIC}/{_slug(world)}/availability"
        f"?doctor_id={world.a.doctor.id}&from={MONDAY.isoformat()}"
    )
    assert resp.status_code == 200, resp.get_json()
    day = next((d for d in resp.get_json()["days"] if d["date"] == MONDAY.isoformat()), None)
    return [] if day is None else list(day["sessions"])


def test_r5_availability_is_computed_without_writing(world: World, db: Engine) -> None:
    _schedule(world, capacity=3, mode="TOKENS")
    before = _scalar(db, "SELECT count(*) FROM sessions")
    [session] = _offers(world)
    assert session["places_left"] == 3
    # The 14-day read generates nothing beyond what staff already see.
    assert _scalar(db, "SELECT count(*) FROM booking_requests") == 0
    assert _scalar(db, "SELECT count(*) FROM sessions") >= before


def test_ac1_ac4_a_request_holds_its_place_and_a_lapsed_hold_is_offered_again(
    world: World, db: Engine
) -> None:
    _schedule(world, capacity=1, mode="TOKENS")
    me = _verified(world, db)
    made = _ask(me, _form(world))
    assert made.status_code == 201, made.get_json()
    body = made.get_json()
    assert body["status"] == "REQUESTED"
    assert REASON not in json.dumps(body) and PHONE not in json.dumps(body)

    # The only place is held, so the page offers none.
    assert _offers(world) == []

    # Another person is refused while it is held.
    other = _verified(world, db, 2)
    refused = _ask(other, _form(world, contact_phone="9000000502"))
    assert refused.status_code == 409

    # No job lifts the hold: only time (ADR-0018).
    _lapse(db)
    assert _offers(world)[0]["places_left"] == 1
    assert _ask(other, _form(world, contact_phone="9000000502")).status_code == 201


def test_ac1_two_parallel_requests_for_the_last_place_one_wins(world: World, db: Engine) -> None:
    _schedule(world, capacity=1, mode="TOKENS")
    a, b = _verified(world, db, 1), _verified(world, db, 2)
    results = _in_parallel(
        [
            lambda: _ask(a, _form(world)),
            lambda: _ask(b, _form(world, contact_phone="9000000502")),
        ]
    )
    assert sorted(r.status_code for r in results) == [201, 409]
    assert _scalar(db, "SELECT count(*) FROM booking_requests WHERE status = 'PENDING'") == 1


def test_a_held_slot_is_not_offered_in_slot_mode(world: World, db: Engine) -> None:
    _schedule(world, mode="SLOTS", slot=60)
    me = _verified(world, db)
    made = _ask(me, _form(world, slot_start=ELEVEN))
    assert made.status_code == 201, made.get_json()
    [session] = _offers(world)
    starts = {s["starts_at"] for s in session["slots"]}
    assert datetime.fromisoformat(ELEVEN).astimezone(UTC).isoformat() not in starts
    assert len(starts) == 2


# --- The form (R9-R12) ---------------------------------------------------------------------------


def test_r12_age_and_sex_are_optional_unless_the_clinic_requires_them(
    world: World, db: Engine
) -> None:
    _schedule(world)
    owner = world.client_for(world.a.owner)
    me = _verified(world, db)
    assert _ask(me, _form(world, reason=None, session_start=TEN)).status_code == 201
    assert (
        _send(owner, "PATCH", "/api/v1/clinic", {"request_requires_age_sex": True}).status_code
        == 200
    )
    other = _verified(world, db, 2)
    missing = _ask(other, _form(world, contact_phone="9000000502"))
    assert missing.status_code == 422, missing.get_json()
    full = _ask(other, _form(world, contact_phone="9000000502", age_years=34, sex="FEMALE"))
    assert full.status_code == 201, full.get_json()


def test_r10_the_emergency_acknowledgement_and_a_verified_account_are_required(
    world: World, db: Engine
) -> None:
    _schedule(world)
    me = _verified(world, db)
    assert _ask(me, _form(world, not_emergency_ack=False)).status_code in (400, 422)
    unverified = portal_client(world, "unverified@example.test")
    resp = _ask(unverified, _form(world))
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "PRT_UNVERIFIED_ACCOUNT"
    assert world.anonymous().post(f"{PORTAL}/booking-requests", json=_form(world)).status_code in (
        401,
        403,
    )


# --- Limits (R14, R15, AC6) ----------------------------------------------------------------------


def test_r14_one_open_request_per_account_and_session(world: World, db: Engine) -> None:
    _schedule(world, capacity=5)
    me = _verified(world, db)
    assert _ask(me, _form(world)).status_code == 201
    again = _ask(me, _form(world))
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "PRT_REQUEST_EXISTS"


def test_ac6_the_hourly_limit_answers_429_with_retry_after(world: World, db: Engine) -> None:
    _schedule(world, capacity=50)
    me = _verified(world, db)
    codes = []
    for _ in range(6):
        r = _ask(me, _form(world, session_start=TEN, contact_phone=PHONE))
        codes.append(r.status_code)
    assert 429 in codes
    limited = next(r for r in [_ask(me, _form(world))] if r.status_code == 429)
    assert limited.get_json()["error"]["code"] == "PRT_RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1


# --- Staff: notification, list, held, override (R16-R22, AC5, AC7) -------------------------------


def test_r16_r22_staff_are_told_and_see_the_request_and_the_hold(world: World, db: Engine) -> None:
    _schedule(world, capacity=3)
    me = _verified(world, db)
    assert _ask(me, _form(world, age_years=40, sex="MALE")).status_code == 201

    desk = world.client_for(world.a.desk)
    [item] = desk.get("/api/v1/booking-requests").get_json()["items"]
    assert item["holding"] is True and item["reason"] == REASON
    assert item["full_name"] == "Requester Number1"
    assert item["phone_e164"].endswith(PHONE[-10:])

    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT recipient_user_id, title, link FROM notifications"
                " WHERE kind = 'booking.requested'"
            )
        ).all()
    recipients = {str(r[0]) for r in rows}
    assert str(world.a.owner.id) in recipients and str(world.a.desk.id) in recipients
    assert str(world.a.doctor_user.id) not in recipients
    for r in rows:
        assert REASON not in r[1] and PHONE not in r[1] and "40" not in r[1]

    assert len(_held(world, desk)) == 1
    # Another clinic's staff see nothing (NFR-08).
    assert world.client_for(world.b.desk).get("/api/v1/booking-requests").get_json()["items"] == []


def test_ac7_no_reason_phone_or_age_reaches_audit_or_logs(
    world: World, db: Engine, json_logs: Any
) -> None:
    _schedule(world)
    me = _verified(world, db)
    assert _ask(me, _form(world, age_years=47, sex="MALE")).status_code == 201
    with db.connect() as conn:
        meta = [
            json.dumps(r[0]) for r in conn.execute(text("SELECT metadata FROM audit_events")).all()
        ]
    blob = " ".join(meta)
    assert REASON not in blob and PHONE not in blob
    assert (
        _scalar(db, "SELECT count(*) FROM audit_events WHERE action = 'booking_request.created'")
        == 1
    )
    logged = json.dumps(json_logs())
    assert REASON not in logged and PHONE not in logged


def test_ac5_staff_must_override_a_hold_explicitly_and_it_is_audited(
    world: World, db: Engine
) -> None:
    _schedule(world, capacity=1, mode="TOKENS")
    me = _verified(world, db)
    assert _ask(me, _form(world)).status_code == 201

    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    patient = _patient(desk)
    refused = _book(desk, session["id"], patient)
    assert refused.status_code == 409
    err = refused.get_json()["error"]
    assert err["code"] == "APT_SLOT_HELD"
    assert REASON not in json.dumps(err)

    done = _book(desk, session["id"], patient, override_hold=True)
    assert done.status_code == 201, done.get_json()
    assert _held(world, desk) == []
    assert _scalar(db, "SELECT status FROM booking_requests") == "PENDING"
    assert _scalar(db, "SELECT hold_overridden_by FROM booking_requests") == world.a.desk.id
    assert (
        _scalar(
            db, "SELECT count(*) FROM audit_events WHERE action = 'appointment.hold_overridden'"
        )
        == 1
    )


def test_ac5_a_booking_succeeds_once_the_hold_has_lapsed(world: World, db: Engine) -> None:
    _schedule(world, capacity=1, mode="TOKENS")
    me = _verified(world, db)
    assert _ask(me, _form(world)).status_code == 201
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    _lapse(db)
    done = _book(desk, session["id"], _patient(desk))
    assert done.status_code == 201, done.get_json()
    assert (
        _scalar(
            db, "SELECT count(*) FROM audit_events WHERE action = 'appointment.hold_overridden'"
        )
        == 0
    )


def test_a_held_slot_refuses_a_staff_booking_in_slot_mode_but_other_slots_book(
    world: World, db: Engine
) -> None:
    _schedule(world, mode="SLOTS", slot=60)
    me = _verified(world, db)
    assert _ask(me, _form(world, slot_start=ELEVEN)).status_code == 201
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    held = _book(desk, session["id"], _patient(desk), slot_start=ELEVEN)
    assert held.status_code == 409 and _code(held) == "APT_SLOT_HELD"
    assert _book(desk, session["id"], _patient(desk), slot_start=TEN).status_code == 201
    forced = _book(desk, session["id"], _patient(desk), slot_start=ELEVEN, override_hold=True)
    assert forced.status_code == 201, forced.get_json()


# --- The patient's side (R23, R24) ---------------------------------------------------------------


def test_r23_the_patient_sees_a_request_as_requested_and_nobody_else_does(
    world: World, db: Engine
) -> None:
    _schedule(world)
    me = _verified(world, db)
    assert _ask(me, _form(world)).status_code == 201
    [mine] = me.get(f"{PORTAL}/booking-requests").get_json()["items"]
    assert mine["status"] == "REQUESTED" and mine["clinic_slug"] == _slug(world)
    assert REASON not in json.dumps(mine)
    other = _verified(world, db, 2)
    assert other.get(f"{PORTAL}/booking-requests").get_json()["items"] == []


def test_r26_a_session_holding_a_request_is_not_dropped_by_a_schedule_change(
    world: World, db: Engine
) -> None:
    _schedule(world)
    me = _verified(world, db)
    assert _ask(me, _form(world)).status_code == 201
    owner = world.client_for(world.a.owner)
    resp = _send(
        owner, "PUT", f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule", {"blocks": []}
    )
    assert resp.status_code == 200, resp.get_json()
    assert (
        _scalar(
            db, "SELECT count(*) FROM sessions WHERE id = (SELECT session_id FROM booking_requests)"
        )
        == 1
    )


def test_r20_the_clinic_settings_are_validated(world: World) -> None:
    owner = world.client_for(world.a.owner)
    ok = _send(owner, "PATCH", "/api/v1/clinic", {"request_hold_minutes": 90})
    assert ok.status_code == 200 and ok.get_json()["request_hold_minutes"] == 90
    assert _send(owner, "PATCH", "/api/v1/clinic", {"request_hold_minutes": 5}).status_code == 422
    assert _send(owner, "PATCH", "/api/v1/clinic", {"request_hold_minutes": 600}).status_code == 422
