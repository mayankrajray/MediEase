"""The daily collection over HTTP (M6d-P5; FR-BIL-06; spec billing R55-R62, AC16-AC18).

AC16 is the milestone's exit criterion: the day's collection matches the recorded payments.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from tests.builders import a_doctor
from tests.conftest import UowFactory, World
from tests.integration.test_appointments_http import _patient
from tests.integration.test_bills_http import BILLS, _draft, _ok
from tests.integration.test_visits_http import _send

URL = "/api/v1/clinic/collection"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def _issued(
    desk: FlaskClient, patient: str, amounts: list[int], doctor: str | None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "lines": [
            {"description": f"Line {n}", "unit_price_paise": a} for n, a in enumerate(amounts)
        ]
    }
    if doctor:
        body["doctor_id"] = doctor
    bill = _draft(desk, patient, **body)
    return _ok(_send(desk, "POST", f"{BILLS}/{bill['id']}/issue"))


def _pay(
    desk: FlaskClient,
    bill: dict[str, Any],
    amount: int,
    mode: str = "CASH",
    kind: str = "PAYMENT",
    **extra: Any,
) -> dict[str, Any]:
    return _ok(
        _send(
            desk,
            "POST",
            f"{BILLS}/{bill['id']}/payments",
            {"kind": kind, "mode": mode, "amount_paise": amount, **extra},
        ),
        201,
    )


def test_ac16_exit_criterion_the_collection_matches_the_recorded_payments(
    world: World, uow_factory: UowFactory, db: Engine
) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    other = a_doctor(world.a.clinic.id, display_name="Dr. Other Sample")
    with uow_factory() as uow:
        uow.tenant(world.a.clinic.id).doctors.add(other)
        uow.commit()
    asha, bina = _patient(desk), _patient(desk, "Bina Shah")
    first = _issued(desk, asha, [50000, 20000], str(world.a.doctor.id))
    second = _issued(owner, bina, [30000], str(other.id))
    third = _issued(desk, bina, [10000], None)

    _pay(desk, first, 40000)
    _pay(desk, first, 30000, mode="UPI", reference="UPI-1")
    _pay(owner, second, 30000, mode="CARD")
    wrong = _pay(desk, third, 10000)["payments"][0]["id"]
    _ok(
        _send(
            desk, "POST", f"{BILLS}/{third['id']}/payments/{wrong}/void", {"reason": "Wrong bill"}
        )
    )
    _ok(
        _send(
            desk,
            "POST",
            f"{BILLS}/{first['id']}/credit-notes",
            {"line_ids": [first["lines"][1]["id"]], "reason": "Not done"},
        ),
        201,
    )
    _pay(desk, first, 20000, kind="REFUND")

    day = _ok(desk.get(URL))
    assert day["date"] == _today().isoformat()
    assert day["total"] == {
        "payments_paise": 100000,
        "refunds_paise": 20000,
        "net_paise": 80000,
        "count": 4,
    }
    assert day["voided"] == {
        "payments_paise": 10000,
        "refunds_paise": 0,
        "net_paise": 10000,
        "count": 1,
    }
    assert len(day["items"]) == 5 and sum(i["voided"] for i in day["items"]) == 1

    # R56: the parts add up to the whole, by mode and by doctor.
    for part in ("by_mode", "by_doctor"):
        assert sum(r["net_paise"] for r in day[part]) == day["total"]["net_paise"]
    modes = {r["mode"]: r["net_paise"] for r in day["by_mode"]}
    assert modes == {"CASH": 20000, "UPI": 30000, "CARD": 30000}
    doctors = {(r["doctor"] or {}).get("display_name"): r["net_paise"] for r in day["by_doctor"]}
    assert doctors == {"Dr. Alpha Sample": 50000, "Dr. Other Sample": 30000}

    # The exit criterion: the same figure from the bills' own paid and refunded amounts.
    with db.connect() as conn:
        on_bills = conn.execute(
            text("SELECT sum(paid_paise - refunded_paise) FROM bills WHERE clinic_id = :c"),
            {"c": world.a.clinic.id},
        ).scalar_one()
        on_payments = conn.execute(
            text(
                "SELECT sum(CASE kind WHEN 'PAYMENT' THEN amount_paise ELSE -amount_paise END)"
                " FROM payments WHERE clinic_id = :c AND voided_at IS NULL AND local_date = :d"
            ),
            {"c": world.a.clinic.id, "d": _today()},
        ).scalar_one()
    assert on_bills == on_payments == day["total"]["net_paise"]


def test_ac17_r60_the_csv_export_is_safe_and_audited(world: World, db: Engine) -> None:
    desk = world.client_for(world.a.desk)
    bill = _issued(desk, _patient(desk, "=HYPERLINK Test"), [50000], str(world.a.doctor.id))
    _pay(desk, bill, 50000, mode="UPI", reference="+CMD-123")
    resp = desk.get(f"{URL}/export")
    assert resp.status_code == 200 and resp.mimetype == "text/csv"
    assert resp.headers["Content-Disposition"].endswith(f'-{_today().isoformat()}.csv"')
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert rows[0][0] == "Time" and len(rows) == 2
    assert rows[1][3] == "500.00" and rows[1][4] == "'+CMD-123" and rows[1][7] == "'=HYPERLINK Test"
    assert rows[1][5] == bill["number"]
    with db.connect() as conn:
        meta = conn.execute(
            text("SELECT metadata FROM audit_events WHERE action = 'collection.exported'")
        ).scalar_one()
    assert meta == {"date": _today().isoformat(), "rows": "1"}


def test_ac18_r55_r59_days_access_and_tenancy(world: World, db: Engine) -> None:
    desk = world.client_for(world.a.desk)
    bill = _issued(desk, _patient(desk), [50000], None)
    paid = _pay(desk, bill, 10000)["payments"][0]["id"]
    with db.begin() as conn:
        conn.execute(
            text("UPDATE payments SET local_date = local_date - 1 WHERE id = :p"), {"p": paid}
        )
    yesterday = (_today() - timedelta(days=1)).isoformat()
    assert _ok(desk.get(URL))["total"]["count"] == 0
    assert _ok(desk.get(f"{URL}?date={yesterday}"))["total"]["net_paise"] == 10000
    assert desk.get(f"{URL}?date={(_today() + timedelta(days=1)).isoformat()}").status_code == 422
    assert desk.get(f"{URL}?date=yesterday").status_code == 422
    assert world.client_for(world.a.doctor_user).get(URL).status_code == 403
    assert world.client_for(world.a.owner).get(f"{URL}?date={yesterday}").status_code == 200
    assert _ok(world.client_for(world.b.owner).get(f"{URL}?date={yesterday}"))["items"] == []
