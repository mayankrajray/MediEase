"""Clinic subscriptions (M6d-P7; ports/subscriptions.py): platform data, one row per clinic."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.subscriptions import ClinicSubscriptionRow
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.subscriptions.subscription import Plan, Subscription


def _subscription(row: ClinicSubscriptionRow) -> Subscription:
    return Subscription(
        clinic_id=row.clinic_id,
        plan=Plan(row.plan),
        trial_started_at=row.trial_started_at.astimezone(UTC) if row.trial_started_at else None,
        trial_ends_at=row.trial_ends_at.astimezone(UTC) if row.trial_ends_at else None,
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
        plan_changed_at=row.plan_changed_at.astimezone(UTC) if row.plan_changed_at else None,
        plan_changed_by=row.plan_changed_by,
        has_trial=row.has_trial,
    )


class SqlAlchemySubscriptionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, subscription: Subscription) -> None:
        self._session.add(
            ClinicSubscriptionRow(
                clinic_id=subscription.clinic_id,
                plan=subscription.plan.value,
                has_trial=subscription.has_trial,
                trial_started_at=subscription.trial_started_at,
                trial_ends_at=subscription.trial_ends_at,
                plan_changed_at=subscription.plan_changed_at,
                plan_changed_by=subscription.plan_changed_by,
                created_at=subscription.created_at,
                updated_at=subscription.updated_at,
            )
        )
        self._session.flush()

    def get(self, clinic_id: UUID, *, for_update: bool = False) -> Subscription | None:
        query = select(ClinicSubscriptionRow).where(ClinicSubscriptionRow.clinic_id == clinic_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _subscription(row) if row else None

    def update(self, subscription: Subscription) -> None:
        row = self._session.get(ClinicSubscriptionRow, subscription.clinic_id)
        if row is None:
            raise NotFound("subscription")
        row.plan = subscription.plan.value
        row.trial_started_at = subscription.trial_started_at
        row.trial_ends_at = subscription.trial_ends_at
        row.plan_changed_at = subscription.plan_changed_at
        row.plan_changed_by = subscription.plan_changed_by
        row.updated_at = subscription.updated_at
        self._session.flush()

    def all_by_clinic(self) -> Mapping[UUID, Subscription]:
        rows = self._session.scalars(select(ClinicSubscriptionRow))
        return {row.clinic_id: _subscription(row) for row in rows}
