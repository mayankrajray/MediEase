"""What the M4-P6 screens need from the API: the queue's prescription state and the preview.

M4-P6 decisions 3A and 4A; spec §6, R20, D6.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine

from tests.conftest import World
from tests.integration.test_prescriptions_http import (
    SENTINEL,
    _audit,
    _code,
    _draft,
    _fill,
    _issued,
    _today,
)
from tests.integration.test_visits_http import _send


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _row(world: World, appointment_id: str) -> dict[str, Any]:
    desk = world.client_for(world.a.desk)
    resp = desk.get(f"/api/v1/queue?date={_today().isoformat()}&doctor_id={world.a.doctor.id}")
    assert resp.status_code == 200, resp.get_json()
    rows = [a for s in resp.get_json()["sessions"] for a in s["appointments"]]
    return next(a for a in rows if a["id"] == appointment_id)


# --- Decision 4A: the queue row ------------------------------------------------------------------


def test_decision_4a_the_row_shows_the_visit_and_the_current_prescription_without_content(
    world: World,
) -> None:
    doctor, visit, rx = _draft(world)
    row = _row(world, visit["appointment_id"])
    assert (row["visit_id"], row["prescription"]) == (visit["id"], None)  # a draft is not shown

    _fill(doctor, rx, items=[{"medicine_name": SENTINEL}])
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert issued.status_code == 200, issued.get_json()
    row = _row(world, visit["appointment_id"])
    assert set(row["prescription"]) == {"id", "version", "issued_at"}
    assert (row["prescription"]["id"], row["prescription"]["version"]) == (rx["id"], 1)
    assert SENTINEL not in str(row)

    v2 = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise").get_json()
    _send(doctor, "POST", f"/api/v1/prescriptions/{v2['id']}/issue", {"revision": 1})
    row = _row(world, visit["appointment_id"])
    assert (row["prescription"]["id"], row["prescription"]["version"]) == (v2["id"], 2)


def test_a_row_without_a_visit_has_neither(world: World) -> None:
    from tests.integration.test_visits_http import _in_consultation

    appointment, _ = _in_consultation(world)
    row = _row(world, appointment)
    assert (row["visit_id"], row["prescription"]) == (None, None)


# --- Decision 3A: the preview --------------------------------------------------------------------


def test_decision_3a_the_preview_shows_a_draft_in_the_patients_words_and_audits_nothing(
    world: World, db: Engine
) -> None:
    doctor, _, rx = _draft(world)
    _fill(doctor, rx)
    before = len(_audit(db, "prescription.viewed", "visit.viewed"))
    resp = doctor.get(f"/api/v1/prescriptions/{rx['id']}/preview")
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "no-store"
    page = resp.get_json()
    fields = {f["label"]: f["value"] for f in page["medicines"][0]["fields"]}
    assert page["language"] == "en" and page["version"] == 1 and page["updated_note"] is None
    assert (
        fields["How to give"] == "Shake well before use; Mix in 10 ml boiled cooled water of water"
    )
    assert page["doctor_name"] == world.a.doctor.display_name

    hindi = doctor.get(f"/api/v1/prescriptions/{rx['id']}/preview?lang=hi").get_json()
    assert hindi["medicines_heading"] == "दवाइयाँ" and hindi["medicines"][0]["name"] == "Syrup X"
    assert len(_audit(db, "prescription.viewed", "visit.viewed")) == before

    bad = doctor.get(f"/api/v1/prescriptions/{rx['id']}/preview?lang=fr")
    assert (bad.status_code, _code(bad)) == (422, "REQ_VALIDATION_FAILED")


def test_the_preview_is_for_drafts_and_clinicians_only(world: World) -> None:
    doctor, _, rx = _issued(world)
    issued = doctor.get(f"/api/v1/prescriptions/{rx['id']}/preview")
    assert (issued.status_code, _code(issued)) == (409, "RX_NOT_DRAFT")

    v2 = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise").get_json()
    revision = doctor.get(f"/api/v1/prescriptions/{v2['id']}/preview").get_json()
    assert revision["version"] == 2 and revision["updated_note"] is not None

    desk = world.client_for(world.a.desk)
    assert desk.get(f"/api/v1/prescriptions/{v2['id']}/preview").status_code == 403
    owner = world.client_for(world.a.owner)  # CLINICAL_VIEW without a doctor profile
    assert owner.get(f"/api/v1/prescriptions/{v2['id']}/preview").status_code == 200
