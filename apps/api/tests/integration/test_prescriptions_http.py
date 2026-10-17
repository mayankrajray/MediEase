"""Prescriptions over HTTP on PostgreSQL (M4-P2; FR-RX-01..03, 06, 09; spec R4-R6, R14, R16, R17).

AC1 (immutable through the API and in the database), AC4 (incomplete doctor), the chain rules
of decisions 1A-2A, concurrency, permissions and AC7 for prescriptions. Visits come from a session
running now (``tests/integration/test_visits_http.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError
from werkzeug.test import TestResponse

from tests.conftest import UowFactory, World
from tests.integration.test_appointments_http import _in_parallel, _patient
from tests.integration.test_visits_http import _move, _send, _start, _started
from tests.sessions_now import running_session

KOLKATA = ZoneInfo("Asia/Kolkata")
SENTINEL = "SENTINEL-rx-91c2"

# PRD §8.6: Syrup X, 5 ml, 1-0-1, after food, 5 days, shake well, dilute in 10 ml water.
SAMPLE_ITEM: dict[str, Any] = {
    "medicine_name": "Syrup X",
    "dose": "5 ml",
    "frequency": "1-0-1",
    "timing": "AFTER_FOOD",
    "duration_days": 5,
    "preparation": [
        {"code": "SHAKE_WELL"},
        {"code": "DILUTE_IN_WATER", "text": "10 ml boiled cooled water"},
    ],
    "storage": [{"code": "ROOM_TEMP"}],
}


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _code(resp: TestResponse) -> str:
    return str(resp.get_json()["error"]["code"])


def _today() -> date:
    from datetime import datetime

    return datetime.now(KOLKATA).date()


def _two_visits(world: World) -> tuple[FlaskClient, dict[str, Any], dict[str, Any]]:
    """Two started visits of the clinic's doctor in one session running now."""
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    session = running_session(owner, world.a.doctor.id)
    visits = []
    for name in ("Asha Rao", "Bina Shah"):
        booked = _send(
            desk,
            "POST",
            "/api/v1/appointments",
            {"session_id": session["id"], "patient_id": _patient(desk, name)},
        )
        appointment = str(booked.get_json()["id"])
        _move(desk, appointment, "BOOKED", "ARRIVED")
        _move(desk, appointment, "ARRIVED", "IN_CONSULTATION")
        started = _start(doctor, appointment)
        assert started.status_code == 201, started.get_json()
        visits.append(started.get_json())
    return doctor, visits[0], visits[1]


def _draft(world: World) -> tuple[FlaskClient, dict[str, Any], dict[str, Any]]:
    doctor, visit = _started(world)
    resp = _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions")
    assert resp.status_code == 201, resp.get_json()
    return doctor, visit, resp.get_json()


def _fill(doctor: FlaskClient, rx: dict[str, Any], **body: Any) -> TestResponse:
    payload = {
        "revision": rx["revision"],
        "items": [SAMPLE_ITEM],
        "advice": {"diet": ["plenty of fluids"], "return_if": ["breathing is difficult"]},
        "follow_up_date": (_today() + timedelta(days=5)).isoformat(),
        **body,
    }
    return _send(doctor, "PUT", f"/api/v1/prescriptions/{rx['id']}", payload)


def _issued(world: World) -> tuple[FlaskClient, dict[str, Any], dict[str, Any]]:
    doctor, visit, rx = _draft(world)
    filled = _fill(doctor, rx).get_json()
    resp = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert resp.status_code == 200, resp.get_json()
    assert filled["revision"] == 2
    return doctor, visit, resp.get_json()


def _audit(db: Engine, *actions: str) -> list[tuple[str, dict[str, Any]]]:
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, metadata FROM audit_events WHERE action = ANY(:a)"
                " ORDER BY occurred_at, id"
            ),
            {"a": list(actions)},
        ).all()
    return [(r[0], r[1]) for r in rows]


# --- Drafts (decisions 1A, 3A) -------------------------------------------------------------------


