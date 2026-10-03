"""Consent, opt-out and opt-in over HTTP on PostgreSQL (M2-P3; FR-PAT-05, 06, FR-MSG-05; AC5)."""

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
SIX_YEARS_OLD = (date.today() - timedelta(days=6 * 365 + 60)).isoformat()


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def _patient(client: FlaskClient, **overrides: Any) -> dict[str, Any]:
    body = {
        "full_name": "Asha Rao",
        "phone": "9000000001",
        "sex": "FEMALE",
        "date_of_birth": "1990-05-17",
        **overrides,
    }
    resp = client.post(PATIENTS, json=body, headers=_csrf(client))
    assert resp.status_code == 201, resp.get_json()
    return dict(resp.get_json())


def _consent(client: FlaskClient, patient_id: str, body: Any) -> TestResponse:
    return client.put(f"{PATIENTS}/{patient_id}/consent", json=body, headers=_csrf(client))


def _opt_out(client: FlaskClient, patient_id: str) -> TestResponse:
    return client.post(f"{PATIENTS}/{patient_id}/opt-out", headers=_csrf(client))


def _opt_in(client: FlaskClient, patient_id: str, body: Any) -> TestResponse:
    return client.post(f"{PATIENTS}/{patient_id}/opt-in", json=body, headers=_csrf(client))


def _audit(
    session_factory: SessionFactory, prefix: str = "patient."
) -> list[tuple[str, dict[str, str]]]:
    with session_factory() as session:
        rows = session.execute(
            text(
                "SELECT action, metadata FROM audit_events WHERE action LIKE :p "
                "AND action NOT IN ('patient.created', 'patient.updated') ORDER BY occurred_at"
            ),
            {"p": f"{prefix}%"},
        )
        return [(row.action, dict(row.metadata)) for row in rows]


def _state(body: dict[str, Any]) -> tuple[bool, bool, bool]:
    return body["whatsapp_allowed"], body["sms_allowed"], body["opted_out"]


def test_p3_a_new_patient_has_not_been_asked(world: World) -> None:
    body = _patient(world.client_for(world.a.desk))

    assert _state(body) == (False, False, False)
    assert body["consent_recorded_at"] is None and body["consent_recorded_by"] is None
    assert body["opted_out_at"] is None


def test_fr_pat_05_recording_consent_says_who_and_when(
    world: World, session_factory: SessionFactory
) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)

    resp = _consent(desk, patient["id"], {"whatsapp": True, "sms": False})

    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-store"
    body = resp.get_json()
    assert (body["whatsapp_consent"], body["sms_consent"]) == (True, False)
    assert _state(body) == (True, False, False)
    assert body["consent_recorded_by"] == str(world.a.desk.id)
    assert body["consent_recorded_at"] is not None
    assert _audit(session_factory) == [
        ("patient.consent_changed", {"whatsapp": "true", "sms": "false", "given_by": "patient"})
    ]


def test_p3_declining_is_recorded_and_differs_from_never_asked(world: World) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)

    body = _consent(desk, patient["id"], {"whatsapp": False, "sms": False}).get_json()

    assert _state(body) == (False, False, False)
    assert body["consent_recorded_at"] is not None  # asked, and said no


def test_fr_pat_06_a_minors_consent_is_recorded_as_the_guardians(
    world: World, session_factory: SessionFactory
) -> None:
    desk = world.client_for(world.a.desk)
    child = _patient(
        desk, full_name="Meera Rao", date_of_birth=SIX_YEARS_OLD, guardian_name="Asha Rao"
    )

    _consent(desk, child["id"], {"whatsapp": True, "sms": True})

    ((action, metadata),) = _audit(session_factory)
    assert action == "patient.consent_changed"
    assert metadata["given_by"] == "guardian"
    assert "Asha" not in str(metadata) and "Meera" not in str(metadata)


def test_ac5_an_opt_out_overrides_consent_until_an_explicit_opt_in(
    world: World, session_factory: SessionFactory
) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)
    _consent(desk, patient["id"], {"whatsapp": True, "sms": True})

    out = _opt_out(desk, patient["id"])
    assert out.status_code == 200
    assert _state(out.get_json()) == (False, False, True)
    assert out.get_json()["opted_out_at"] is not None
    assert out.get_json()["whatsapp_consent"] is True  # the record stays; it has no effect

    # Decision A: consent cannot be edited back on while opted out.
    refused = _consent(desk, patient["id"], {"whatsapp": True, "sms": True})
    assert refused.status_code == 409
    assert refused.get_json()["error"]["code"] == "PAT_OPTED_OUT"
    assert _state(desk.get(f"{PATIENTS}/{patient['id']}").get_json()) == (False, False, True)

    back = _opt_in(desk, patient["id"], {"whatsapp": True, "sms": False})
    assert back.status_code == 200
    assert _state(back.get_json()) == (True, False, False)
    assert back.get_json()["opted_out_at"] is None

    assert [action for action, _ in _audit(session_factory)] == [
        "patient.consent_changed",
        "patient.opted_out",
        "patient.opted_in",
    ]
    assert _audit(session_factory)[1][1] == {"source": "staff"}
    assert _audit(session_factory)[2][1] == {
        "whatsapp": "true",
        "sms": "false",
        "given_by": "patient",
    }


