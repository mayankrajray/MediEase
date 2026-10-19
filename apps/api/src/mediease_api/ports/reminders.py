"""Reminders and the follow-up and no-show queries (M5-P4; FR-REM-01, 02, 05, 07; appts R10)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.reminders.reminder import Reminder


@dataclass(frozen=True, slots=True)
class ReminderRead:
    """A reminder with what its message says, once it has one (decision 3A)."""

    reminder: Reminder
    message_status: str | None = None
    message_error: str | None = None

    @property
    def visible_status(self) -> str:
        """FR-REM-05: the message's status once sent, else the reminder's own."""
        return self.message_status or self.reminder.status.value


@dataclass(frozen=True, slots=True)
class PendingFollowUp:
    """R17: a patient whose follow-up date passed without a completed visit since."""

    patient_id: UUID
    patient_code: str
    patient_name: str
    doctor_id: UUID
    prescription_id: UUID
    visit_id: UUID
    follow_up_date: date
    reminder_status: str | None


class ReminderRepository(Protocol):
    """``reminders`` of one clinic (tenant-scoped, ADR-0003)."""

    def add(self, reminder: Reminder) -> None: ...
    def update(self, reminder: Reminder) -> None: ...
    def get(self, reminder_id: UUID, *, for_update: bool = False) -> Reminder | None: ...

    def scheduled_for_chain(self, chain_id: UUID, *, for_update: bool = False) -> Reminder | None:
        """The chain's one ``SCHEDULED`` reminder (``source_id`` = version 1), if any."""
        ...

    def sent_for_chain(self, chain_id: UUID, follow_up_date: date) -> bool:
        """Whether a reminder for this chain and date was already handed to messaging."""
        ...

    def list_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[ReminderRead]: ...

    def pending_follow_ups(
        self, *, today: date, timezone: str, limit: int, offset: int
    ) -> Sequence[PendingFollowUp]: ...


class NoShowSweep(Protocol):
    """Which clinics have bookings overdue for ``NO_SHOW`` (appointments R10).

    Reviewed cross-clinic exception, like the job store: it returns clinic IDs only, for active
    clinics; each clinic's own job then reads and changes its appointments.
    """

    def clinics_with_overdue(self, *, ended_before: datetime) -> Sequence[UUID]: ...