def test_fr_rx_01_a_visit_gets_one_draft_saved_whole_with_its_revision(
    world: World, db: Engine
) -> None:
    doctor, visit, rx = _draft(world)
    assert (rx["version"], rx["status"], rx["revision"], rx["items"]) == (1, "DRAFT", 1, [])
    again = _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions")
    assert (again.status_code, _code(again)) == (409, "RX_ALREADY_EXISTS")
    assert again.get_json()["error"]["details"] == {"prescription_id": rx["id"]}

    saved = _fill(doctor, rx)
    assert saved.status_code == 200, saved.get_json()
    body = saved.get_json()
    [item] = body["items"]
    assert (item["medicine_name"], item["frequency"], item["timing"], item["position"]) == (
        "Syrup X",
        "1-0-1",
        "AFTER_FOOD",
        1,
    )
    assert item["preparation"][1] == {
        "code": "DILUTE_IN_WATER",
        "text": "10 ml boiled cooled water",
    }
    assert body["advice"]["return_if"] == ["breathing is difficult"]
    stale = _fill(doctor, rx)
    assert (stale.status_code, _code(stale)) == (409, "RX_STALE")
    assert stale.get_json()["error"]["details"] == {"revision": "2"}

    bad = _fill(doctor, body, items=[{**SAMPLE_ITEM, "frequency": "CUSTOM"}])
    assert (bad.status_code, _code(bad)) == (422, "REQ_VALIDATION_FAILED")
    assert bad.get_json()["error"]["details"]["fields"][0]["field"] == "items.0.frequency_text"
    phrase = _fill(doctor, body, items=[{**SAMPLE_ITEM, "storage": [{"code": "FREEZE"}]}])
    assert (phrase.status_code, _code(phrase)) == (422, "REQ_VALIDATION_FAILED")
    past = _fill(doctor, body, follow_up_date=_today().isoformat())
    assert past.get_json()["error"]["details"]["fields"][0]["field"] == "follow_up_date"

    updates = [m for _, m in _audit(db, "prescription.updated")]
    assert updates == [{"visit_id": visit["id"], "version": "1", "revision": "2", "items": "1"}]


def test_a_draft_can_be_discarded_but_never_an_issued_version(world: World) -> None:
    doctor, visit, _ = _two_visits(world)
    rx = _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions").get_json()
    gone = _send(doctor, "DELETE", f"/api/v1/prescriptions/{rx['id']}")
    assert gone.status_code == 204
    assert doctor.get(f"/api/v1/prescriptions/{rx['id']}").status_code == 404
    fresh = _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions").get_json()
    assert fresh["version"] == 1

    _fill(doctor, fresh)
    assert (
        _send(doctor, "POST", f"/api/v1/prescriptions/{fresh['id']}/issue", {"revision": 2})
    ).status_code == 200
    refused = _send(doctor, "DELETE", f"/api/v1/prescriptions/{fresh['id']}")
    assert (refused.status_code, _code(refused)) == (409, "RX_NOT_DRAFT")


# --- Issue (R4, R5, R14, R20, AC1, AC4) ----------------------------------------------------------


def test_r5_issuing_freezes_the_prescription_with_what_is_printed(world: World, db: Engine) -> None:
    doctor, visit, rx = _issued(world)
    assert (rx["status"], rx["version"], rx["language"]) == ("ISSUED", 1, "en")
    assert rx["doctor_snapshot"]["display_name"] == world.a.doctor.display_name
    assert rx["doctor_snapshot"]["registration_number"] == world.a.doctor.registration_number
    assert rx["clinic_snapshot"]["name"] == world.a.clinic.name
    # The synthetic patients of the visit tests gave no consent: nothing will be sent (R14).
    assert rx["link_delivery"] == "NOT_CONSENTED"
    assert [v["status"] for v in rx["versions"]] == ["ISSUED"]

    edit = _fill(doctor, rx)
    assert (edit.status_code, _code(edit)) == (409, "RX_NOT_DRAFT")  # AC1
    again = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 3})
    assert (again.status_code, _code(again)) == (409, "RX_NOT_DRAFT")
    [(_, meta)] = _audit(db, "prescription.issued")
    assert meta == {
        "visit_id": visit["id"],
        "version": "1",
        "items": "1",
        "language": "en",
        "link_delivery": "NOT_CONSENTED",
    }


