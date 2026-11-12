"""Web push subscriptions in PostgreSQL (M7e-E2, ADR-0025): owned by an account or a user."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.push import PushSubscriptionRow
from mediease_api.domain.push.subscription import (
    DisabledReason,
    OwnerKind,
    PushOwner,
    PushSubscription,
)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def _owner_of(row: PushSubscriptionRow) -> PushOwner:
    if row.account_id is not None:
        return PushOwner.patient(row.account_id)
    assert row.user_id is not None  # the one_owner CHECK
    return PushOwner.staff(row.user_id)


def _is(owner: PushOwner) -> ColumnElement[bool]:
    if owner.kind is OwnerKind.PATIENT:
        return PushSubscriptionRow.account_id == owner.id
    return PushSubscriptionRow.user_id == owner.id


def _subscription(row: PushSubscriptionRow) -> PushSubscription:
    return PushSubscription(
        id=row.id,
        owner=_owner_of(row),
        endpoint_digest=row.endpoint_digest,
        endpoint_encrypted=row.endpoint_encrypted,
        p256dh_encrypted=row.p256dh_encrypted,
        auth_encrypted=row.auth_encrypted,
        label=row.label,
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
        last_success_at=_utc(row.last_success_at),
        disabled_at=_utc(row.disabled_at),
        disabled_reason=DisabledReason(row.disabled_reason) if row.disabled_reason else None,
    )


def _copy(s: PushSubscription, row: PushSubscriptionRow) -> None:
    row.account_id = s.owner.id if s.owner.kind is OwnerKind.PATIENT else None
    row.user_id = s.owner.id if s.owner.kind is OwnerKind.STAFF else None
    row.p256dh_encrypted = s.p256dh_encrypted
    row.auth_encrypted = s.auth_encrypted
    row.label = s.label
    row.updated_at = s.updated_at
    row.last_success_at = s.last_success_at
    row.disabled_at = s.disabled_at
    row.disabled_reason = s.disabled_reason.value if s.disabled_reason else None


class SqlAlchemyPushSubscriptionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, subscription: PushSubscription) -> None:
        row = PushSubscriptionRow(
            id=subscription.id,
            endpoint_digest=subscription.endpoint_digest,
            endpoint_encrypted=subscription.endpoint_encrypted,
            created_at=subscription.created_at,
        )
        _copy(subscription, row)
        self._session.add(row)
        self._session.flush()

    def update(self, subscription: PushSubscription) -> None:
        row = self._session.get_one(PushSubscriptionRow, subscription.id)
        _copy(subscription, row)
        self._session.flush()

    def delete(self, subscription_id: UUID) -> None:
        self._session.execute(
            delete(PushSubscriptionRow).where(PushSubscriptionRow.id == subscription_id)
        )
        self._session.flush()

    def by_digest(self, digest: str, *, for_update: bool = False) -> PushSubscription | None:
        query = select(PushSubscriptionRow).where(PushSubscriptionRow.endpoint_digest == digest)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _subscription(row) if row else None

    def get_for_owner(self, subscription_id: UUID, owner: PushOwner) -> PushSubscription | None:
        query = select(PushSubscriptionRow).where(
            PushSubscriptionRow.id == subscription_id, _is(owner)
        )
        row = self._session.scalars(query).one_or_none()
        return _subscription(row) if row else None

    def list_for_owner(self, owner: PushOwner) -> Sequence[PushSubscription]:
        query = (
            select(PushSubscriptionRow)
            .where(_is(owner))
            .order_by(PushSubscriptionRow.created_at.desc(), PushSubscriptionRow.id)
        )
        return [_subscription(row) for row in self._session.scalars(query)]

    def active_for_owners(
        self, kind: OwnerKind, owner_ids: Collection[UUID]
    ) -> Sequence[PushSubscription]:
        if not owner_ids:
            return []
        column = (
            PushSubscriptionRow.account_id
            if kind is OwnerKind.PATIENT
            else PushSubscriptionRow.user_id
        )
        query = (
            select(PushSubscriptionRow)
            .where(column.in_(list(owner_ids)), PushSubscriptionRow.disabled_at.is_(None))
            .order_by(PushSubscriptionRow.created_at, PushSubscriptionRow.id)
        )
        return [_subscription(row) for row in self._session.scalars(query)]

    def count_active(self, owner: PushOwner) -> int:
        query = select(func.count()).where(_is(owner), PushSubscriptionRow.disabled_at.is_(None))
        return int(self._session.scalar(query) or 0)
