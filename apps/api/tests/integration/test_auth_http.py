"""Auth endpoints end to end against real PostgreSQL (FR-AUTH-01/02/04; spec R1-R5, AC1, AC2).

Drives the real composition root: Flask routes, CSRF hook, cookies, use
cases, SQLAlchemy repositories and Argon2id (with minimal cost parameters).
"""

from __future__ import annotations

from http.cookies import SimpleCookie

import pytest
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.user import User
from tests.conftest import DEMO_PASSWORD, UowFactory, make_db_app, seed_staff

SIGN_IN = "/api/v1/auth/sign-in"
REFRESH = "/api/v1/auth/refresh"
SIGN_OUT = "/api/v1/auth/sign-out"


def _sign_in(client: FlaskClient, identifier: str, password: str = DEMO_PASSWORD) -> TestResponse:
    return client.post(SIGN_IN, json={"identifier": identifier, "password": password})


def _email(user: User) -> str:
    assert user.email is not None
    return user.email.value


def _cookies(resp: TestResponse) -> dict[str, SimpleCookie]:
    parsed = {}
    for header in resp.headers.getlist("Set-Cookie"):
        cookie: SimpleCookie = SimpleCookie()
        cookie.load(header)
        parsed[next(iter(cookie))] = cookie
    return parsed


def _cookie(client: FlaskClient, name: str, path: str) -> str:
    cookie = client.get_cookie(name, path=path)
    assert cookie is not None, name
    return cookie.value


def _csrf(client: FlaskClient) -> dict[str, str]:
    return {"X-CSRF-Token": _cookie(client, "me_csrf", "/")}


# --- Sign-in ---------------------------------------------------------------------------------


def test_fr_auth_01_sign_in_sets_cookies_and_returns_no_tokens(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory, role=Role.DOCTOR)
    resp = _sign_in(db_client, _email(user))

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["id"] == str(user.id)
    assert [m["role"] for m in body["memberships"]] == ["DOCTOR"]
    assert set(body["session"]) == {"access_expires_at", "refresh_expires_at"}
    assert resp.headers["Cache-Control"] == "no-store"

    cookies = _cookies(resp)
    assert set(cookies) == {"me_access", "me_refresh", "me_csrf"}
    for name, path, http_only in [
        ("me_access", "/api", True),
        ("me_refresh", "/api/v1/auth", True),
        ("me_csrf", "/", False),
    ]:
        morsel = cookies[name][name]
        assert morsel["path"] == path
        assert morsel["samesite"] == "Lax"
        assert bool(morsel["httponly"]) is http_only
        assert not morsel["secure"]  # COOKIE_SECURE=false locally
        assert morsel.value not in resp.get_data(as_text=True)  # R4: never in the body


def test_r1_sign_in_with_a_phone_number(db_client: FlaskClient, uow_factory: UowFactory) -> None:
    user = seed_staff(uow_factory)
    assert user.phone is not None
    assert _sign_in(db_client, "0" + user.phone.e164[3:]).status_code == 200


def test_cookies_are_secure_when_configured(
    migrated_database_url: str, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    client = make_db_app(migrated_database_url, cookie_secure=True).test_client()
    resp = _sign_in(client, _email(user))
    assert all(c[name]["secure"] for name, c in _cookies(resp).items())


def test_r2_wrong_password_and_unknown_user_look_the_same(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    wrong = _sign_in(db_client, _email(user), "not-the-password")
    unknown = _sign_in(db_client, "nobody@example.test", "not-the-password")

    assert wrong.status_code == unknown.status_code == 401
    w, u = wrong.get_json()["error"], unknown.get_json()["error"]
    assert w["code"] == u["code"] == "AUTH_INVALID_CREDENTIALS"
    assert (w["message"], w["details"]) == (u["message"], u["details"])
    assert "Set-Cookie" not in wrong.headers


def test_ac1_fr_auth_04_sixth_attempt_with_correct_password_is_423(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    for _ in range(5):
        assert _sign_in(db_client, _email(user), "not-the-password").status_code == 401

    resp = _sign_in(db_client, _email(user))
    assert resp.status_code == 423
    assert resp.get_json()["error"]["code"] == "AUTH_LOCKED"
    assert 0 < int(resp.headers["Retry-After"]) <= 900


def test_r7_disabled_user_is_403(db_client: FlaskClient, uow_factory: UowFactory) -> None:
    user = seed_staff(uow_factory)
    with uow_factory() as uow:
        stored = uow.users.get(user.id)
        assert stored is not None
        stored.disable(now=stored.updated_at)
        uow.users.update(stored)
        uow.commit()
    resp = _sign_in(db_client, _email(user))
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "AUTH_ACCOUNT_DISABLED"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"identifier": "owner@example.test"}, "password"),
        ({"password": "x"}, "identifier"),
        ({"identifier": "", "password": "x"}, "identifier"),
        ({"identifier": "a@example.test", "password": "x", "remember": True}, "remember"),
    ],
)
def test_invalid_sign_in_body_is_422_naming_the_field(
    db_client: FlaskClient, body: dict[str, object], field: str
) -> None:
    resp = db_client.post(SIGN_IN, json=body)
    assert resp.status_code == 422
    error = resp.get_json()["error"]
    assert error["code"] == "REQ_VALIDATION_FAILED"
    assert field in [f["field"] for f in error["details"]["fields"]]
    assert "owner@example.test" not in resp.get_data(as_text=True)


