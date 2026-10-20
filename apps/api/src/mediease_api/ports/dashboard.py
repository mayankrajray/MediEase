"""The *Today* dashboard's counts (M6-P1, decision 5A).

One tenant-scoped read port: every query filters every table it touches by the repository's
clinic (ADR-0003). It returns counts, codes, first names and times only, never a reason, a note,
a diagnosis or a message's content.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StatusCounts:
    """Active appointments of a set of sessions by status (cancelled ones are not counted)."""

    not_arrived: int = 0
    waiting: int = 0
    in_consultation: int = 0
    completed: int = 0
    no_show: int = 0

    @property
    def total(self) -> int:
        return (
            self.not_arrived + self.waiting + self.in_consultation + self.completed + self.no_show
        )

    @classmethod
    def sum(cls, many: Iterable[StatusCounts]) -> StatusCounts:
        total = cls()
        for c in many:
            total = cls(
                not_arrived=total.not_arrived + c.not_arrived,
                waiting=total.waiting + c.waiting,
                in_consultation=total.in_consultation + c.in_consultation,
                completed=total.completed + c.completed,
                no_show=total.no_show + c.no_show,
            )
        return total


@dataclass(frozen=True, slots=True)
class NextPatient:
    """Who is next: those waiting first, by token or slot, then those not yet arrived."""

    appointment_id: UUID
    session_id: UUID
    doctor_id: UUID
    status: str
    token_number: int | None
    slot_start: datetime | None
    patient_code: str
    patient_first_name: str


@dataclass(frozen=True, slots=True)
class DayTotals:
    """One day of the 7-day strip. ``messages_sent`` is None when the caller sees one doctor."""

    on_date: date
    appointments: int
    completed: int
    no_show: int
    messages_sent: int | None


class DashboardReads(Protocol):
    """Counts for one clinic's *Today* screen (tenant-scoped)."""

    def status_counts_by_session(self, session_ids: Sequence[UUID]) -> Mapping[UUID, StatusCounts]:
        """Each session's counts; a session with no appointment is absent."""
        ...

    def next_patients(self, session_ids: Sequence[UUID], *, limit: int) -> Sequence[NextPatient]:
        """Up to ``limit`` patients still to be seen, those waiting first."""
        ...

    def pending_follow_up_count(self, *, today: date, timezone: str) -> int:
        """How many patients ``GET /follow-ups/pending`` would list (FR-REM-07)."""
        ...

    def failed_message_count(self, *, since: datetime, until: datetime) -> int:
        """Messages that failed in ``[since, until)``."""
        ...

    def week(
        self, *, first: date, last: date, doctor_id: UUID | None, timezone: str
    ) -> Sequence[DayTotals]:
        """One entry per date from ``first`` to ``last``, empty days included, oldest first.

        Appointments are counted by their session's date; with ``doctor_id`` only that doctor's,
        and messages are not counted (they belong to the clinic, not to a doctor).
        """
        ...
