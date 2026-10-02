"""IP fingerprints for audit events (``ports/security.py::IpHasher``).

HMAC-SHA256 under ``AUDIT_IP_SALT``, truncated to 32 hex characters (128 bits:
no collisions at any volume we will see). HMAC rather than a plain hash so the
fingerprints cannot be recomputed from a list of candidate addresses without
the salt, and the salt is its own setting so rotating it does not touch the
JWT key — rotating it makes older fingerprints incomparable, which is the
expected trade-off.
"""

from __future__ import annotations

import hashlib
import hmac

_DIGEST_LENGTH = 32


class HmacIpHasher:
    def __init__(self, salt: str) -> None:
        self._key = salt.encode()

    def hash(self, ip_address: str | None) -> str | None:
        address = (ip_address or "").strip()
        if not address:
            return None
        digest = hmac.new(self._key, address.encode(), hashlib.sha256).hexdigest()
        return digest[:_DIGEST_LENGTH]
