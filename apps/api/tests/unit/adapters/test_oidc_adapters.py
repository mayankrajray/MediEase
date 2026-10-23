"""Google ID token checks, the fake provider and the flow cookie (M6a-P3, ADR-0015 3, 6).

Signed with throwaway RSA keys and served from an in-memory JWKS: no network.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mediease_api.adapters.oidc.fake import FakeOidcProvider
from mediease_api.adapters.oidc.google import (
    AUTHORIZATION_ENDPOINT,
    JWKS_URI,
    TOKEN_ENDPOINT,
    GoogleOidcProvider,
)
from mediease_api.adapters.security.jwt_flow import JwtFlowSealer
from mediease_api.adapters.security.jwt_tokens import JwtAccessTokenIssuer
from mediease_api.application.auth.google import pkce_challenge
from mediease_api.ports.oidc import OidcFailed
from mediease_api.ports.security import InvalidFlow
from tests.builders import NOW, new_id

CLIENT_ID = "client-123.apps.googleusercontent.example"
NONCE = "nonce-abc"
KEY = "test-only-signing-key-0123456789abcdef"


def _rsa() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


_PRIVATE = _rsa()
_OTHER = _rsa()


def _jwk(private: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    return {**public, "kid": kid, "alg": "RS256", "use": "sig"}


def _id_token(*, private: rsa.RSAPrivateKey = _PRIVATE, kid: str = "k1", **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1098765",
        "email": "asha.patient@example.test",
        "email_verified": True,
        "name": "Asha Patient",
        "nonce": NONCE,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": kid})


class FakeGoogle:
    """The token and JWKS endpoints, recording calls."""

    def __init__(self, keys: list[dict[str, Any]]) -> None:
        self.keys = keys
        self.token_response: tuple[int, bytes] = (200, b"{}")
        self.calls: list[tuple[str, str, Mapping[str, str] | None]] = []

    def __call__(self, method: str, url: str, form: Mapping[str, str] | None) -> tuple[int, bytes]:
        self.calls.append((method, url, form))
        if url == JWKS_URI:
            return 200, json.dumps({"keys": self.keys}).encode()
        assert url == TOKEN_ENDPOINT
        return self.token_response


def _provider(google: FakeGoogle) -> GoogleOidcProvider:
    return GoogleOidcProvider(client_id=CLIENT_ID, client_secret="secret", transport=google)


def test_adr_0015_authorization_url_uses_pkce_s256_and_our_client() -> None:
    url = _provider(FakeGoogle([])).authorization_url(
        state="staff.s",
        nonce=NONCE,
        code_challenge="challenge",
        redirect_uri="https://app.example/api/v1/auth/google/callback",
        login_hint="doctor@example.test",
    )
    base, _, query = url.partition("?")
    params = dict(urllib.parse.parse_qsl(query))
    assert base == AUTHORIZATION_ENDPOINT
    assert params["code_challenge_method"] == "S256"
    assert params["client_id"] == CLIENT_ID
    assert params["scope"] == "openid email profile"
    assert params["login_hint"] == "doctor@example.test"
    assert params["state"] == "staff.s" and params["nonce"] == NONCE


def test_adr_0015_a_valid_id_token_from_the_code_exchange_is_accepted() -> None:
    google = FakeGoogle([_jwk(_PRIVATE, "k1")])
    google.token_response = (200, json.dumps({"id_token": _id_token()}).encode())
    identity = _provider(google).exchange(
        code="c", code_verifier="v", redirect_uri="https://app.example/cb", nonce=NONCE
    )
    assert identity.subject == "1098765"
    assert identity.email == "asha.patient@example.test"
    assert identity.email_verified
    assert identity.name == "Asha Patient"
    form = google.calls[0][2]
    assert form is not None and form["code_verifier"] == "v"
    assert form["grant_type"] == "authorization_code"


@pytest.mark.parametrize(
    ("token", "reason"),
    [
        (lambda: _id_token(private=_OTHER), "id_token_invalid"),  # wrong signature
        (lambda: _id_token(iss="https://evil.example"), "id_token_invalid"),
        (lambda: _id_token(aud="someone-else"), "id_token_invalid"),
        (lambda: _id_token(exp=int(time.time()) - 120), "id_token_invalid"),
        (lambda: _id_token(nonce="other"), "nonce_mismatch"),
        (lambda: _id_token(nonce=None), "nonce_mismatch"),
        (lambda: _id_token(kid="unknown"), "id_token_unknown_kid"),
        (lambda: "not-a-jwt", "id_token_malformed"),
    ],
)
def test_adr_0015_each_id_token_check_refuses(token: Any, reason: str) -> None:
    provider = _provider(FakeGoogle([_jwk(_PRIVATE, "k1")]))
    with pytest.raises(OidcFailed) as failure:
        provider.verify_id_token(token(), nonce=NONCE)
    assert failure.value.reason == reason


def test_adr_0015_an_hs256_token_is_refused_before_any_key_is_used() -> None:
    forged = jwt.encode({"sub": "x"}, "secret-secret-secret-secret-secret", algorithm="HS256")
    with pytest.raises(OidcFailed) as failure:
        _provider(FakeGoogle([])).verify_id_token(forged, nonce=NONCE)
    assert failure.value.reason == "id_token_algorithm"


def test_unverified_email_is_reported_not_trusted() -> None:
    provider = _provider(FakeGoogle([_jwk(_PRIVATE, "k1")]))
    identity = provider.verify_id_token(_id_token(email_verified=False), nonce=NONCE)
    assert identity.email_verified is False


def test_a_rotated_key_is_fetched_again_once() -> None:
    google = FakeGoogle([_jwk(_OTHER, "old")])
    provider = _provider(google)
    with pytest.raises(OidcFailed):
        provider.verify_id_token(_id_token(private=_OTHER, kid="old", aud="x"), nonce=NONCE)
    google.keys = [_jwk(_PRIVATE, "k1")]  # Google rotated
    assert provider.verify_id_token(_id_token(), nonce=NONCE).subject == "1098765"
    assert [c[1] for c in google.calls].count(JWKS_URI) == 2


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ((400, b'{"error": "invalid_grant"}'), "token_refused"),
        ((200, b"{}"), "token_malformed"),
        ((200, b"not json"), "token_malformed"),
    ],
)
def test_a_refused_or_malformed_code_exchange_fails(
    response: tuple[int, bytes], reason: str
) -> None:
    google = FakeGoogle([])
    google.token_response = response
    with pytest.raises(OidcFailed) as failure:
        _provider(google).exchange(code="c", code_verifier="v", redirect_uri="r", nonce=NONCE)
    assert failure.value.reason == reason


def test_google_unreachable_fails_cleanly() -> None:
    def down(method: str, url: str, form: Mapping[str, str] | None) -> tuple[int, bytes]:
        raise OSError("down")

    provider = GoogleOidcProvider(client_id=CLIENT_ID, client_secret="s", transport=down)
    with pytest.raises(OidcFailed) as failure:
        provider.exchange(code="c", code_verifier="v", redirect_uri="r", nonce=NONCE)
    assert failure.value.reason == "token_unreachable"


# --- The fake provider (decision 6) ----------------------------------------------------------


def _fake_round_trip(hint: str | None, nonce: str = NONCE) -> Any:
    fake = FakeOidcProvider()
    url = fake.authorization_url(
        state="patient.s",
        nonce=NONCE,
        code_challenge="c",
        redirect_uri="http://localhost:3000/api/v1/auth/google/callback",
        login_hint=hint,
    )
    path, _, query = url.partition("?")
    params = dict(urllib.parse.parse_qsl(query))
    assert path == "/api/v1/auth/google/callback"  # same origin as the browser
    assert params["state"] == "patient.s"
    return fake.exchange(code=params["code"], code_verifier="v", redirect_uri="r", nonce=nonce)


def test_adr_0015_the_fake_signs_in_the_login_hint_as_a_verified_identity() -> None:
    identity = _fake_round_trip("Asha.Patient@example.test")
    assert identity.email == "asha.patient@example.test"
    assert identity.email_verified
    assert identity.name == "Asha Patient"
    assert identity.subject == _fake_round_trip("asha.patient@example.test").subject


def test_the_fake_still_checks_the_nonce_and_needs_a_hint() -> None:
    with pytest.raises(OidcFailed, match="Google"):
        _fake_round_trip("a@example.test", nonce="other")
    with pytest.raises(OidcFailed) as failure:
        _fake_round_trip(None)
    assert failure.value.reason == "fake_login_hint_missing"
    with pytest.raises(OidcFailed):
        FakeOidcProvider().exchange(code="garbage", code_verifier="v", redirect_uri="r", nonce="n")


# --- The flow cookie -------------------------------------------------------------------------


def test_adr_0015_the_flow_round_trips_and_expires_after_its_ttl() -> None:
    sealer = JwtFlowSealer(signing_key=KEY)
    sealed = sealer.seal({"state": "s", "next": "/today"}, now=NOW, ttl=timedelta(minutes=10))
    assert sealer.open(sealed, now=NOW + timedelta(minutes=9)) == {"state": "s", "next": "/today"}
    with pytest.raises(InvalidFlow):
        sealer.open(sealed, now=NOW + timedelta(minutes=11))


def test_a_tampered_or_foreign_flow_is_refused() -> None:
    sealer = JwtFlowSealer(signing_key=KEY)
    sealed = sealer.seal({"state": "s"}, now=NOW, ttl=timedelta(minutes=10))
    with pytest.raises(InvalidFlow):
        JwtFlowSealer(signing_key="another-key-0123456789abcdef0123456789").open(sealed, now=NOW)
    with pytest.raises(InvalidFlow):
        sealer.open(sealed[:-3] + "abc", now=NOW)
    # An access token is signed with the same key but is not a flow (another audience).
    access = JwtAccessTokenIssuer(signing_key=KEY, ttl=timedelta(minutes=15), ids=_Ids())
    token = access.issue(user_id=new_id(), session_id=new_id(), now=NOW).value
    with pytest.raises(InvalidFlow):
        sealer.open(token, now=NOW)
    with pytest.raises(ValueError):
        sealer.seal({"exp": "1"}, now=NOW, ttl=timedelta(minutes=1))


def test_rfc_7636_s256_challenge_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


class _Ids:
    def new_id(self) -> Any:
        return new_id()
