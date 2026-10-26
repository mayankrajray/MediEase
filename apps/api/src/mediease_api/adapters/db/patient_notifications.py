"""Patient notification repositories (M6b-P6, ports/patient_notifications.py).

``SqlAlchemyPatientNotificationRepository`` is tenant-scoped (the service writes in a clinic's
context). ``SqlAlchemyPatientNotificationLookup`` is a reviewed cross-clinic exception: it reads
one account's notices by account, limited to the clinics the caller passes as linked (plus the
account's own booking notices), never a suspended clinic's other than its booking answers (M6c-P4).
The preferences belong to the account.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.clinics import ClinicRow
from mediease_api.adapters.db.models.patient_notifications import (
    PatientNotificationPreferenceRow,
    PatientNotificationRow,
)
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.portal.notifications import (
    BOOKING_KINDS,
    PatientChannel,
    PatientNotification,
    PatientNotificationKind,
)
from mediease_api.ports.patient_notifications import PatientPreference

_BOOKING = sorted(k.value for k in BOOKING_KINDS)


def _not_suspended() -> ColumnElement[bool]:
    """A suspended clinic's notices disappear, except the booking answers: M6c-P4 (R57) tells the
    patient that a suspended clinic cannot take their request."""
    return or_(ClinicRow.status != "SUSPENDED", PatientNotificationRow.kind.in_(_BOOKING))


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def _notice(row: PatientNotificationRow) -> PatientNotification:
    return PatientNotification(
        id=row.id,
        clinic_id=row.clinic_id,
        account_id=row.account_id,
        kind=PatientNotificationKind(row.kind),
        event_key=row.event_key,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        link=row.link,
        params={str(k): str(v) for k, v in (row.params or {}).items()},
        created_at=row.created_at.astimezone(UTC),
        read_at=_utc(row.read_at),
    )


class SqlAlchemyPatientNotificationRepository(TenantScopedRepository[PatientNotificationRow]):
    model = PatientNotificationRow
    entity_name = "patient notification"

    def add_many(self, notifications: Sequence[PatientNotification]) -> list[UUID]:
        if not notifications:
            return []
        for n in notifications:
            self._check_owned(n.clinic_id)
        statement = (
            insert(PatientNotificationRow)
            .values(
                [
                    {
                        "id": n.id,
                        "clinic_id": self.clinic_id,
                        "account_id": n.account_id,
                        "kind": n.kind.value,
                        "event_key": n.event_key,
                        "entity_type": n.entity_type,
                        "entity_id": n.entity_id,
                        "link": n.link,
                        "params": dict(n.params),
                        "created_at": n.created_at,
                        "read_at": n.read_at,
                    }
                    for n in notifications
                ]
            )
            # R58: the database decides, so two workers handling one event write one row.
            .on_conflict_do_nothing(index_elements=["account_id", "event_key"])
            .returning(PatientNotificationRow.id)
        )
        return [row[0] for row in self._session.execute(statement).all()]


class SqlAlchemyPatientNotificationLookup:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _visible(account_id: UUID, linked: Collection[UUID]) -> ColumnElement[bool]:
        clinics = sorted(set(linked))
        reach: ColumnElement[bool] = PatientNotificationRow.kind.in_(_BOOKING)
        if clinics:
            reach = or_(reach, PatientNotificationRow.clinic_id.in_(clinics))
        return and_(PatientNotificationRow.account_id == account_id, reach)

    def _select(self, account_id: UUID, linked: Collection[UUID]) -> Select[PatientNotificationRow]:
        return (
            select(PatientNotificationRow)
            .join(ClinicRow, ClinicRow.id == PatientNotificationRow.clinic_id)
            .where(self._visible(account_id, linked), _not_suspended())
        )

    def list_for(
        self, account_id: UUID, linked: Collection[UUID], *, limit: int
    ) -> Sequence[PatientNotification]:
        query = (
            self._select(account_id, linked)
            .order_by(PatientNotificationRow.created_at.desc(), PatientNotificationRow.id.desc())
            .limit(limit)
        )
        return [_notice(row) for row in self._session.scalars(query)]

    def unread_count(self, account_id: UUID, linked: Collection[UUID]) -> int:
        query = (
            select(func.count())
            .select_from(PatientNotificationRow)
            .join(ClinicRow, ClinicRow.id == PatientNotificationRow.clinic_id)
            .where(
                self._visible(account_id, linked),
                _not_suspended(),
                PatientNotificationRow.read_at.is_(None),
            )
        )
        return int(self._session.scalar(query) or 0)

    def get_for(
        self, account_id: UUID, linked: Collection[UUID], notification_id: UUID
    ) -> PatientNotification | None:
        query = self._select(account_id, linked).where(PatientNotificationRow.id == notification_id)
        row = self._session.scalars(query).one_or_none()
        return _notice(row) if row else None

    def mark_read(self, account_id: UUID, notification_id: UUID, now: datetime) -> bool:
        result = self._session.execute(
            update(PatientNotificationRow)
            .where(
                PatientNotificationRow.id == notification_id,
                PatientNotificationRow.account_id == account_id,
                PatientNotificationRow.read_at.is_(None),
            )
            .values(read_at=now)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    def mark_all_read(self, account_id: UUID, linked: Collection[UUID], now: datetime) -> int:
        ids = [n.id for n in self.list_for(account_id, linked, limit=500) if n.read_at is None]
        if not ids:
            return 0
        result = self._session.execute(
            update(PatientNotificationRow)
            .where(PatientNotificationRow.id.in_(ids), PatientNotificationRow.read_at.is_(None))
            .values(read_at=now)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def clinics_with_reminders(self) -> Sequence[UUID]:
        rows = self._session.execute(
            text(
                "SELECT DISTINCT r.clinic_id FROM medicine_reminder_prefs r"
                " JOIN clinics c ON c.id = r.clinic_id"
                " WHERE r.enabled AND c.status = 'ACTIVE' ORDER BY r.clinic_id"
            )
        )
        return [row.clinic_id for row in rows]


class SqlAlchemyPatientPreferenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for(self, account_id: UUID) -> Sequence[PatientPreference]:
        query = (
            select(PatientNotificationPreferenceRow)
            .where(PatientNotificationPreferenceRow.account_id == account_id)
            .order_by(
                PatientNotificationPreferenceRow.kind, PatientNotificationPreferenceRow.channel
            )
        )
        return [
            PatientPreference(
                PatientNotificationKind(row.kind), PatientChannel(row.channel), row.enabled
            )
            for row in self._session.scalars(query)
        ]

    def is_off(
        self, account_id: UUID, kind: PatientNotificationKind, channel: PatientChannel
    ) -> bool:
        query = select(PatientNotificationPreferenceRow.enabled).where(
            PatientNotificationPreferenceRow.account_id == account_id,
            PatientNotificationPreferenceRow.kind == kind.value,
            PatientNotificationPreferenceRow.channel == channel.value,
        )
        enabled = self._session.scalar(query)
        return enabled is False

    def set(
        self, account_id: UUID, preference: PatientPreference, *, id: UUID, now: datetime
    ) -> None:
        self._session.execute(
            insert(PatientNotificationPreferenceRow)
            .values(
                id=id,
                account_id=account_id,
                kind=preference.kind.value,
                channel=preference.channel.value,
                enabled=preference.enabled,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["account_id", "kind", "channel"],
                set_={"enabled": preference.enabled, "updated_at": now},
            )
        )
        self._session.flush()
