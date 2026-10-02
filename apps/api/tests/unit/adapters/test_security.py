"""Security adapters: Argon2id, JWT access tokens, refresh secrets, clock (FR-AUTH-01/02)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.security.argon2_hasher import Argon2PasswordHasher
from mediease_api.adapters.security.ip_hash import HmacIpHasher
from mediease_api.adapters.security.jwt_tokens import AUDIENCE, ISSUER, JwtAccessTokenIssuer
from mediease_api.adapters.security.refresh_secrets import Sha256RefreshTokenSecrets
from mediease_api.ports.security import InvalidAccessToken
from tests.builders import NOW, new_id

KEY = "unit-test-signing-key-0123456789abcdef"

# --- Argon2id --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher(time_cost=1, memory_cost_kib=8, parallelism=1)


def test_fr_auth_01_hash_is_argon2id_and_salted(hasher: Argon2PasswordHasher) -> None:
    first, second = hasher.hash("correct horse"), hasher.hash("correct horse")
    assert first.startswith("$argon2id$")
    assert first != second  # random salt per hash
    assert "correct horse" not in first


def test_fr_auth_01_verify_accepts_only_the_right_password(hasher: Argon2PasswordHasher) -> None:
    stored = hasher.hash("correct horse")
    assert hasher.verify(stored, "correct horse")
    assert not hasher.verify(stored, "correct horsE")
    assert not hasher.verify(stored, "")


@pytest.mark.parametrize("garbage", ["", "not-a-hash", "$argon2id$v=19$broken"])
def test_malformed_hash_is_a_mismatch_not_an_error(
    hasher: Argon2PasswordHasher, garbage: str
) -> None:
    assert not hasher.verify(garbage, "anything")
    assert hasher.needs_rehash(garbage)


def test_weaker_hashes_need_rehash(hasher: Argon2PasswordHasher) -> None:
    production = Argon2PasswordHasher()
    weak = hasher.hash("pw")
    assert production.needs_rehash(weak)
    assert not hasher.needs_rehash(weak)


def test_production_parameters_are_rfc_9106_low_memory() -> None:
    stored = Argon2PasswordHasher().hash("pw")
    assert "$m=65536,t=3,p=4$" in stored


# --- JWT access tokens ----------------------------------------------------------------------


@pytest.fixture
def issuer() -> JwtAccessTokenIssuer:
    return JwtAccessTokenIssuer(signing_key=KEY, ttl=timedelta(minutes=15), ids=Uuid7Generator())


def test_fr_auth_02_issued_token_round_trips(issuer: JwtAccessTokenIssuer) -> None:
    user_id, session_id = new_id(), new_id()
    issued = issuer.issue(user_id=user_id, session_id=session_id, now=NOW)
    assert issued.expires_at == NOW + timedelta(minutes=15)
    assert issued.value not in repr(issued)

    claims = issuer.verify(issued.value, now=NOW + timedelta(minutes=14))
    assert (claims.user_id, claims.session_id) == (user_id, session_id)
    assert claims.expires_at == issued.expires_at


def test_token_carries_issuer_audience_and_unique_jti(issuer: JwtAccessTokenIssuer) -> None:
    a = issuer.issue(user_id=new_id(), session_id=new_id(), now=NOW).value
    b = issuer.issue(user_id=new_id(), session_id=new_id(), now=NOW).value
    claims_a = jwt.decode(a, options={"verify_signature": False})
    claims_b = jwt.decode(b, options={"verify_signature": False})
    assert claims_a["iss"] == ISSUER and claims_a["aud"] == AUDIENCE
    assert claims_a["jti"] != claims_b["jti"]
    assert jwt.get_unverified_header(a)["alg"] == "HS256"


def test_spec_clock_skew_of_30_seconds_is_tolerated(issuer: JwtAccessTokenIssuer) -> None:
    issued = issuer.issue(user_id=new_id(), session_id=new_id(), now=NOW)
    issuer.verify(issued.value, now=issued.expires_at + timedelta(seconds=29))
    with pytest.raises(InvalidAccessToken) as excinfo:
        issuer.verify(issued.value, now=issued.expires_at + timedelta(seconds=30))
    assert excinfo.value.code == "AUTH_SESSION_EXPIRED"


def _forge(claims: dict[str, object], key: str = KEY, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


def _valid_claims() -> dict[str, object]:
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(new_id()),
        "sid": str(new_id()),
        "jti": str(new_id()),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=15)).timestamp()),
    }


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda: _forge(_valid_claims(), key="another-key-of-sufficient-length-0123"),
        lambda: _forge({**_valid_claims(), "aud": "someone-else"}),
        lambda: _forge({**_valid_claims(), "iss": "someone-else"}),
        lambda: _forge({k: v for k, v in _valid_claims().items() if k != "sid"}),
        lambda: _forge({**_valid_claims(), "sub": "not-a-uuid"}),
        lambda: jwt.encode(_valid_claims(), None, algorithm="none"),
        lambda: _forge(_valid_claims())[:-2] + "AA",
        lambda: "not.a.jwt",
        lambda: "",
    ],
    ids=[
        "wrong-key",
        "wrong-audience",
        "wrong-issuer",
        "missing-sid",
        "bad-sub",
        "alg-none",
        "tampered-signature",
        "garbage",
        "empty",
    ],
)
def test_untrustworthy_tokens_are_rejected(
    issuer: JwtAccessTokenIssuer, token_factory: object
) -> None:
    with pytest.raises(InvalidAccessToken):
        issuer.verify(token_factory(), now=NOW)  # type: ignore[operator]


# --- Refresh secrets and clock ----------------------------------------------------------------


def test_refresh_tokens_are_random_and_stored_as_sha256() -> None:
    secrets = Sha256RefreshTokenSecrets()
    first, second = secrets.generate(), secrets.generate()
    assert first != second
    assert len(first) >= 43  # 32 bytes, URL-safe base64
    assert secrets.digest(first) == secrets.digest(first)
    assert len(secrets.digest(first)) == 64
    assert secrets.digest(first) != secrets.digest(second)


def test_system_clock_is_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is UTC
    assert abs(now - datetime.now(UTC)) < timedelta(seconds=5)


# --- IP fingerprints for audit events (M1-P4) -------------------------------------------------


def test_fr_aud_01_ip_hash_is_stable_salted_and_irreversible() -> None:
    hasher = HmacIpHasher(KEY)
    fingerprint = hasher.hash("203.0.113.42")

    assert fingerprint == hasher.hash(" 203.0.113.42 ")  # stable, whitespace ignored
    assert fingerprint is not None and len(fingerprint) == 32
    assert "203.0.113.42" not in fingerprint
    assert fingerprint != hasher.hash("203.0.113.43")
    # A different salt gives a different fingerprint, so one leaked table does
    # not identify addresses in another environment.
    assert fingerprint != HmacIpHasher("another-unit-test-salt-0123456789").hash("203.0.113.42")


@pytest.mark.parametrize("address", [None, "", "   "])
def test_an_unknown_address_has_no_fingerprint(address: str | None) -> None:
    assert HmacIpHasher(KEY).hash(address) is None
