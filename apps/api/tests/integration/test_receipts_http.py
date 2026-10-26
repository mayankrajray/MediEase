"""Receipts over HTTP (M6d-P4; FR-BIL-04; spec billing R43-R54, AC13-AC16).

Real PostgreSQL and the real WeasyPrint renderer.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pypdfium2 as pdfium
import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from tests.conftest import World
from tests.integration.test_appointments_http import _patient
from tests.integration.test_bills_http import BILLS, _code, _draft, _ok
from tests.integration.test_visits_http import _send
from tests.portal_helpers import link_by_invite, portal_client

LINKS = "/api/v1/public/links"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _text(pdf: bytes) -> str:
    doc = pdfium.PdfDocument(pdf)
    try:
        return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    finally:
        doc.close()


def _issued(desk: FlaskClient, patient: str) -> dict[str, Any]:
    bill = _draft(
        desk,
        patient,
        lines=[
            {"description": "Consultation", "unit_price_paise": 50000},
            {"description": "Dressing", "unit_price_paise": 20000},
        ],
        notes="Paid at the desk",
    )
    return _ok(_send(desk, "POST", f"{BILLS}/{bill['id']}/issue"))


def _last4(desk: FlaskClient, patient: str) -> str:
    return str(desk.get(f"/api/v1/patients/{patient}").get_json()["phone_e164"])[-4:]


def test_ac13_r43_r46_the_printed_bill_is_rendered_once_per_state(world: World, db: Engine) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)
    draft = _draft(desk, patient, lines=[{"description": "X", "unit_price_paise": 100}])
    assert _code(desk.get(f"{BILLS}/{draft['id']}/receipt.pdf")) == (409, "BIL_RECEIPT_NOT_READY")

    bill = _issued(desk, patient)
    url = f"{BILLS}/{bill['id']}/receipt.pdf"
    first = desk.get(url)
    assert first.status_code == 200 and first.mimetype == "application/pdf"
    assert first.headers["Cache-Control"] == "no-store"
    text_ = _text(first.data)
    for words in (
        bill["number"],
        "Consultation",
        "Dressing",
        "₹700.00",
        "Balance due",
        "Alpha Sample Clinic",
    ):
        assert words in text_
    assert world.client_for(world.a.owner).get(url).data == first.data  # the stored file

    _ok(
        _send(
            desk,
            "POST",
            f"{BILLS}/{bill['id']}/payments",
            {"mode": "UPI", "amount_paise": 70000, "reference": "UPI-77"},
        ),
        201,
    )
    paid = desk.get(url)
    assert (
        paid.data != first.data
        and "Paid in full" in _text(paid.data)
        and "UPI-77" in _text(paid.data)
    )
    with db.connect() as conn:
        rendered = (
            conn.execute(
                text(
                    "SELECT metadata->>'rendered' FROM audit_events"
                    " WHERE action = 'bill.receipt_downloaded' ORDER BY occurred_at, id"
                )
            )
            .scalars()
            .all()
        )
    assert rendered == ["true", "false", "true"]


def test_ac14_r48_r51_the_receipt_link_with_the_last_4_check(world: World, db: Engine) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)
    bill = _issued(desk, patient)
    link = _ok(desk.get(f"{BILLS}/{bill['id']}/link"))
    assert "/r/" in link["url"] and link["locked"] is False
    assert desk.get(f"{BILLS}/{bill['id']}/link").get_json()["id"] == link["id"]  # one link
    token = link["url"].rsplit("/r/", 1)[1]

    anon = world.anonymous()
    described = _ok(anon.get(f"{LINKS}/{token}"))
    assert (described["purpose"], described["clinic_name"]) == ("RECEIPT", "Alpha Sample Clinic")
    assert _code(anon.get(f"{LINKS}/{token}/receipt")) == (401, "LINK_CHALLENGE_REQUIRED")
    wrong = anon.post(
        f"{LINKS}/{token}/verify",
        json={"phone_last4": "0000" if _last4(desk, patient) != "0000" else "1111"},
    )
    assert _code(wrong) == (401, "LINK_CHALLENGE_FAILED")
    view = _ok(anon.post(f"{LINKS}/{token}/verify", json={"phone_last4": _last4(desk, patient)}))[
        "view_token"
    ]
    headers = {"X-Link-View": view}
    summary = _ok(anon.get(f"{LINKS}/{token}/receipt", headers=headers))
    assert (summary["number"], summary["total_paise"], summary["balance_paise"]) == (
        bill["number"],
        70000,
        70000,
    )
    pdf = anon.get(f"{LINKS}/{token}/receipt.pdf", headers=headers)
    assert pdf.status_code == 200 and bill["number"] in _text(pdf.data)
    assert pdf.data == desk.get(f"{BILLS}/{bill['id']}/receipt.pdf").data  # the same file
    # A receipt token opens no prescription, and a view token of one link opens no other.
    assert _code(anon.get(f"{LINKS}/{token}/prescription", headers=headers)) == (
        404,
        "LINK_INVALID",
    )
    with db.connect() as conn:
        actions = (
            conn.execute(
                text(
                    "SELECT action FROM audit_events WHERE action LIKE 'receipt_link.%'"
                    " ORDER BY occurred_at"
                )
            )
            .scalars()
            .all()
        )
    assert actions == ["receipt_link.created", "receipt_link.opened", "receipt_link.downloaded"]


def test_r51_five_wrong_answers_lock_the_link_and_staff_reset_it(world: World) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)
    bill = _issued(desk, patient)
    token = _ok(desk.get(f"{BILLS}/{bill['id']}/link"))["url"].rsplit("/r/", 1)[1]
    anon = world.anonymous()
    digits = "0000" if _last4(desk, patient) != "0000" else "1111"
    for _ in range(5):
        anon.post(f"{LINKS}/{token}/verify", json={"phone_last4": digits})
    assert _ok(desk.get(f"{BILLS}/{bill['id']}/link"))["locked"] is True
    assert _code(
        anon.post(f"{LINKS}/{token}/verify", json={"phone_last4": _last4(desk, patient)})
    ) == (423, "LINK_LOCKED")
    reset = _ok(_send(desk, "POST", f"{BILLS}/{bill['id']}/link/reset"))
    assert reset["locked"] is False
    assert (
        anon.post(
            f"{LINKS}/{token}/verify", json={"phone_last4": _last4(desk, patient)}
        ).status_code
        == 200
    )
    assert _send(desk, "POST", f"{BILLS}/{bill['id']}/link/reset").status_code == 409  # not locked


def test_ac15_r52_the_portal_lists_a_linked_records_bills_and_their_receipts(world: World) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)
    bill = _issued(desk, patient)
    _draft(desk, patient, lines=[{"description": "Draft", "unit_price_paise": 100}])
    other = _issued(desk, _patient(desk, "Bina Shah"))

    account = portal_client(world, email="asha.bills@example.test")
    link_by_invite(desk, account, patient)
    listed = _ok(account.get("/api/v1/portal/bills"))["items"]
    assert [(b["id"], b["number"], b["balance_paise"]) for b in listed] == [
        (bill["id"], bill["number"], 70000)
    ]
    pdf = account.get(f"/api/v1/portal/bills/{bill['id']}/receipt.pdf")
    assert pdf.status_code == 200 and bill["number"] in _text(pdf.data)
    assert account.get(f"/api/v1/portal/bills/{other['id']}/receipt.pdf").status_code == 404


def test_r21_a_doctor_prints_only_their_own_bills(world: World) -> None:
    desk, doctor = world.client_for(world.a.desk), world.client_for(world.a.doctor_user)
    bill = _issued(desk, _patient(desk))  # no doctor on it
    assert doctor.get(f"{BILLS}/{bill['id']}/receipt.pdf").status_code == 404
    assert doctor.get(f"{BILLS}/{bill['id']}/link").status_code == 404
