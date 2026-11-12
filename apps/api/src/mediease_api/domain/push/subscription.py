"""A device that receives web push for one patient account or one staff user (M7e-E2, ADR-0025).

A subscription is what a browser's push manager hands over: an endpoint (a capability URL at the
browser maker's push service) and two keys used to encrypt each message for that browser. The
server will POST to the endpoint (E3), so only the known browser push services are accepted:
anything else could point the server at an internal address (server-side request forgery).

Ownership is by an account or a user, never a clinic: a device follows a person across clinics,
and the notice it carries says nothing clinical (design §1 decision 3). One endpoint belongs to
one owner; when another person subscribes the same browser, the device moves to them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

ENDPOINT_MAX = 2048
LABEL_MAX = 60
MAX_DEVICES = 10
SUBSCRIBES_PER_HOUR = 30

# The browsers' own push services (FCM for Chrome and Edge on Android and desktop, Mozilla
# autopush, Apple's web push, Windows push for legacy Edge). Exact hosts or a dot-suffix.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com")
PUSH_HOST_SUFFIXES = (".push.apple.com", ".notify.windows.com")

_P256DH_BYTES = 65  # an uncompressed P-256 point: 0x04, then X and Y
_AUTH_BYTES = 16


class OwnerKind(StrEnum):
    PATIENT = "PATIENT"
    STAFF = "STAFF"


@dataclass(frozen=True, slots=True)
class PushOwner:
    """Whose device it is: a patient account or a staff user."""

    kind: OwnerKind
    id: UUID

    @classmethod
    def patient(cls, account_id: UUID) -> PushOwner:
        return cls(OwnerKind.PATIENT, account_id)

    @classmethod
    def staff(cls, user_id: UUID) -> PushOwner:
        return cls(OwnerKind.STAFF, user_id)


class DisabledReason(StrEnum):
    """Why a device no longer receives push (set by delivery in E3)."""

    EXPIRED = "EXPIRED"  # the push service answered 404 or 410: the browser unsubscribed


def _host_allowed(host: str) -> bool:
    return host in PUSH_HOSTS or any(
        host.endswith(s) and len(host) > len(s) for s in PUSH_HOST_SUFFIXES
    )


def check_endpoint(endpoint: str) -> str:
    """The endpoint as given, if it is an https URL at a browser push service."""
    if not 1 <= len(endpoint) <= ENDPOINT_MAX:
        raise InvalidValue("endpoint", f"must be 1-{ENDPOINT_MAX} characters")
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError as exc:
        raise InvalidValue("endpoint", "must be a push service URL") from exc
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or not _host_allowed(host)
        or not parts.path.startswith("/")
    ):
        raise InvalidValue("endpoint", "must be a browser push service URL")
    return endpoint


_B64URL = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")


def _decode(value: str, field: str, size: int) -> bytes:
    if not _B64URL.fullmatch(value) or len(value) > 128:
        raise InvalidValue(field, "must be base64url")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise InvalidValue(field, "must be base64url") from exc
    if len(raw) != size:
        raise InvalidValue(field, f"must decode to {size} bytes")
    return raw


def check_keys(p256dh: str, auth: str) -> tuple[str, str]:
    """The browser's public key (a P-256 point) and its 16-byte auth secret, as base64url."""
    if _decode(p256dh, "keys.p256dh", _P256DH_BYTES)[0] != 0x04:
        raise InvalidValue("keys.p256dh", "must be an uncompressed P-256 public key")
    _decode(auth, "keys.auth", _AUTH_BYTES)
    return p256dh, auth


def endpoint_digest(endpoint: str) -> str:
    """The lookup key for an endpoint. The URL itself is stored only encrypted."""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


_BROWSERS = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("SamsungBrowser/", "Samsung Internet"),
    ("Firefox/", "Firefox"),
    ("FxiOS/", "Firefox"),
    ("CriOS/", "Chrome"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)
_SYSTEMS = (
    ("Android", "Android"),
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Windows", "Windows"),
    ("Mac OS X", "Mac"),
    ("CrOS", "ChromeOS"),
    ("Linux", "Linux"),
)


def device_label(user_agent: str | None) -> str:
    """A short, fixed-vocabulary name for a device ("Chrome on Android"): never the raw agent."""
    ua = user_agent or ""
    browser = next((name for token, name in _BROWSERS if token in ua), "Browser")
    system = next((name for token, name in _SYSTEMS if token in ua), None)
    label = f"{browser} on {system}" if system else browser
    return label[:LABEL_MAX]


@dataclass(slots=True)
class PushSubscription:
    """One device of one owner. Build with ``create``; the constructor rehydrates."""

    id: UUID
    owner: PushOwner
    endpoint_digest: str
    endpoint_encrypted: str
    p256dh_encrypted: str
    auth_encrypted: str
    label: str
    created_at: datetime
    updated_at: datetime
    last_success_at: datetime | None = None
    disabled_at: datetime | None = None
    disabled_reason: DisabledReason | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        owner: PushOwner,
        digest: str,
        endpoint_encrypted: str,
        p256dh_encrypted: str,
        auth_encrypted: str,
        label: str,
        now: datetime,
    ) -> PushSubscription:
        now = require_utc(now, "now")
        return cls(
            id=id,
            owner=owner,
            endpoint_digest=digest,
            endpoint_encrypted=endpoint_encrypted,
            p256dh_encrypted=p256dh_encrypted,
            auth_encrypted=auth_encrypted,
            label=label[:LABEL_MAX],
            created_at=now,
            updated_at=now,
        )

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None

    def refresh(
        self, *, p256dh_encrypted: str, auth_encrypted: str, label: str, now: datetime
    ) -> None:
        """The same browser subscribed again: new keys, and it receives push again."""
        self.p256dh_encrypted = p256dh_encrypted
        self.auth_encrypted = auth_encrypted
        self.label = label[:LABEL_MAX]
        self.disabled_at = None
        self.disabled_reason = None
        self.updated_at = require_utc(now, "now")

    def mark_sent(self, now: datetime) -> None:
        """E3: the push service accepted a message for this device."""
        self.last_success_at = require_utc(now, "now")

    def disable(self, reason: DisabledReason, now: datetime) -> None:
        """E3 (R34): the push service says the browser is gone; nothing more is sent to it."""
        now = require_utc(now, "now")
        self.disabled_at = now
        self.disabled_reason = reason
        self.updated_at = now
