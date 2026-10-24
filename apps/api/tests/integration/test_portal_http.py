"""Patient portal accounts end to end against real PostgreSQL (M6a-P3; FR-PRT-01; ADR-0015).

Sign-up, sign-in, lockout, refresh rotation and reuse, sign-out, rate limits and the audit trail,
through the real composition root.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

from flask.testing import FlaskClient
from sqlalchemy import text
from werkzeug.test import TestResponse

from mediease_api.domain.audit.event import ActorType
from mediease_api.domain.jobs.schedule import RetentionCutoffs
from tests.conftest import UowFactory

SIGN_UP = "/api/v1/portal/auth/sign-up"
SIGN_IN = "/api/v1/portal/auth/sign-in"
REFRESH = "/api/v1/portal/auth/refresh"
SIGN_OUT = "/api/v1/portal/auth/sign-out"
ME = "/api/v1/portal/me"
PASSWORD = "synthetic-patient-pass-1"  # gitleaks:allow (synthetic test value)
EMAIL = "asha.patient@example.test"


def sign_up(
    client: FlaskClient, email: str = EMAIL, password: str = PASSWORD, name: str = "Asha Patient"
) -> TestResponse:
    return client.post(SIGN_UP, json={"full_name": name, "email": email, "password": password})


def portal_csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_pt_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def _cookies(resp: TestResponse) -> dict[str, SimpleCookie]:
    parsed = {}
    for header in resp.headers.getlist("Set-Cookie"):
        cookie: SimpleCookie = SimpleCookie()
        cookie.load(header)
        parsed[next(iter(cookie))] = cookie
    return parsed


def _audit(uow_factory: UowFactory) -> list[tuple[str, str, str | None, dict[str, str]]]:
    with uow_factory() as uow:
        rows = uow._require_open().session.execute(
            text(
                "SELECT action, actor_type, entity_type, metadata FROM audit_events "
                "ORDER BY occurred_at, id"
            )
        )
        return [(r[0], r[1], r[2], r[3]) for r in rows]


def test_fr_prt_01_sign_up_creates_an_account_and_sets_only_portal_cookies(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    resp = sign_up(db_client, email="  Asha.Patient@Example.TEST ")

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["account"] == {
        "id": body["account"]["id"],
        "full_name": "Asha Patient",
        "email": EMAIL,
        "sign_in_method": "PASSWORD",
        "email_verified": False,
        "language": "en",
    }
    assert set(body["session"]) == {"access_expires_at", "refresh_expires_at"}
    cookies = _cookies(resp)
    assert set(cookies) == {"me_pt_access", "me_pt_refresh", "me_pt_csrf"}
    for name, path, http_only in [
        ("me_pt_access", "/api/v1/portal", True),
        ("me_pt_refresh", "/api/v1/portal/auth", True),
        ("me_pt_csrf", "/", False),
    ]:
        morsel = cookies[name][name]
        assert morsel["path"] == path
        assert morsel["samesite"] == "Lax"
        assert bool(morsel["httponly"]) is http_only
        assert morsel.value not in resp.get_data(as_text=True)

    me = db_client.get(ME)
    assert me.status_code == 200
    assert me.get_json()["account"]["email"] == EMAIL
    assert me.headers["Cache-Control"] == "no-store"

    trail = _audit(uow_factory)
    assert [(a, t, e) for a, t, e, _ in trail] == [
        ("patient_account.created", ActorType.PATIENT.value, "patient_account"),
        ("patient.signed_in", ActorType.PATIENT.value, "patient_account"),
    ]
    assert all(EMAIL not in str(meta) for *_, meta in trail)  # IDs and enums only


def test_adr_0015_a_second_password_account_for_one_email_is_refused(
    db_client: FlaskClient,
) -> None:
    assert sign_up(db_client).status_code == 201
    again = sign_up(db_client.application.test_client(), email=EMAIL.upper())
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "PRT_EMAIL_TAKEN"


def test_fr_auth_01_the_staff_password_policy_applies_to_patients(db_client: FlaskClient) -> None:
    short = sign_up(db_client, password="short-pass")
    assert short.status_code == 422
    assert short.get_json()["error"]["details"]["fields"][0]["field"] == "password"
    assert "short-pass" not in short.get_data(as_text=True)
    bad_email = sign_up(db_client, email="not-an-email")
    assert bad_email.status_code == 422
    assert sign_up(db_client, name="   ").status_code == 422


def test_fr_prt_01_sign_in_with_the_password_and_a_generic_error_otherwise(
    db_client: FlaskClient,
) -> None:
    sign_up(db_client)
    client = db_client.application.test_client()
    ok = client.post(SIGN_IN, json={"email": EMAIL, "password": PASSWORD})
    assert ok.status_code == 200
    assert ok.get_json()["account"]["email"] == EMAIL

    wrong = client.post(SIGN_IN, json={"email": EMAIL, "password": "not-the-password"})
    unknown = client.post(SIGN_IN, json={"email": "nobody@example.test", "password": PASSWORD})
    for resp in (wrong, unknown):
        assert resp.status_code == 401
        assert resp.get_json()["error"]["code"] == "PRT_INVALID_CREDENTIALS"
    assert wrong.get_json()["error"]["message"] == unknown.get_json()["error"]["message"]


def test_fr_auth_04_five_wrong_passwords_lock_a_patient(db_client: FlaskClient) -> None:
    sign_up(db_client)
    client = db_client.application.test_client()
    for _ in range(5):
        client.post(SIGN_IN, json={"email": EMAIL, "password": "not-the-password"})
    locked = client.post(SIGN_IN, json={"email": EMAIL, "password": PASSWORD})
    assert locked.status_code == 423
    assert locked.get_json()["error"]["code"] == "AUTH_LOCKED"
    assert int(locked.headers["Retry-After"]) > 0


def test_fr_auth_02_portal_refresh_rotates_and_reuse_ends_the_session(
    db_client: FlaskClient,
) -> None:
    sign_up(db_client)
    first = db_client.get_cookie("me_pt_refresh", path="/api/v1/portal/auth")
    assert first is not None
    rotated = db_client.post(REFRESH, headers=portal_csrf(db_client))
    assert rotated.status_code == 200

    thief = db_client.application.test_client()
    thief.set_cookie("me_pt_refresh", first.value, path="/api/v1/portal/auth")
    thief.set_cookie("me_pt_csrf", "thief", path="/")
    reused = thief.post(REFRESH, headers={"X-CSRF-Token": "thief"})
    assert reused.status_code == 401
    assert reused.get_json()["error"]["code"] == "AUTH_REFRESH_REUSED"
    # The whole family is revoked: the legitimate session ends too, at its next request.
    assert db_client.get(ME).status_code == 401


def test_portal_refresh_and_sign_out_need_the_portal_csrf_token(db_client: FlaskClient) -> None:
    sign_up(db_client)
    assert db_client.post(REFRESH).status_code == 403
    assert db_client.post(SIGN_OUT).status_code == 403
    out = db_client.post(SIGN_OUT, headers=portal_csrf(db_client))
    assert out.status_code == 204
    assert db_client.get(ME).status_code == 401
    assert db_client.post(REFRESH).get_json()["error"]["code"] == "AUTH_SESSION_EXPIRED"


def test_portal_me_without_a_session_is_401(db_client: FlaskClient) -> None:
    resp = db_client.get(ME)
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "AUTH_SESSION_EXPIRED"


def test_adr_0015_sign_up_is_rate_limited_per_caller(db_client: FlaskClient) -> None:
    # 21 attempts: even if a minute boundary splits them, one window holds more than 10.
    responses = [
        sign_up(db_client.application.test_client(), email=f"p{n}@example.test") for n in range(21)
    ]
    codes = [r.status_code for r in responses]
    assert set(codes) == {201, 429}
    assert codes.count(201) <= 20
    limited = next(r for r in responses if r.status_code == 429)
    assert limited.get_json()["error"]["code"] == "AUTH_RATE_LIMITED"
    assert 0 < int(limited.headers["Retry-After"]) <= 60


def test_expired_portal_sessions_are_purged_like_staff_ones(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    sign_up(db_client)
    with uow_factory() as uow:
        session = uow._require_open().session
        assert (
            session.execute(text("SELECT count(*) FROM patient_refresh_tokens")).scalar_one() == 1
        )
        # A cutoff after every token's expiry: the purge removes the portal token too.
        far = datetime.now(UTC) + timedelta(days=400)
        counts = uow.retention.purge(
            RetentionCutoffs(
                refresh_tokens=far, patient_links=far, finished_jobs=far, dead_jobs=far
            )
        )
        uow.commit()
    assert counts.refresh_tokens == 1
    with uow_factory() as uow:
        session = uow._require_open().session
        assert (
            session.execute(text("SELECT count(*) FROM patient_refresh_tokens")).scalar_one() == 0
        )