def test_sign_in_accepts_only_json(db_client: FlaskClient) -> None:
    resp = db_client.post(SIGN_IN, data={"identifier": "a@example.test", "password": "x"})
    assert resp.status_code == 415
    assert resp.get_json()["error"]["code"] == "REQ_UNSUPPORTED_MEDIA_TYPE"


def test_sign_in_body_must_be_an_object(db_client: FlaskClient) -> None:
    resp = db_client.post(SIGN_IN, json=["not", "an", "object"])
    assert resp.status_code == 422


# --- Refresh and CSRF ------------------------------------------------------------------------


def test_fr_auth_02_refresh_rotates_the_cookies(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    _sign_in(db_client, _email(user))
    first = _cookie(db_client, "me_refresh", "/api/v1/auth")

    resp = db_client.post(REFRESH, headers=_csrf(db_client))
    assert resp.status_code == 200
    assert resp.get_json()["user"]["id"] == str(user.id)
    assert _cookie(db_client, "me_refresh", "/api/v1/auth") != first


def test_refresh_without_the_csrf_header_is_403(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    _sign_in(db_client, _email(user))
    for headers in ({}, {"X-CSRF-Token": "forged"}):
        resp = db_client.post(REFRESH, headers=headers)
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "AUTH_CSRF_INVALID"


def test_refresh_without_a_session_is_401_session_expired(db_client: FlaskClient) -> None:
    resp = db_client.post(REFRESH)
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "AUTH_SESSION_EXPIRED"


def test_ac2_replayed_refresh_token_revokes_the_family(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    _sign_in(db_client, _email(user))
    stolen = _cookie(db_client, "me_refresh", "/api/v1/auth")
    assert db_client.post(REFRESH, headers=_csrf(db_client)).status_code == 200
    newer = _cookie(db_client, "me_refresh", "/api/v1/auth")

    # The attacker replays the rotated token.
    db_client.set_cookie("me_refresh", stolen, path="/api/v1/auth")
    resp = db_client.post(REFRESH, headers=_csrf(db_client))
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "AUTH_REFRESH_REUSED"
    assert all(not c[name].value for name, c in _cookies(resp).items())  # cookies cleared

    # The legitimate holder's newer token stopped working too.
    db_client.set_cookie("me_refresh", newer, path="/api/v1/auth")
    db_client.set_cookie("me_csrf", "restored", path="/")
    resp = db_client.post(REFRESH, headers={"X-CSRF-Token": "restored"})
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "AUTH_SESSION_EXPIRED"


# --- Sign-out --------------------------------------------------------------------------------


def test_fr_auth_02_sign_out_clears_cookies_and_ends_the_session(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    _sign_in(db_client, _email(user))
    token = _cookie(db_client, "me_refresh", "/api/v1/auth")
    csrf = _csrf(db_client)

    resp = db_client.post(SIGN_OUT, headers=csrf)
    assert resp.status_code == 204
    assert set(_cookies(resp)) == {"me_access", "me_refresh", "me_csrf"}
    assert db_client.get_cookie("me_refresh", path="/api/v1/auth") is None

    db_client.set_cookie("me_refresh", token, path="/api/v1/auth")
    db_client.set_cookie("me_csrf", csrf["X-CSRF-Token"], path="/")
    assert db_client.post(REFRESH, headers=csrf).status_code == 401


def test_sign_out_without_a_session_is_204(db_client: FlaskClient) -> None:
    assert db_client.post(SIGN_OUT).status_code == 204


def test_sign_out_needs_csrf_when_signed_in(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    _sign_in(db_client, _email(user))
    assert db_client.post(SIGN_OUT).status_code == 403
