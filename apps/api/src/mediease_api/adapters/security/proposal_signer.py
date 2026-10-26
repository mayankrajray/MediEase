"""HMAC-SHA256 for assistant proposals (M7a-P3; spec assistant R7; ADR-0024).

The token is ``base64url(payload) "." base64url(mac)``. The key is derived from the JWT signing
key with its own label, so a proposal can never be confused with an access token or a link and
rotating the JWT key also invalidates open proposals (they live 10 minutes anyway). The payload
holds IDs and the action's short arguments, nothing clinical; it is signed, not encrypted.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac

_LABEL = b"mediease/assistant-proposal/v1"
MAX_TOKEN_LENGTH = 4096


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class HmacProposalSigner:
    def __init__(self, signing_key: str) -> None:
        if len(signing_key) < 32:
            raise ValueError("the signing key is too short")
        self._key = hmac.new(signing_key.encode(), _LABEL, hashlib.sha256).digest()

    def _mac(self, payload: bytes) -> bytes:
        return hmac.new(self._key, payload, hashlib.sha256).digest()

    def sign(self, payload: bytes) -> str:
        return f"{_b64(payload)}.{_b64(self._mac(payload))}"

    def open(self, token: str) -> bytes | None:
        if len(token) > MAX_TOKEN_LENGTH or token.count(".") != 1:
            return None
        body, mac = token.split(".")
        try:
            payload, given = _unb64(body), _unb64(mac)
        except (binascii.Error, ValueError):
            return None
        return payload if hmac.compare_digest(self._mac(payload), given) else None