def test_r14_a_consenting_patient_gets_a_pending_link(world: World, db: Engine) -> None:
    doctor, visit, rx = _draft(world)
    desk = world.client_for(world.a.desk)
    consent = _send(
        desk,
        "PUT",
        f"/api/v1/patients/{visit['patient_id']}/consent",
        {"whatsapp": True, "sms": False},
    )
    assert consent.status_code == 200, consent.get_json()
    _fill(doctor, rx)
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert issued.get_json()["link_delivery"] == "PENDING"
    with db.connect() as conn:
        requested = conn.execute(
            text("SELECT link_delivery_requested_at = issued_at FROM prescriptions WHERE id = :i"),
            {"i": rx["id"]},
        ).scalar()
    assert requested is True


def test_r4_empty_and_ac4_incomplete_doctor_are_refused(world: World, db: Engine) -> None:
    doctor, _, rx = _draft(world)
    empty = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 1})
    assert (empty.status_code, _code(empty)) == (422, "RX_EMPTY")

    _fill(doctor, rx)
    with db.begin() as conn:  # data imported or corrected outside the app (I3 guard)
        conn.execute(
            text("UPDATE doctors SET registration_number = '  ' WHERE id = :d"),
            {"d": str(world.a.doctor.id)},
        )
    incomplete = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert (incomplete.status_code, _code(incomplete)) == (422, "RX_DOCTOR_INCOMPLETE")
    assert incomplete.get_json()["error"]["details"] == {"fields": "registration_number"}
    assert doctor.get(f"/api/v1/prescriptions/{rx['id']}").get_json()["status"] == "DRAFT"


def test_ac1_the_database_refuses_changes_to_an_issued_prescription(
    world: World, db: Engine
) -> None:
    _, _, rx = _issued(world)
    rid = {"i": rx["id"]}
    refused = [
        ("UPDATE prescriptions SET advice = '{}' WHERE id = :i", rid),
        ("UPDATE prescriptions SET follow_up_date = NULL WHERE id = :i", rid),
        ("UPDATE prescriptions SET status = 'DRAFT' WHERE id = :i", rid),
        ("UPDATE prescriptions SET link_delivery = 'PENDING' WHERE id = :i", rid),
        ("DELETE FROM prescriptions WHERE id = :i", rid),
        ("UPDATE prescription_items SET dose = '50 ml' WHERE prescription_id = :i", rid),
        ("DELETE FROM prescription_items WHERE prescription_id = :i", rid),
        (
            "INSERT INTO prescription_items (id, clinic_id, prescription_id, position,"
            " medicine_name) SELECT gen_random_uuid(), clinic_id, id, 9, 'Tab Z'"
            " FROM prescriptions WHERE id = :i",
            rid,
        ),
        ("TRUNCATE prescription_items", {}),
    ]
    for statement, params in refused:
        with pytest.raises(DBAPIError, match="RX_NOT_DRAFT"), db.begin() as conn:
            conn.execute(text(statement), params)

    # The operational columns move only forward, once.
    with db.begin() as conn:
        conn.execute(
            text("UPDATE prescriptions SET pdf_object_key = 'rx/k/v1.pdf' WHERE id = :i"), rid
        )
    with pytest.raises(DBAPIError, match="RX_NOT_DRAFT"), db.begin() as conn:
        conn.execute(text("UPDATE prescriptions SET pdf_object_key = 'other' WHERE id = :i"), rid)
    with db.begin() as conn:
        conn.execute(text("UPDATE prescriptions SET status = 'SUPERSEDED' WHERE id = :i"), rid)


