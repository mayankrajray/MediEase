"""Google sign-in end to end with the fake provider (M6a-P3; FR-AUTH-07; ADR-0015 3, 4, 6).

The fake runs the real flow: the sealed flow cookie, the state check, the code exchange (the
nonce included), identity matching and the cookies. Only Google itself is skipped.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit

from flask.testing import FlaskClient
from sqlalchemy import text
from werkzeug.test import TestResponse

from mediease_api.domain.identity.membership import Role
from mediease_api.domain.shared.email import EmailAddress
from tests.conftest import UowFactory, seed_staff
from tests.integration.test_portal_http import EMAIL, sign_up

START = "/api/v1/auth/google/start"


def _start(
    client: FlaskClient, intent: str, hint: str | None, next_path: str | None = None
) -> TestResponse:
    query = {"intent": intent}
    if hint is not None:
        query["login_hint"] = hint
    if next_path is not None:
        query["next"] = next_path
    return client.get(f"{START}?{urlencode(query)}")


def google(
    client: FlaskClient, intent: str, hint: str | None, next_path: str | None = None
) -> TestResponse:
    """Start, then follow the fake's redirect to the callback, as a browser would."""
    started = _start(client, intent, hint, next_path)
    assert started.status_code == 302
    assert client.get_cookie("me_oidc", path="/api/v1/auth/google") is not None
    return client.get(started.headers["Location"])


def _reason(resp: TestResponse) -> tuple[str, str]:
    assert resp.status_code == 302
    location = urlsplit(resp.headers["Location"])
    return location.path, parse_qs(location.query)["reason"][0]


def _count(uow_factory: UowFactory, sql: str) -> int:
    with uow_factory() as uow:
        return int(uow._require_open().session.execute(text(sql)).scalar_one())


# --- Patients --------------------------------------------------------------------------------


