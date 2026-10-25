"""Answering booking requests over HTTP (M6b-P5; spec booking-requests R31-R50, AC9-AC16).

Real PostgreSQL, the real composition root. Times come from the clinic's own availability
(``tests/booking_helpers.py``); deadlines are moved in the database instead of waiting.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.application.booking.expiry import ExpireBookingRequests, SweepRequestExpiry
from mediease_api.domain.jobs.job import EXPIRE_REQUESTS_KIND, ClaimedJob
from tests.booking_helpers import (
    ask,
    ensure_schedule,
    offers,
    propose,
    request_in,
    staff_post,
    verified_client,
)
from tests.conftest import UowFactory, World
from tests.integration.test_appointments_http import _in_parallel
from tests.integration.test_portal_http import portal_csrf
from tests.portal_helpers import PORTAL, link_by_invite

STAFF = "/api/v1/booking-requests"
NEW = {"new_patient": {"sex": "FEMALE", "age_years": 34}}
NOTE = "synthetic-staff-note-marker"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _scalar(db: Engine, sql: str, **params: object) -> Any:
    with db.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _column(db: Engine, sql: str) -> list[Any]:
    with db.connect() as conn:
        return list(conn.execute(text(sql)).scalars())


def _row(db: Engine, query: Any, params: dict[str, object]) -> Any:
    with db.connect() as conn:
        return conn.execute(query, params).one()


def _desk(world: World) -> FlaskClient:
    return world.client_for(world.a.desk)


def _code(resp: Any) -> str:
    return str(resp.get_json()["error"]["code"])


def _mine(client: FlaskClient) -> list[dict[str, Any]]:
    return list(client.get(f"{PORTAL}/booking-requests").get_json()["items"])


# --- Accept (R34-R38, AC9-AC12) ------------------------------------------------------------------


def test_ac9_accept_with_a_new_record_books_links_and_the_patient_sees_it(
    world: World, db: Engine
) -> None:
    patient, rid = request_in(world, world.a, "accept.new@example.test")
    accepted = staff_post(_desk(world), f"{STAFF}/{rid}/accept", NEW)
    assert accepted.status_code == 201, accepted.get_json()
    body = accepted.get_json()
    assert body["status"] == "ACCEPTED" and body["appointment_id"]

    assert _scalar(
        db, "SELECT source FROM appointments WHERE id = :i", i=body["appointment_id"]
    ) == ("PUBLIC_PAGE")
    assert (
        _scalar(
            db,
            "SELECT method FROM patient_account_links WHERE patient_id = :p AND revoked_at IS NULL",
            p=body["patient_id"],
        )
        == "BOOKING"
    )
    # The patient now sees the appointment under the clinic, and no longer the request.
    groups = patient.get(f"{PORTAL}/appointments").get_json()["items"]
    assert [a["id"] for g in groups for a in g["appointments"]] == [body["appointment_id"]]
    assert _mine(patient) == []
    actions = set(_column(db, "SELECT action FROM audit_events"))
    assert {"booking_request.accepted", "appointment.booked", "patient.portal_linked"} <= actions


def test_ac10_accept_excludes_its_own_hold_but_another_patients_hold_still_counts(
    world: World, db: Engine
) -> None:
    owner = world.client_for(world.a.owner)
    ensure_schedule(world, world.a)
    # A one-place-free session: the first offered session, with capacity filled but two.
    first = offers(world, world.a)[0]
    a = verified_client(world, "hold.a@example.test")
    b = verified_client(world, "hold.b@example.test")
    ra = ask(a, world.a, first, phone="9000000781")
    rb = ask(b, world.a, first, phone="9000000782", slot=1 if first["slots"] else 0)
    assert ra.status_code == 201 and rb.status_code == 201
    assert owner is not None
    accepted = staff_post(_desk(world), f"{STAFF}/{ra.get_json()['id']}/accept", NEW)
    assert accepted.status_code == 201, accepted.get_json()
    still = _scalar(
        db,
        "SELECT count(*) FROM booking_requests WHERE id = :i AND status = 'PENDING'"
        " AND hold_expires_at > now()",
        i=rb.get_json()["id"],
    )
    assert still == 1


def test_ac11_two_staff_answer_at_once_exactly_one_wins(world: World, db: Engine) -> None:
    _, rid = request_in(world, world.a, "race@example.test")
    desk, owner = _desk(world), world.client_for(world.a.owner)
    results = _in_parallel(
        [
            lambda: staff_post(desk, f"{STAFF}/{rid}/accept", NEW),
            lambda: staff_post(owner, f"{STAFF}/{rid}/accept", NEW),
        ]
    )
    assert sorted(r.status_code for r in results) == [201, 409]
    loser = next(r for r in results if r.status_code == 409)
    assert _code(loser) == "BKG_ALREADY_ANSWERED"
    assert _scalar(db, "SELECT count(*) FROM appointments WHERE source = 'PUBLIC_PAGE'") == 1
    # A later decline of the same request is refused too (R31a).
    late = staff_post(desk, f"{STAFF}/{rid}/decline", {"reason": "OTHER"})
    assert (late.status_code, _code(late)) == (409, "BKG_ALREADY_ANSWERED")


def test_ac12_a_record_linked_to_another_account_is_refused(world: World, db: Engine) -> None:
    owner = world.client_for(world.a.owner)
    other = verified_client(world, "already.linked@example.test")
    made = staff_post(
        owner,
        "/api/v1/patients",
        {"full_name": "Linked Elsewhere", "phone": "9000000790", "sex": "MALE", "age_years": 40},
    )
    assert made.status_code == 201, made.get_json()
    record = made.get_json()["id"]
    link_by_invite(owner, other, record)

    _, rid = request_in(world, world.a, "wants.that.record@example.test")
    refused = staff_post(_desk(world), f"{STAFF}/{rid}/accept", {"patient_id": record})
    assert (refused.status_code, _code(refused)) == (409, "PRT_ALREADY_LINKED")
    assert _scalar(db, "SELECT status FROM booking_requests WHERE id = :i", i=rid) == "PENDING"
    assert _scalar(db, "SELECT count(*) FROM appointments WHERE source = 'PUBLIC_PAGE'") == 0


def test_r36_r47_candidates_by_phone_with_the_no_show_count(world: World, db: Engine) -> None:
    owner = world.client_for(world.a.owner)
    made = staff_post(
        owner,
        "/api/v1/patients",
        {"full_name": "Same Phone", "phone": "9000000777", "sex": "FEMALE", "age_years": 33},
    )
    assert made.status_code == 201
    _, rid = request_in(world, world.a, "candidates@example.test", age_years=33, sex="FEMALE")
    resp = _desk(world).get(f"{STAFF}/{rid}/candidates")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["linked"] is False
    [item] = body["items"]
    assert item["code"] and item["no_shows"] == 0
    assert body["suggested"] == {"full_name": "Asha Patient", "age_years": 33, "sex": "FEMALE"}


def test_r37_a_new_record_needs_sex_when_the_patient_gave_none(world: World) -> None:
    _, rid = request_in(world, world.a, "no.sex@example.test")
    resp = staff_post(_desk(world), f"{STAFF}/{rid}/accept", {"new_patient": {"age_years": 30}})
    assert resp.status_code == 422, resp.get_json()
    neither = staff_post(_desk(world), f"{STAFF}/{rid}/accept", {})
    assert neither.status_code == 422


# --- Decline (R39, R50, AC13) --------------------------------------------------------------------


def test_ac13_decline_frees_the_slot_shows_the_reason_and_never_the_note(
    world: World, db: Engine, json_logs: Any
) -> None:
    patient, rid = request_in(world, world.a, "decline@example.test")
    resp = staff_post(
        _desk(world), f"{STAFF}/{rid}/decline", {"reason": "PLEASE_CALL", "note": NOTE}
    )
    assert resp.status_code == 200, resp.get_json()
    assert _scalar(db, "SELECT hold_expires_at <= now() FROM booking_requests WHERE id = :i", i=rid)
    [mine] = _mine(patient)
    assert mine["status"] == "DECLINED" and mine["decline_reason"] == "PLEASE_CALL"
    assert NOTE not in json.dumps(patient.get(f"{PORTAL}/booking-requests").get_json())
    with db.connect() as conn:
        audit = json.dumps([r[0] for r in conn.execute(text("SELECT metadata FROM audit_events"))])
    assert NOTE not in audit
    assert NOTE not in json.dumps(json_logs())
    # Staff see their note on the answered list.
    [answered] = _desk(world).get(f"{STAFF}?state=answered").get_json()["items"]
    assert answered["decline_note"] == NOTE and answered["status"] == "DECLINED"


def test_r39_the_patients_own_reason_is_not_a_staff_choice(world: World) -> None:
    _, rid = request_in(world, world.a, "bad.reason@example.test")
    resp = staff_post(_desk(world), f"{STAFF}/{rid}/decline", {"reason": "PATIENT_DECLINED"})
    assert resp.status_code == 422


# --- Propose (R40-R43, AC14) ---------------------------------------------------------------------


def test_ac14_propose_then_the_patient_accepts_one_appointment_at_the_new_time(
    world: World, db: Engine
) -> None:
    patient, rid = request_in(world, world.a, "propose.yes@example.test")
    original = _scalar(db, "SELECT session_id FROM booking_requests WHERE id = :i", i=rid)
    first = offers(world, world.a)[0]
    proposed = propose(world, world.a, rid, first["starts_at"])
    assert proposed.status_code == 200, proposed.get_json()
    row = _row(
        db,
        text("SELECT status, session_id, original_session_id FROM booking_requests WHERE id = :i"),
        {"i": rid},
    )
    assert row.status == "PROPOSED" and row.original_session_id == original
    assert row.session_id != original
    [mine] = _mine(patient)
    assert mine["status"] == "PROPOSED" and mine["original_starts_at"] is not None

    taken = patient.post(
        f"{PORTAL}/booking-requests/{rid}/accept-proposal", headers=portal_csrf(patient)
    )
    assert taken.status_code == 200, taken.get_json()
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM appointments WHERE session_id = :s AND source = 'PUBLIC_PAGE'",
            s=row.session_id,
        )
        == 1
    )
    assert _scalar(db, "SELECT count(*) FROM appointments WHERE session_id = :s", s=original) == 0
    assert _scalar(db, "SELECT count(*) FROM patient_account_links WHERE method = 'BOOKING'") == 1
    # Staff cannot also answer it now.
    again = staff_post(_desk(world), f"{STAFF}/{rid}/decline", {"reason": "OTHER"})
    assert again.status_code == 409


def test_r43_no_thanks_is_declined_and_frees_the_proposed_time(world: World, db: Engine) -> None:
    patient, rid = request_in(world, world.a, "propose.no@example.test")
    first = offers(world, world.a)[0]
    assert propose(world, world.a, rid, first["starts_at"]).status_code == 200
    resp = patient.post(
        f"{PORTAL}/booking-requests/{rid}/decline-proposal", headers=portal_csrf(patient)
    )
    assert resp.status_code == 200, resp.get_json()
    row = _row(
        db,
        text(
            "SELECT status, decline_reason, hold_expires_at <= now() AS ended"
            " FROM booking_requests WHERE id = :i"
        ),
        {"i": rid},
    )
    assert (row.status, row.decline_reason, row.ended) == ("DECLINED", "PATIENT_DECLINED", True)
    # A second No thanks, or a Yes after it, is refused.
    late = patient.post(
        f"{PORTAL}/booking-requests/{rid}/accept-proposal", headers=portal_csrf(patient)
    )
    assert (late.status_code, _code(late)) == (409, "BKG_ALREADY_ANSWERED")


def test_r41_a_proposal_is_made_once_and_the_patient_cannot_answer_a_pending_request(
    world: World,
) -> None:
    patient, rid = request_in(world, world.a, "propose.once@example.test")
    early = patient.post(
        f"{PORTAL}/booking-requests/{rid}/accept-proposal", headers=portal_csrf(patient)
    )
    assert (early.status_code, _code(early)) == (409, "BKG_ALREADY_ANSWERED")
    first = offers(world, world.a)[0]
    assert propose(world, world.a, rid, first["starts_at"]).status_code == 200
    twice = propose(world, world.a, rid, first["starts_at"])
    assert (twice.status_code, _code(twice)) == (409, "BKG_ALREADY_ANSWERED")


# --- Expiry (R32, AC15) and counts (R45, R46, AC16) ----------------------------------------------


def _overdue(db: Engine, rid: str) -> None:
    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE booking_requests SET hold_expires_at = now() - interval '2 minutes',"
                " respond_by = now() - interval '1 minute' WHERE id = :i"
            ),
            {"i": rid},
        )


def test_ac15_an_overdue_request_is_expired_before_and_after_the_sweep(
    world: World, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rid = request_in(world, world.a, "expire@example.test")
    _overdue(db, rid)
    late = staff_post(_desk(world), f"{STAFF}/{rid}/accept", NEW)
    assert (late.status_code, _code(late)) == (409, "BKG_ALREADY_ANSWERED")
    assert _mine(patient)[0]["status"] == "EXPIRED"  # read as expired before the sweep
    assert _desk(world).get(STAFF).get_json()["items"] == []

    clock, ids = SystemClock(), Uuid7Generator()
    SweepRequestExpiry(uow=uow_factory(), clock=clock, ids=ids)(_job(None))
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM jobs WHERE kind = :k AND clinic_id = :c",
            k=EXPIRE_REQUESTS_KIND,
            c=world.a.clinic.id,
        )
        == 1
    )
    ExpireBookingRequests(uow=uow_factory(), clock=clock, ids=ids)(_job(world.a.clinic.id))
    ExpireBookingRequests(uow=uow_factory(), clock=clock, ids=ids)(_job(world.a.clinic.id))
    assert _scalar(db, "SELECT status FROM booking_requests WHERE id = :i", i=rid) == "EXPIRED"
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM audit_events WHERE action = 'booking_request.expired'"
            " AND actor_type = 'SYSTEM'",
        )
        == 1
    )


def _job(clinic_id: Any) -> ClaimedJob:
    return ClaimedJob(
        id=uuid4(),
        kind="test",
        clinic_id=clinic_id,
        payload={},
        attempts=1,
        max_attempts=5,
        request_id=None,
        locked_by="test",
    )


def test_ac16_inbox_counts_and_the_owners_response_rate(world: World, db: Engine) -> None:
    _, answered = request_in(world, world.a, "count.1@example.test")
    _, expired = request_in(world, world.a, "count.2@example.test", phone="9000000791")
    _, waiting = request_in(world, world.a, "count.3@example.test", phone="9000000792")
    assert (
        staff_post(_desk(world), f"{STAFF}/{answered}/decline", {"reason": "OTHER"}).status_code
        == 200
    )
    _overdue(db, expired)

    inbox = _desk(world).get(STAFF).get_json()
    assert [i["id"] for i in inbox["items"]] == [waiting]
    assert (inbox["open_count"], inbox["expired_7d"]) == (1, 1)
    owner_today = world.client_for(world.a.owner).get("/api/v1/dashboard/today").get_json()
    assert owner_today["booking_requests_open"] == 1
    assert (owner_today["requests_answered_30d"], owner_today["requests_expired_30d"]) == (1, 1)
    desk_today = _desk(world).get("/api/v1/dashboard/today").get_json()
    assert desk_today["booking_requests_open"] == 1
    assert desk_today["requests_answered_30d"] is None


def test_nfr_08_another_clinics_staff_cannot_list_or_answer(world: World) -> None:
    _, rid = request_in(world, world.a, "tenancy@example.test")
    beta = world.client_for(world.b.desk)
    assert beta.get(STAFF).get_json()["items"] == []
    resp = staff_post(beta, f"{STAFF}/{rid}/decline", {"reason": "OTHER"})
    assert resp.status_code == 404
