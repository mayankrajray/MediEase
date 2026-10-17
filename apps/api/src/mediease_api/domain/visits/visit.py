"""A visit: the clinical record of one consultation (FR-VIS-01, 02, 05; spec R1, R3).

A visit hangs off an appointment that is ``IN_CONSULTATION`` (R1; M4-P1 decisions 1A and 5A) and
belongs to that appointment's doctor. It is edited while open and for 24 hours after completion;
from ``locked_at`` on it is read-only and later changes are addenda (R3, AC6). "Locked" is a
comparison with the injected ``now``, so nothing has to run at the 24-hour mark (decision 6A).

Each change bumps ``revision``; an edit must name the revision it was made on, so a second tab
cannot silently overwrite the first (decision 4A, ``VIS_STALE``).

Clinical text is never logged or audited (R17): ``edit`` returns the *names* of the fields that
changed, which is all the audit row and the log line carry. Validation errors name the field and
the rule, never the value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc
from mediease_api.domain.visits.errors import (
    VisitLocked,
    VisitNotCompleted,
    VisitNotStartable,
    VisitNotYours,
    VisitStale,
)
from mediease_api.domain.visits.vitals import Vitals

LOCK_AFTER = timedelta(hours=24)

# Limits on free text (characters). Generous for a consultation; they stop accidents, not doctors.
TEXT_LIMITS: Mapping[str, int] = {
    "chief_complaint": 500,
    "findings": 5000,
    "diagnosis": 1000,
    "notes": 5000,
}
ADDENDUM_MAX = 5000
EDITABLE = frozenset({*TEXT_LIMITS, "vitals"})


class VisitStatus(StrEnum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True, slots=True)
class VisitAddendum:
    """A later note on a completed visit, with its author and time. Never changed or removed."""

    id: UUID
    clinic_id: UUID
    visit_id: UUID
    author_user_id: UUID
    body: str
    created_at: datetime


@dataclass(slots=True)
class Visit:
    id: UUID
    clinic_id: UUID
    patient_id: UUID
    doctor_id: UUID
    appointment_id: UUID
    status: VisitStatus
    chief_complaint: str | None
    findings: str | None
    diagnosis: str | None
    notes: str | None
    vitals: Vitals
    revision: int
    started_at: datetime
    completed_at: datetime | None
    locked_at: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def start(
        cls,
        appointment: Appointment,
        *,
        id: UUID,
        doctor_id: UUID,
        created_by: UUID,
        now: datetime,
    ) -> Visit:
        """R1: from an appointment in consultation, by its doctor (``doctor_id``: the caller's)."""
        now = require_utc(now, "now")
        if appointment.status is not AppointmentStatus.IN_CONSULTATION:
            raise VisitNotStartable(appointment.status.value)
        if doctor_id != appointment.doctor_id:
            raise VisitNotYours()
        return cls(
            id=id,
            clinic_id=appointment.clinic_id,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            appointment_id=appointment.id,
            status=VisitStatus.OPEN,
            chief_complaint=None,
            findings=None,
            diagnosis=None,
            notes=None,
            vitals=Vitals.empty(),
            revision=1,
            started_at=now,
            completed_at=None,
            locked_at=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_completed(self) -> bool:
        return self.status is VisitStatus.COMPLETED

    def is_locked(self, now: datetime) -> bool:
        """R3: read-only from exactly ``completed_at + 24 h``."""
        return self.locked_at is not None and require_utc(now, "now") >= self.locked_at

    def check_writer(self, doctor_id: UUID | None) -> None:
        """§2, decision 3A: only the visit's doctor writes it or adds an addendum."""
        if doctor_id != self.doctor_id:
            raise VisitNotYours()

    def edit(
        self, changes: Mapping[str, object], *, seen_revision: int, now: datetime
    ) -> tuple[str, ...]:
        """Apply ``changes`` (text fields and/or ``vitals``); return the names that changed.

        ``None`` or blank text clears a field. ``vitals`` replaces the whole set. Nothing changed
        means no new revision. Locked first: a stale tab on a locked visit is told the lasting
        reason, not asked to reload.
        """
        now = require_utc(now, "now")
        if self.is_locked(now):
            assert self.locked_at is not None
            raise VisitLocked(self.locked_at)
        if seen_revision != self.revision:
            raise VisitStale(self.revision)
        unknown = set(changes) - EDITABLE
        if unknown:
            raise InvalidValue(sorted(unknown)[0], "cannot be changed")

        changed: list[str] = []
        for name in sorted(changes):
            value = changes[name]
            if name == "vitals":
                if not isinstance(value, Vitals):
                    raise InvalidValue("vitals", "must be a vitals map")
                if value != self.vitals:
                    self.vitals = value
                    changed.append(name)
                continue
            text = _clinical_text(value, name, TEXT_LIMITS[name])
            if text != getattr(self, name):
                setattr(self, name, text)
                changed.append(name)
        if changed:
            self.revision += 1
            self.updated_at = now
        return tuple(changed)

    def complete(self, now: datetime) -> bool:
        """R3: completed now, locked 24 hours later. False when it already was (idempotent)."""
        now = require_utc(now, "now")
        if self.is_completed:
            return False
        self.status = VisitStatus.COMPLETED
        self.completed_at = now
        self.locked_at = now + LOCK_AFTER
        self.revision += 1
        self.updated_at = now
        return True

    def addendum(
        self, *, id: UUID, author_user_id: UUID, body: str, now: datetime
    ) -> VisitAddendum:
        """R3: a note on a completed visit, locked or not. An open visit is edited instead."""
        now = require_utc(now, "now")
        if not self.is_completed:
            raise VisitNotCompleted()
        text = _clinical_text(body, "body", ADDENDUM_MAX)
        if text is None:
            raise InvalidValue("body", "must not be empty")
        return VisitAddendum(
            id=id,
            clinic_id=self.clinic_id,
            visit_id=self.id,
            author_user_id=author_user_id,
            body=text,
            created_at=now,
        )


def _clinical_text(value: object, field: str, limit: int) -> str | None:
    """Trimmed text or None; the value itself never appears in the error."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidValue(field, "must be text")
    text = value.strip()
    if not text:
        return None
    if len(text) > limit:
        raise InvalidValue(field, f"must be at most {limit} characters")
    return text
