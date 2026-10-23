"""Notification storage ports (M6a-P7, ADR-0017). Both are tenant repositories (ADR-0003)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.notifications.notification import (
    Channel,
    Notification,
    NotificationKind,
    Preference,
)


class NotificationRepository(Protocol):
    def add_many(self, notifications: Sequence[Notification]) -> int:
        """Insert those not already there (one per recipient and event key); returns how many."""
        ...

    def list_for(self, user_id: UUID, *, limit: int) -> Sequence[Notification]:
        """This member's newest first."""
        ...

    def unread_count(self, user_id: UUID) -> int: ...

    def get_for(self, user_id: UUID, notification_id: UUID) -> Notification | None:
        """Only this member's own: another member's (or clinic's) is None."""
        ...

    def update(self, notification: Notification) -> None: ...

    def mark_all_read(self, user_id: UUID, now: datetime) -> int: ...


class PreferenceRepository(Protocol):
    def list_for(self, user_id: UUID) -> Sequence[Preference]:
        """The member's changed choices (a kind absent here is on)."""
        ...

    def disabled_among(
        self, user_ids: Collection[UUID], kind: NotificationKind, channel: Channel
    ) -> set[UUID]:
        """Which of these members turned ``kind`` off for ``channel``: one query."""
        ...

    def set(self, preference: Preference, *, id: UUID, now: datetime) -> None:
        """Insert or change the choice; ``id`` is used only when it is new."""
        ...
