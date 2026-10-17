#!/usr/bin/env python3
"""Show what a patient link token says, offline (DEBUGGING §5.9; M4-P5).

    apps/api/.venv/bin/python scripts/inspect_link_token.py <token-or-url>

Prints the header (kind, key ID) and the claims (link ID, clinic, prescription, purpose,
expiry) without the signing key and without the network. The signature is **not** checked, so
this proves nothing about whether the token is genuine: use it to read an ``exp`` or find the
``patient_links`` row (``jti`` is its ID). Never paste tokens into tickets or chat; the token
plus the patient's last 4 digits opens the prescription.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "src"))

from mediease_api.domain.links.errors import LinkInvalid
from mediease_api.domain.links.token import describe


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    token = argv[1].strip().rsplit("/p/", 1)[-1].split("?", 1)[0]
    try:
        shown = describe(token)
    except LinkInvalid:
        print("not a MediEase patient link token", file=sys.stderr)
        return 1
    for key, value in shown.items():
        print(f"{key:>10}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
