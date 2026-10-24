"""The patient's medicine plan and reminder choices (M6b-P3; FR-REM-03; patient portal R28-R44).

Everything here is laid out by the one engine (``domain/prescriptions/plan.py``) from each linked
record's **current** versions, read through ``PortalScope``; nothing is decided here (R28). The
words come from the prescription phrasebook in the account's language (R42); medicine names,
doses and the doctor's own text are passed through as written.

Reads and preference changes are not audited (R41); logs carry IDs and counts only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID

import structlog

from mediease_api.application.portal.records import issued_in_scope
from mediease_api.application.portal.scope import PortalScope, ScopeEntry
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.clinics.clinic import DEFAULT_TIMEZONE
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.doses import (
    DoseRecord,
    DoseStatus,
    scheduled_at,
    status_of,
    window_open,
)
from mediease_api.domain.portal.medicines import MedicineReminderPref, SlotTimes
from mediease_api.domain.prescriptions.document import (
    duration_words,
    frequency_words,
    preparation_text,
    sentence,
)
from mediease_api.domain.prescriptions.phrasebook import phrase
from mediease_api.domain.prescriptions.plan import (
    Course,
    PlanLine,
    PlanSource,
    course_start,
    courses,
    is_remindable,
    line_slots,
    plan_for_day,
)
from mediease_api.domain.prescriptions.prescription import PrescriptionItem
from mediease_api.domain.prescriptions.schedule import DAY_ORDER, Slot
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

PLAN_WINDOW_DAYS = 30
PRESCRIPTIONS_PER_CLINIC = 50


@dataclass(frozen=True, slots=True)
class Reminder:
    """R38: the person's choice for one line in one slot; off and the slot's time by default."""

    enabled: bool
    remind_at: time | None  # None = the slot's own time

    @classmethod
    def of(cls, pref: MedicineReminderPref | None) -> Reminder:
        return cls(pref.enabled, pref.remind_at) if pref else cls(False, None)


@dataclass(frozen=True, slots=True)
class LineWords:
    """One prescribed line as the doctor wrote it, in the account's words (R31, R36)."""

    item_id: UUID
    medicine_name: str
    form_strength: str | None
    dose: str | None
    as_written: str | None  # SOS, ONCE, CUSTOM or no frequency: the doctor's words
    timing: str | None
    how: str | None
    duration: str


@dataclass(frozen=True, slots=True)
class PlanContext:
    """Where a line comes from (R36): the version, its clinic and doctor."""

    prescription_id: UUID
    version: int
    clinic_id: UUID
    clinic_name: str
    clinic_phone_e164: str | None
    doctor_name: str
    starts_on: date
    # M6b-P3b: the clinic's zone, so a dose's marked time is shown on the clinic's clock.
    timezone: str


@dataclass(frozen=True, slots=True)
class DoseView:
    """M6b-P3b (R45-R47): one scheduled dose: its state, when it was marked, and if it can be."""

    status: DoseStatus
    marked_at: datetime | None
    markable: bool


@dataclass(frozen=True, slots=True)
class PlanEntry:
    context: PlanContext
    line: LineWords
    day: int
    days_total: int | None
    reminder: Reminder | None  # timed entries only
    dose: DoseView | None = None  # timed entries only


@dataclass(frozen=True, slots=True)
class PlanSlot:
    slot: Slot
    label: str
    time: time
    entries: tuple[PlanEntry, ...]


@dataclass(frozen=True, slots=True)
class MedicinePlan:
    on_date: date
    today: date
    language: Language
    slots: tuple[PlanSlot, ...]  # only slots with a dose, in the day's order
    as_written: tuple[PlanEntry, ...]
    has_prescriptions: bool  # R44: false when no linked record has a current version


@dataclass(frozen=True, slots=True)
class CourseSlot:
    slot: Slot
    label: str
    time: time
    reminder: Reminder


@dataclass(frozen=True, slots=True)
class CourseLineView:
    line: LineWords
    slots: tuple[CourseSlot, ...]
    ends_on: date | None


@dataclass(frozen=True, slots=True)
class CourseView:
    context: PlanContext
    revised: bool  # R39: a version after the first
    reminders_set: bool  # R39: any choice saved for this version
    ends_on: date | None
    lines: tuple[CourseLineView, ...]


@dataclass(frozen=True, slots=True)
class _Source:
    entry: ScopeEntry
    plan: PlanSource
    context: PlanContext


