"""``reminders`` and the follow-up and no-show queries (M5-P4).

``SqlAlchemyReminderRepository`` is tenant-scoped like every clinic table; its two read queries
filter every table they touch by the same clinic. ``SqlAlchemyNoShowSweep`` is the reviewed
cross-clinic exception: it returns clinic IDs only.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Select, select, text, true
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models import MessageRow
from mediease_api.adapters.db.models.reminders import ReminderRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.messaging.message import SourceType
from mediease_api.domain.reminders.reminder import (
    Reminder,
    ReminderKind,
    ReminderSource,
    ReminderStatus,
)
from mediease_api.ports.reminders import PendingFollowUp, ReminderRead


def _write(row: ReminderRow, reminder: Reminder) -> None:
    row.follow_up_date = reminder.follow_up_date
    row.due_at = reminder.due_at
    row.status = reminder.status.value
    row.revision = reminder.revision
    row.error_code = reminder.error_code
    row.cancelled_by = reminder.cancelled_by
    row.cancelled_at = reminder.cancelled_at
    row.updated_at = reminder.updated_at


def _from_row(row: ReminderRow) -> Reminder:
    return Reminder(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        doctor_id=row.doctor_id,
        kind=ReminderKind(row.kind),
        source=ReminderSource(row.source),
        source_id=row.source_id,
        follow_up_date=row.follow_up_date,
        due_at=row.due_at,
        status=ReminderStatus(row.status),
        revision=row.revision,
        error_code=row.error_code,
        created_by=row.created_by,
        cancelled_by=row.cancelled_by,
        cancelled_at=row.cancelled_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


_LATEST_OVERDUE = """
    WITH latest AS (
        SELECT DISTINCT ON (p.patient_id)
               p.id, p.visit_id, p.patient_id, p.doctor_id, p.follow_up_date
        FROM prescriptions p
        WHERE p.clinic_id = :clinic AND p.status = 'ISSUED'
          AND p.follow_up_date IS NOT NULL AND p.follow_up_date < :today
        ORDER BY p.patient_id, p.follow_up_date DESC, p.issued_at DESC
    )
"""

# No completed visit on or after the follow-up date (R17). Shared by the list and the count
# (M6-P1), so the dashboard's number is always the length of the list.
_NOT_SEEN_SINCE = """
    NOT EXISTS (
        SELECT 1 FROM visits v
        WHERE v.clinic_id = :clinic AND v.patient_id = l.patient_id AND v.status = 'COMPLETED'
          AND (v.started_at AT TIME ZONE :tz)::date >= l.follow_up_date
    )