# --- Revise and supersede (R6, decision 2A) ------------------------------------------------------


def test_r6_a_revision_supersedes_the_issued_version(world: World, db: Engine) -> None:
    doctor, visit, v1 = _issued(world)
    revised = _send(doctor, "POST", f"/api/v1/prescriptions/{v1['id']}/revise")
    assert revised.status_code == 201, revised.get_json()
    v2 = revised.get_json()
    assert (v2["version"], v2["supersedes_id"], v2["status"], v2["revision"]) == (
        2,
        v1["id"],
        "DRAFT",
        1,
    )
    assert [i["medicine_name"] for i in v2["items"]] == ["Syrup X"]
    twice = _send(doctor, "POST", f"/api/v1/prescriptions/{v1['id']}/revise")
    assert (twice.status_code, _code(twice)) == (409, "RX_DRAFT_EXISTS")
    assert twice.get_json()["error"]["details"] == {"prescription_id": v2["id"]}

    changed = _fill(doctor, v2, items=[{**SAMPLE_ITEM, "dose": "2.5 ml"}])
    assert changed.status_code == 200
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{v2['id']}/issue", {"revision": 2})
    assert issued.status_code == 200, issued.get_json()
    assert [(v["version"], v["status"]) for v in issued.get_json()["versions"]] == [
        (1, "SUPERSEDED"),
        (2, "ISSUED"),
    ]
    old = doctor.get(f"/api/v1/prescriptions/{v1['id']}").get_json()
    assert (old["status"], old["items"][0]["dose"]) == ("SUPERSEDED", "5 ml")  # never rewritten

    stale = _send(doctor, "POST", f"/api/v1/prescriptions/{v1['id']}/revise")
    assert (stale.status_code, _code(stale)) == (409, "RX_NOT_LATEST")
    assert stale.get_json()["error"]["details"] == {"latest_id": v2["id"]}
    [(_, meta)] = _audit(db, "prescription.revised")
    assert meta == {"visit_id": visit["id"], "version": "2", "from_id": v1["id"]}


def test_decision_2a_version_1_stops_at_the_lock_but_revisions_do_not(
    world: World, db: Engine
) -> None:
    doctor, visit, other_visit = _two_visits(world)
    rx = _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions").get_json()
    _fill(doctor, rx)
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert issued.status_code == 200
    assert _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/complete").status_code == 200
    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE visits SET completed_at = now() - interval '25 hours',"
                " locked_at = now() - interval '1 hour' WHERE id = :id"
            ),
            {"id": visit["id"]},
        )
    revised = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise")
    assert revised.status_code == 201, revised.get_json()
    v2 = revised.get_json()
    assert _fill(doctor, v2).status_code == 200
    assert (
        _send(
            doctor, "POST", f"/api/v1/prescriptions/{v2['id']}/issue", {"revision": 2}
        ).status_code
        == 200
    )

    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE visits SET status = 'COMPLETED',"
                " completed_at = now() - interval '25 hours',"
                " locked_at = now() - interval '1 hour' WHERE id = :id"
            ),
            {"id": other_visit["id"]},
        )
    late = _send(doctor, "POST", f"/api/v1/visits/{other_visit['id']}/prescriptions")
    assert (late.status_code, _code(late)) == (409, "VIS_LOCKED")


# --- Concurrency ---------------------------------------------------------------------------------


def test_two_issues_and_two_revisions_at_once_each_give_one_result(world: World) -> None:
    doctor, _, rx = _draft(world)
    _fill(doctor, rx)
    url = f"/api/v1/prescriptions/{rx['id']}/issue"
    issues = _in_parallel([lambda: _send(doctor, "POST", url, {"revision": 2})] * 2)
    assert sorted(r.status_code for r in issues) == [200, 409]

    revise = f"/api/v1/prescriptions/{rx['id']}/revise"
    revisions = _in_parallel([lambda: _send(doctor, "POST", revise)] * 2)
    assert sorted(r.status_code for r in revisions) == [201, 409]
    loser = next(r for r in revisions if r.status_code == 409)
    assert _code(loser) == "RX_DRAFT_EXISTS"


