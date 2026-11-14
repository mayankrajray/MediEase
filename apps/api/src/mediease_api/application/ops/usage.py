"""How much each clinic uses MediEase (M9-P4; FR-OPS-03; PRD §11.2; spec ops-clinic-usage).

For the ops console: per clinic, who is active, when it was last used, and the records it made
(patients, appointments, visits, prescriptions, bills) all time and in each of the last weeks.
It is also the design partners' usage evidence. A reviewed cross-clinic read of counts only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ops import ClinicUsageFacts, UsageMetric
from mediease_api.ports.unit_of_work import UnitOfWork

DEFAULT_WEEKS = 4
MAX_WEEKS = 12
# The pilot runs in one region: the weeks shown are India's (M5-P6 decision 6A, as the costs).
REPORT_TIMEZONE = "Asia/Kolkata"
ACTIVE_WINDOW = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class WeekUsage:
    start: date  # a Monday
    counts: Mapping[UsageMetric, int]

    @property
    def end(self) -> date:
        return self.start + timedelta(days=6)


@dataclass(frozen=True, slots=True)
class ClinicUsage:
    facts: ClinicUsageFacts
    weeks: Sequence[WeekUsage]  # oldest first, the current week last
    totals: Mapping[UsageMetric, int]  # all time

    @property
    def active_this_week(self) -> bool:
        """Someone signed in or worked in the last 7 days, or a record was made this week."""
        return self.facts.active_users_7d > 0 or any(self.weeks[-1].counts.values())


@dataclass(frozen=True, slots=True)
class UsageReport:
    generated_at: datetime
    week_starts: Sequence[date]
    clinics: Sequence[ClinicUsage]

    @property
    def active_clinics(self) -> int:
        return sum(1 for c in self.clinics if c.active_this_week)

    def total(self, metric: UsageMetric) -> int:
        """Across every clinic, in the weeks shown."""
        return sum(w.counts[metric] for c in self.clinics for w in c.weeks)


def week_starts(today: date, weeks: int) -> list[date]:
    """The Mondays of the last ``weeks`` weeks, oldest first; the current week is the last."""
    monday = today - timedelta(days=today.weekday())
    return [monday - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]


class GetClinicUsage:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, weeks: int = DEFAULT_WEEKS) -> UsageReport:
        if isinstance(weeks, bool) or not 1 <= weeks <= MAX_WEEKS:
            raise InvalidValue("weeks", f"must be 1-{MAX_WEEKS}")
        now = self._clock.now()
        starts = week_starts(local_date(now, REPORT_TIMEZONE), weeks)
        with self._uow as uow:
            facts = uow.clinic_usage.facts(since=now - ACTIVE_WINDOW)
        return UsageReport(
            generated_at=now,
            week_starts=starts,
            clinics=[_clinic(f, starts) for f in facts],
        )


def _clinic(facts: ClinicUsageFacts, starts: Sequence[date]) -> ClinicUsage:
    totals = dict.fromkeys(UsageMetric, 0)
    for (metric, _week), n in facts.counts.items():
        totals[metric] += n
    weeks = [
        WeekUsage(start, {metric: facts.counts.get((metric, start), 0) for metric in UsageMetric})
        for start in starts
    ]
    return ClinicUsage(facts=facts, weeks=weeks, totals=totals)
