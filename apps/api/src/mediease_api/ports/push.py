"""Ports for web push: subscriptions (M7e-E2) and sending (M7e-E3), ADR-0025."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from mediease_api.domain.push.subscription import OwnerKind, PushOwner, PushSubscription


class PushSubscriptionRepository(Protocol):
    """Devices owned by a patient account or a staff user (platform data, not a tenant table)."""

    def add(self, subscription: PushSubscription) -> None: ...

    def update(self, subscription: PushSubscription) -> None: ...

    def delete(self, subscription_id: UUID) -> None: ...

    def by_digest(self, digest: str, *, for_update: bool = False) -> PushSubscription | None:
        """The device with this endpoint, whoever owns it."""
        ...

    def get_for_owner(self, subscription_id: UUID, owner: PushOwner) -> PushSubscription | None:
        """One of the owner's devices; another owner's is not found."""
        ...

    def list_for_owner(self, owner: PushOwner) -> Sequence[PushSubscription]:
        """The owner's devices, newest first."""
        ...

    def active_for_owners(
        self, kind: OwnerKind, owner_ids: Collection[UUID]
    ) -> Sequence[PushSubscription]:
        """E3: the active devices of all these owners, in one query (a notice's recipients)."""
        ...

    def count_active(self, owner: PushOwner) -> int: ...


class TextCipherPort(Protocol):
    """Encryption at rest for short secrets (push endpoints and keys), with key rotation."""

    def encrypt(self, value: str) -> str: ...

    def decrypt(self, token: str) -> str: ...


@dataclass(frozen=True, slots=True)
class PushTarget:
    """One browser to send to, decrypted only for the send."""

    endpoint: str
    p256dh: str
    auth: str

    def __repr__(self) -> str:
        # The endpoint is a capability URL (whoever has it can push to the device): never print it.
        return "PushTarget(<redacted>)"


class PushFailure(StrEnum):
    """What the push service answered, as the job records it (docs/ERRORS.md, ``PSH_``)."""

    GONE = "PSH_SUBSCRIPTION_GONE"  # 404 or 410: the browser unsubscribed; disable the device
    RATE_LIMITED = "PSH_SERVICE_RATE_LIMITED"  # 429: retried on the job's backoff
    UNAVAILABLE = "PSH_SERVICE_UNAVAILABLE"  # 5xx, a timeout or no connection: retried
    REFUSED = "PSH_REFUSED"  # any other answer (a bad key, too large, a redirect): not retried

    @property
    def retryable(self) -> bool:
        return self in (PushFailure.RATE_LIMITED, PushFailure.UNAVAILABLE)


class PushFailed(Exception):
    def __init__(self, failure: PushFailure, *, status: int | None = None) -> None:
        super().__init__(failure.value)
        self.failure = failure
        self.status = status


class WebPushPort(Protocol):
    @property
    def provider(self) -> str:
        """For logs: ``webpush`` or ``console``."""
        ...

    def send(self, target: PushTarget, data: str, *, ttl: int) -> None:
        """Encrypt ``data`` for the browser and hand it to its push service, or raise
        ``PushFailed``."""
        ...
