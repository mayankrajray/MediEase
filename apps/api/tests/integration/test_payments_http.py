"""Payments, refunds and dues over HTTP (M6d-P3; FR-BIL-03, 05; spec billing R31-R42, AC9-AC12).

Real PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from tests.conftest import World
from tests.integration.test_appointments_http import _in_parallel, _patient
from tests.integration.test_bills_http import BILLS, _code, _draft, _ok
from tests.integration.test_visits_http import _send
from tests.sessions_now import running_session

DUES = "/api/v1/clinic/dues"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _issued(
    client: FlaskClient, patient: str, *amounts: int, doctor: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "lines": [
            {"description": f"Line {n}", "unit_price_paise": a} for n, a in enumerate(amounts)
        ]
    }
    if doctor is not None:
        body["doctor_id"] = doctor
    bill = _draft(client, patient, **body)
    return _ok(_send(client, "POST", f"{BILLS}/{bill['id']}/issue"))


def _pay(client: FlaskClient, bill: dict[str, Any], amount: int, **extra: Any) -> Any:
    return _send(
        client,
        "POST",
        f"{BILLS}/{bill['id']}/payments",
        {"mode": "CASH", "amount_paise": amount, **extra},
    )


def test_ac9_r31_r34_partial_payments_up_to_the_balance(world: World, db: Engine) -> None:
    desk = world.client_for(world.a.desk)
    bill = _issued(desk, _patient(desk), 50000)
    part = _ok(_pay(desk, bill, 20000), 201)
    assert (part["paid_paise"], part["balance_paise"]) == (20000, 30000)
    [payment] = part["payments"]
    assert (payment["mode"], payment["received_by"], payment["voided_at"]) == (
        "CASH",
        "Alpha Front_Desk",
        None,
    )

    too_much = _pay(desk, bill, 30001)
    assert _code(too_much) == (409, "BIL_PAYMENT_TOO_LARGE")
    assert too_much.get_json()["error"]["details"] == {"most_paise": "30000"}
    rest = _ok(_pay(desk, bill, 30000, mode="UPI", reference="UPI-REF-1"), 201)
    assert (rest["balance_paise"], rest["payments"][1]["reference"]) == (0, "UPI-REF-1")
    assert _code(_pay(desk, bill, 1)) == (409, "BIL_PAYMENT_TOO_LARGE")
    draft = _draft(
        desk, _patient(desk, "Bina Shah"), lines=[{"description": "X", "unit_price_paise": 100}]
    )
    assert _code(_pay(desk, draft, 100)) == (409, "BIL_NOT_ISSUED")
    assert (
        _send(
            desk, "POST", f"{BILLS}/{bill['id']}/payments", {"mode": "CHEQUE", "amount_paise": 5}
        ).status_code
        == 422
    )

    with db.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT metadata FROM audit_events WHERE action = 'payment.recorded'"
                    " ORDER BY occurred_at"
                )
            )
            .scalars()
            .all()
        )
    assert [r["amount_paise"] for r in rows] == ["20000", "30000"]


def test_ac10_r33_a_credit_note_then_a_refund(world: World) -> None:
    desk = world.client_for(world.a.desk)
    bill = _issued(desk, _patient(desk), 30000, 20000)
    _ok(_pay(desk, bill, 50000), 201)
    refund = {"kind": "REFUND", "mode": "CASH", "amount_paise": 1}
    assert _code(_send(desk, "POST", f"{BILLS}/{bill['id']}/payments", refund)) == (
        409,
        "BIL_PAYMENT_TOO_LARGE",
    )
    credited = _ok(
        _send(
            desk,
            "POST",
            f"{BILLS}/{bill['id']}/credit-notes",
            {"line_ids": [bill["lines"][1]["id"]], "reason": "Not done"},
        ),
        201,
    )
    assert credited["balance_paise"] == -20000
    refunded = _ok(
        _send(desk, "POST", f"{BILLS}/{bill['id']}/payments", {**refund, "amount_paise": 20000}),
        201,
    )
    assert (refunded["refunded_paise"], refunded["balance_paise"]) == (20000, 0)


def test_ac11_r35_r36_a_void_the_same_day_only_and_never_under_a_refund(
    world: World, db: Engine
) -> None:
    desk = world.client_for(world.a.desk)
    bill = _issued(desk, _patient(desk), 30000, 20000)
    paid = _ok(_pay(desk, bill, 50000), 201)
    payment = paid["payments"][0]["id"]
    _ok(
        _send(
            desk,
            "POST",
            f"{BILLS}/{bill['id']}/credit-notes",
            {"line_ids": [bill["lines"][1]["id"]], "reason": "Not done"},
        ),
        201,
    )
    refunded = _ok(
        _send(
            desk,
            "POST",
            f"{BILLS}/{bill['id']}/payments",
            {"kind": "REFUND", "mode": "CASH", "amount_paise": 20000},
        ),
        201,
    )
    refund = refunded["payments"][1]["id"]

    void = f"{BILLS}/{bill['id']}/payments/{payment}/void"
    assert _code(_send(desk, "POST", void, {"reason": "Wrong"})) == (409, "BIL_VOID_REFUNDED")
    _ok(
        _send(
            desk, "POST", f"{BILLS}/{bill['id']}/payments/{refund}/void", {"reason": "Not paid out"}
        )
    )
    voided = _ok(_send(desk, "POST", void, {"reason": "Wrong amount"}))
    assert (voided["paid_paise"], voided["refunded_paise"], voided["balance_paise"]) == (
        0,
        0,
        30000,
    )
    assert voided["payments"][0]["void_reason"] == "Wrong amount"
    assert voided["payments"][0]["voided_by"] == "Alpha Front_Desk"
    assert _code(_send(desk, "POST", void, {"reason": "Again"})) == (409, "BIL_ALREADY_VOIDED")

    late = _ok(_pay(desk, bill, 1000), 201)["payments"][2]["id"]
    with db.begin() as conn:
        conn.execute(
            text("UPDATE payments SET local_date = local_date - 1 WHERE id = :p"), {"p": late}
        )
    late_void = f"{BILLS}/{bill['id']}/payments/{late}/void"
    assert _code(_send(desk, "POST", late_void, {"reason": "Too late"})) == (
        409,
        "BIL_VOID_TOO_LATE",
    )
    other = _issued(desk, _patient(desk, "Bina Shah"), 100)
    wrong_bill = f"{BILLS}/{other['id']}/payments/{late}/void"
    assert _send(desk, "POST", wrong_bill, {"reason": "x"}).status_code == 404


def test_r34_two_payments_at_once_never_exceed_the_balance(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    bill = _issued(desk, _patient(desk), 50000)
    results = _in_parallel([lambda: _pay(owner, bill, 40000), lambda: _pay(desk, bill, 40000)])
    assert sorted(r.status_code for r in results) == [201, 409]
    assert desk.get(f"{BILLS}/{bill['id']}").get_json()["paid_paise"] == 40000


def test_d2_a_doctor_takes_payments_on_their_own_bills_only(world: World) -> None:
    desk, doctor = world.client_for(world.a.desk), world.client_for(world.a.doctor_user)
    patient = _patient(desk)
    theirs = _issued(desk, patient, 500)
    mine = _issued(desk, patient, 500, doctor=str(world.a.doctor.id))
    assert _pay(doctor, mine, 500).status_code == 201
    assert _pay(doctor, theirs, 500).status_code == 404


def test_ac12_r39_r40_dues_for_the_desk_and_on_the_queue(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    asha, bina = _patient(desk), _patient(desk, "Bina Shah")
    first = _issued(desk, asha, 30000)
    _issued(desk, asha, 20000)
    _ok(_pay(desk, first, 10000), 201)
    settled = _issued(desk, bina, 500)
    _ok(_pay(desk, settled, 500), 201)
    _draft(desk, bina, lines=[{"description": "Draft", "unit_price_paise": 900}])

    dues = _ok(desk.get(DUES))
    assert dues["total_paise"] == 40000
    [row] = dues["items"]
    assert (row["patient"]["id"], row["bills"], row["due_paise"]) == (asha, 2, 40000)
    assert _ok(desk.get(f"{DUES}?patient_id={bina}"))["items"] == []
    assert world.client_for(world.a.doctor_user).get(DUES).status_code == 403
    assert world.client_for(world.b.owner).get(DUES).get_json()["items"] == []

    session = running_session(owner, world.a.doctor.id)
    booked = _send(
        desk, "POST", "/api/v1/appointments", {"session_id": session["id"], "patient_id": asha}
    )
    assert booked.status_code == 201, booked.get_json()
    queue = desk.get("/api/v1/queue").get_json()
    [entry] = [
        a for s in queue["sessions"] for a in s["appointments"] if a["patient"]["id"] == asha
    ]
    assert entry["dues_paise"] == 40000
