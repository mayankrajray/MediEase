"""The *Today* dashboard's counts (M6-P1, decision 5A; ``ports/dashboard.py``).

Tenant-scoped like every clinic read (ADR-0003): the repository is bound to one clinic and every
query filters every table it touches by it, joins included, so another clinic's rows can never
be counted (``tests/tenancy/``). Counts are computed in PostgreSQL; nothing here returns a reason,
a note or a message's content.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func, select, text
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models import AppointmentRow, MessageRow, PatientRow, SessionRow
from mediease_api.adapters.db.reminders import PENDING_COUNT
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.messaging.message import MessageStatus
from mediease_api.domain.shared.time import local_day_start
from mediease_api.ports.dashboard import DayTotals, NextPatient, StatusCounts

_STILL_TO_SEE = (AppointmentStatus.ARRIVED.value, AppointmentStatus.BOOKED.value)

_WEEK_APPOINTMENTS = text(
    """
    SELECT s.on_date,
           count(*) AS appointments,
           count(*) FILTER (WHERE a.status = 'COMPLETED') AS completed,
           count(*) FILTER (WHERE a.status = 'NO_SHOW') AS no_show
    FROM appointments a
    JOIN sessions s ON s.id = a.session_id AND s.clinic_id = :clinic
    WHERE a.clinic_id = :clinic AND a.status <> 'CANCELLED'
      AND s.on_date BETWEEN :first AND :last
      AND (CAST(:doctor AS uuid) IS NULL OR a.doctor_id = CAST(:doctor AS uuid))
    GROUP BY s.on_date
    """
)

# A message counts as sent once the provider accepted it (it has sent_at), whatever came after.
_WEEK_MESSAGES = text(
    """
    SELECT (m.sent_at AT TIME ZONE :tz)::date AS on_date, count(*) AS sent
    FROM messages m
    WHERE m.clinic_id = :clinic AND m.sent_at >= :since AND m.sent_at < :until
    GROUP BY 1
    """
)


def first_name(full_name: str) -> str:
    """The first word of a name: enough to call a patient, less than the whole name."""
    parts = full_name.split()
    return parts[0] if parts else ""


class SqlAlchemyDashboardReads:
    """``DashboardReads`` for one clinic."""

    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    @property
    def clinic_id(self) -> UUID:
        return self._clinic_id

    def status_counts_by_session(self, session_ids: Sequence[UUID]) -> Mapping[UUID, StatusCounts]:
        if not session_ids:
            return {}
        query = (
            select(AppointmentRow.session_id, AppointmentRow.status, func.count())
            .where(
                AppointmentRow.clinic_id == self._clinic_id,
                AppointmentRow.session_id.in_(session_ids),
                AppointmentRow.status != AppointmentStatus.CANCELLED.value,
            )
            .group_by(AppointmentRow.session_id, AppointmentRow.status)
        )
        raw: dict[UUID, dict[str, int]] = {}
        for session_id, status, n in self._session.execute(query):
            raw.setdefault(session_id, {})[status] = int(n)
        return {
            session_id: StatusCounts(
                not_arrived=counts.get(AppointmentStatus.BOOKED.value, 0),
                waiting=counts.get(AppointmentStatus.ARRIVED.value, 0),
                in_consultation=counts.get(AppointmentStatus.IN_CONSULTATION.value, 0),
                completed=counts.get(AppointmentStatus.COMPLETED.value, 0),
                no_show=counts.get(AppointmentStatus.NO_SHOW.value, 0),
            )
            for session_id, counts in raw.items()
        }

    def next_patients(self, session_ids: Sequence[UUID], *, limit: int) -> Sequence[NextPatient]:
        if not session_ids:
            return []
        waiting_first = case((AppointmentRow.status == AppointmentStatus.ARRIVED.value, 0), else_=1)
        query = (
            select(
                AppointmentRow.id,
                AppointmentRow.session_id,
                AppointmentRow.doctor_id,
                AppointmentRow.status,
                AppointmentRow.token_number,
                AppointmentRow.slot_start,
                PatientRow.code,
                PatientRow.full_name,
            )
            .join(
                SessionRow,
                and_(
                    SessionRow.id == AppointmentRow.session_id,
                    SessionRow.clinic_id == self._clinic_id,
                ),
            )
            .join(
                PatientRow,
                and_(
                    PatientRow.id == AppointmentRow.patient_id,
                    PatientRow.clinic_id == self._clinic_id,
                ),
            )
            .where(
                AppointmentRow.clinic_id == self._clinic_id,
                AppointmentRow.session_id.in_(session_ids),
                AppointmentRow.status.in_(_STILL_TO_SEE),
            )
            .order_by(
                waiting_first,
                func.coalesce(AppointmentRow.slot_start, SessionRow.starts_at),
                AppointmentRow.token_number.nulls_last(),
                AppointmentRow.id,
            )
            .limit(limit)
        )
        return [
            NextPatient(
                appointment_id=row.id,
                session_id=row.session_id,
                doctor_id=row.doctor_id,
                status=row.status,
                token_number=row.token_number,
                slot_start=row.slot_start,
                patient_code=row.code,
                patient_first_name=first_name(row.full_name),
            )
            for row in self._session.execute(query)
        ]

    def pending_follow_up_count(self, *, today: date, timezone: str) -> int:
        count = self._session.execute(
            PENDING_COUNT, {"clinic": self._clinic_id, "today": today, "tz": timezone}
        ).scalar_one()
        return int(count)

    def failed_message_count(self, *, since: datetime, until: datetime) -> int:
        query = select(func.count()).where(
            MessageRow.clinic_id == self._clinic_id,
            MessageRow.status == MessageStatus.FAILED.value,
            MessageRow.failed_at >= since,
            MessageRow.failed_at < until,
        )
        return int(self._session.execute(query).scalar_one())

    def week(
        self, *, first: date, last: date, doctor_id: UUID | None, timezone: str
    ) -> Sequence[DayTotals]:
        appointments = {
            row.on_date: row
            for row in self._session.execute(
                _WEEK_APPOINTMENTS,
                {
                    "clinic": self._clinic_id,
                    "first": first,
                    "last": last,
                    "doctor": str(doctor_id) if doctor_id else None,
                },
            )
        }
        sent: dict[date, int] = {}
        if doctor_id is None:
            sent = {
                row.on_date: int(row.sent)
                for row in self._session.execute(
                    _WEEK_MESSAGES,
                    {
                        "clinic": self._clinic_id,
                        "tz": timezone,
                        "since": local_day_start(first, timezone),
                        "until": local_day_start(last + timedelta(days=1), timezone),
                    },
                )
            }
        days: list[DayTotals] = []
        day = first
        while day <= last:
            row = appointments.get(day)
            days.append(
                DayTotals(
                    on_date=day,
                    appointments=int(row.appointments) if row else 0,
                    completed=int(row.completed) if row else 0,
                    no_show=int(row.no_show) if row else 0,
                    messages_sent=None if doctor_id is not None else sent.get(day, 0),
                )
            )
            day += timedelta(days=1)
        return days
