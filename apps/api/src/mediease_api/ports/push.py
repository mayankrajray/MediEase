"""Ports for web push subscriptions (M7e-E2, ADR-0025)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from mediease_api.domain.push.subscription import PushOwner, PushSubscription


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

    def count_active(self, owner: PushOwner) -> int: ...


class TextCipherPort(Protocol):
    """Encryption at rest for short secrets (push endpoints and keys), with key rotation."""

    def encrypt(self, value: str) -> str: ...

    def decrypt(self, token: str) -> str: ...
