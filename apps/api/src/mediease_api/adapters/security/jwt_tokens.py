"""JWT access tokens with PyJWT (FR-AUTH-02, ADR-0006).

HS256 with one server-side key. Claims: ``iss``, ``aud``, ``sub`` (user ID),
``sid`` (refresh-token family, i.e. the session), ``jti``, ``iat``, ``exp``.
Verification pins the algorithm (no ``alg: none`` or key-confusion tricks),
requires every claim, checks issuer and audience, and allows 30 seconds of
clock skew between API replicas (spec §8).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import AccessClaims, InvalidAccessToken, IssuedAccessToken

ISSUER = "mediease-api"
AUDIENCE = "mediease"
CLOCK_SKEW = timedelta(seconds=30)
_ALGORITHM = "HS256"
_REQUIRED = ["iss", "aud", "sub", "sid", "jti", "iat", "exp"]


class JwtAccessTokenIssuer:
    def __init__(self, *, signing_key: str, ttl: timedelta, ids: IdPort) -> None:
        self._key = signing_key
        self._ttl = ttl
        self._ids = ids

    def issue(self, *, user_id: UUID, session_id: UUID, now: datetime) -> IssuedAccessToken:
        # JWT times are whole seconds; truncate so expires_at matches the token exactly.
        issued_at = now.replace(microsecond=0)
        expires_at = issued_at + self._ttl
        claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(self._ids.new_id()),
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(claims, self._key, algorithm=_ALGORITHM)
        return IssuedAccessToken(value=token, expires_at=expires_at)

    def verify(self, token: str, *, now: datetime) -> AccessClaims:
        try:
            # PyJWT checks exp/iat against the real clock, so expiry is checked
            # here against the injected clock instead (same leeway).
            claims = jwt.decode(
                token,
                self._key,
                algorithms=[_ALGORITHM],
                audience=AUDIENCE,
                issuer=ISSUER,
                options={"require": _REQUIRED, "verify_exp": False, "verify_iat": False},
            )
            expires_at = datetime.fromtimestamp(int(claims["exp"]), UTC)
            user_id, session_id = UUID(claims["sub"]), UUID(claims["sid"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise InvalidAccessToken() from None
        if now >= expires_at + CLOCK_SKEW:
            raise InvalidAccessToken()
        return AccessClaims(user_id=user_id, session_id=session_id, expires_at=expires_at)