def test_fr_prt_01_a_first_google_sign_in_creates_a_verified_patient_account(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    resp = google(db_client, "patient", "Asha.Google@example.test")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/portal"
    assert db_client.get_cookie("me_pt_access", path="/api/v1/portal") is not None
    assert db_client.get_cookie("me_access", path="/api") is None  # no staff session
    assert db_client.get_cookie("me_oidc", path="/api/v1/auth/google") is None  # spent

    account = db_client.get("/api/v1/portal/me").get_json()["account"]
    assert account["email"] == "asha.google@example.test"
    assert account["sign_in_method"] == "GOOGLE"
    assert account["email_verified"] is True
    assert account["full_name"] == "Asha Google"

    # The second sign-in finds the same account by Google's sub.
    again = google(db_client.application.test_client(), "patient", "asha.google@example.test")
    assert again.headers["Location"] == "/portal"
    assert _count(uow_factory, "SELECT count(*) FROM patient_accounts") == 1
    assert _count(uow_factory, "SELECT count(*) FROM external_identities") == 1


def test_adr_0015_google_and_a_password_account_with_one_email_are_never_merged(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    sign_up(db_client)
    google(db_client.application.test_client(), "patient", EMAIL)
    assert _count(uow_factory, "SELECT count(*) FROM patient_accounts") == 2
    methods = _count(
        uow_factory,
        f"SELECT count(DISTINCT sign_in_method) FROM patient_accounts WHERE email = '{EMAIL}'",
    )
    assert methods == 2


def test_a_patient_lands_on_a_safe_next_inside_the_portal(db_client: FlaskClient) -> None:
    resp = google(db_client, "patient", "p@example.test", next_path="https://evil.example/x")
    assert resp.headers["Location"] == "/portal"
    resp = google(db_client.application.test_client(), "patient", "p@example.test", "/portal/x?y=1")
    assert resp.headers["Location"] == "/portal/x?y=1"


# --- Staff -----------------------------------------------------------------------------------


def test_fr_auth_07_the_first_google_sign_in_links_the_staff_user_by_verified_email(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory, role=Role.DOCTOR)
    assert user.email is not None
    resp = google(db_client, "staff", user.email.value, next_path="/queue")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/queue"
    assert db_client.get_cookie("me_pt_access", path="/api/v1/portal") is None
    me = db_client.get("/api/v1/me").get_json()
    assert me["user"]["id"] == str(user.id)
    assert [m["role"] for m in me["memberships"]] == ["DOCTOR"]
    with uow_factory() as uow:
        session = uow._require_open().session
        actions = session.execute(
            text("SELECT action, metadata->>'linked' FROM audit_events")
        ).all()
    assert ("staff.signed_in_google", "true") in [tuple(a) for a in actions]


def test_adr_0015_after_linking_staff_are_matched_by_sub_not_by_email(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    first = google(db_client, "staff", user.email.value)
    assert first.headers["Location"] == "/today"
    # The staff address changes at MediEase; the Google account (sub) still signs them in.
    with uow_factory() as uow:
        stored = uow.users.get(user.id, for_update=True)
        assert stored is not None
        stored.email = EmailAddress.parse("moved@example.test")
        uow.users.update(stored)
        uow.commit()
    again = google(db_client.application.test_client(), "staff", user.email.value)
    assert again.headers["Location"] == "/today"
    with uow_factory() as uow:
        session = uow._require_open().session
        linked = session.execute(
            text("SELECT metadata->>'linked' FROM audit_events WHERE action = :a ORDER BY id"),
            {"a": "staff.signed_in_google"},
        ).scalars()
        assert list(linked) == ["true", "false"]  # matched by sub the second time
    assert _count(uow_factory, "SELECT count(*) FROM external_identities") == 1


def test_fr_auth_07_google_never_creates_staff_access(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    resp = google(db_client, "staff", "stranger@example.test")
    assert _reason(resp) == ("/sign-in", "google_no_account")
    assert db_client.get_cookie("me_access", path="/api") is None
    assert _count(uow_factory, "SELECT count(*) FROM users") == 0
    assert _count(uow_factory, "SELECT count(*) FROM external_identities") == 0


def test_adr_0015_platform_ops_may_not_use_google(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    ops = seed_staff(uow_factory, is_platform_ops=True)
    assert ops.email is not None
    assert _reason(google(db_client, "staff", ops.email.value)) == ("/sign-in", "google_no_account")


def test_a_staff_user_without_an_active_membership_is_refused(
    db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    with uow_factory() as uow:
        stored = uow.users.get(user.id, for_update=True)
        assert stored is not None
        stored.disable(now=stored.updated_at)
        uow.users.update(stored)
        uow.commit()
    assert user.email is not None
    assert _reason(google(db_client, "staff", user.email.value)) == (
        "/sign-in",
        "account_disabled",
    )


# --- The flow itself -------------------------------------------------------------------------


def test_adr_0015_a_callback_without_its_flow_cookie_or_with_another_state_fails(
    db_client: FlaskClient,
) -> None:
    started = _start(db_client, "patient", "p@example.test")
    location = started.headers["Location"]
    stranger = db_client.application.test_client()  # no me_oidc cookie
    assert _reason(stranger.get(location)) == ("/portal/sign-in", "google_failed")

    path, _, query = location.partition("?")
    params = parse_qs(query)
    forged = f"{path}?{urlencode({'state': 'patient.other', 'code': params['code'][0]})}"
    assert _reason(db_client.get(forged)) == ("/portal/sign-in", "google_failed")
    # The flow cookie was spent by the failed attempt: replaying the real one fails too.
    assert _reason(db_client.get(location)) == ("/portal/sign-in", "google_failed")


def test_a_cancelled_consent_screen_returns_to_the_sign_in_page(db_client: FlaskClient) -> None:
    started = _start(db_client, "staff", "d@example.test")
    state = parse_qs(urlsplit(started.headers["Location"]).query)["state"][0]
    resp = db_client.get(
        f"/api/v1/auth/google/callback?{urlencode({'state': state, 'error': 'access_denied'})}"
    )
    assert _reason(resp) == ("/sign-in", "google_cancelled")


def test_no_login_hint_with_the_fake_provider_fails_politely(db_client: FlaskClient) -> None:
    assert _reason(google(db_client, "patient", None)) == ("/portal/sign-in", "google_failed")


def test_an_unknown_intent_goes_back_to_the_staff_sign_in(db_client: FlaskClient) -> None:
    assert _reason(db_client.get(f"{START}?intent=admin")) == ("/sign-in", "google_failed")
