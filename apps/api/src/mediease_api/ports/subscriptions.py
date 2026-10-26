"""Clinic subscriptions (M6d-P7; FR-SUB-01): platform data, one row per clinic."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from mediease_api.domain.subscriptions.subscription import Subscription


class SubscriptionRepository(Protocol):
    def add(self, subscription: Subscription) -> None: ...

    def get(self, clinic_id: UUID, *, for_update: bool = False) -> Subscription | None:
        """``for_update`` locks the row: every limit check on one clinic takes it (R4)."""
        ...

    def update(self, subscription: Subscription) -> None: ...

    def all_by_clinic(self) -> Mapping[UUID, Subscription]:
        """Ops' clinic list: every clinic's subscription."""
        ...
