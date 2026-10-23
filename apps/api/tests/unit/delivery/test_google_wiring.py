"""Where a Google sign-in may land, and which provider may run where (M6a-P3, ADR-0015)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from mediease_api.adapters.oidc.fake import FakeOidcProvider
from mediease_api.adapters.oidc.google import GoogleOidcProvider
from mediease_api.application.auth.google import GoogleIntent, intent_from_state
from mediease_api.bootstrap import build_oidc
from mediease_api.config.settings import AppSettings
from mediease_api.delivery.http.google import safe_next
from tests.conftest import SetEnv

STAFF, PATIENT = GoogleIntent.STAFF, GoogleIntent.PATIENT


@pytest.mark.parametrize(
    ("raw", "intent", "expected"),
    [
        ("/queue?day=today", STAFF, "/queue?day=today"),
        ("/portal", PATIENT, "/portal"),
        ("/portal/appointments", PATIENT, "/portal/appointments"),
        (None, STAFF, "/today"),
        (None, PATIENT, "/portal"),
        ("https://evil.example/today", STAFF, "/today"),
        ("//evil.example/today", STAFF, "/today"),
        ("/\\evil.example", STAFF, "/today"),
        ("/today\r\nSet-Cookie: x=y", STAFF, "/today"),
        ("javascript:alert(1)", STAFF, "/today"),
        ("/sign-in", STAFF, "/today"),
        ("/portal/sign-in", PATIENT, "/portal"),
        ("/portal/sign-up?x=1", PATIENT, "/portal"),
        # A staff sign-in never lands in the portal, and a patient never outside it.
        ("/portal", STAFF, "/today"),
        ("/today", PATIENT, "/portal"),
        ("/portalx", PATIENT, "/portal"),
        ("/" + "a" * 600, STAFF, "/today"),
    ],
)
def test_adr_0015_next_is_a_same_origin_path_for_the_right_kind_of_session(
    raw: str | None, intent: GoogleIntent, expected: str
) -> None:
    assert safe_next(raw, intent) == expected


def test_the_state_names_the_page_to_return_to() -> None:
    assert intent_from_state("patient.abc") is PATIENT
    assert intent_from_state("staff.abc") is STAFF
    assert intent_from_state("other.abc") is None
    assert intent_from_state(None) is None


@pytest.mark.parametrize("app_env", ["local", "test"])
def test_adr_0015_the_fake_provider_runs_locally(
    app_env: str, set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env({**valid_env, "APP_ENV": app_env})
    assert isinstance(build_oidc(AppSettings()), FakeOidcProvider)  # type: ignore[call-arg]


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_adr_0015_the_fake_provider_is_refused_when_deployed(
    app_env: str, set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env({**valid_env, "APP_ENV": app_env, "COOKIE_SECURE": "true"})
    with pytest.raises(ValueError, match="GOOGLE_OIDC_PROVIDER=fake"):
        build_oidc(AppSettings())  # type: ignore[call-arg]


def test_google_needs_its_client_id_and_secret(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    set_env({**valid_env, "GOOGLE_OIDC_PROVIDER": "google"})
    with pytest.raises(ValidationError) as failure:
        AppSettings()  # type: ignore[call-arg]
    fields = {str(e["loc"][0]) for e in failure.value.errors()}
    assert fields == {"GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"}

    set_env(
        {
            "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.example",
            "GOOGLE_CLIENT_SECRET": "synthetic-google-secret",  # gitleaks:allow
            "APP_ENV": "production",
            "COOKIE_SECURE": "true",
        }
    )
    settings = AppSettings()  # type: ignore[call-arg]
    assert SecretStr("synthetic-google-secret") == settings.GOOGLE_CLIENT_SECRET
    assert isinstance(build_oidc(settings), GoogleOidcProvider)
