"""Patient link tokens (spec prescriptions R9; M4-P5 decision 2A). Encoding only, no crypto.

``<header>.<claims>.<mac>``, each part base64url without padding:

- header: version (1 byte), kind (1 byte: ``1`` link, ``2`` view, ``3`` live queue), key ID (1-16
  ASCII bytes);
- claims, a link: ``jti`` (16 bytes) ``cid`` (16) ``rid`` (16) ``exp`` (4, Unix seconds, big
  endian) ``pur`` (1); a view (the 30-minute cookie): ``jti`` (16) ``exp`` (4); a live-queue link
  (M6b-P6, ADR-0019): ``cid`` (16) ``aid`` (16, the appointment) ``nbf`` (4) ``exp`` (4);
- mac: HMAC-SHA256 over ``<header>.<claims>`` (the ASCII text), truncated to 16 bytes, made and
  checked by ``LinkSignerPort`` with the key the header names.

About 100 characters for a link, short enough for a QR code and a message. The kind byte keeps a
view token from ever being accepted as a link and the other way round. Decoding never trusts
anything before the MAC is checked; every malformed input is ``LinkInvalid``.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum
from uuid import UUID

from mediease_api.domain.links.errors import LinkInvalid
from mediease_api.domain.links.link import LinkPurpose

VERSION = 1
MAC_BYTES = 16
_KEY_ID = re.compile(r"[A-Za-z0-9_-]{1,16}")
_PURPOSE_CODES = {LinkPurpose.RX_VIEW: 1, LinkPurpose.RECEIPT: 2}
_PURPOSES = {code: purpose for purpose, code in _PURPOSE_CODES.items()}
_MAX_TOKEN = 200


class Kind(IntEnum):
    LINK = 1
    VIEW = 2
    # M6b-P6: a signed live-queue link; its own kind, so it is never taken for a prescription link.
    QUEUE = 3


@dataclass(frozen=True, slots=True)
class LinkClaims:
    jti: UUID
    cid: UUID
    rid: UUID
    purpose: LinkPurpose
    exp: datetime


@dataclass(frozen=True, slots=True)
class ViewClaims:
    jti: UUID
    exp: datetime


@dataclass(frozen=True, slots=True)
class QueueClaims:
    """M6b-P6 (R69, ADR-0019): one appointment's live-queue link, valid from ``nbf`` to ``exp``."""

    cid: UUID
    aid: UUID
    nbf: datetime
    exp: datetime


@dataclass(frozen=True, slots=True)
class Unverified:
    """A token split into its parts. Nothing in it may be used before ``mac`` is checked."""

    kind: Kind
    key_id: str
    signing_input: bytes
    claims: bytes
    mac: bytes


def check_key_id(key_id: str) -> str:
    if not _KEY_ID.fullmatch(key_id):
        raise ValueError("a key ID is 1-16 letters, digits, '-' or '_'")
    return key_id


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    if not text or not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise LinkInvalid()
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise LinkInvalid() from None


def _seconds(moment: datetime) -> bytes:
    value = int(moment.astimezone(UTC).timestamp())
    return value.to_bytes(4, "big")


def _moment(raw: bytes) -> datetime:
    return datetime.fromtimestamp(int.from_bytes(raw, "big"), tz=UTC)


def signing_input(kind: Kind, key_id: str, claims: bytes) -> bytes:
    header = bytes([VERSION, int(kind)]) + check_key_id(key_id).encode("ascii")
    return f"{_b64(header)}.{_b64(claims)}".encode("ascii")


def link_claims_bytes(claims: LinkClaims) -> bytes:
    return (
        claims.jti.bytes
        + claims.cid.bytes
        + claims.rid.bytes
        + _seconds(claims.exp)
        + bytes([_PURPOSE_CODES[claims.purpose]])
    )


def view_claims_bytes(claims: ViewClaims) -> bytes:
    return claims.jti.bytes + _seconds(claims.exp)


def queue_claims_bytes(claims: QueueClaims) -> bytes:
    return claims.cid.bytes + claims.aid.bytes + _seconds(claims.nbf) + _seconds(claims.exp)


def assemble(signing: bytes, mac: bytes) -> str:
    if len(mac) != MAC_BYTES:
        raise ValueError(f"a MAC is {MAC_BYTES} bytes")
    return f"{signing.decode('ascii')}.{_b64(mac)}"


def split(token: str) -> Unverified:
    """The parts of a token; ``LinkInvalid`` for anything that is not one."""
    if len(token) > _MAX_TOKEN:
        raise LinkInvalid()
    parts = token.split(".")
    if len(parts) != 3:
        raise LinkInvalid()
    header, claims, mac = (_unb64(p) for p in parts)
    if len(header) < 3 or header[0] != VERSION or header[1] not in (k.value for k in Kind):
        raise LinkInvalid()
    try:
        key_id = check_key_id(header[2:].decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise LinkInvalid() from None
    if len(mac) != MAC_BYTES:
        raise LinkInvalid()
    return Unverified(
        kind=Kind(header[1]),
        key_id=key_id,
        signing_input=f"{parts[0]}.{parts[1]}".encode("ascii"),
        claims=claims,
        mac=mac,
    )


def read_link_claims(token: Unverified) -> LinkClaims:
    """Call only after the MAC was verified."""
    raw = token.claims
    if token.kind is not Kind.LINK or len(raw) != 53 or raw[52] not in _PURPOSES:
        raise LinkInvalid()
    return LinkClaims(
        jti=UUID(bytes=raw[0:16]),
        cid=UUID(bytes=raw[16:32]),
        rid=UUID(bytes=raw[32:48]),
        exp=_moment(raw[48:52]),
        purpose=_PURPOSES[raw[52]],
    )


def read_view_claims(token: Unverified) -> ViewClaims:
    """Call only after the MAC was verified."""
    raw = token.claims
    if token.kind is not Kind.VIEW or len(raw) != 20:
        raise LinkInvalid()
    return ViewClaims(jti=UUID(bytes=raw[0:16]), exp=_moment(raw[16:20]))


def read_queue_claims(token: Unverified) -> QueueClaims:
    """Call only after the MAC was verified."""
    raw = token.claims
    if token.kind is not Kind.QUEUE or len(raw) != 40:
        raise LinkInvalid()
    return QueueClaims(
        cid=UUID(bytes=raw[0:16]),
        aid=UUID(bytes=raw[16:32]),
        nbf=_moment(raw[32:36]),
        exp=_moment(raw[36:40]),
    )


def describe(token: str) -> dict[str, str]:
    """Header and claims without checking the MAC, for ``scripts/inspect_link_token.py``."""
    parts = split(token)
    shown = {"kind": parts.kind.name, "key_id": parts.key_id, "signature": "not checked"}
    if parts.kind is Kind.LINK:
        link = read_link_claims(parts)
        shown |= {
            "jti": str(link.jti),
            "cid": str(link.cid),
            "rid": str(link.rid),
            "purpose": link.purpose.value,
            "exp": link.exp.isoformat(),
        }
    elif parts.kind is Kind.QUEUE:
        queue = read_queue_claims(parts)
        shown |= {
            "cid": str(queue.cid),
            "aid": str(queue.aid),
            "nbf": queue.nbf.isoformat(),
            "exp": queue.exp.isoformat(),
        }
    else:
        view = read_view_claims(parts)
        shown |= {"jti": str(view.jti), "exp": view.exp.isoformat()}
    return shown