def _sources(scope: PortalScope) -> list[_Source]:
    found = []
    for entry in scope:
        for rx in entry.tenant.prescriptions.list_issued_for_patient(
            entry.patient_id, limit=PRESCRIPTIONS_PER_CLINIC
        ):
            assert rx.doctor_snapshot is not None
            tz = entry.clinic.timezone
            found.append(
                _Source(
                    entry,
                    PlanSource(rx, entry.clinic.id, entry.clinic.name, tz),
                    PlanContext(
                        prescription_id=rx.id,
                        version=rx.version,
                        clinic_id=entry.clinic.id,
                        clinic_name=entry.clinic.name,
                        clinic_phone_e164=entry.clinic.phone.e164 if entry.clinic.phone else None,
                        doctor_name=rx.doctor_snapshot.display_name,
                        starts_on=course_start(rx, tz),
                        timezone=tz,
                    ),
                )
            )
    return found


def _prefs(
    sources: Sequence[_Source], account_id: UUID
) -> dict[tuple[UUID, UUID, Slot], MedicineReminderPref]:
    by_clinic: dict[UUID, list[_Source]] = {}
    for s in sources:
        by_clinic.setdefault(s.entry.clinic.id, []).append(s)
    found = {}
    for group in by_clinic.values():
        tenant = group[0].entry.tenant
        for pref in tenant.reminder_prefs.for_account(
            account_id, [s.plan.prescription.id for s in group]
        ):
            found[(pref.prescription_id, pref.item_id, pref.slot)] = pref
    return found


DoseKey = tuple[UUID, UUID, date, Slot]


def dose_records(sources: Sequence[_Source], account_id: UUID) -> dict[DoseKey, DoseRecord]:
    """M6b-P3b: the account's marks for these versions, read through each clinic's scope."""
    by_clinic: dict[UUID, list[_Source]] = {}
    for s in sources:
        by_clinic.setdefault(s.entry.clinic.id, []).append(s)
    found = {}
    for group in by_clinic.values():
        tenant = group[0].entry.tenant
        for record in tenant.dose_records.for_account(
            account_id, [s.plan.prescription.id for s in group]
        ):
            found[(record.prescription_id, record.item_id, record.on_date, record.slot)] = record
    return found


def _today(scope: PortalScope, clock: ClockPort) -> date:
    """The clinic calendar's today (the pilot is one time zone; the first linked clinic's)."""
    tz = next((e.clinic.timezone for e in scope), DEFAULT_TIMEZONE)
    return local_date(clock.now(), tz)


def _words(item: PrescriptionItem, lang: Language) -> LineWords:
    as_written = None
    if not line_slots(item):
        as_written = (
            frequency_words(item.frequency, item.frequency_text, lang)
            if item.frequency
            else phrase("schedule.not_stated", lang)
        )
    form_strength = " ".join(v for v in (item.form, item.strength) if v) or None
    return LineWords(
        item_id=item.id,
        medicine_name=item.medicine_name,
        form_strength=form_strength,
        dose=item.dose,
        as_written=as_written,
        timing=sentence(phrase(f"timing.{item.timing.value}", lang), lang) if item.timing else None,
        how=preparation_text(item, lang),
        duration=duration_words(item, lang),
    )


