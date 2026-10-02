"""Refresh-token values and their stored digests (ADR-0006 "stored hashed").

A token is 32 random bytes (256 bits), URL-safe base64. Only its SHA-256 digest
is stored. A plain hash is enough because the input is random, not a password:
there is nothing to guess, so no salt or slow hash is needed, and a database
leak yields no usable token.
"""

from __future__ import annotations

import hashlib
import secrets

_TOKEN_BYTES = 32


class Sha256RefreshTokenSecrets:
    def generate(self) -> str:
        return secrets.token_urlsafe(_TOKEN_BYTES)

    def digest(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
