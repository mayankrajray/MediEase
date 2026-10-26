"""Bills and credit notes over HTTP (M6d-P2; FR-BIL-02, 07; spec billing R13-R30, AC4-AC8).

Real PostgreSQL. Completed visits are written through the repositories (``_past_visit``).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from mediease_api.domain.billing.bill import financial_year
from tests.builders import a_doctor
from tests.conftest import UowFactory, World
from tests.integration.test_appointments_http import _in_parallel, _patient
from tests.integration.test_visits_http import _past_visit, _send

BILLS = "/api/v1/clinic/bills"
FEES = "/api/v1/clinic/fees"
SENTINEL = "SENTINEL-clinical-7f3a"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _ok(resp: TestResponse, status: int = 200) -> dict[str, Any]:
    assert resp.status_code == status, resp.get_json()
    body: dict[str, Any] = resp.get_json()
    return body


def _code(resp: TestResponse) -> tuple[int, str]:
    return resp.status_code, str(resp.get_json()["error"]["code"])


def _priced_consultation(owner: FlaskClient, paise: int = 50000) -> str:
    body = _ok(
        _send(
            owner,
            "POST",
            f"{FEES}/services",
            {"name": "Consultation", "kind": "CONSULTATION", "default_price_paise": paise},
        ),
        201,
    )
    return str(next(s["id"] for s in body["services"] if s["name"] == "Consultation"))


def _year() -> str:
    return financial_year(datetime.now(ZoneInfo("Asia/Kolkata")).date())


def _draft(client: FlaskClient, patient: str, **body: Any) -> dict[str, Any]:
    return _ok(_send(client, "POST", BILLS, {"patient_id": patient, **body}), 201)


def test_ac4_a_completed_visits_bill_starts_with_the_doctors_consultation_and_is_numbered(
    world: World, uow_factory: UowFactory, db: Engine
) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    _priced_consultation(owner)
    patient = _patient(desk)
    visit = _past_visit(uow_factory, world, patient, days_ago=0)

    bill = _draft(desk, patient, visit_id=str(visit))
    assert (bill["status"], bill["number"], bill["doctor"]["id"]) == (
        "DRAFT",
        None,
        str(world.a.doctor.id),
    )
    assert [(line["description"], line["amount_paise"]) for line in bill["lines"]] == [
        ("Consultation", 50000)
    ]
    assert bill["patient"]["code"] and bill["balance_paise"] is None

    # R14: one open bill per visit.
    again = _send(desk, "POST", BILLS, {"patient_id": patient, "visit_id": str(visit)})
    assert _code(again) == (409, "BIL_VISIT_BILLED")
    assert again.get_json()["error"]["details"] == {"bill_id": bill["id"]}

    issued = _ok(_send(desk, "POST", f"{BILLS}/{bill['id']}/issue"))
    prefix = world.a.clinic.patient_code_prefix
    assert issued["number"] == f"{prefix}/{_year()}/0001"
    assert (issued["status"], issued["balance_paise"]) == ("ISSUED", 50000)
    second = _draft(
        desk, _patient(desk, "Bina Shah"), lines=[{"description": "X", "unit_price_paise": 100}]
    )
    assert _ok(_send(desk, "POST", f"{BILLS}/{second['id']}/issue"))["number"] == (
        f"{prefix}/{_year()}/0002"
    )

    # R13: nothing clinical from the visit reaches the bill, its log or its audit rows.
    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE action LIKE 'bill.%'")
        ).all()
    assert {r[0] for r in rows} == {"bill.drafted", "bill.issued"}
    assert all("diagnosis" not in r[1] and "complaint" not in r[1] for r in rows)
    assert "earlier diagnosis" not in desk.get(f"{BILLS}/{bill['id']}").text


def test_r15_r16_lines_from_the_schedule_discounts_and_typed_lines(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    consultation = _priced_consultation(owner)
    bill = _draft(
        desk,
        _patient(desk),
        doctor_id=str(world.a.doctor.id),
        lines=[
            {"service_id": consultation},
            {
                "description": "Dressing",
                "unit_price_paise": 15000,
                "quantity": 2,
                "discount": {"kind": "AMOUNT", "value": 5000},
            },
        ],
        discount={"kind": "PERCENT", "value": 1000},
        notes="Senior citizen",
    )
    assert (bill["subtotal_paise"], bill["discount_paise"], bill["total_paise"]) == (
        75000,
        7500,
        67500,
    )
    assert sum(line["amount_paise"] for line in bill["lines"]) == 67500

    unknown = {
        "patient_id": bill["patient"]["id"],
        "lines": [{"service_id": str(world.b.doctor.id)}],
    }
    refused = _send(desk, "POST", BILLS, unknown)
    assert _code(refused) == (422, "REQ_VALIDATION_FAILED")
    unpriced = _send(owner, "POST", f"{FEES}/services", {"name": "Review", "kind": "OTHER"})
    review = next(s["id"] for s in unpriced.get_json()["services"] if s["name"] == "Review")
    no_price = {"patient_id": bill["patient"]["id"], "lines": [{"service_id": review}]}
    assert _code(_send(desk, "POST", BILLS, no_price)) == (422, "REQ_VALIDATION_FAILED")
    too_much = {
        "patient_id": bill["patient"]["id"],
        "lines": [{"description": "X", "unit_price_paise": 10_000_001}],
    }
    assert _send(desk, "POST", BILLS, too_much).status_code == 422


def test_ac5_r18_r19_a_draft_changes_or_is_discarded_and_an_issued_bill_never_changes(
    world: World,
) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)
    bill = _draft(desk, patient, lines=[{"description": "Consultation", "unit_price_paise": 50000}])
    url = f"{BILLS}/{bill['id']}"
    changed = _ok(
        _send(
            desk,
            "PUT",
            url,
            {"lines": [{"description": "Follow-up", "unit_price_paise": 30000}], "notes": "Paid"},
        )
    )
    assert (changed["total_paise"], changed["notes"], changed["lines"][0]["description"]) == (
        30000,
        "Paid",
        "Follow-up",
    )
    assert _send(desk, "DELETE", url).status_code == 204
    assert desk.get(url).status_code == 404

    kept = _draft(desk, patient, lines=[{"description": "Consultation", "unit_price_paise": 500}])
    kept_url = f"{BILLS}/{kept['id']}"
    _ok(_send(desk, "POST", f"{kept_url}/issue"))
    assert _code(_send(desk, "PUT", kept_url, {"lines": []})) == (409, "BIL_NOT_DRAFT")
    assert _code(_send(desk, "DELETE", kept_url)) == (409, "BIL_NOT_DRAFT")
    assert _code(_send(desk, "POST", f"{kept_url}/issue")) == (409, "BIL_NOT_DRAFT")

    empty = _draft(desk, patient, lines=[])
    assert _code(_send(desk, "POST", f"{BILLS}/{empty['id']}/issue")) == (409, "BIL_EMPTY")


def test_ac6_r23_r26_credit_notes_reverse_lines_once_and_cancel_the_bill(
    world: World, uow_factory: UowFactory
) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)
    visit = _past_visit(uow_factory, world, patient, days_ago=1)
    bill = _draft(
        desk,
        patient,
        visit_id=str(visit),
        lines=[
            {"description": "Consultation", "unit_price_paise": 50000},
            {"description": "Dressing", "unit_price_paise": 20000},
        ],
    )
    url = f"{BILLS}/{bill['id']}"
    assert _code(_send(desk, "POST", f"{url}/credit-notes", {"reason": "x"})) == (
        409,
        "BIL_NOT_ISSUED",
    )
    issued = _ok(_send(desk, "POST", f"{url}/issue"))
    dressing = issued["lines"][1]["id"]

    partly = _ok(
        _send(desk, "POST", f"{url}/credit-notes", {"line_ids": [dressing], "reason": "Not done"}),
        201,
    )
    [note] = partly["credit_notes"]
    prefix = world.a.clinic.patient_code_prefix
    assert note["number"] == f"{prefix}/CN/{_year()}/0001"
    assert (note["total_paise"], note["lines"][0]["credits_line_id"]) == (20000, dressing)
    assert (partly["status"], partly["credited_paise"], partly["balance_paise"]) == (
        "ISSUED",
        20000,
        50000,
    )
    assert [line["credited"] for line in partly["lines"]] == [False, True]
    again = {"line_ids": [dressing], "reason": "Twice"}
    assert _code(_send(desk, "POST", f"{url}/credit-notes", again)) == (
        409,
        "BIL_LINE_ALREADY_CREDITED",
    )

    cancelled = _ok(_send(desk, "POST", f"{url}/credit-notes", {"reason": "Wrong patient"}), 201)
    assert (cancelled["status"], cancelled["balance_paise"], len(cancelled["credit_notes"])) == (
        "CANCELLED",
        0,
        2,
    )
    assert cancelled["credit_notes"][1]["number"] == f"{prefix}/CN/{_year()}/0002"
    # R14: a cancelled bill frees its visit for a new one.
    _draft(desk, patient, visit_id=str(visit))
    listed = desk.get(f"{BILLS}?status=CANCELLED").get_json()["items"]
    assert [b["id"] for b in listed] == [bill["id"]]


def test_ac7_r21_a_doctor_bills_only_their_own_and_sees_only_theirs(
    world: World, uow_factory: UowFactory
) -> None:
    desk, doctor = world.client_for(world.a.desk), world.client_for(world.a.doctor_user)
    other = a_doctor(world.a.clinic.id, display_name="Dr. Other Sample")
    with uow_factory() as uow:
        uow.tenant(world.a.clinic.id).doctors.add(other)
        uow.commit()
    patient = _patient(desk)
    line = [{"description": "Consultation", "unit_price_paise": 500}]
    theirs = _draft(desk, patient, doctor_id=str(other.id), lines=line)
    mine = _draft(doctor, patient, lines=line)
    assert mine["doctor"]["id"] == str(world.a.doctor.id)

    assert doctor.get(f"{BILLS}/{theirs['id']}").status_code == 404
    assert [b["id"] for b in doctor.get(BILLS).get_json()["items"]] == [mine["id"]]
    assert {b["id"] for b in desk.get(BILLS).get_json()["items"]} == {mine["id"], theirs["id"]}
    for_other = {"patient_id": patient, "doctor_id": str(other.id), "lines": line}
    assert _code(_send(doctor, "POST", BILLS, for_other)) == (403, "BIL_NOT_YOURS")
    assert _code(doctor.get(f"{BILLS}?doctor_id={other.id}")) == (403, "BIL_NOT_YOURS")
    move = {"lines": line, "doctor_id": str(other.id)}
    assert _send(doctor, "PUT", f"{BILLS}/{mine['id']}", move).status_code == 422


def test_r22_the_list_pages_newest_first_and_filters_by_patient(world: World) -> None:
    desk = world.client_for(world.a.desk)
    asha, bina = _patient(desk), _patient(desk, "Bina Shah")
    line = [{"description": "Consultation", "unit_price_paise": 500}]
    made = [_draft(desk, asha, lines=line)["id"] for _ in range(52)]
    _draft(desk, bina, lines=line)
    first = desk.get(f"{BILLS}?patient_id={asha}").get_json()
    assert [b["id"] for b in first["items"]] == list(reversed(made))[:50]
    rest = desk.get(f"{BILLS}?patient_id={asha}&cursor={first['next_cursor']}").get_json()
    assert [b["id"] for b in rest["items"]] == list(reversed(made))[50:]
    assert rest["next_cursor"] is None
    assert desk.get(f"{BILLS}?cursor=nonsense").status_code == 422
    assert desk.get(f"{BILLS}?status=PAID").status_code == 422


def test_b5_two_issues_at_once_get_two_numbers(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    patient = _patient(desk)
    line = [{"description": "Consultation", "unit_price_paise": 500}]
    ids = [_draft(desk, patient, lines=line)["id"] for _ in range(2)]
    results = _in_parallel(
        [
            lambda: _send(owner, "POST", f"{BILLS}/{ids[0]}/issue"),
            lambda: _send(desk, "POST", f"{BILLS}/{ids[1]}/issue"),
        ]
    )
    numbers = sorted(r.get_json()["number"] for r in results)
    prefix = world.a.clinic.patient_code_prefix
    assert numbers == [f"{prefix}/{_year()}/0001", f"{prefix}/{_year()}/0002"]


def test_r21_an_open_visit_cannot_be_billed_and_another_patients_visit_is_refused(
    world: World, uow_factory: UowFactory, db: Engine
) -> None:
    desk = world.client_for(world.a.desk)
    asha, bina = _patient(desk), _patient(desk, "Bina Shah")
    visit = _past_visit(uow_factory, world, asha, days_ago=2)
    wrong = {"patient_id": bina, "visit_id": str(visit)}
    assert _code(_send(desk, "POST", BILLS, wrong)) == (422, "REQ_VALIDATION_FAILED")
    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE visits SET status = 'OPEN', completed_at = NULL, locked_at = NULL"
                " WHERE id = :v"
            ),
            {"v": visit},
        )
    open_ = {"patient_id": asha, "visit_id": str(visit)}
    assert _code(_send(desk, "POST", BILLS, open_)) == (409, "BIL_VISIT_NOT_COMPLETED")
    assert _send(desk, "POST", BILLS, {"patient_id": str(UUID(int=1))}).status_code == 404