class GetMedicinePlan:
    """R35, R36: one day's plan across the linked records (default today; ±30 days)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, principal: PatientPrincipal, on: date | None) -> MedicinePlan:
        lang = principal.account.language
        times = principal.account.slot_times
        with self._uow as uow:
            scope = PortalScope.read(uow, principal.account_id)
            today = _today(scope, self._clock)
            on = on or today
            if abs((on - today).days) > PLAN_WINDOW_DAYS:
                raise InvalidValue("date", f"must be within {PLAN_WINDOW_DAYS} days of today")
            sources = _sources(scope)
            prefs = _prefs(sources, principal.account_id)
            doses = dose_records(sources, principal.account_id)
        now = self._clock.now()
        contexts = {s.plan.prescription.id: s.context for s in sources}
        day = plan_for_day([s.plan for s in sources], on)

        def entry(line: PlanLine, slot: Slot | None) -> PlanEntry:
            rx = line.prescription
            if slot is None:
                return PlanEntry(
                    contexts[rx.id], _words(line.item, lang), line.day, line.days_total, None
                )
            tz = contexts[rx.id].timezone
            due = scheduled_at(on, times.at(slot), tz)
            record = doses.get((rx.id, line.item.id, on, slot))
            return PlanEntry(
                contexts[rx.id],
                _words(line.item, lang),
                line.day,
                line.days_total,
                Reminder.of(prefs.get((rx.id, line.item.id, slot))),
                DoseView(
                    status_of(record, due=due, now=now),
                    record.marked_at if record else None,
                    window_open(on_date=on, due=due, today=local_date(now, tz), now=now),
                ),
            )

        slots = []
        for slot in (s for s in DAY_ORDER if any(d.slot is s for d in day.doses)):
            slots.append(
                PlanSlot(
                    slot,
                    phrase(f"slot.{slot.value}", lang),
                    times.at(slot),
                    tuple(entry(d.line, slot) for d in day.doses if d.slot is slot),
                )
            )
        logger.info(
            "portal.medicine_plan_read",
            account_id=str(principal.account_id),
            prescriptions=len(sources),
        )
        return MedicinePlan(
            on_date=on,
            today=today,
            language=lang,
            slots=tuple(slots),
            as_written=tuple(entry(line, None) for line in day.untimed),
            has_prescriptions=bool(sources),
        )


class ListMedicineCourses:
    """R35, R36: each current version's course; a DAYS course over 7 days ago is left out."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, principal: PatientPrincipal) -> list[CourseView]:
        lang = principal.account.language
        times = principal.account.slot_times
        with self._uow as uow:
            scope = PortalScope.read(uow, principal.account_id)
            today = _today(scope, self._clock)
            sources = _sources(scope)
            prefs = _prefs(sources, principal.account_id)
        contexts = {s.plan.prescription.id: s.context for s in sources}
        return [
            _course_view(course, contexts[course.source.prescription.id], prefs, times, lang)
            for course in courses([s.plan for s in sources], today)
        ]


def _course_view(
    course: Course,
    context: PlanContext,
    prefs: dict[tuple[UUID, UUID, Slot], MedicineReminderPref],
    times: SlotTimes,
    lang: Language,
) -> CourseView:
    rx = course.source.prescription
    return CourseView(
        context=context,
        revised=rx.version > 1,
        reminders_set=any(key[0] == rx.id for key in prefs),
        ends_on=course.end,
        lines=tuple(
            CourseLineView(
                _words(line.item, lang),
                tuple(
                    CourseSlot(
                        slot,
                        phrase(f"slot.{slot.value}", lang),
                        times.at(slot),
                        Reminder.of(prefs.get((rx.id, line.item.id, slot))),
                    )
                    for slot in line.slots
                ),
                line.end,
            )
            for line in course.lines
        ),
    )


@dataclass(frozen=True, slots=True)
class ReminderChoice:
    prescription_id: UUID
    item_id: UUID
    slot: Slot
    enabled: bool
    remind_at: time | None


class SetMedicineReminder:
    """R38: on/off and a preferred time for one line of a current version in one of its slots.

    Refused (422) for an untimed line or a slot the line does not have; a version or line outside
    the scope, or no longer current, is not found. Never touches the prescription.
    """

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, principal: PatientPrincipal, choice: ReminderChoice) -> Reminder:
        now = self._clock.now()
        with self._uow as uow:
            scope = PortalScope.read(uow, principal.account_id)
            entry, rx = issued_in_scope(scope, choice.prescription_id)
            item = next((i for i in rx.items if i.id == choice.item_id), None)
            if item is None:
                logger.info("portal.not_found", entity="prescription item")
                raise NotFound("prescription item")
            if not is_remindable(item):
                raise InvalidValue("item_id", "this medicine has no time of day to remind at")
            if choice.slot not in line_slots(item):
                raise InvalidValue("slot", "is not one of this medicine's times of day")
            repo = entry.tenant.reminder_prefs
            pref = repo.get(principal.account_id, rx.id, item.id, choice.slot)
            if pref is None:
                pref = MedicineReminderPref.create(
                    id=self._ids.new_id(),
                    clinic_id=entry.clinic.id,
                    patient_id=entry.patient_id,
                    account_id=principal.account_id,
                    prescription_id=rx.id,
                    item_id=item.id,
                    slot=choice.slot,
                    enabled=choice.enabled,
                    remind_at=choice.remind_at,
                    now=now,
                )
                repo.add(pref)
            elif pref.change(enabled=choice.enabled, remind_at=choice.remind_at, now=now):
                repo.update(pref)
            uow.commit()
        logger.info(
            "portal.medicine_reminder_set",
            account_id=str(principal.account_id),
            prescription_id=str(rx.id),
            item_id=str(item.id),
        )
        return Reminder.of(pref)