def test_two_new_prescription_clicks_make_one_draft(world: World) -> None:
    doctor, visit = _started(world)
    url = f"/api/v1/visits/{visit['id']}/prescriptions"
    results = _in_parallel([lambda: _send(doctor, "POST", url)] * 2)
    assert sorted(r.status_code for r in results) == [201, 409]


# --- Reads, permissions, audit (R16, R17, spec §2) -----------------------------------------------


def test_r16_reads_write_one_row_and_the_consultation_view_shows_the_chain(
    world: World, db: Engine
) -> None:
    doctor, visit, rx = _issued(world)
    owner = world.client_for(world.a.owner)
    read = owner.get(f"/api/v1/prescriptions/{rx['id']}")
    assert read.status_code == 200 and read.headers["Cache-Control"] == "no-store"
    assert len(_audit(db, "prescription.viewed")) == 1

    before = len(_audit(db, "visit.viewed", "prescription.viewed"))
    view = doctor.get(f"/api/v1/visits/{visit['id']}").get_json()
    assert [p["id"] for p in view["prescriptions"]] == [rx["id"]]
    assert len(_audit(db, "visit.viewed", "prescription.viewed")) == before + 1


def test_d4_front_desk_never_sees_or_writes_a_prescription(world: World) -> None:
    _, visit, rx = _issued(world)
    desk = world.client_for(world.a.desk)
    one = f"/api/v1/prescriptions/{rx['id']}"
    for method, url, body in (
        ("POST", f"/api/v1/visits/{visit['id']}/prescriptions", None),
        ("GET", one, None),
        ("PUT", one, {"revision": 1}),
        ("DELETE", one, None),
        ("POST", f"{one}/issue", {"revision": 1}),
        ("POST", f"{one}/revise", None),
    ):
        resp = _send(desk, method, url, body)
        assert (resp.status_code, _code(resp)) == (403, "PERM_DENIED"), (method, url)


def test_only_the_visits_doctor_writes(world: World, uow_factory: UowFactory) -> None:
    from tests.builders import a_doctor

    _, _, rx = _draft(world)
    with uow_factory() as uow:
        uow.tenant(world.a.clinic.id).doctors.add(
            a_doctor(world.a.clinic.id, user_id=world.a.owner.id)
        )
        uow.commit()
    owner_doctor = world.client_for(world.a.owner)
    resp = _send(owner_doctor, "PUT", f"/api/v1/prescriptions/{rx['id']}", {"revision": 1})
    assert (resp.status_code, _code(resp)) == (403, "VIS_NOT_YOURS")


def test_r17_prescription_text_never_reaches_logs_audit_or_errors(
    world: World, db: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    doctor, _, rx = _draft(world)
    capsys.readouterr()
    item = {
        **SAMPLE_ITEM,
        "medicine_name": f"{SENTINEL} syrup",
        "warnings": f"{SENTINEL} warning",
        "notes": f"{SENTINEL} notes",
    }
    advice = {"diet": [f"{SENTINEL} diet"], "notes": f"{SENTINEL} advice"}
    assert _fill(doctor, rx, items=[item], advice=advice).status_code == 200
    too_long = _fill(doctor, {**rx, "revision": 2}, items=[{**item, "dose": SENTINEL * 20}])
    assert too_long.status_code == 422
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert issued.status_code == 200
    doctor.get(f"/api/v1/prescriptions/{rx['id']}")
    _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise")

    logged = capsys.readouterr().out
    assert SENTINEL not in logged and "prescription.issued" in logged
    assert SENTINEL not in str(too_long.get_json())
    with db.connect() as conn:
        leaked = conn.execute(
            text("SELECT count(*) FROM audit_events WHERE metadata::text LIKE :s"),
            {"s": f"%{SENTINEL}%"},
        ).scalar()
    assert leaked == 0
