"""The notification centre and preferences (M6a-P7; FR-NTF-03, FR-NTF-05).

Every use case acts on the caller's own notifications in the request's clinic: another member's
or another clinic's is "not found". Reading is not audited (decision 8A); changing a preference is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.notifications.notification import (
    KINDS,
    Channel,
    Notification,
    NotificationKind,
    Preference,
    ensure_in_app,
)
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

LIST_MAX = 50


@dataclass(frozen=True, slots=True)
class Summary:
    unread: int
    # The newest notification's ID: the ETag changes when one arrives, even if read meanwhile.
    latest_id: UUID | None


@dataclass(frozen=True, slots=True)
class PreferenceView:
    kind: NotificationKind
    label: str
    channel: Channel
    enabled: bool


class ListNotifications:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext, *, limit: int) -> Sequence[Notification]:
        if not 1 <= limit <= LIST_MAX:
            raise InvalidValue("limit", f"must be 1-{LIST_MAX}")
        with self._uow as uow:
            return uow.tenant(ctx.clinic_id).notifications.list_for(ctx.user_id, limit=limit)


class GetNotificationSummary:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext) -> Summary:
        with self._uow as uow:
            notifications = uow.tenant(ctx.clinic_id).notifications
            latest = notifications.list_for(ctx.user_id, limit=1)
            return Summary(
                unread=notifications.unread_count(ctx.user_id),
                latest_id=latest[0].id if latest else None,
            )


class ReadNotification:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext, notification_id: UUID) -> Notification:
        with self._uow as uow:
            notifications = uow.tenant(ctx.clinic_id).notifications
            notification = notifications.get_for(ctx.user_id, notification_id)
            if notification is None:
                logger.info(
                    "tenancy.not_found",
                    entity="notification",
                    entity_id=str(notification_id),
                    clinic_id=str(ctx.clinic_id),
                )
                raise NotFound("notification")
            if notification.mark_read(self._clock.now()):
                notifications.update(notification)
                uow.commit()
            return notification


class ReadAllNotifications:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext) -> int:
        with self._uow as uow:
            count = uow.tenant(ctx.clinic_id).notifications.mark_all_read(
                ctx.user_id, self._clock.now()
            )
            uow.commit()
        return count


def _views(saved: Sequence[Preference]) -> list[PreferenceView]:
    chosen = {(p.kind, p.channel): p.enabled for p in saved}
    return [
        PreferenceView(
            kind=kind,
            label=info.label,
            channel=Channel.IN_APP,
            enabled=chosen.get((kind, Channel.IN_APP), True),
        )
        for kind, info in KINDS.items()
    ]


class GetNotificationPreferences:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext) -> list[PreferenceView]:
        with self._uow as uow:
            return _views(uow.tenant(ctx.clinic_id).notification_preferences.list_for(ctx.user_id))


@dataclass(frozen=True, slots=True)
class PreferenceChange:
    kind: NotificationKind
    channel: Channel
    enabled: bool


class SetNotificationPreferences:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, ctx: RequestContext, changes: Sequence[PreferenceChange]
    ) -> list[PreferenceView]:
        for change in changes:
            ensure_in_app(change.channel)
        with self._uow as uow:
            now = self._clock.now()
            preferences = uow.tenant(ctx.clinic_id).notification_preferences
            before = {v.kind: v.enabled for v in _views(preferences.list_for(ctx.user_id))}
            turned_on: list[str] = []
            turned_off: list[str] = []
            for change in changes:
                if before[change.kind] is change.enabled:
                    continue
                preferences.set(
                    Preference(
                        user_id=ctx.user_id,
                        kind=change.kind,
                        channel=change.channel,
                        enabled=change.enabled,
                    ),
                    id=self._ids.new_id(),
                    now=now,
                )
                before[change.kind] = change.enabled
                (turned_on if change.enabled else turned_off).append(change.kind.value)
            if turned_on or turned_off:
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.NOTIFICATION_PREFERENCES_CHANGED,
                    actor=Actor.staff(ctx),
                    now=now,
                    clinic_id=ctx.clinic_id,
                    entity_type="user",
                    entity_id=ctx.user_id,
                    metadata={"on": ",".join(turned_on), "off": ",".join(turned_off)},
                )
            views = _views(preferences.list_for(ctx.user_id))
            uow.commit()
        return views
