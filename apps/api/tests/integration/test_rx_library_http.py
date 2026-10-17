"""Favourites, templates and suggestions over HTTP on PostgreSQL (M4-P3; FR-RX-05, 10; R7, AC5).

Decisions 1A-5A. History comes from prescriptions issued through the API (P2), or written
through the repositories for volume (the performance check).
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from mediease_api.domain.prescriptions.prescription import (
    Advice,
    LinkDelivery,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
)
from tests.builders import NOW, new_id
from tests.conftest import UowFactory, World
from tests.integration.test_prescriptions_http import SAMPLE_ITEM, _two_visits
from tests.integration.test_visits_http import _past_visit, _send, _started

FAVOURITES = "/api/v1/rx-favourites"
TEMPLATES = "/api/v1/rx-templates"
SUGGEST = "/api/v1/medicine-suggestions"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _code(resp: TestResponse) -> str:
    return str(resp.get_json()["error"]["code"])


def _issue(doctor: FlaskClient, visit_id: str, items: list[dict[str, Any]], **body: Any) -> str:
    rx = _send(doctor, "POST", f"/api/v1/visits/{visit_id}/prescriptions").get_json()
    saved = _send(
        doctor,
        "PUT",
        f"/api/v1/prescriptions/{rx['id']}",
        {"revision": 1, "items": items, **body},
    )
    assert saved.status_code == 200, saved.get_json()
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert issued.status_code == 200, issued.get_json()
    return str(rx["id"])


def _names(client: FlaskClient, q: str) -> list[tuple[str, str]]:
    resp = client.get(SUGGEST, query_string={"q": q})
    assert resp.status_code == 200, resp.get_json()
    return [(s["name"], s["source"]) for s in resp.get_json()["items"]]


# --- Favourites and templates (FR-RX-05, decision 1A) --------------------------------------------


def test_fr_rx_05_a_doctor_keeps_favourites_with_unique_names_and_revisions(
    world: World, db: Engine
) -> None:
    doctor = world.client_for(world.a.doctor_user)
    created = _send(doctor, "POST", FAVOURITES, {"name": " Fever syrup ", "item": SAMPLE_ITEM})
    assert created.status_code == 201, created.get_json()
    fav = created.get_json()
    assert (fav["name"], fav["revision"], fav["use_count"], fav["item"]["dose"]) == (
        "Fever syrup",
        1,
        0,
        "5 ml",
    )
    assert "id" not in fav["item"]
    same = _send(doctor, "POST", FAVOURITES, {"name": "FEVER  syrup", "item": SAMPLE_ITEM})
    assert (same.status_code, _code(same)) == (409, "RX_NAME_TAKEN")  # case and spaces ignored

    url = f"{FAVOURITES}/{fav['id']}"
    changed = _send(
        doctor,
        "PUT",
        url,
        {"revision": 1, "name": "Fever", "item": {**SAMPLE_ITEM, "dose": "2.5 ml"}},
    )
    assert (changed.status_code, changed.get_json()["revision"]) == (200, 2)
    stale = _send(doctor, "PUT", url, {"revision": 1, "name": "Fever", "item": SAMPLE_ITEM})
    assert (stale.status_code, _code(stale)) == (409, "RX_STALE")
    bad = _send(
        doctor, "POST", FAVOURITES, {"name": "x", "item": {**SAMPLE_ITEM, "frequency": "CUSTOM"}}
    )
    assert bad.get_json()["error"]["details"]["fields"][0]["field"] == "item.frequency_text"

    listed = doctor.get(FAVOURITES).get_json()["items"]
    assert fav["id"] in [f["id"] for f in listed]
    assert _send(doctor, "DELETE", url).status_code == 204
    assert _send(doctor, "DELETE", url).status_code == 404
    with db.connect() as conn:
        actions = list(
            conn.execute(
                text("SELECT action FROM audit_events WHERE entity_type = 'rx_favourite'")
            ).scalars()
        )
    assert actions.count("rx_favourite.created") >= 1 and "rx_favourite.deleted" in actions


def test_templates_hold_a_body_and_the_limits_hold(world: World) -> None:
    doctor = world.client_for(world.a.doctor_user)
    body = {
        "name": "Viral fever",
        "items": [SAMPLE_ITEM, {"medicine_name": "Tab Y"}],
        "advice": {"diet": ["fluids"], "return_if": ["fever above 102"]},
        "follow_up_days": 5,
    }
    created = _send(doctor, "POST", TEMPLATES, body)
    assert created.status_code == 201, created.get_json()
    template = created.get_json()
    assert ([i["medicine_name"] for i in template["items"]], template["follow_up_days"]) == (
        ["Syrup X", "Tab Y"],
        5,
    )
    assert doctor.get(f"{TEMPLATES}/{template['id']}").get_json()["advice"]["diet"] == ["fluids"]
    empty = _send(doctor, "POST", TEMPLATES, {"name": "Nothing"})
    assert (empty.status_code, _code(empty)) == (422, "REQ_VALIDATION_FAILED")
    stale = _send(doctor, "PUT", f"{TEMPLATES}/{template['id']}", {**body, "revision": 5})
    assert (stale.status_code, _code(stale)) == (409, "RX_STALE")


def test_rx_library_full_at_the_limit(world: World, db: Engine) -> None:
    doctor = world.client_for(world.a.doctor_user)
    with db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO rx_templates (id, clinic_id, doctor_id, name, items, created_at,"
                " updated_at) SELECT gen_random_uuid(), :c, :d, 't' || n,"
                ' \'[{"medicine_name": "Tab Y"}]\', now(), now() FROM generate_series(1, 50) n'
            ),
            {"c": str(world.a.clinic.id), "d": str(world.a.doctor.id)},
        )
    full = _send(doctor, "POST", TEMPLATES, {"name": "one more", "items": [{"medicine_name": "X"}]})
    assert (full.status_code, _code(full)) == (409, "RX_LIBRARY_FULL")


def test_d1a_another_doctors_library_is_not_found_and_others_are_refused(
    world: World, uow_factory: UowFactory
) -> None:
    from tests.builders import a_doctor, a_user
    from tests.conftest import CHEAP_HASHER, DEMO_PASSWORD

    doctor = world.client_for(world.a.doctor_user)
    fav = _send(doctor, "POST", FAVOURITES, {"name": "Mine", "item": SAMPLE_ITEM}).get_json()
    other_user = a_user(password_hash=CHEAP_HASHER.hash(DEMO_PASSWORD))
    with uow_factory() as uow:
        from mediease_api.domain.identity.membership import Role
        from tests.builders import a_membership

        uow.users.add(other_user)
        staff = uow.tenant(world.a.clinic.id)
        staff.memberships.add(a_membership(world.a.clinic.id, other_user.id, Role.DOCTOR))
        staff.doctors.add(a_doctor(world.a.clinic.id, user_id=other_user.id))
        uow.commit()
    colleague = world.client_for(other_user)
    assert colleague.get(FAVOURITES).get_json()["items"] == []
    for method, body in (
        ("PUT", {"revision": 1, "name": "x", "item": SAMPLE_ITEM}),
        ("DELETE", None),
    ):
        resp = _send(colleague, method, f"{FAVOURITES}/{fav['id']}", body)
        assert (resp.status_code, _code(resp)) == (404, "REQ_NOT_FOUND")
    # The colleague may reuse the name: names are unique per doctor.
    assert (
        _send(colleague, "POST", FAVOURITES, {"name": "Mine", "item": SAMPLE_ITEM}).status_code
        == 201
    )

    for client in (world.client_for(world.a.desk), world.client_for(world.a.owner)):
        for method, url in (("GET", FAVOURITES), ("GET", TEMPLATES), ("GET", f"{SUGGEST}?q=sy")):
            resp = _send(client, method, url)
            assert (resp.status_code, _code(resp)) == (403, "PERM_DENIED"), url


# --- Suggestions (R7, AC5, decisions 2A, 5A) -----------------------------------------------------


def test_ac5_only_names_this_clinic_issued_are_suggested(world: World) -> None:
    doctor, first, second = _two_visits(world)
    _issue(doctor, first["id"], [{"medicine_name": "Drug P"}])
    # A draft here and an issued prescription in another clinic both name "Drug Q".
    draft = _send(doctor, "POST", f"/api/v1/visits/{second['id']}/prescriptions").get_json()
    _send(
        doctor,
        "PUT",
        f"/api/v1/prescriptions/{draft['id']}",
        {"revision": 1, "items": [{"medicine_name": "Drug Q"}]},
    )
    other_doctor, other_visit = _started_in(world, "b")
    _issue(other_doctor, other_visit["id"], [{"medicine_name": "Drug Q"}])

    assert _names(doctor, "Dru") == [("Drug P", "HISTORY")]
    assert _names(doctor, "dRuG p") == [("Drug P", "HISTORY")]
    assert _names(doctor, "Drug Q") == []
    assert _names(other_doctor, "Dru") == [("Drug Q", "HISTORY")]


def _started_in(world: World, which: str) -> tuple[FlaskClient, dict[str, Any]]:
    """A started visit in clinic ``which`` (``a`` or ``b``)."""
    from tests.integration.test_appointments_http import _patient
    from tests.integration.test_visits_http import _move, _start
    from tests.sessions_now import running_session

    tenant = world.a if which == "a" else world.b
    owner = world.client_for(tenant.owner)
    desk = world.client_for(tenant.desk)
    session = running_session(owner, tenant.doctor.id)
    booked = _send(
        desk,
        "POST",
        "/api/v1/appointments",
        {"session_id": session["id"], "patient_id": _patient(desk)},
    ).get_json()
    _move(desk, booked["id"], "BOOKED", "ARRIVED")
    _move(desk, booked["id"], "ARRIVED", "IN_CONSULTATION")
    doctor = world.client_for(tenant.doctor_user)
    return doctor, _start(doctor, booked["id"]).get_json()


def test_r7_favourites_first_then_history_by_distinct_visits(
    world: World, uow_factory: UowFactory
) -> None:
    doctor, visit = _started(world)
    patient = visit["patient_id"]
    # Syrup Para in three visits (one revised: counts once per visit), Syrup Iron in one.
    for days, names in (
        (10, ["Syrup Para"]),
        (8, ["Syrup Para", "syrup  iron"]),
        (6, ["Syrup Para"]),
    ):
        _issued_past(uow_factory, world, patient, days, names)
    fav = _send(doctor, "POST", FAVOURITES, {"name": "Kof", "item": {"medicine_name": "Syrup Kof"}})
    assert fav.status_code == 201
    ranked = doctor.get(SUGGEST, query_string={"q": "syr"}).get_json()["items"]
    assert [(s["name"], s["source"], s["uses"]) for s in ranked] == [
        ("Syrup Kof", "FAVOURITE", 0),
        ("Syrup Para", "HISTORY", 3),
        ("syrup  iron", "HISTORY", 1),
    ]
    assert ranked[0]["favourite_id"] == fav.get_json()["id"]
    short = doctor.get(SUGGEST, query_string={"q": "s"})
    assert (short.status_code, _code(short)) == (422, "REQ_VALIDATION_FAILED")


def _issued_past(
    uow_factory: UowFactory, world: World, patient_id: str, days_ago: int, names: list[str]
) -> None:
    """An issued prescription on an earlier visit, through the repositories."""
    visit_id = _past_visit(uow_factory, world, patient_id, days_ago)
    at = NOW - timedelta(days=days_ago)
    rx = Prescription(
        id=new_id(),
        clinic_id=world.a.clinic.id,
        visit_id=visit_id,
        patient_id=UUID(patient_id),
        doctor_id=world.a.doctor.id,
        version=1,
        supersedes_id=None,
        status=PrescriptionStatus.DRAFT,
        revision=1,
        items=tuple(
            PrescriptionItem.create(id=new_id(), position=i, medicine_name=n)
            for i, n in enumerate(names, start=1)
        ),
        advice=Advice(),
        follow_up_date=None,
        language=None,
        issued_at=None,
        doctor_snapshot=None,
        clinic_snapshot=None,
        pdf_object_key=None,
        link_delivery=None,
        link_delivery_requested_at=None,
        created_by=world.a.doctor_user.id,
        created_at=at,
        updated_at=at,
    )
    from mediease_api.domain.patients.patient import Language

    with uow_factory() as uow:
        staff = uow.tenant(world.a.clinic.id)
        staff.prescriptions.add(rx)
        rx.issue(
            doctor=staff.doctors.get(world.a.doctor.id),  # type: ignore[arg-type]
            clinic=uow.clinics.get(world.a.clinic.id),  # type: ignore[arg-type]
            language=Language.EN,
            may_message=False,
            seen_revision=1,
            today=at.date(),
            now=at,
        )
        assert rx.link_delivery is LinkDelivery.NOT_CONSENTED
        staff.prescriptions.update(rx)
        uow.commit()


# --- Use counts (decision 3A) --------------------------------------------------------------------


def test_d3a_issuing_counts_each_favourite_and_template_once(world: World, db: Engine) -> None:
    doctor, first, second = _two_visits(world)
    fav = _send(doctor, "POST", FAVOURITES, {"name": "Fever syrup", "item": SAMPLE_ITEM}).get_json()
    template = _send(
        doctor, "POST", TEMPLATES, {"name": "Viral", "items": [SAMPLE_ITEM]}
    ).get_json()
    line = {**SAMPLE_ITEM, "favourite_id": fav["id"]}

    rx = _send(doctor, "POST", f"/api/v1/visits/{first['id']}/prescriptions").get_json()
    url = f"/api/v1/prescriptions/{rx['id']}"
    for revision in (1, 2):  # saving drafts counts nothing
        saved = _send(
            doctor,
            "PUT",
            url,
            {"revision": revision, "items": [line, line], "template_id": template["id"]},
        )
        assert saved.status_code == 200, saved.get_json()
    assert saved.get_json()["template_id"] == template["id"]
    assert saved.get_json()["items"][0]["favourite_id"] == fav["id"]
    assert doctor.get(FAVOURITES).get_json()["items"][0]["use_count"] == 0
    assert _send(doctor, "POST", f"{url}/issue", {"revision": 3}).status_code == 200

    counts = {f["id"]: f["use_count"] for f in doctor.get(FAVOURITES).get_json()["items"]}
    assert counts[fav["id"]] == 1  # two lines from one favourite: one use
    assert doctor.get(f"{TEMPLATES}/{template['id']}").get_json()["use_count"] == 1

    # A deleted favourite leaves the issued prescription as it was, and a later issue naming it
    # simply counts nothing.
    assert _send(doctor, "DELETE", f"{FAVOURITES}/{fav['id']}").status_code == 204
    assert doctor.get(url).get_json()["items"][0]["favourite_id"] == fav["id"]
    _issue(doctor, second["id"], [line])


# --- Performance (design "Tests") ----------------------------------------------------------------


def test_suggestions_over_20000_issued_lines_answer_quickly(world: World, db: Engine) -> None:
    doctor, visit = _started(world)
    with db.begin() as conn:
        params = {
            "c": str(world.a.clinic.id),
            "v": visit["id"],
            "p": visit["patient_id"],
            "d": str(world.a.doctor.id),
            "u": str(world.a.doctor_user.id),
        }
        # 400 issued prescriptions (one visit is enough: the index, not the visits, is measured).
        conn.execute(text("ALTER TABLE prescriptions DISABLE TRIGGER USER"))
        conn.execute(
            text(
                "INSERT INTO prescriptions (id, clinic_id, visit_id, patient_id, doctor_id,"
                " version, supersedes_id, status, advice, language, issued_at, doctor_snapshot,"
                " clinic_snapshot, link_delivery, created_by, created_at, updated_at)"
                " SELECT s.id, :c, :v, :p, :d, s.n, CASE WHEN s.n = 1 THEN NULL ELSE s.id END,"
                " 'SUPERSEDED', '{}', 'en', now(), '{}', '{}', 'NOT_CONSENTED', :u, now(), now()"
                " FROM (SELECT gen_random_uuid() AS id, n FROM generate_series(1, 400) n) s"
            ),
            params,
        )
        conn.execute(text("ALTER TABLE prescription_items DISABLE TRIGGER USER"))
        conn.execute(
            text(
                "INSERT INTO prescription_items (id, clinic_id, prescription_id, position,"
                " medicine_name) SELECT gen_random_uuid(), :c, p.id, n,"
                " (ARRAY['Syrup ', 'Tab ', 'Cap ', 'Drops '])[1 + (n % 4)] || 'Name ' || (n % 997)"
                " FROM prescriptions p, generate_series(1, 50) n WHERE p.visit_id = :v"
            ),
            {"c": params["c"], "v": params["v"]},
        )
        conn.execute(text("ALTER TABLE prescription_items ENABLE TRIGGER USER"))
        conn.execute(text("ALTER TABLE prescriptions ENABLE TRIGGER USER"))
        conn.execute(text("ANALYZE prescription_items"))
        count = conn.execute(text("SELECT count(*) FROM prescription_items")).scalar()
    assert count is not None and count >= 20_000

    timings = []
    for q in ["sy", "syr", "tab n", "cap name 1", "dro"] * 6:
        started = time.perf_counter()
        assert doctor.get(SUGGEST, query_string={"q": q}).status_code == 200
        timings.append(time.perf_counter() - started)
    p95 = statistics.quantiles(timings, n=20)[18]
    assert p95 < 0.15, f"p95 {p95 * 1000:.0f} ms"
