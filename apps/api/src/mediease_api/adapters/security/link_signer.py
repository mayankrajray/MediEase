"""HMAC-SHA256 for patient link and view tokens (spec prescriptions R9; M4-P5 decision 2A).

Keys come from ``PATIENT_LINK_SIGNING_KEYS`` (``kid:secret,…``): the first signs new links and
every key verifies, so a key is rotated by putting a new one first and removing the old one only
after its links have expired (90 days). The MAC is truncated to 16 bytes (128 bits), which
NIST SP 800-107 allows for HMAC; comparison is constant-time where it is checked.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping

from mediease_api.domain.links.token import MAC_BYTES, check_key_id


class HmacLinkSigner:
    def __init__(self, keys: Mapping[str, bytes]) -> None:
        if not keys:
            raise ValueError("at least one patient link key is required")
        self._keys = {check_key_id(kid): secret for kid, secret in keys.items()}
        self._current = next(iter(self._keys))

    @property
    def current_key_id(self) -> str:
        return self._current

    def mac(self, key_id: str, message: bytes) -> bytes | None:
        secret = self._keys.get(key_id)
        if secret is None:
            return None
        return hmac.new(secret, message, hashlib.sha256).digest()[:MAC_BYTES]