"""

_PENDING = text(
    _LATEST_OVERDUE
    + """
    SELECT l.id, l.visit_id, l.patient_id, l.doctor_id, l.follow_up_date,
           pt.code, pt.full_name,
           (SELECT coalesce(m.status, r.status)
              FROM prescriptions first
              JOIN reminders r ON r.clinic_id = :clinic AND r.source_id = first.id
              LEFT JOIN messages m ON m.clinic_id = :clinic AND m.source_type = 'REMINDER'
                                  AND m.source_id = r.id
             WHERE first.clinic_id = :clinic AND first.visit_id = l.visit_id AND first.version = 1
             ORDER BY r.created_at DESC, m.created_at DESC NULLS LAST, m.id DESC
             LIMIT 1) AS reminder_status
    FROM latest l
    JOIN patients pt ON pt.id = l.patient_id AND pt.clinic_id = :clinic
    WHERE"""
    + _NOT_SEEN_SINCE
    + """
      -- M6a-P6 (decision 7A): the Doctor workspace's "my follow-ups".
      AND (CAST(:doctor AS uuid) IS NULL OR l.doctor_id = CAST(:doctor AS uuid))
    ORDER BY l.follow_up_date, l.patient_id
    LIMIT :limit OFFSET :offset
    """
)

PENDING_COUNT = text(
    _LATEST_OVERDUE
    + """
    SELECT count(*) FROM latest l
    JOIN patients pt ON pt.id = l.patient_id AND pt.clinic_id = :clinic
    WHERE"""
    + _NOT_SEEN_SINCE
)


class SqlAlchemyReminderRepository(TenantScopedRepository[ReminderRow]):
    model = ReminderRow
    entity_name = "reminder"

    def add(self, reminder: Reminder) -> None:
        self._check_owned(reminder.clinic_id)
        row = ReminderRow(
            id=reminder.id,
            clinic_id=self.clinic_id,
            patient_id=reminder.patient_id,
            doctor_id=reminder.doctor_id,
            kind=reminder.kind.value,
            source=reminder.source.value,
            source_id=reminder.source_id,
            created_by=reminder.created_by,
            created_at=reminder.created_at,
        )
        _write(row, reminder)
        self._session.add(row)
        self._session.flush()

    def update(self, reminder: Reminder) -> None:
        self._check_owned(reminder.clinic_id)
        _write(self._require_row(reminder.id), reminder)
        self._session.flush()

    def get(self, reminder_id: UUID, *, for_update: bool = False) -> Reminder | None:
        return self._one(self._scoped_select().where(ReminderRow.id == reminder_id), for_update)

    def scheduled_for_chain(self, chain_id: UUID, *, for_update: bool = False) -> Reminder | None:
        query = self._scoped_select().where(
            ReminderRow.source_id == chain_id,
            ReminderRow.status == ReminderStatus.SCHEDULED.value,
        )
        return self._one(query, for_update)

    def sent_for_chain(self, chain_id: UUID, follow_up_date: date) -> bool:
        query = self._scoped_select().where(
            ReminderRow.source_id == chain_id,
            ReminderRow.follow_up_date == follow_up_date,
            ReminderRow.status == ReminderStatus.SENT.value,
        )
        return self._session.scalars(query.limit(1)).first() is not None

    def list_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[ReminderRead]:
        # A reminder shows its latest message (P4 decision 3A): the SMS once it fell back (P5).
        latest = (
            select(MessageRow.status, MessageRow.error_code)
            .where(
                MessageRow.clinic_id == ReminderRow.clinic_id,
                MessageRow.source_type == SourceType.REMINDER.value,
                MessageRow.source_id == ReminderRow.id,
            )
            .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
            .limit(1)
            .lateral("latest_message")
        )
        query = (
            select(ReminderRow, latest.c.status, latest.c.error_code)
            .outerjoin(latest, true())
            .where(ReminderRow.clinic_id == self.clinic_id, ReminderRow.patient_id == patient_id)
            .order_by(ReminderRow.due_at.desc(), ReminderRow.id.desc())
            .limit(limit)
        )
        return [
            ReminderRead(_from_row(row), status, error)
            for row, status, error in self._session.execute(query)
        ]

    def pending_follow_ups(
        self,
        *,
        today: date,
        timezone: str,
        limit: int,
        offset: int,
        doctor_id: UUID | None = None,
    ) -> Sequence[PendingFollowUp]:
        rows = self._session.execute(
            _PENDING,
            {
                "clinic": self.clinic_id,
                "today": today,
                "tz": timezone,
                "limit": limit,
                "offset": offset,
                "doctor": doctor_id,
            },
        )
        return [
            PendingFollowUp(
                patient_id=r.patient_id,
                patient_code=r.code,
                patient_name=r.full_name,
                doctor_id=r.doctor_id,
                prescription_id=r.id,
                visit_id=r.visit_id,
                follow_up_date=r.follow_up_date,
                reminder_status=r.reminder_status,
            )
            for r in rows
        ]

    def _one(self, query: Select[ReminderRow], for_update: bool) -> Reminder | None:
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _from_row(row) if row else None


class SqlAlchemyNoShowSweep:
    """Active clinics with bookings still ``BOOKED`` after their session (IDs only)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def clinics_with_overdue(self, *, ended_before: datetime) -> Sequence[UUID]:
        rows = self._session.execute(
            text(
                "SELECT DISTINCT a.clinic_id FROM appointments a"
                " JOIN sessions s ON s.id = a.session_id"
                " JOIN clinics c ON c.id = a.clinic_id"
                " WHERE a.status = 'BOOKED' AND s.ends_at <= :cutoff AND c.status = 'ACTIVE'"
                " ORDER BY a.clinic_id"
            ),
            {"cutoff": ended_before},
        )
        return [row.clinic_id for row in rows]
