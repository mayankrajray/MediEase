"""Dose tracking: the patient marks a scheduled dose Taken or Skipped (M6b-P3b; R45-R54).

Private to the patient account: every call goes through ``PortalScope`` and no staff or ops
route reads ``dose_records`` (tests/tenancy). No audit row per change (D4); the log events
``dose.marked`` and ``dose.cleared`` carry IDs and a count only, never a state, a medicine or a
time (R51, AC22). Only a timed entry of the version's course can be marked, within its window
(``domain/portal/doses.py``); untimed lines never can.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.portal.records import issued_in_scope
from mediease_api.application.portal.scope import PortalScope, ScopeEntry
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.portal.doses import (
    DoseNotMarkable,
    DoseRecord,
    DoseState,
    DoseStatus,
    scheduled_at,
    status_of,
    window_open,
)
from mediease_api.domain.prescriptions.plan import course_end, course_start, line_slots
from mediease_api.domain.prescriptions.prescription import (
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
)
from mediease_api.domain.prescriptions.schedule import DAY_ORDER, Slot
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# The history shows at most this many days back from today (an open-ended course can be long).
HISTORY_DAYS = 60


@dataclass(frozen=True, slots=True)
class DoseChoice:
    prescription_id: UUID
    item_id: UUID
    on_date: date
    slot: Slot


@dataclass(frozen=True, slots=True)
class DoseResult:
    status: DoseStatus
    marked_at: datetime | None
    markable: bool


def _line(rx: Prescription, item_id: UUID) -> PrescriptionItem:
    item = next((i for i in rx.items if i.id == item_id), None)
    if item is None:
        logger.info("portal.not_found", entity="prescription item")
        raise NotFound("prescription item")
    return item


def _check_scheduled(
    entry: ScopeEntry, rx: Prescription, item: PrescriptionItem, c: DoseChoice
) -> date | None:
    """R45: a slot of a timed line, on a day of its course. Returns the course's last day."""
    slots = line_slots(item)
    if not slots:
        raise InvalidValue("item_id", "this medicine has no time of day to mark")
    if c.slot not in slots:
        raise InvalidValue("slot", "is not one of this medicine's times of day")
    start = course_start(rx, entry.clinic.timezone)
    end = course_end(item, start)
    if c.on_date < start or (end is not None and c.on_date > end):
        raise InvalidValue("on_date", "is not a day of this medicine's course")
    return end


class _DoseUseCase:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def _apply(
        self, principal: PatientPrincipal, c: DoseChoice, state: DoseState | None
    ) -> DoseResult:
        now = self._clock.now()
        with self._uow as uow:
            entry, rx = issued_in_scope(
                PortalScope.read(uow, principal.account_id), c.prescription_id
            )
            item = _line(rx, c.item_id)
            end = _check_scheduled(entry, rx, item, c)
            tz = entry.clinic.timezone
            due = scheduled_at(c.on_date, principal.account.slot_times.at(c.slot), tz)
            if not window_open(on_date=c.on_date, due=due, today=local_date(now, tz), now=now):
                raise DoseNotMarkable()
            repo = entry.tenant.dose_records
            record = repo.get(principal.account_id, rx.id, item.id, c.on_date, c.slot)
            changed = 0
            if state is None:
                if record is not None:
                    repo.delete(record)
                    record, changed = None, 1
            elif record is None:
                record = DoseRecord.create(
                    id=self._ids.new_id(),
                    clinic_id=entry.clinic.id,
                    patient_id=entry.patient_id,
                    account_id=principal.account_id,
                    prescription_id=rx.id,
                    item_id=item.id,
                    on_date=c.on_date,
                    slot=c.slot,
                    state=state,
                    course_end=end,
                    now=now,
                )
                repo.add(record)
                changed = 1
            elif record.change(state, now=now):
                repo.update(record)
                changed = 1
            uow.commit()
        # R51: IDs and a count only, never the state, the medicine or the time.
        logger.info(
            "dose.cleared" if state is None else "dose.marked",
            account_id=str(principal.account_id),
            prescription_id=str(rx.id),
            count=changed,
        )
        return DoseResult(
            status_of(record, due=due, now=now), record.marked_at if record else None, True
        )


class MarkDose(_DoseUseCase):
    """R45, R46: Taken or Skipped, or a change between them, within the dose's window."""

    def execute(
        self, principal: PatientPrincipal, choice: DoseChoice, state: DoseState
    ) -> DoseResult:
        return self._apply(principal, choice, state)


