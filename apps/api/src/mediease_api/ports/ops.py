"""Ops reads across clinics (M9-P4; FR-OPS-03; spec ops-clinic-usage).

A reviewed cross-clinic exception (ADR-0003), like the ops clinic list and the monthly messaging
totals: counts, dates and clinic names only. Never a patient, a name of a person, a number, a
message or anything clinical.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class UsageMetric(StrEnum):
    """The records a clinic creates while it works, counted by the week they were made in."""

    PATIENTS = "patients"  # registered (created_at)
    APPOINTMENTS = "appointments"  # booked, not cancelled (created_at)
    VISITS = "visits"  # seen (started_at)
    PRESCRIPTIONS = "prescriptions"  # issued versions (issued_at)
    BILLS = "bills"  # issued bills, not credit notes (issued_at)


@dataclass(frozen=True, slots=True)
class ClinicUsageFacts:
    """One clinic's activity. ``counts`` maps (metric, Monday of the clinic-local week) to a count,
    for every week the clinic has a record in, so all-time totals are their sum."""

    clinic_id: UUID
    name: str
    slug: str
    status: str
    timezone: str
    created_at: datetime
    owners: int
    # Active doctor profiles (a practising owner counts here and as an owner).
    doctors: int
    front_desk: int
    # Distinct people with an active membership (a person counts once, whatever their roles).
    members: int
    # Members who signed in or did something audited in the last 7 days.
    active_users_7d: int
    last_active_at: datetime | None
    counts: Mapping[tuple[UsageMetric, date], int]
    # Delivery health in the last 7 days: messages that failed (not those held back because
    # messaging is switched off, which are counted apart) and jobs that gave up.
    failed_messages_7d: int
    not_sent_7d: int
    failed_jobs_7d: int


class ClinicUsageReport(Protocol):
    def facts(self, *, since: datetime) -> Sequence[ClinicUsageFacts]:
        """Every clinic, newest first; ``since`` bounds the 7-day signals."""
        ...
