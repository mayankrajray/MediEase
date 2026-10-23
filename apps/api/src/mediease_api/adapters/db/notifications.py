"""``notifications`` and ``notification_preferences`` (M6a-P7, ADR-0017).

Both are tenant tables reached only through ``TenantScopedRepository``: every query carries the
clinic, and a member's notifications are also filtered by recipient, so another member's or
another clinic's are simply not found.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from mediease_api.adapters.db.models.notifications import NotificationPreferenceRow, NotificationRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.notifications.notification import (
    Channel,
    Notification,
    NotificationKind,
    Preference,
)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def _from_row(row: NotificationRow) -> Notification:
    created = _utc(row.created_at)
    assert created is not None
    return Notification(
        id=row.id,
        clinic_id=row.clinic_id,
        recipient_user_id=row.recipient_user_id,
        kind=NotificationKind(row.kind),
        event_key=row.event_key,
        title=row.title,
        link=row.link,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        created_at=created,
        read_at=_utc(row.read_at),
    )


class SqlAlchemyNotificationRepository(TenantScopedRepository[NotificationRow]):
    model = NotificationRow
    entity_name = "notification"

    def add_many(self, notifications: Sequence[Notification]) -> int:
        if not notifications:
            return 0
        for n in notifications:
            self._check_owned(n.clinic_id)
        statement = (
            insert(NotificationRow)
            .values(
                [
                    {
                        "id": n.id,
                        "clinic_id": self.clinic_id,
                        "recipient_user_id": n.recipient_user_id,
                        "kind": n.kind.value,
                        "event_key": n.event_key,
                        "title": n.title,
                        "link": n.link,
                        "entity_type": n.entity_type,
                        "entity_id": n.entity_id,
                        "created_at": n.created_at,
                        "read_at": n.read_at,
                    }
                    for n in notifications
                ]
            )
            .on_conflict_do_nothing(index_elements=["clinic_id", "recipient_user_id", "event_key"])
            .returning(NotificationRow.id)
        )
        return len(self._session.execute(statement).all())

    def list_for(self, user_id: UUID, *, limit: int) -> Sequence[Notification]:
        query = (
            self._scoped_select()
            .where(NotificationRow.recipient_user_id == user_id)
            .order_by(NotificationRow.created_at.desc(), NotificationRow.id.desc())
            .limit(limit)
        )
        return [_from_row(row) for row in self._session.scalars(query)]

    def unread_count(self, user_id: UUID) -> int:
        query = select(func.count()).where(
            NotificationRow.clinic_id == self.clinic_id,
            NotificationRow.recipient_user_id == user_id,
            NotificationRow.read_at.is_(None),
        )
        return int(self._session.scalar(query) or 0)

    def get_for(self, user_id: UUID, notification_id: UUID) -> Notification | None:
        query = self._scoped_select().where(
            NotificationRow.id == notification_id, NotificationRow.recipient_user_id == user_id
        )
        row = self._session.scalars(query).one_or_none()
        return _from_row(row) if row else None

    def update(self, notification: Notification) -> None:
        self._check_owned(notification.clinic_id)
        row = self._require_row(notification.id)
        row.read_at = notification.read_at
        self._session.flush()

    def mark_all_read(self, user_id: UUID, now: datetime) -> int:
        statement = (
            update(NotificationRow)
            .where(
                NotificationRow.clinic_id == self.clinic_id,
                NotificationRow.recipient_user_id == user_id,
                NotificationRow.read_at.is_(None),
            )
            .values(read_at=now)
        )
        return int(self._session.execute(statement).rowcount)  # type: ignore[attr-defined]


class SqlAlchemyPreferenceRepository(TenantScopedRepository[NotificationPreferenceRow]):
    model = NotificationPreferenceRow
    entity_name = "notification preference"

    def list_for(self, user_id: UUID) -> Sequence[Preference]:
        query = self._scoped_select().where(NotificationPreferenceRow.user_id == user_id)
        return [
            Preference(
                user_id=row.user_id,
                kind=NotificationKind(row.kind),
                channel=Channel(row.channel),
                enabled=row.enabled,
            )
            for row in self._session.scalars(query)
        ]

    def disabled_among(
        self, user_ids: Collection[UUID], kind: NotificationKind, channel: Channel
    ) -> set[UUID]:
        ids = sorted(set(user_ids))
        if not ids:
            return set()
        query = select(NotificationPreferenceRow.user_id).where(
            NotificationPreferenceRow.clinic_id == self.clinic_id,
            NotificationPreferenceRow.user_id.in_(ids),
            NotificationPreferenceRow.kind == kind.value,
            NotificationPreferenceRow.channel == channel.value,
            NotificationPreferenceRow.enabled.is_(False),
        )
        return set(self._session.scalars(query))

    def set(self, preference: Preference, *, id: UUID, now: datetime) -> None:
        """Insert or change the choice; ``id`` is used only when it is new."""
        statement = (
            insert(NotificationPreferenceRow)
            .values(
                id=id,
                clinic_id=self.clinic_id,
                user_id=preference.user_id,
                kind=preference.kind.value,
                channel=preference.channel.value,
                enabled=preference.enabled,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["clinic_id", "user_id", "kind", "channel"],
                set_={"enabled": preference.enabled, "updated_at": now},
            )
        )
        self._session.execute(statement)
