"""The Google sign-in flow cookie, sealed as a short JWT (M6a-P3, ADR-0015 decision 3).

HS256 with the access-token key but its own audience (``mediease-oidc-flow``), so a flow value
can never pass as an access token or the other way round. Signed, not encrypted: it holds the
PKCE verifier, the ``state`` and the ``nonce`` of the person's own sign-in, and lives only in
their browser in an HttpOnly cookie, which is where PKCE expects the verifier to be.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import jwt

from mediease_api.adapters.security.jwt_tokens import CLOCK_SKEW, ISSUER
from mediease_api.ports.security import InvalidFlow

FLOW_AUDIENCE = "mediease-oidc-flow"
_ALGORITHM = "HS256"
_RESERVED = frozenset({"iss", "aud", "iat", "exp"})


class JwtFlowSealer:
    def __init__(self, *, signing_key: str) -> None:
        self._key = signing_key

    def seal(self, values: Mapping[str, str], *, now: datetime, ttl: timedelta) -> str:
        if _RESERVED & values.keys():
            raise ValueError("flow values may not use reserved claim names")
        issued_at = now.replace(microsecond=0)
        claims: dict[str, object] = {
            **values,
            "iss": ISSUER,
            "aud": FLOW_AUDIENCE,
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + ttl).timestamp()),
        }
        return jwt.encode(claims, self._key, algorithm=_ALGORITHM)

    def open(self, sealed: str, *, now: datetime) -> dict[str, str]:
        try:
            claims = jwt.decode(
                sealed,
                self._key,
                algorithms=[_ALGORITHM],
                audience=FLOW_AUDIENCE,
                issuer=ISSUER,
                options={"require": ["iss", "aud", "iat", "exp"], "verify_exp": False},
            )
            expires_at = datetime.fromtimestamp(int(claims["exp"]), UTC)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise InvalidFlow() from None
        if now >= expires_at + CLOCK_SKEW:
            raise InvalidFlow()
        values = {k: v for k, v in claims.items() if k not in _RESERVED}
        if not all(isinstance(v, str) for v in values.values()):
            raise InvalidFlow()
        return values
