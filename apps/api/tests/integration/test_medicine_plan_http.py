"""The medicine planner over HTTP on PostgreSQL (M6b-P3).

Prescriptions R21-R25 (the editor's patterns, warnings, duration kinds, start day, vocabulary);
patient portal R28-R44 (the plan, courses, slot times and reminder choices) and AC13-AC17.
Synthetic data only.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import World
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_prescriptions_http import (
    SAMPLE_ITEM,
    _code,
    _draft,
    _fill,
    _today,
)
from tests.integration.test_visits_http import _send
from tests.portal_helpers import PORTAL, link_by_invite, portal_client

EMAIL = "planner.patient@example.test"
SENTINEL = "SENTINEL-plan-5e1a"

TABLET: dict[str, Any] = {
    "medicine_name": f"Tab Sample {SENTINEL}",
    "dose": "1 tablet",
    "frequency": "110",
    "timing": "AFTER_FOOD",
    "duration_kind": "DAYS",
    "duration_days": 5,
    "preparation": [{"code": "WITH_WATER"}],
}
AS_NEEDED: dict[str, Any] = {
    "medicine_name": "Syrup Sample",
    "dose": "5 ml",
    "frequency": "SOS",
    "duration_kind": "ONGOING",
}


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _issue(
    doctor: FlaskClient, rx: dict[str, Any], items: list[dict[str, Any]], **body: Any
) -> Any:
    filled = _fill(doctor, rx, items=items, **body)
    assert filled.status_code == 200, filled.get_json()
    issued = _send(
        doctor,
        "POST",
        f"/api/v1/prescriptions/{rx['id']}/issue",
        {"revision": filled.get_json()["revision"]},
    )
    assert issued.status_code == 200, issued.get_json()
    return issued.get_json()


def _planned(world: World, **body: Any) -> tuple[FlaskClient, FlaskClient, dict[str, Any]]:
    """An issued prescription (Tab 1-1-0 after food for 5 days; Syrup SOS) and a linked account."""
    doctor, visit, rx = _draft(world)
    issued = _issue(doctor, rx, [TABLET, AS_NEEDED], **body)
    patient = portal_client(world, EMAIL)
    link_by_invite(world.client_for(world.a.owner), patient, visit["patient_id"])
    return doctor, patient, issued


# --- The editor's side (prescriptions R21-R25) ---------------------------------------------------


def test_r21_any_binary_pattern_is_saved_canonical_with_its_slots(world: World) -> None:
    doctor, _, rx = _draft(world)
    items = [
        {"medicine_name": "A", "frequency": "110"},
        {"medicine_name": "B", "frequency": "1 0 1 1"},
        {"medicine_name": "C", "frequency": "0-0-1-0"},
        {"medicine_name": "D", "frequency": "sos"},
    ]
    saved = _fill(doctor, rx, items=items)
    assert saved.status_code == 200, saved.get_json()
    got = [(i["frequency"], i["slots"]) for i in saved.get_json()["items"]]
    assert got == [
        ("1-1-0", ["MORNING", "AFTERNOON"]),
        ("1-0-1-1", ["MORNING", "EVENING", "NIGHT"]),
        ("0-0-1-0", ["EVENING"]),
        ("SOS", []),
    ]


@pytest.mark.parametrize("raw", ["0-0-0", "0000", "2-0-2", "½-0-½", "1-0", "1-0-1-0-1", "BD"])
def test_r21_other_patterns_are_refused_on_the_line(world: World, raw: str) -> None:
    doctor, _, rx = _draft(world)
    resp = _fill(doctor, rx, items=[SAMPLE_ITEM, {"medicine_name": "X", "frequency": raw}])
    assert (resp.status_code, _code(resp)) == (422, "REQ_VALIDATION_FAILED")
    assert "items.1.frequency" in str(resp.get_json()["error"])


def test_r22_bedtime_warnings_never_block_issuing(world: World) -> None:
    doctor, _, rx = _draft(world)
    items = [
        {"medicine_name": "A", "frequency": "1-0-0", "timing": "BEDTIME"},
        {"medicine_name": "B", "frequency": "1-0-1", "timing": "BEDTIME"},
        {"medicine_name": "C", "frequency": "0-0-1", "timing": "BEDTIME"},
        {"medicine_name": "D", "frequency": "SOS", "timing": "BEDTIME"},
    ]
    issued = _issue(doctor, rx, items)
    assert [i["line_warnings"] for i in issued["items"]] == [
        ["BEDTIME_WITHOUT_NIGHT"],
        ["BEDTIME_WITH_OTHER_SLOTS"],
        [],
        ["BEDTIME_UNTIMED"],
    ]
    # Shown as written: the line keeps its slots and its bedtime.
    assert (issued["items"][0]["slots"], issued["items"][0]["timing"]) == (["MORNING"], "BEDTIME")


def test_r23_duration_kinds_and_days_go_together(world: World) -> None:
    doctor, _, rx = _draft(world)
    items = [
        {"medicine_name": "A", "duration_days": 5},
        {"medicine_name": "B", "duration_kind": "UNTIL_REVIEW"},
        {"medicine_name": "C", "duration_kind": "ONGOING"},
        {"medicine_name": "D"},
    ]
    saved = _fill(doctor, rx, items=items).get_json()
    assert [(i["duration_kind"], i["duration_days"]) for i in saved["items"]] == [
        ("DAYS", 5),
        ("UNTIL_REVIEW", None),
        ("ONGOING", None),
        (None, None),
    ]
    for bad in (
        {"medicine_name": "E", "duration_kind": "DAYS"},
        {"medicine_name": "F", "duration_kind": "ONGOING", "duration_days": 3},
    ):
        resp = _fill(doctor, saved, items=[bad])
        assert (resp.status_code, _code(resp)) == (422, "REQ_VALIDATION_FAILED"), bad


def test_r24_the_start_day_is_within_30_days_and_a_revision_starts_empty(world: World) -> None:
    doctor, _, rx = _draft(world)
    late = _fill(doctor, rx, starts_on=(_today() + timedelta(days=31)).isoformat())
    assert (late.status_code, _code(late)) == (422, "REQ_VALIDATION_FAILED")
    start = _today() + timedelta(days=2)
    issued = _issue(doctor, rx, [SAMPLE_ITEM], starts_on=start.isoformat())
    assert issued["starts_on"] == start.isoformat()

    revised = _send(doctor, "POST", f"/api/v1/prescriptions/{issued['id']}/revise").get_json()
    assert (revised["starts_on"], revised["previous_starts_on"]) == (None, start.isoformat())
    again = doctor.get(f"/api/v1/prescriptions/{revised['id']}").get_json()
    assert again["previous_starts_on"] == start.isoformat()


def test_r21_the_vocabulary_is_the_engines(world: World) -> None:
    for user in (world.a.doctor_user, world.a.owner):
        resp = world.client_for(user).get("/api/v1/rx-vocabulary")
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["slot_sets"] == [
            {"length": 3, "slots": ["MORNING", "AFTERNOON", "NIGHT"]},
            {"length": 4, "slots": ["MORNING", "AFTERNOON", "EVENING", "NIGHT"]},
        ]
        assert body["special_frequencies"] == ["SOS", "ONCE", "CUSTOM"]
        assert {"WITH_WATER", "WITH_WARM_WATER", "WITH_MILK"} <= set(body["preparations"])
        assert body["start_window_days"] == 30


def test_the_database_refuses_a_pattern_the_engine_refuses(world: World, db: Engine) -> None:
    doctor, _, rx = _draft(world)
    _fill(doctor, rx)
    for bad in ("0-0-0", "2-0-2", "1-1"):
        with pytest.raises(DBAPIError, match="ck_prescription_items_frequency"), db.begin() as c:
            c.execute(
                text("UPDATE prescription_items SET frequency = :f WHERE prescription_id = :i"),
                {"f": bad, "i": rx["id"]},
            )


# --- The patient's plan (patient portal R28-R44) -------------------------------------------------


def test_ac13_the_plan_lays_out_what_the_doctor_wrote(world: World) -> None:
    _, patient, issued = _planned(world)
    plan = patient.get(f"{PORTAL}/medicine-plan")
    assert plan.status_code == 200, plan.get_json()
    assert plan.headers["Cache-Control"] == "no-store"
    body = plan.get_json()
    assert (body["date"], body["has_prescriptions"]) == (_today().isoformat(), True)
    assert [(s["slot"], s["label"], s["time"]) for s in body["slots"]] == [
        ("MORNING", "Morning", "08:00"),
        ("AFTERNOON", "Afternoon", "14:00"),
    ]
    entry = body["slots"][0]["entries"][0]
    assert entry["medicine_name"] == TABLET["medicine_name"]
    assert (entry["dose"], entry["timing"], entry["how"]) == (
        "1 tablet",
        "After food",
        "Take with water",
    )
    assert (entry["day"], entry["days_total"], entry["duration"]) == (1, 5, "5 days")
    assert (entry["prescription_id"], entry["clinic_name"]) == (issued["id"], "Alpha Sample Clinic")
    assert entry["reminder"] == {"enabled": False, "remind_at": None}
    [as_needed] = body["as_written"]
    assert (as_needed["medicine_name"], as_needed["reminder"]) == ("Syrup Sample", None)
    assert as_needed["duration"] == "Ongoing — as prescribed"

    later = patient.get(f"{PORTAL}/medicine-plan?date={_today() + timedelta(days=5)}").get_json()
    assert later["slots"] == []  # day 6 of a 5-day course: nothing invented
    assert [e["medicine_name"] for e in later["as_written"]] == ["Syrup Sample"]
    for bad in ((_today() + timedelta(days=31)).isoformat(), "tomorrow"):
        resp = patient.get(f"{PORTAL}/medicine-plan?date={bad}")
        assert (resp.status_code, _code(resp)) == (422, "REQ_VALIDATION_FAILED")


def test_r42_the_plan_speaks_the_accounts_language(world: World) -> None:
    _, patient, _ = _planned(world)
    changed = patient.patch(f"{PORTAL}/me", json={"language": "hi"}, headers=portal_csrf(patient))
    assert changed.status_code == 200, changed.get_json()
    body = patient.get(f"{PORTAL}/medicine-plan").get_json()
    assert body["language"] == "hi"
    assert body["slots"][0]["label"] == "सुबह"
    assert body["slots"][0]["entries"][0]["medicine_name"] == TABLET["medicine_name"]


def test_r44_no_current_version_gives_an_empty_plan(world: World) -> None:
    patient = portal_client(world, EMAIL)
    body = patient.get(f"{PORTAL}/medicine-plan").get_json()
    assert (body["has_prescriptions"], body["slots"], body["as_written"]) == (False, [], [])
    assert patient.get(f"{PORTAL}/medicine-plan/courses").get_json() == {"items": []}


def test_r35_courses_carry_the_start_end_and_slots(world: World) -> None:
    _, patient, issued = _planned(world)
    [course] = patient.get(f"{PORTAL}/medicine-plan/courses").get_json()["items"]
    assert (course["prescription_id"], course["revised"], course["reminders_set"]) == (
        issued["id"],
        False,
        False,
    )
    assert course["starts_on"] == _today().isoformat()
    assert course["ends_on"] is None  # the SOS line is open-ended
    tab, syrup = course["lines"]
    assert tab["ends_on"] == (_today() + timedelta(days=4)).isoformat()
    assert [s["slot"] for s in tab["slots"]] == ["MORNING", "AFTERNOON"]
    assert (syrup["slots"], syrup["as_written"]) == ([], "Only when needed")


def test_ac14_r34_slot_times_move_the_plan_and_must_run_in_order(world: World) -> None:
    _, patient, _ = _planned(world)
    times = {"morning": "07:00", "afternoon": "13:30", "evening": "18:00", "night": "22:00"}
    resp = patient.patch(f"{PORTAL}/me", json={"slot_times": times}, headers=portal_csrf(patient))
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["account"]["slot_times"] == times
    plan = patient.get(f"{PORTAL}/medicine-plan").get_json()
    assert [s["time"] for s in plan["slots"]] == ["07:00", "13:30"]
    for bad in (
        {**times, "afternoon": "06:00"},
        {**times, "morning": "04:30"},
        {**times, "night": "23:45"},
    ):
        refused = patient.patch(
            f"{PORTAL}/me", json={"slot_times": bad}, headers=portal_csrf(patient)
        )
        assert (refused.status_code, _code(refused)) == (422, "REQ_VALIDATION_FAILED"), bad
    empty = patient.patch(f"{PORTAL}/me", json={}, headers=portal_csrf(patient))
    assert empty.status_code == 422


def test_ac15_r38_a_reminder_choice_is_stored_and_never_changes_the_prescription(
    world: World, db: Engine
) -> None:
    doctor, patient, issued = _planned(world)
    tab, syrup = issued["items"]
    url = f"{PORTAL}/medicine-plan/reminders"
    choice = {
        "prescription_id": issued["id"],
        "item_id": tab["id"],
        "slot": "MORNING",
        "enabled": True,
        "remind_at": "07:30",
    }
    saved = patient.put(url, json=choice, headers=portal_csrf(patient))
    assert saved.status_code == 200, saved.get_json()
    assert saved.get_json() == {"enabled": True, "remind_at": "07:30"}
    plan = patient.get(f"{PORTAL}/medicine-plan").get_json()
    assert plan["slots"][0]["entries"][0]["reminder"] == {"enabled": True, "remind_at": "07:30"}
    assert plan["slots"][1]["entries"][0]["reminder"] == {"enabled": False, "remind_at": None}
    [course] = patient.get(f"{PORTAL}/medicine-plan/courses").get_json()["items"]
    assert course["reminders_set"] is True

    for bad, field in (
        ({**choice, "item_id": syrup["id"]}, "item_id"),
        ({**choice, "slot": "NIGHT"}, "slot"),
        ({**choice, "remind_at": "04:00"}, "remind_at"),
    ):
        refused = patient.put(url, json=bad, headers=portal_csrf(patient))
        assert (refused.status_code, _code(refused)) == (422, "REQ_VALIDATION_FAILED"), bad
        assert field in str(refused.get_json()["error"])
    stranger = patient.put(
        url, json={**choice, "prescription_id": tab["id"]}, headers=portal_csrf(patient)
    )
    assert (stranger.status_code, _code(stranger)) == (404, "REQ_NOT_FOUND")

    # The prescription is exactly as issued.
    assert (
        doctor.get(f"/api/v1/prescriptions/{issued['id']}").get_json()["items"] == issued["items"]
    )
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM medicine_reminder_prefs")).scalar_one() == 1


def test_r39_a_revision_starts_without_choices_and_an_unlink_clears_them(
    world: World, db: Engine
) -> None:
    doctor, patient, issued = _planned(world)
    choice = {
        "prescription_id": issued["id"],
        "item_id": issued["items"][0]["id"],
        "slot": "AFTERNOON",
        "enabled": True,
    }
    assert (
        patient.put(
            f"{PORTAL}/medicine-plan/reminders", json=choice, headers=portal_csrf(patient)
        ).status_code
        == 200
    )
    draft = _send(doctor, "POST", f"/api/v1/prescriptions/{issued['id']}/revise").get_json()
    revised = _issue(doctor, draft, [TABLET])
    [course] = patient.get(f"{PORTAL}/medicine-plan/courses").get_json()["items"]
    assert (course["prescription_id"], course["revised"], course["reminders_set"]) == (
        revised["id"],
        True,
        False,
    )
    # The superseded version is no longer current: no choice can be made for it.
    stale = patient.put(
        f"{PORTAL}/medicine-plan/reminders", json=choice, headers=portal_csrf(patient)
    )
    assert stale.status_code == 404

    [link] = patient.get(f"{PORTAL}/links").get_json()["items"]
    assert (
        patient.delete(f"{PORTAL}/links/{link['id']}", headers=portal_csrf(patient)).status_code
        == 200
    )
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM medicine_reminder_prefs")).scalar_one() == 0


def test_r41_reading_and_choosing_write_no_audit_and_log_no_medicine(
    world: World, db: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    _, patient, issued = _planned(world)
    with db.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
    capsys.readouterr()
    patient.get(f"{PORTAL}/medicine-plan")
    patient.get(f"{PORTAL}/medicine-plan/courses")
    patient.put(
        f"{PORTAL}/medicine-plan/reminders",
        json={
            "prescription_id": issued["id"],
            "item_id": issued["items"][0]["id"],
            "slot": "MORNING",
            "enabled": True,
        },
        headers=portal_csrf(patient),
    )
    logged = capsys.readouterr().out
    assert SENTINEL not in logged and "1 tablet" not in logged
    assert "portal.medicine_plan_read" in logged and "portal.medicine_reminder_set" in logged
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == before
