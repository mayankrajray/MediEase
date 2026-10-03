"""Patients over HTTP against a real PostgreSQL (M2-P2; FR-PAT-01..04, spec patients R1-R10).

Covers registration and the duplicate-phone flow, the two-thread race (AC6), gap-free codes
under parallel registrations (AC3), editing, lookup, tenancy (AC7), the role matrix, and the
promise that a patient's name and phone number appear in the response and nowhere else.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.test import TestResponse

from mediease_api.domain.identity.membership import Role
from tests.conftest import World

PATIENTS = "/api/v1/patients"
SessionFactory = sessionmaker[Session]

ADULT_BORN = "1990-05-17"
SIX_YEARS_OLD = (date.today() - timedelta(days=6 * 365 + 60)).isoformat()


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def _register(client: FlaskClient, **overrides: Any) -> TestResponse:
    body: dict[str, Any] = {
        "full_name": "Asha Rao",
        "phone": "9000000001",
        "sex": "FEMALE",
        "date_of_birth": ADULT_BORN,
        **overrides,
    }
    return client.post(PATIENTS, json=body, headers=_csrf(client))


def _edit(client: FlaskClient, patient_id: str, body: dict[str, Any]) -> TestResponse:
    return client.patch(f"{PATIENTS}/{patient_id}", json=body, headers=_csrf(client))


def _codes(world: World) -> tuple[FlaskClient, str]:
    return world.client_for(world.a.desk), world.a.clinic.patient_code_prefix


def _audit(session_factory: SessionFactory, action: str) -> list[dict[str, Any]]:
    with session_factory() as session:
        rows = session.execute(
            text("SELECT * FROM audit_events WHERE action = :a ORDER BY occurred_at"), {"a": action}
        )
        return [dict(row) for row in rows.mappings()]


def _checklist_patients_at(session_factory: SessionFactory, clinic_id: object) -> object:
    with session_factory() as session:
        return session.execute(
            text("SELECT patients_imported_at FROM onboarding_checklists WHERE clinic_id = :c"),
            {"c": clinic_id},
        ).scalar_one_or_none()


# --- Registering (R1-R4, R10) -----------------------------------------------------------------


def test_fr_pat_01_03_registering_an_adult_returns_the_first_clinic_code(world: World) -> None:
    desk, prefix = _codes(world)

    resp = _register(desk, phone="090000 00001")

    assert resp.status_code == 201, resp.get_json()
    assert resp.headers["Cache-Control"] == "no-store"
    body = resp.get_json()
    assert body["code"] == f"{prefix}-0001"
    assert body["phone_e164"] == "+919000000001"  # R1: spaces and the leading 0 are removed
    assert body["full_name"] == "Asha Rao"
    assert (body["sex"], body["language"]) == ("FEMALE", "en")
    assert body["age_years"] >= 35 and body["age_is_estimated"] is False
    assert body["is_minor"] is False and body["guardian_name"] is None
    assert (body["whatsapp_consent"], body["sms_consent"], body["opted_out"]) == (
        False,
        False,
        False,
    )

    second = _register(desk, full_name="Arun Rao", phone="9000000002")
    assert second.get_json()["code"] == f"{prefix}-0002"
    assert resp.get_json()["id"] != second.get_json()["id"]


def test_r3_ac2_a_six_year_old_needs_a_guardian_and_the_phone_is_theirs(world: World) -> None:
    desk, _ = _codes(world)

    refused = _register(desk, full_name="Meera Jr", date_of_birth=SIX_YEARS_OLD)
    assert refused.status_code == 422
    assert refused.get_json()["error"]["code"] == "PAT_GUARDIAN_REQUIRED"

    accepted = _register(
        desk, full_name="Meera Jr", date_of_birth=SIX_YEARS_OLD, guardian_name="Meera Rao"
    )
    assert accepted.status_code == 201
    body = accepted.get_json()
    assert body["is_minor"] is True and body["age_years"] == 6
    assert body["guardian_name"] == "Meera Rao"
    assert body["phone_e164"] == "+919000000001"  # the guardian's number is the contact of record
    # A refusal spends no code: the accepted one is the first.
    assert body["code"].endswith("-0001")


def test_d4_a_patient_registered_by_age_alone_is_an_estimate(world: World) -> None:
    desk, _ = _codes(world)

    body = _register(desk, date_of_birth=None, age_years=34).get_json()

    assert body["age_is_estimated"] is True and body["age_years"] == 34
    assert body["date_of_birth"] is None


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"date_of_birth": None}, "age"),  # neither a date of birth nor an age
        ({"age_years": 30}, "age"),  # both
        ({"date_of_birth": (date.today() + timedelta(days=3)).isoformat()}, "date_of_birth"),
        ({"full_name": "   "}, "full_name"),
    ],
)
def test_i1_i4_bad_demographics_are_422_with_the_field_named(
    world: World, overrides: dict[str, Any], field: str
) -> None:
    desk, _ = _codes(world)

    resp = _register(desk, **overrides)

    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "REQ_VALIDATION_FAILED"
    assert field in {f["field"] for f in resp.get_json()["error"]["details"]["fields"]}


@pytest.mark.parametrize("phone", ["12345", "not a phone", "0000000000", "+911234567890123456"])
def test_r1_an_invalid_phone_is_pat_phone_invalid_without_echoing_it(
    world: World, phone: str
) -> None:
    desk, _ = _codes(world)

    resp = _register(desk, phone=phone)

    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "PAT_PHONE_INVALID"
    assert phone not in resp.get_data(as_text=True)


def test_r10_a_phone_is_required(world: World) -> None:
    desk, _ = _codes(world)

    resp = desk.post(
        PATIENTS,
        json={"full_name": "Asha Rao", "sex": "FEMALE", "date_of_birth": ADULT_BORN},
        headers=_csrf(desk),
    )

    assert resp.status_code == 422
    assert "phone" in {f["field"] for f in resp.get_json()["error"]["details"]["fields"]}


# --- The duplicate-phone flow (R2, R9, AC1, AC6, AC3) -------------------------------------------


def test_ac1_r2_registering_a_shared_phone_lists_who_is_already_on_it(world: World) -> None:
    desk, prefix = _codes(world)
    first = _register(desk, full_name="Asha Rao").get_json()

    resp = _register(desk, full_name="Arun Rao", phone="090000 00001")

    assert resp.status_code == 409
    error = resp.get_json()["error"]
    assert error["code"] == "PAT_PHONE_EXISTS"
    assert error["details"]["candidates"] == [
        {
            "id": first["id"],
            "code": f"{prefix}-0001",
            "full_name": "Asha Rao",
            "age_years": first["age_years"],
        }
    ]


def test_r2_a_refusal_spends_no_code_and_confirm_new_registers_the_family_member(
    world: World,
) -> None:
    desk, prefix = _codes(world)
    _register(desk, full_name="Asha Rao")
    assert _register(desk, full_name="Arun Rao").status_code == 409

    confirmed = _register(desk, full_name="Arun Rao", confirm_new=True)

    assert confirmed.status_code == 201
    assert confirmed.get_json()["code"] == f"{prefix}-0002"  # not -0003: the refusal took nothing
    lookup = desk.get(PATIENTS, query_string={"q": "9000000001"}).get_json()["items"]
    assert [p["full_name"] for p in lookup] == ["Asha Rao", "Arun Rao"]


def test_r2_the_candidate_list_is_capped_at_ten(world: World) -> None:
    desk, _ = _codes(world)
    for n in range(12):
        assert _register(desk, full_name=f"Family Member {n}", confirm_new=True).status_code == 201

    resp = _register(desk, full_name="One More")

    assert resp.status_code == 409
    assert len(resp.get_json()["error"]["details"]["candidates"]) == 10


def test_ac6_r9_two_simultaneous_registrations_of_one_new_phone_have_one_winner(
    world: World,
) -> None:
    clients = [world.client_for(world.a.owner), world.client_for(world.a.desk)]

    for round_number in range(6):
        phone = f"91000{round_number:05d}"
        barrier = threading.Barrier(2)

        def attempt(index: int, phone: str = phone, barrier: threading.Barrier = barrier) -> int:
            barrier.wait()
            return _register(clients[index], full_name=f"Racer {index}", phone=phone).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(attempt, [0, 1]))

        assert statuses == [201, 409], f"round {round_number}: {statuses}"


def test_ac3_parallel_registrations_get_unique_gap_free_codes(world: World) -> None:
    clients = [world.client_for(world.a.desk) for _ in range(6)]
    total = 30

    def register(n: int) -> str:
        resp = _register(
            clients[n % 6], full_name=f"Parallel {n}", phone="9000000001", confirm_new=True
        )
        assert resp.status_code == 201, resp.get_json()
        return str(resp.get_json()["code"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(register, range(total)))

    prefix = world.a.clinic.patient_code_prefix
    assert sorted(codes) == [f"{prefix}-{n:04d}" for n in range(1, total + 1)]


# --- Audit, checklist and personal data (R7, D5, FR-OPS-04) -----------------------------------


def test_fr_aud_01_registration_is_audited_with_the_code_and_no_personal_data(
    world: World, session_factory: SessionFactory
) -> None:
    desk, prefix = _codes(world)

    patient = _register(desk, full_name="Asha Rao", phone="9000000001").get_json()

    (event,) = _audit(session_factory, "patient.created")
    assert event["entity_type"] == "patient" and str(event["entity_id"]) == patient["id"]
    assert str(event["clinic_id"]) == str(world.a.clinic.id)
    assert str(event["actor_user_id"]) == str(world.a.desk.id)
    assert event["request_id"]
    assert event["metadata"] == {"code": f"{prefix}-0001", "confirmed_shared_phone": "false"}
    everything = str(event)
    assert "Asha" not in everything and "9000000001" not in everything


def test_a_confirmed_shared_phone_is_marked_in_the_audit_row(
    world: World, session_factory: SessionFactory
) -> None:
    desk, _ = _codes(world)
    _register(desk)
    _register(desk, full_name="Arun Rao", confirm_new=True)

    flags = [
        e["metadata"]["confirmed_shared_phone"] for e in _audit(session_factory, "patient.created")
    ]

    assert flags == ["false", "true"]


def test_fr_ops_04_the_first_registration_sets_patients_imported_at_and_later_ones_keep_it(
    world: World, session_factory: SessionFactory
) -> None:
    desk, _ = _codes(world)
    assert _checklist_patients_at(session_factory, world.a.clinic.id) is None

    _register(desk)
    first = _checklist_patients_at(session_factory, world.a.clinic.id)
    _register(desk, full_name="Arun Rao", phone="9000000002")

    assert first is not None
    assert _checklist_patients_at(session_factory, world.a.clinic.id) == first


def test_d5_names_and_phones_never_reach_the_logs(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    desk, _ = _codes(world)
    capsys.readouterr()

    created = _register(desk, full_name="Zubin Quillfeather", phone="9123456780").get_json()
    _register(desk, full_name="Other Person", phone="9123456780")  # offered as a duplicate
    _edit(desk, created["id"], {"full_name": "Zubin Q. Quillfeather", "phone": "9123456781"})
    desk.get(PATIENTS, query_string={"q": "Zubin"})
    desk.get(PATIENTS, query_string={"q": "9123456781"})
    desk.get(f"{PATIENTS}/{created['id']}")

    logged = capsys.readouterr().out
    for secret in ("Zubin", "Quillfeather", "Other Person", "9123456780", "9123456781"):
        assert secret not in logged
    assert "patient.created" in logged and "patient.duplicate_phone_offered" in logged


# --- Editing (R7) -----------------------------------------------------------------------------


def test_r7_an_edit_changes_only_what_was_sent_and_audits_field_names_only(
    world: World, session_factory: SessionFactory
) -> None:
    desk, _ = _codes(world)
    patient = _register(desk, full_name="Asha Rao").get_json()

    resp = _edit(desk, patient["id"], {"full_name": "Asha R. Rao", "language": "hi"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert (body["full_name"], body["language"]) == ("Asha R. Rao", "hi")
    assert body["code"] == patient["code"] and body["phone_e164"] == patient["phone_e164"]
    (event,) = _audit(session_factory, "patient.updated")
    assert event["metadata"] == {"fields": "full_name,language"}
    assert "Asha" not in str(event)


def test_r7_an_edit_that_changes_nothing_writes_no_audit_row(
    world: World, session_factory: SessionFactory
) -> None:
    desk, _ = _codes(world)
    patient = _register(desk, full_name="Asha Rao").get_json()

    resp = _edit(desk, patient["id"], {"full_name": "Asha Rao"})

    assert resp.status_code == 200
    assert _audit(session_factory, "patient.updated") == []
    assert resp.get_json()["updated_at"] == patient["updated_at"]


def test_r7_the_age_columns_are_reported_as_one_field(
    world: World, session_factory: SessionFactory
) -> None:
    desk, _ = _codes(world)
    patient = _register(desk).get_json()

    body = _edit(desk, patient["id"], {"age_years": 40}).get_json()

    assert body["age_is_estimated"] is True and body["age_years"] == 40
    (event,) = _audit(session_factory, "patient.updated")
    assert event["metadata"] == {"fields": "age"}


def test_r3_an_edit_cannot_leave_a_minor_without_a_guardian(world: World) -> None:
    desk, _ = _codes(world)
    minor = _register(desk, date_of_birth=SIX_YEARS_OLD, guardian_name="Meera Rao").get_json()

    cleared = _edit(desk, minor["id"], {"guardian_name": ""})
    assert cleared.status_code == 422
    assert cleared.get_json()["error"]["code"] == "PAT_GUARDIAN_REQUIRED"

    aged = _register(desk, full_name="Adult", phone="9000000005").get_json()
    into_childhood = _edit(desk, aged["id"], {"date_of_birth": SIX_YEARS_OLD})
    assert into_childhood.status_code == 422
    assert desk.get(f"{PATIENTS}/{aged['id']}").get_json()["date_of_birth"] == ADULT_BORN


def test_r2_editing_a_phone_onto_a_shared_number_is_allowed(world: World) -> None:
    desk, _ = _codes(world)
    _register(desk, full_name="Asha Rao", phone="9000000001")
    other = _register(desk, full_name="Arun Rao", phone="9000000002").get_json()

    resp = _edit(desk, other["id"], {"phone": "9000000001"})

    assert resp.status_code == 200 and resp.get_json()["phone_e164"] == "+919000000001"


def test_an_edit_with_no_fields_or_a_bad_phone_is_refused(world: World) -> None:
    desk, _ = _codes(world)
    patient = _register(desk).get_json()

    assert _edit(desk, patient["id"], {}).status_code == 422
    bad = _edit(desk, patient["id"], {"phone": "12345"})
    assert bad.status_code == 422 and bad.get_json()["error"]["code"] == "PAT_PHONE_INVALID"
    assert (
        _edit(desk, patient["id"], {"code": "XX-9999"}).status_code == 422
    )  # the code is not editable


# --- Lookup (R5, FR-PAT-04) ---------------------------------------------------------------------


def test_r5_lookup_reads_the_text_as_phone_then_code_then_name_prefix(world: World) -> None:
    desk, prefix = _codes(world)
    asha = _register(desk, full_name="Asha Rao", phone="9000000001").get_json()
    _register(desk, full_name="Arun Rao", phone="9000000001", confirm_new=True)
    _register(desk, full_name="Bina Shah", phone="9000000003")

    def names(text_: str) -> list[str]:
        resp = desk.get(PATIENTS, query_string={"q": text_})
        assert resp.status_code == 200
        return [p["full_name"] for p in resp.get_json()["items"]]

    assert names("+91 90000-00001") == ["Asha Rao", "Arun Rao"]  # a phone: the family
    assert names("09000000001") == ["Asha Rao", "Arun Rao"]
    assert names(f"{prefix.lower()}{asha['code'][-4:]}") == ["Asha Rao"]  # a code, any case
    assert names(asha["code"]) == ["Asha Rao"]
    assert names("a") == ["Arun Rao", "Asha Rao"]  # a name prefix, ordered by name
    assert names("BIN") == ["Bina Shah"]
    assert names("rao") == []  # a prefix, not a substring
    assert names("9000000099") == []
    assert names("1234567") == []  # phone-shaped but not a number: matches nobody
    assert names("   ") == [] and names("") == []


def test_r5_lookup_returns_at_most_twenty(world: World) -> None:
    desk, _ = _codes(world)
    for n in range(25):
        _register(desk, full_name=f"Kumar {n:02d}", phone=f"92000{n:05d}")

    found = desk.get(PATIENTS, query_string={"q": "kum"}).get_json()["items"]

    assert len(found) == 20
    assert [p["full_name"] for p in found] == [f"Kumar {n:02d}" for n in range(20)]


def test_lookup_needs_a_query_and_bounds_its_length(world: World) -> None:
    desk, _ = _codes(world)

    missing = desk.get(PATIENTS)
    assert missing.status_code == 422
    assert missing.get_json()["error"]["details"]["fields"] == [
        {"field": "q", "reason": "is required"}
    ]
    assert desk.get(PATIENTS, query_string={"q": "x" * 101}).status_code == 422


def test_a_patient_can_be_read_by_id(world: World) -> None:
    desk, _ = _codes(world)
    patient = _register(desk).get_json()

    resp = desk.get(f"{PATIENTS}/{patient['id']}")

    assert resp.status_code == 200 and resp.get_json() == patient
    assert desk.get(f"{PATIENTS}/00000000-0000-0000-0000-000000000001").status_code == 404


# --- Tenancy and roles (NFR-08, AC7, R10) ------------------------------------------------------


def test_ac7_nfr_08_another_clinics_patients_are_invisible_by_every_route(world: World) -> None:
    desk_a, _ = _codes(world)
    owner_b = world.client_for(world.b.owner)
    theirs = _register(owner_b, full_name="Asha Rao", phone="9000000001").get_json()
    mine = _register(desk_a, full_name="Asha Rao", phone="9000000001").get_json()

    # A's staff get their own patient on the same phone, name and (prefixed) code shape ...
    for text_ in ("9000000001", "Asha", mine["code"]):
        found = desk_a.get(PATIENTS, query_string={"q": text_}).get_json()["items"]
        assert [p["id"] for p in found] == [mine["id"]]
    # ... and B's patient by ID is simply absent, for reading and for editing.
    assert desk_a.get(f"{PATIENTS}/{theirs['id']}").status_code == 404
    forged = _edit(desk_a, theirs["id"], {"full_name": "Hijacked"})
    assert forged.status_code == 404
    assert forged.get_json()["error"]["code"] == "REQ_NOT_FOUND"
    assert owner_b.get(f"{PATIENTS}/{theirs['id']}").get_json()["full_name"] == "Asha Rao"
    # Registering the same phone in another clinic is not a duplicate.
    assert _register(desk_a, full_name="Asha Rao", phone="9000000001").status_code == 409
    assert (
        _register(
            world.client_for(world.b.desk), full_name="Someone", phone="9000000077"
        ).status_code
        == 201
    )


@pytest.mark.parametrize("role", list(Role))
def test_fr_auth_03_every_clinic_role_can_register_look_up_and_edit(
    world: World, role: Role
) -> None:
    client = world.client_for(world.a.user_for(role))

    created = _register(client, full_name=f"By {role.value}", phone="9000000010")
    assert created.status_code == 201
    patient_id = created.get_json()["id"]
    assert client.get(PATIENTS, query_string={"q": "by"}).status_code == 200
    assert _edit(client, patient_id, {"sex": "OTHER"}).status_code == 200
    assert client.get(f"{PATIENTS}/{patient_id}").status_code == 200


def test_r10_ops_users_cannot_browse_or_register_patients(world: World) -> None:
    ops_client = world.client_for(world.ops)

    for resp in (
        ops_client.get(PATIENTS, query_string={"q": "a"}),
        _register(ops_client),
        ops_client.get(f"{PATIENTS}/00000000-0000-0000-0000-000000000001"),
    ):
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "PERM_DENIED"


@pytest.mark.parametrize("method", ["get", "post"])
def test_signed_out_requests_are_401(world: World, method: str) -> None:
    resp = getattr(world.anonymous(), method)(PATIENTS, query_string={"q": "a"})
    assert resp.status_code == 401
