"""Dose tracking over HTTP on PostgreSQL (M6b-P3b; patient portal R45-R54, AC19-AC22).

The course starts three days ago, so the windows are the same whatever the time of day: last
night's dose (21:00 yesterday) is always within 48 hours, the night three days ago never is.
Synthetic data only.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from mediease_api.application.jobs.purge import PurgeExpired
from mediease_api.delivery.cli import dose_data
from tests.conftest import UowFactory, World
from tests.fakes import FakeClock, FakeIds
from tests.integration.test_medicine_plan_http import AS_NEEDED, _issue
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_prescriptions_http import _code, _draft, _today
from tests.integration.test_seed import seed_env  # noqa: F401 (fixture)
from tests.portal_helpers import PORTAL, link_by_invite, portal_client

EMAIL = "doses.patient@example.test"
SENTINEL = "SENTINEL-dose-7b3c"

TABLET: dict[str, Any] = {
    "medicine_name": f"Tab Sample {SENTINEL}",
    "dose": "1 tablet",
    "frequency": "1-0-1",
    "duration_kind": "DAYS",
    "duration_days": 7,
}
DOSES = f"{PORTAL}/medicine-plan/doses"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _scene(world: World) -> tuple[FlaskClient, dict[str, Any], str]:
    """An issued Tab 1-0-1 for 7 days from three days ago, plus an SOS line; a linked account."""
    doctor, visit, rx = _draft(world)
    issued = _issue(
        doctor, rx, [TABLET, AS_NEEDED], starts_on=(_today() - timedelta(days=3)).isoformat()
    )
    patient = portal_client(world, EMAIL)
    link_by_invite(world.client_for(world.a.owner), patient, visit["patient_id"])
    return patient, issued, str(visit["patient_id"])


def _choice(
    issued: dict[str, Any], days_ago: int, slot: str = "NIGHT", line: int = 0
) -> dict[str, Any]:
    return {
        "prescription_id": issued["id"],
        "item_id": issued["items"][line]["id"],
        "on_date": (_today() - timedelta(days=days_ago)).isoformat(),
        "slot": slot,
    }


def _mark(patient: FlaskClient, choice: dict[str, Any], state: str) -> Any:
    return patient.put(DOSES, json={**choice, "state": state}, headers=portal_csrf(patient))


def _rows(db: Engine) -> int:
    with db.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM dose_records")).scalar_one())


def test_ac19_mark_change_and_clear_within_the_window_never_a_future_day(
    world: World, db: Engine
) -> None:
    patient, issued, _ = _scene(world)
    last_night = _choice(issued, 1)

    taken = _mark(patient, last_night, "TAKEN")
    assert taken.status_code == 200, taken.get_json()
    assert taken.get_json()["status"] == "TAKEN" and taken.get_json()["markable"] is True
    assert taken.get_json()["marked_at"] is not None
    plan = patient.get(f"{PORTAL}/medicine-plan?date={last_night['on_date']}").get_json()
    night = next(s for s in plan["slots"] if s["slot"] == "NIGHT")["entries"][0]
    assert night["mark"]["status"] == "TAKEN" and night["timezone"] == "Asia/Kolkata"
    assert plan["as_written"][0]["mark"] is None  # an untimed line has no dose to mark

    assert _mark(patient, last_night, "SKIPPED").get_json()["status"] == "SKIPPED"
    assert _rows(db) == 1  # one record per dose, changed in place
    cleared = patient.delete(DOSES, query_string=last_night, headers=portal_csrf(patient))
    assert cleared.status_code == 200, cleared.get_json()
    assert cleared.get_json() == {"status": "NOT_RECORDED", "marked_at": None, "markable": True}
    assert _rows(db) == 0

    for refused in (_choice(issued, -1, "MORNING"), _choice(issued, 3)):
        resp = _mark(patient, refused, "TAKEN")
        assert (resp.status_code, _code(resp)) == (409, "PRT_DOSE_NOT_MARKABLE"), refused
    old = patient.get(f"{PORTAL}/medicine-plan?date={_choice(issued, 3)['on_date']}").get_json()
    assert (
        next(s for s in old["slots"] if s["slot"] == "NIGHT")["entries"][0]["mark"]["markable"]
        is False
    )
    assert _rows(db) == 0


def test_r45_only_a_scheduled_dose_of_a_timed_line_can_be_marked(world: World) -> None:
    patient, issued, _ = _scene(world)
    for bad, field in (
        (_choice(issued, 1, line=1), "item_id"),  # the SOS line
        (_choice(issued, 1, "AFTERNOON"), "slot"),  # 1-0-1 has no afternoon dose
        (_choice(issued, 4), "on_date"),  # the day before the course started
    ):
        resp = _mark(patient, bad, "TAKEN")
        assert (resp.status_code, _code(resp)) == (422, "REQ_VALIDATION_FAILED"), bad
        assert field in str(resp.get_json()["error"])
    wrong = _mark(patient, _choice(issued, 1), "MISSED")  # only Taken or Skipped are stored
    assert wrong.status_code == 422


def test_ac20_history_derives_not_recorded_and_stores_nothing_for_it(
    world: World, db: Engine
) -> None:
    patient, issued, _ = _scene(world)
    _mark(patient, _choice(issued, 1), "TAKEN")
    resp = patient.get(
        f"{PORTAL}/medicine-plan/history", query_string={"prescription_id": issued["id"]}
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["starts_on"] == (_today() - timedelta(days=3)).isoformat()
    assert [d["date"] for d in body["days"]][-1] == body["starts_on"]  # newest first
    yesterday = next(d for d in body["days"] if d["date"] == _choice(issued, 1)["on_date"])
    by_slot = {x["slot"]: x["status"] for x in yesterday["doses"]}
    assert by_slot == {"MORNING": "NOT_RECORDED", "NIGHT": "TAKEN"}
    assert body["counts"]["TAKEN"] == 1 and body["counts"]["NOT_RECORDED"] >= 5
    assert _rows(db) == 1  # Not recorded is never stored
    assert [v["version"] for v in body["versions"]] == [1]
    # No advice and no score: only states, counts and the clinic to call.
    assert set(body) == {
        "prescription_id",
        "version",
        "clinic_name",
        "clinic_phone_e164",
        "timezone",
        "starts_on",
        "counts",
        "days",
        "versions",
    }


def test_ac21_unlink_hides_the_records_and_relinking_the_same_record_shows_them(
    world: World, db: Engine
) -> None:
    patient, issued, patient_id = _scene(world)
    _mark(patient, _choice(issued, 1), "SKIPPED")
    [link] = patient.get(f"{PORTAL}/links").get_json()["items"]
    assert (
        patient.delete(f"{PORTAL}/links/{link['id']}", headers=portal_csrf(patient)).status_code
        == 200
    )
    history = f"{PORTAL}/medicine-plan/history"
    gone = patient.get(history, query_string={"prescription_id": issued["id"]})
    assert (gone.status_code, _code(gone)) == (404, "REQ_NOT_FOUND")
    assert _rows(db) == 1  # hidden, kept

    link_by_invite(world.client_for(world.a.owner), patient, patient_id)
    back = patient.get(history, query_string={"prescription_id": issued["id"]}).get_json()
    assert back["counts"]["SKIPPED"] == 1


def test_ac22_r51_marking_logs_no_state_medicine_or_time_and_writes_no_audit(
    world: World, db: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    patient, issued, _ = _scene(world)
    with db.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
    capsys.readouterr()
    choice = _choice(issued, 1)
    _mark(patient, choice, "TAKEN")
    _mark(patient, choice, "SKIPPED")
    patient.delete(DOSES, query_string=choice, headers=portal_csrf(patient))
    patient.get(f"{PORTAL}/medicine-plan/history", query_string={"prescription_id": issued["id"]})
    logged = capsys.readouterr().out
    for secret in (SENTINEL, "1 tablet", "TAKEN", "SKIPPED", "NOT_RECORDED"):
        assert secret not in logged, secret
    # No dose day, slot or time as a field of any line (the log's own timestamp is not one).
    for field in ("on_date=", "slot=", "state=", "marked_at="):
        assert field not in logged, field
    assert "dose.marked" in logged and "dose.cleared" in logged
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == before


def test_r53_the_purge_deletes_a_record_after_its_keep_until_day(
    world: World, db: Engine, uow_factory: UowFactory
) -> None:
    patient, issued, _ = _scene(world)
    _mark(patient, _choice(issued, 1), "TAKEN")
    _mark(patient, _choice(issued, 0, "MORNING"), "TAKEN")
    with db.begin() as conn:
        keep = (
            conn.execute(text("SELECT keep_until FROM dose_records ORDER BY on_date"))
            .scalars()
            .all()
        )
        # A 7-day course from three days ago ends in three days; kept a year after that.
        assert keep == [_today() + timedelta(days=3 + 365)] * 2
        conn.execute(
            text("UPDATE dose_records SET keep_until = :d WHERE on_date = :o"),
            {"d": _today() - timedelta(days=2), "o": _today() - timedelta(days=1)},
        )
    counts = PurgeExpired(
        uow=uow_factory(), clock=FakeClock(datetime.now(UTC)), ids=FakeIds()
    ).execute()
    assert counts.dose_records == 1
    assert _rows(db) == 1


def test_r54_support_exports_then_deletes_an_accounts_records_on_request(
    world: World,
    db: Engine,
    seed_env: dict[str, str],  # noqa: F811
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    patient, issued, _ = _scene(world)
    _mark(patient, _choice(issued, 1), "TAKEN")
    account = patient.get(f"{PORTAL}/me").get_json()["account"]["id"]
    capsys.readouterr()

    out = tmp_path / "export.json"
    assert dose_data.main(["export", account, "--out", str(out)]) == 0
    assert out.stat().st_mode & 0o077 == 0  # readable by its owner only
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert exported["account_id"] == account
    [one] = exported["dose_records"]
    assert (one["prescription_id"], one["slot"], one["state"]) == (issued["id"], "NIGHT", "TAKEN")
    assert SENTINEL not in json.dumps(exported)  # no medicine name is stored

    assert dose_data.main(["delete", account]) == 2  # --confirm is required
    assert _rows(db) == 1
    assert dose_data.main(["delete", account, "--confirm"]) == 0
    assert "deleted 1 dose records" in capsys.readouterr().out
    assert _rows(db) == 0
