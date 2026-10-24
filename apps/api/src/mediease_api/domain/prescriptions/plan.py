"""The medicine-plan engine (M6b-P3; FR-REM-03; patient portal R28-R33, prescriptions R21-R24).

The one place that turns a prescription into a schedule: the portal's plan, the PDF and patient
page's Medicine schedule section and P6's reminders all call these functions; no screen works a
schedule out for itself (D8).

It lays out what the doctor wrote and nothing else (D9): a line appears in the slots its pattern
marks (``schedule.SLOT_SETS``), from the prescription's start, for its stated number of days.
It never computes or changes a dose, never moves a dose for food or bedtime, never merges lines
or prescriptions, never invents an end for "until review", "ongoing" or a duration not stated,
and never resolves a contradiction: a possible conflict is a **warning to the doctor** while
drafting (``line_warnings``), and the patient sees the line as written.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.prescriptions.prescription import Prescription, PrescriptionItem
from mediease_api.domain.prescriptions.schedule import DAY_ORDER, DurationKind, Slot
from mediease_api.domain.prescriptions.vocabulary import Timing
from mediease_api.domain.shared.time import local_date


class LineWarning(StrEnum):
    """Prescriptions R22: never blocking; the issued line stays exactly as written."""

    BEDTIME_WITHOUT_NIGHT = "BEDTIME_WITHOUT_NIGHT"
    BEDTIME_WITH_OTHER_SLOTS = "BEDTIME_WITH_OTHER_SLOTS"
    BEDTIME_UNTIMED = "BEDTIME_UNTIMED"


def line_slots(item: PrescriptionItem) -> tuple[Slot, ...]:
    """The slots the doctor's pattern marks; none for SOS, ONCE, CUSTOM or no frequency."""
    return item.frequency.slots if item.frequency is not None else ()


def is_remindable(item: PrescriptionItem) -> bool:
    """D6: only a line with slots may have a reminder; SOS, ONCE and CUSTOM never do."""
    return bool(line_slots(item))


def line_warnings(item: PrescriptionItem) -> tuple[LineWarning, ...]:
    if item.timing is not Timing.BEDTIME:
        return ()
    slots = line_slots(item)
    if not slots:
        return (LineWarning.BEDTIME_UNTIMED,) if item.frequency is not None else ()
    if Slot.NIGHT not in slots:
        return (LineWarning.BEDTIME_WITHOUT_NIGHT,)
    if len(slots) > 1:
        return (LineWarning.BEDTIME_WITH_OTHER_SLOTS,)
    return ()


def course_start(rx: Prescription, timezone: str) -> date:
    """R24: the doctor's chosen start, else the issue day on the clinic's calendar."""
    if rx.starts_on is not None:
        return rx.starts_on
    assert rx.issued_at is not None, "only an issued version has a course"
    return local_date(rx.issued_at, timezone)


def course_end(item: PrescriptionItem, start: date) -> date | None:
    """The last day for a number of days; None for every other kind (no invented end)."""
    if item.duration_kind is DurationKind.DAYS:
        assert item.duration_days is not None
        return start + timedelta(days=item.duration_days - 1)
    return None


@dataclass(frozen=True, slots=True)
class PlanSource:
    """One current version to plan, with where it is from (the caller has scoped it)."""

    prescription: Prescription
    clinic_id: UUID
    clinic_name: str
    timezone: str


@dataclass(frozen=True, slots=True)
class PlanLine:
    """One prescribed line on one day, as written, with its course progress."""

    source: PlanSource
    item: PrescriptionItem
    start: date
    end: date | None
    day: int  # 1-based day of the course

    @property
    def days_total(self) -> int | None:
        return self.item.duration_days if self.item.duration_kind is DurationKind.DAYS else None

    @property
    def prescription(self) -> Prescription:
        return self.source.prescription


@dataclass(frozen=True, slots=True)
class PlanDose:
    """A timed entry: one line in one of its slots. Two prescriptions, two entries (D9)."""

    slot: Slot
    line: PlanLine


@dataclass(frozen=True, slots=True)
class DayPlan:
    on_date: date
    doses: tuple[PlanDose, ...]  # by slot in the day's order, then prescription, then line
    untimed: tuple[PlanLine, ...]  # SOS, ONCE, CUSTOM or no frequency: "As the doctor wrote"


def _lines_on(source: PlanSource, on: date) -> list[PlanLine]:
    start = course_start(source.prescription, source.timezone)
    if on < start:
        return []
    lines = []
    for item in source.prescription.items:
        end = course_end(item, start)
        if end is not None and on > end:
            continue
        lines.append(PlanLine(source, item, start, end, (on - start).days + 1))
    return lines


def plan_for_day(sources: Sequence[PlanSource], on: date) -> DayPlan:
    """R32, R36: every line whose course includes ``on``, in its slots or as written."""
    doses: list[PlanDose] = []
    untimed: list[PlanLine] = []
    for source in sources:
        for line in _lines_on(source, on):
            slots = line_slots(line.item)
            if slots:
                doses.extend(PlanDose(slot, line) for slot in slots)
            else:
                untimed.append(line)
    order = {slot: i for i, slot in enumerate(DAY_ORDER)}
    doses.sort(
        key=lambda d: (
            order[d.slot],
            d.line.source.clinic_name,
            str(d.line.prescription.id),
            d.line.item.position,
        )
    )
    return DayPlan(on, tuple(doses), tuple(untimed))


@dataclass(frozen=True, slots=True)
class CourseLine:
    item: PrescriptionItem
    slots: tuple[Slot, ...]
    end: date | None


@dataclass(frozen=True, slots=True)
class Course:
    source: PlanSource
    start: date
    lines: tuple[CourseLine, ...]

    @property
    def end(self) -> date | None:
        """The course's last day when every line has a number of days; else None."""
        ends = [line.end for line in self.lines]
        if not ends or any(e is None for e in ends):
            return None
        return max(e for e in ends if e is not None)


ENDED_SHOWN_DAYS = 7


def courses(sources: Sequence[PlanSource], today: date) -> list[Course]:
    """R35: each current version's course; one that ended over 7 days ago is left out."""
    found = []
    for source in sources:
        start = course_start(source.prescription, source.timezone)
        course = Course(
            source,
            start,
            tuple(
                CourseLine(item, line_slots(item), course_end(item, start))
                for item in source.prescription.items
            ),
        )
        if course.end is not None and course.end < today - timedelta(days=ENDED_SHOWN_DAYS):
            continue
        found.append(course)
    return sorted(found, key=lambda c: (c.start, str(c.source.prescription.id)), reverse=True)
