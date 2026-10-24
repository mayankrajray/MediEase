"""A reminder: a follow-up (spec R1-R5; FR-REM-01, 02, 05; M5-P4 decisions 1A, 3A), or from
M6a-P8 an appointment reminder (FR-APT-08; decisions 1A, 4A) that follows its appointment.

One reminder per prescription chain at most is ``SCHEDULED`` (``source_id`` is the chain's
version 1, like its patient link). Moving it bumps ``revision``; every send job carries the revision
it was made for, so a job made before a move finds a newer revision and does nothing (1A). No job
is ever edited.

Statuses kept here are what happens before a message exists: ``SCHEDULED``, ``CANCELLED``,
``SKIPPED_NO_CONSENT``, ``FAILED`` (the clinic has no phone) and ``SENT`` once the message row is
written. From then on the visible status is the message's own (``SENT``, ``DELIVERED``, ``READ``,
``FAILED``), so status webhooks never touch two tables (3A).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.reminders.errors import NotScheduled
from mediease_api.domain.shared.time import require_utc


class ReminderKind(StrEnum):
    FOLLOW_UP = "FOLLOW_UP"
    # M6a-P8: before a booked visit. `follow_up_date` holds the visit's date.
    APPOINTMENT = "APPOINTMENT"


class ReminderSource(StrEnum):
    PRESCRIPTION = "PRESCRIPTION"
    MANUAL = "MANUAL"
    # M6a-P8: scheduled by the notification service for an appointment (``appointment_id``).
    APPOINTMENT = "APPOINTMENT"


class ReminderStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    CANCELLED = "CANCELLED"
    SKIPPED_NO_CONSENT = "SKIPPED_NO_CONSENT"
    FAILED = "FAILED"


@dataclass(slots=True)
class Reminder:
    id: UUID
    clinic_id: UUID
    patient_id: UUID
    doctor_id: UUID
    kind: ReminderKind
    source: ReminderSource
    source_id: UUID | None
    follow_up_date: date
    due_at: datetime
    status: ReminderStatus
    revision: int
    error_code: str | None
    # Null for the system: an appointment reminder for a booking made without a staff member.
    created_by: UUID | None
    cancelled_by: UUID | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    appointment_id: UUID | None = None

    @classmethod
    def schedule(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        doctor_id: UUID,
        source: ReminderSource,
        source_id: UUID | None,
        follow_up_date: date,
        due_at: datetime,
        created_by: UUID,
        now: datetime,
    ) -> Reminder:
        now = require_utc(now, "now")
        assert (source is ReminderSource.PRESCRIPTION) == (source_id is not None)
        assert source is not ReminderSource.APPOINTMENT, "use for_appointment"
        return cls(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            kind=ReminderKind.FOLLOW_UP,
            source=source,
            source_id=source_id,
            follow_up_date=follow_up_date,
            due_at=require_utc(due_at, "due_at"),
            status=ReminderStatus.SCHEDULED,
            revision=1,
            error_code=None,
            created_by=created_by,
            cancelled_by=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def for_appointment(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        doctor_id: UUID,
        appointment_id: UUID,
        visit_date: date,
        due_at: datetime,
        created_by: UUID | None,
        now: datetime,
    ) -> Reminder:
        """M6a-P8 (FR-APT-08): one of an appointment's reminders, due at ``due_at``."""
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            kind=ReminderKind.APPOINTMENT,
            source=ReminderSource.APPOINTMENT,
            source_id=None,
            follow_up_date=visit_date,
            due_at=require_utc(due_at, "due_at"),
            status=ReminderStatus.SCHEDULED,
            revision=1,
            error_code=None,
            created_by=created_by,
            cancelled_by=None,
            cancelled_at=None,
            created_at=now,
            updated_at=now,
            appointment_id=appointment_id,
        )

    @property
    def follows_appointment(self) -> bool:
        return self.kind is ReminderKind.APPOINTMENT

    @property
    def is_scheduled(self) -> bool:
        return self.status is ReminderStatus.SCHEDULED

    def move(self, *, follow_up_date: date, due_at: datetime, now: datetime) -> None:
        """R2 / FR-REM-02: a new date; the job made for the old revision will do nothing."""
        self._require_scheduled()
        self.follow_up_date = follow_up_date
        self._reschedule(due_at, now)

    def defer(self, due_at: datetime, now: datetime) -> None:
        """R4: due inside the quiet hours; sent at the next 08:00 instead."""
        self._require_scheduled()
        self._reschedule(due_at, now)

    def cancel(self, *, by: UUID | None, now: datetime, code: str | None = None) -> None:
        """``code``: why the system cancelled an appointment reminder that no longer applies."""
        self._require_scheduled()
        now = require_utc(now, "now")
        self.status = ReminderStatus.CANCELLED
        self.error_code = code
        self.cancelled_by = by
        self.cancelled_at = now
        self.revision += 1
        self.updated_at = now

    def handed_off(self, now: datetime) -> None:
        """The message row is written; its status is the reminder's from now on (3A)."""
        if self.status is ReminderStatus.SENT:
            return
        self._settle(ReminderStatus.SENT, None, now)

    def skipped_no_consent(self, now: datetime) -> None:
        """R5: no consent at send time; no message row."""
        self._settle(ReminderStatus.SKIPPED_NO_CONSENT, None, now)

    def failed(self, code: str, now: datetime) -> None:
        self._settle(ReminderStatus.FAILED, code, now)

    def _settle(self, status: ReminderStatus, code: str | None, now: datetime) -> None:
        self._require_scheduled()
        self.status = status
        self.error_code = code
        self.updated_at = require_utc(now, "now")

    def _reschedule(self, due_at: datetime, now: datetime) -> None:
        self.due_at = require_utc(due_at, "due_at")
        self.revision += 1
        self.updated_at = require_utc(now, "now")

    def _require_scheduled(self) -> None:
        if self.status is not ReminderStatus.SCHEDULED:
            raise NotScheduled(self.status.value)
