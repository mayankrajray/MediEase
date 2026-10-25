"""Patient notifications (M6b-P6; portal spec R55-R68)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.portal.notifications import (
    PatientChannel,
    PatientNotification,
    PatientNotificationKind,
)


class PatientNotificationRepository(Protocol):
    """``patient_notifications`` written in one clinic's context (tenant-scoped, ADR-0003)."""

    def add_many(self, notifications: Sequence[PatientNotification]) -> list[UUID]:
        """Insert, skipping any whose ``(account_id, event_key)`` exists (R58); returns the IDs
        actually written, so a replay enqueues no second email."""
        ...


class PatientNotificationLookup(Protocol):
    """One account's notices in every clinic (reviewed cross-clinic exception, like the portal
    lookup). Visible: notices of the ``linked`` clinics, and booking notices of the account's own
    requests; never a suspended clinic's (R60)."""

    def list_for(
        self, account_id: UUID, linked: Collection[UUID], *, limit: int
    ) -> Sequence[PatientNotification]:
        """Newest first."""
        ...

    def unread_count(self, account_id: UUID, linked: Collection[UUID]) -> int: ...

    def get_for(
        self, account_id: UUID, linked: Collection[UUID], notification_id: UUID
    ) -> PatientNotification | None: ...

    def mark_read(self, account_id: UUID, notification_id: UUID, now: datetime) -> bool: ...

    def mark_all_read(self, account_id: UUID, linked: Collection[UUID], now: datetime) -> int: ...

    def clinics_with_reminders(self) -> Sequence[UUID]:
        """R66: active clinics with an enabled medicine reminder choice (IDs only, the sweep)."""
        ...


@dataclass(frozen=True, slots=True)
class PatientPreference:
    kind: PatientNotificationKind
    channel: PatientChannel
    enabled: bool


class PatientPreferenceRepository(Protocol):
    """``patient_notification_preferences``: the account's own, not tenant data (R62, R63)."""

    def list_for(self, account_id: UUID) -> Sequence[PatientPreference]: ...

    def is_off(
        self, account_id: UUID, kind: PatientNotificationKind, channel: PatientChannel
    ) -> bool:
        """True only when the account turned it off; everything is on by default."""
        ...

    def set(
        self, account_id: UUID, preference: PatientPreference, *, id: UUID, now: datetime
    ) -> None: ...
