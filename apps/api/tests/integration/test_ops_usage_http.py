"""The ops clinic usage view on PostgreSQL (M9-P4; FR-OPS-03; spec ops-clinic-usage).

The bundled demo clinic (invented data, two weeks of history) is imported beside the test world's
clinics; the ops console then reads every clinic's activity in counts.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from mediease_api.application.ops.usage import week_starts
from mediease_api.delivery.cli import import_clinic
from tests.conftest import TEST_IP_SALT, TEST_SIGNING_KEY, SetEnv, World

USAGE = "/api/v1/ops/clinic-usage"
DEMO = "kesar-bagh-family-clinic"


@pytest.fixture
def demo(world: World, set_env: SetEnv, migrated_database_url: str) -> World:
    set_env(
        {
            "APP_ENV": "local",
            "DATABASE_URL": migrated_database_url,
            "JWT_SIGNING_KEY": TEST_SIGNING_KEY,
            "AUDIT_IP_SALT": TEST_IP_SALT,
        }
    )
    assert import_clinic.main(["--demo", "--password", "usage-test-password-1"]) == 0
    return world


def test_fr_ops_03_ops_see_each_clinics_records_by_week_and_in_total(demo: World) -> None:
    resp = demo.client_for(demo.ops).get(USAGE)
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-store"
    body = resp.get_json()

    assert len(body["weeks"]) == 4
    first, last = date.fromisoformat(body["weeks"][0]["start"]), body["weeks"][-1]
    assert first.weekday() == 0 and date.fromisoformat(last["end"]).weekday() == 6

    row = next(c for c in body["clinics"] if c["slug"] == DEMO)
    assert row["totals"] == {
        "patients": 20,
        "appointments": 36,  # 26 seen and 10 upcoming
        "visits": 26,
        "prescriptions": 24,
        "bills": 26,
    }
    # Two weeks of history fall inside the last four calendar weeks.
    weekly = {m: sum(w["counts"][m] for w in row["weeks"]) for m in row["totals"]}
    assert weekly == row["totals"]
    assert [w["start"] for w in row["weeks"]] == [w["start"] for w in body["weeks"]]
    assert row["staff"] == {
        "owners": 1,
        "doctors": 2,
        "front_desk": 1,
        "members": 4,
        "active_7d": 1,
    }
    assert row["active_this_week"] is True and row["last_active_at"] is not None
    assert row["health"] == {"failed_messages_7d": 0, "not_sent_7d": 0, "failed_jobs_7d": 0}

    # The summary adds every clinic's weeks; the test world's clinics have no records.
    assert body["summary"]["clinics"] == len(body["clinics"]) >= 4
    assert body["summary"]["totals"] == weekly
    # Counts and names only: nothing about a patient or a person (spec R2).
    text = resp.get_data(as_text=True)
    for word in ("Neha", "Kapoor", "+91", "Migraine", "Demo Tablet", "mentor."):
        assert word not in text


def test_fr_ops_03_the_number_of_weeks_is_1_to_12(world: World) -> None:
    client = world.client_for(world.ops)
    assert len(client.get(f"{USAGE}?weeks=1").get_json()["weeks"]) == 1
    assert len(client.get(f"{USAGE}?weeks=12").get_json()["weeks"]) == 12
    for bad in ("0", "13", "four", "-1"):
        resp = client.get(f"{USAGE}?weeks={bad}")
        assert (resp.status_code, resp.get_json()["error"]["code"]) == (
            422,
            "REQ_VALIDATION_FAILED",
        )


def test_fr_ops_03_clinic_staff_cannot_read_the_usage_view(world: World) -> None:
    assert world.client_for(world.a.owner).get(USAGE).status_code == 403


def test_week_starts_are_the_last_mondays_oldest_first() -> None:
    thursday = date(2026, 11, 12)
    starts = week_starts(thursday, 4)
    assert starts == [date(2026, 10, 19), date(2026, 10, 26), date(2026, 11, 2), date(2026, 11, 9)]
    assert week_starts(date(2026, 11, 9), 1) == [date(2026, 11, 9)]
    assert all(s.weekday() == 0 for s in week_starts(thursday + timedelta(days=3), 6))