def test_fr_msg_05_opting_out_twice_changes_nothing_and_records_once(
    world: World, session_factory: SessionFactory
) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)

    first = _opt_out(desk, patient["id"]).get_json()
    second = _opt_out(desk, patient["id"])

    assert second.status_code == 200
    assert second.get_json()["opted_out_at"] == first["opted_out_at"]
    assert [action for action, _ in _audit(session_factory)] == ["patient.opted_out"]


def test_opting_in_without_an_opt_out_is_refused(world: World) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)

    resp = _opt_in(desk, patient["id"], {"whatsapp": True, "sms": True})

    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "PAT_NOT_OPTED_OUT"


@pytest.mark.parametrize(
    "body",
    [
        {"whatsapp": True},  # both are required
        {"sms": False},
        {},
        {"whatsapp": "yes", "sms": False},  # booleans only
        {"whatsapp": 1, "sms": 0},
        {"whatsapp": True, "sms": False, "opted_out": False},  # opt-out is its own action
    ],
)
def test_consent_needs_both_flags_as_booleans_and_nothing_else(world: World, body: Any) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)

    assert _consent(desk, patient["id"], body).status_code == 422
    assert _opt_out(desk, patient["id"]).status_code == 200
    assert _opt_in(desk, patient["id"], body).status_code == 422


def test_r9_style_race_an_opt_out_and_a_consent_edit_never_leave_consent_over_an_opt_out(
    world: World,
) -> None:
    desk, owner = world.client_for(world.a.desk), world.client_for(world.a.owner)
    for round_number in range(5):
        patient = _patient(desk, full_name=f"Race {round_number}", phone=f"91000{round_number:05d}")
        # A timeout so a broken test fails in seconds instead of hanging the suite.
        barrier = threading.Barrier(2, timeout=10)

        def opt_out(patient_id: str = patient["id"], barrier: threading.Barrier = barrier) -> int:
            barrier.wait()
            return _opt_out(desk, patient_id).status_code

        def consent(patient_id: str = patient["id"], barrier: threading.Barrier = barrier) -> int:
            barrier.wait()
            return _consent(owner, patient_id, {"whatsapp": True, "sms": True}).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            # Both are submitted before either is awaited, so both reach the barrier.
            out_future, consent_future = pool.submit(opt_out), pool.submit(consent)
            out_status, consent_status = out_future.result(), consent_future.result()

        final = desk.get(f"{PATIENTS}/{patient['id']}").get_json()
        assert out_status == 200 and consent_status in (200, 409)
        # Whichever ran first, the patient ends opted out and not messageable.
        assert _state(final)[2] is True and final["whatsapp_allowed"] is False


@pytest.mark.parametrize("role", list(Role))
def test_fr_auth_03_every_clinic_role_may_record_consent(world: World, role: Role) -> None:
    client = world.client_for(world.a.user_for(role))
    patient = _patient(client, phone="9000000050")

    assert _consent(client, patient["id"], {"whatsapp": True, "sms": True}).status_code == 200
    assert _opt_out(client, patient["id"]).status_code == 200
    assert _opt_in(client, patient["id"], {"whatsapp": False, "sms": True}).status_code == 200


def test_ac7_another_clinics_patient_is_404_on_every_consent_route(world: World) -> None:
    owner_b = world.client_for(world.b.owner)
    theirs = _patient(owner_b)
    desk_a = world.client_for(world.a.desk)

    for resp in (
        _consent(desk_a, theirs["id"], {"whatsapp": True, "sms": True}),
        _opt_out(desk_a, theirs["id"]),
        _opt_in(desk_a, theirs["id"], {"whatsapp": True, "sms": True}),
    ):
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "REQ_NOT_FOUND"
    assert _state(owner_b.get(f"{PATIENTS}/{theirs['id']}").get_json()) == (False, False, False)


def test_r10_ops_users_cannot_record_consent(world: World) -> None:
    ops = world.client_for(world.ops)
    missing = "00000000-0000-0000-0000-000000000001"

    for resp in (
        _consent(ops, missing, {"whatsapp": True, "sms": True}),
        _opt_out(ops, missing),
        _opt_in(ops, missing, {"whatsapp": True, "sms": True}),
    ):
        assert resp.status_code == 403


def test_d5_consent_changes_put_no_names_or_phones_in_the_logs(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk, full_name="Zubin Quillfeather", phone="9123456780")
    capsys.readouterr()

    _consent(desk, patient["id"], {"whatsapp": True, "sms": True})
    _opt_out(desk, patient["id"])
    _opt_in(desk, patient["id"], {"whatsapp": True, "sms": False})

    logged = capsys.readouterr().out
    assert "Zubin" not in logged and "9123456780" not in logged
    assert "patient.opted_out" in logged and "patient_opted_out" in logged
