"""The printed verification code (M7a-P1; FR-RX-11; ADR-0023; spec assistant §3).

Every version issued on layout 3 or later prints its own ID, ``prescriptions.id`` (a UUIDv7),
twice: as text a person can read and type ("Verification code") and as a QR code whose payload is
``MEDIEASE-RX:1:<uuid>``. The ID is the whole payload: no name, phone, clinic, medicine or date,
and no signature. It is not a link and grants nothing by itself: an upload or a typed code is
only ever resolved inside the uploader's own access (spec prescription-uploads R20-R27).

``parse_payload`` reads a QR payload, ``parse_typed_code`` what a person typed, and
``codes_in_text`` the codes in a PDF's text layer. All three accept only the exact grammar, so
anything else is "no identifier" rather than a guess.
"""

from __future__ import annotations

import re
from uuid import UUID

# The first layout that prints the code (``prescription.CURRENT_LAYOUT`` is at least this).
VERIFICATION_LAYOUT = 3
PAYLOAD_PREFIX = "MEDIEASE-RX"
PAYLOAD_VERSION = 1
MAX_PAYLOAD_LENGTH = 64

_HEX = "[0-9a-fA-F]"
_UUID = f"{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}"
_PAYLOAD = re.compile(rf"{PAYLOAD_PREFIX}:{PAYLOAD_VERSION}:({_UUID})", re.IGNORECASE)
_CODE = re.compile(rf"(?<![0-9a-fA-F-])({_UUID})(?![0-9a-fA-F-])")
_COMPACT = re.compile(f"{_HEX}{{32}}")


def printed_code(prescription_id: UUID) -> str:
    """The code as printed: the canonical lower-case UUID."""
    return str(prescription_id)


def qr_payload(prescription_id: UUID) -> str:
    """What the QR code holds: an opaque, versioned identifier and nothing else."""
    return f"{PAYLOAD_PREFIX}:{PAYLOAD_VERSION}:{prescription_id}"


def parse_payload(payload: str) -> UUID | None:
    """A decoded QR payload's prescription ID, or ``None`` unless it is exactly ours."""
    if len(payload) > MAX_PAYLOAD_LENGTH:
        return None
    match = _PAYLOAD.fullmatch(payload.strip())
    return UUID(match.group(1)) if match else None


def parse_typed_code(text: str) -> UUID | None:
    """A code a person typed: the printed UUID (any case, with or without its dashes, inner
    spaces ignored) or a full QR payload. Anything else is ``None``."""
    if len(text) > MAX_PAYLOAD_LENGTH + 8:
        return None
    compact = "".join(text.split())
    from_payload = parse_payload(compact)
    if from_payload is not None:
        return from_payload
    if _CODE.fullmatch(compact):
        return UUID(compact)
    if _COMPACT.fullmatch(compact):
        return UUID(hex=compact)
    return None


def codes_in_text(text: str) -> frozenset[UUID]:
    """Every distinct code in a document's text layer (payloads and printed codes alike)."""
    found = {UUID(m.group(1)) for m in _PAYLOAD.finditer(text)}
    found.update(UUID(m.group(1)) for m in _CODE.finditer(text))
    return frozenset(found)