class ClearDose(_DoseUseCase):
    """R46: removes a mark within the window; the dose is then Not recorded or Upcoming again."""

    def execute(self, principal: PatientPrincipal, choice: DoseChoice) -> DoseResult:
        return self._apply(principal, choice, None)


@dataclass(frozen=True, slots=True)
class HistoryDose:
    item_id: UUID
    medicine_name: str
    dose: str | None
    slot: Slot
    status: DoseStatus
    marked_at: datetime | None


@dataclass(frozen=True, slots=True)
class HistoryDay:
    on_date: date
    doses: tuple[HistoryDose, ...]


@dataclass(frozen=True, slots=True)
class VersionRef:
    prescription_id: UUID
    version: int
    status: PrescriptionStatus


@dataclass(frozen=True, slots=True)
class DoseHistory:
    """R47, R49: one version's course, newest day first, with counts per state (no score)."""

    prescription_id: UUID
    version: int
    clinic_name: str
    clinic_phone_e164: str | None
    timezone: str
    starts_on: date
    days: tuple[HistoryDay, ...]
    counts: dict[DoseStatus, int]
    versions: tuple[VersionRef, ...]  # the chain's issued versions, newest first


def _version_in_scope(scope: PortalScope, rx_id: UUID) -> tuple[ScopeEntry, Prescription]:
    """R49: an issued or superseded version of a linked record; drafts and others not found."""
    for entry in scope:
        rx = entry.tenant.prescriptions.get(rx_id)
        if rx is not None and rx.patient_id == entry.patient_id:
            if rx.status in (PrescriptionStatus.ISSUED, PrescriptionStatus.SUPERSEDED):
                return entry, rx
            break
    logger.info("portal.not_found", entity="prescription", entity_id=str(rx_id))
    raise NotFound("prescription")


class GetDoseHistory:
    """R47-R49: each day and slot of a version's course as Taken, Skipped, Not recorded or
    Upcoming, from its start (at most 60 days back) to today or its end."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, principal: PatientPrincipal, prescription_id: UUID) -> DoseHistory:
        now = self._clock.now()
        times = principal.account.slot_times
        with self._uow as uow:
            entry, rx = _version_in_scope(
                PortalScope.read(uow, principal.account_id), prescription_id
            )
            chain = entry.tenant.prescriptions.list_for_visit(rx.visit_id)
            records = {
                (r.item_id, r.on_date, r.slot): r
                for r in entry.tenant.dose_records.for_account(principal.account_id, [rx.id])
            }
        tz = entry.clinic.timezone
        today = local_date(now, tz)
        start = course_start(rx, tz)
        timed = [i for i in rx.items if line_slots(i)]
        ends = [course_end(i, start) for i in timed]
        last = (
            today
            if not ends or any(e is None for e in ends)
            else min(today, max(e for e in ends if e))
        )
        first = max(start, today - timedelta(days=HISTORY_DAYS - 1))
        days = []
        counts = dict.fromkeys(DoseStatus, 0)
        on = last
        while on >= first:
            doses = []
            for slot in DAY_ORDER:
                for item in timed:
                    end = course_end(item, start)
                    if slot not in line_slots(item) or (end is not None and on > end):
                        continue
                    record = records.get((item.id, on, slot))
                    status = status_of(record, due=scheduled_at(on, times.at(slot), tz), now=now)
                    counts[status] += 1
                    doses.append(
                        HistoryDose(
                            item.id,
                            item.medicine_name,
                            item.dose,
                            slot,
                            status,
                            record.marked_at if record else None,
                        )
                    )
            if doses:
                days.append(HistoryDay(on, tuple(doses)))
            on -= timedelta(days=1)
        logger.info(
            "portal.dose_history_read", account_id=str(principal.account_id), days=len(days)
        )
        return DoseHistory(
            prescription_id=rx.id,
            version=rx.version,
            clinic_name=entry.clinic.name,
            clinic_phone_e164=entry.clinic.phone.e164 if entry.clinic.phone else None,
            timezone=tz,
            starts_on=start,
            days=tuple(days),
            counts=counts,
            versions=tuple(
                VersionRef(v.id, v.version, v.status)
                for v in sorted(chain, key=lambda v: v.version, reverse=True)
                if v.status in (PrescriptionStatus.ISSUED, PrescriptionStatus.SUPERSEDED)
            ),
        )
