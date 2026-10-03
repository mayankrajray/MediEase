"""OnboardingChecklist — when each onboarding step first happened (FR-OPS-04, spec R12).

Goal G4 is "a clinic is live in under an hour". That is only measurable if the
steps timestamp themselves as they happen, so each action records its own step
and the elapsed time becomes a fact in the database rather than a note in
someone's head.

**R12: the first time wins.** Adding a second doctor does not move
``doctors_added_at``, and re-importing patients does not move
``patients_imported_at``. ``record`` returns whether it changed anything, so a
caller can tell a first from a repeat without reading the row again.

Steps after ``STAFF_INVITED`` belong to later milestones (patients in M2, the
first appointment in M3, the first prescription in M4); the column exists from
the start so the measurement is not retrofitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.time import require_utc


class OnboardingStep(StrEnum):
    """Values are the column names in ``onboarding_checklists``."""

    CLINIC_CREATED = "clinic_created_at"
    DOCTORS_ADDED = "doctors_added_at"
    STAFF_INVITED = "staff_invited_at"
    PATIENTS_IMPORTED = "patients_imported_at"
    FIRST_APPOINTMENT = "first_appointment_at"
    FIRST_PRESCRIPTION = "first_prescription_at"


@dataclass(slots=True)
class OnboardingChecklist:
    """Build new ones with ``start``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    started_at: datetime
    steps: dict[OnboardingStep, datetime] = field(default_factory=dict)

    @classmethod
    def start(cls, *, id: UUID, clinic_id: UUID, now: datetime) -> OnboardingChecklist:
        return cls(id=id, clinic_id=clinic_id, started_at=require_utc(now, "now"))

    def record(self, step: OnboardingStep, *, now: datetime) -> bool:
        """Timestamp ``step`` the first time it happens. True when it changed (R12)."""
        now = require_utc(now, "now")
        if step in self.steps:
            return False
        self.steps[step] = now
        return True

    def at(self, step: OnboardingStep) -> datetime | None:
        return self.steps.get(step)

    @property
    def completed_steps(self) -> tuple[OnboardingStep, ...]:
        return tuple(step for step in OnboardingStep if step in self.steps)

    def elapsed(self, step: OnboardingStep) -> timedelta | None:
        """How long after the start that step took — the raw material for G4."""
        done = self.at(step)
        return done - self.started_at if done else None
