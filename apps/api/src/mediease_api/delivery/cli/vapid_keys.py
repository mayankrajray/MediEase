"""``make vapid-keys``: a new VAPID key pair for web push (M7e-E5; RUNBOOK §36).

Prints the two lines to put in ``.env`` (or the deployment's secret store). Nothing is stored or
sent anywhere: the pair exists only in this output. Generate one pair per environment and keep
it: browsers subscribe with the public key, so a new pair means every device turns alerts on
again.
"""

from __future__ import annotations

import base64
import sys
from typing import TextIO

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def new_pair() -> tuple[str, str]:
    """(public, private): an uncompressed P-256 point and the raw 32-byte key, base64url."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return _b64(public), _b64(key.private_numbers().private_value.to_bytes(32, "big"))


def main(out: TextIO = sys.stdout) -> int:
    public, private = new_pair()
    out.write(
        "# A new VAPID pair for web push. Put these in .env (never commit the private key),\n"
        "# with PUSH_PROVIDER=webpush and VAPID_SUBJECT=mailto:<an address you read>.\n"
        f"VAPID_PUBLIC_KEY={public}\n"
        f"VAPID_PRIVATE_KEY={private}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - the make target
    raise SystemExit(main())
