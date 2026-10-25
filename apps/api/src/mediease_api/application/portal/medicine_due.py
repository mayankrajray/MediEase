"""Medicine-due notices (M6b-P6; FR-REM-03; portal spec R65, R66).

Every 5 minutes the system job ``schedule_medicine_due`` asks which active clinics have a
medicine reminder turned on (IDs only) and enqueues one ``notify_medicine_due`` job per clinic.
That job reads the clinic's enabled choices and, **through the P3 schedule engine**
(``plan_for_day``: the same plan the *Medicines* tab shows), finds the doses of today whose time
(the choice's own, else the account's slot time) fell in the last 30 minutes. One notice per
account, slot and day: "Morning medicines · 08:00", never a medicine, dose or count (R59).
Nothing older than 30 minutes is back-filled; the unique ``event_key`` makes reruns harmless.

Only a current version (``ISSUED``) of a record still linked to the account is reminded.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from mediease_api.application.portal.patient_notifications import MEDICINES_LINK, notify_patient
from mediease_api.domain.jobs.job import (
    MEDICINE_DUE_SWEEP_KIND,
    NOTIFY_MEDICINE_DUE_KIND,
    ClaimedJob,
    NewJob,
)
from mediease_api.domain.jobs.schedule import RECURRING, dedupe_key
from mediease_api.domain.portal.notifications import PatientNotificationKind
from mediease_api.domain.prescriptions.plan import PlanSource, plan_for_day
from mediease_api.domain.prescriptions.prescription import Prescription, PrescriptionStatus
from mediease_api.domain.prescriptions.schedule import Slot
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

LATEST = timedelta(minutes=30)
BATCH = 5000


class SweepMedicineDue:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def __call__(self, job: ClaimedJob) -> None:
        now = self._clock.now()
        period = next(r for r in RECURRING if r.kind == MEDICINE_DUE_SWEEP_KIND)
        suffix = dedupe_key(period, now)
        with self._uow as uow:
            for clinic_id in uow.patient_notification_lookup.clinics_with_reminders():
                uow.jobs.enqueue(
                    NewJob.create(
                        id=self._ids.new_id(),
                        kind=NOTIFY_MEDICINE_DUE_KIND,
                        now=now,
                        clinic_id=clinic_id,
                        request_id=job.request_id,
                        dedupe_key=f"{NOTIFY_MEDICINE_DUE_KIND}:{clinic_id}:{suffix}",
                    )
                )
            uow.commit()


class NotifyMedicineDue:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def __call__(self, job: ClaimedJob) -> None:
        assert job.clinic_id is not None
        written = 0
        with self._uow as uow:
            clinic = uow.clinics.get(job.clinic_id)
            if clinic is None:  # pragma: no cover - the sweep found it
                return
            now = self._clock.now()
            written = notify_due(uow, clinic.id, clinic.name, clinic.timezone, now, self._ids)
            uow.commit()
        logger.info("medicine_due.notified", clinic_id=str(job.clinic_id), notices=written)


def notify_due(
    uow: UnitOfWork, clinic_id: UUID, clinic_name: str, timezone: str, now: datetime, ids: IdPort
) -> int:
    """R65, R66: the notices due in the last 30 minutes for one clinic; returns rows written."""
    tenant = uow.tenant(clinic_id)
    zone = ZoneInfo(timezone)
    today = local_date(now, timezone)
    plans: dict[UUID, set[tuple[UUID, Slot]]] = {}
    prescriptions: dict[UUID, Prescription | None] = {}
    due: dict[tuple[UUID, Slot], tuple[datetime, UUID]] = {}
    for pref in tenant.reminder_prefs.list_enabled(limit=BATCH):
        link = tenant.portal_links.active_for_account(pref.account_id)
        if link is None or link.patient_id != pref.patient_id:
            continue  # unlinked since: no reminders (R60)
        if pref.prescription_id not in prescriptions:
            rx = tenant.prescriptions.get(pref.prescription_id)
            prescriptions[pref.prescription_id] = (
                rx if rx is not None and rx.status is PrescriptionStatus.ISSUED else None
            )
        rx = prescriptions[pref.prescription_id]
        if rx is None:
            continue  # a superseded version: its revision has its own choices
        if rx.id not in plans:
            day = plan_for_day([PlanSource(rx, clinic_id, clinic_name, timezone)], today)
            plans[rx.id] = {(d.line.item.id, d.slot) for d in day.doses}
        if (pref.item_id, pref.slot) not in plans[rx.id]:
            continue  # not a dose of today (outside the course, or not this slot)
        account = uow.patient_accounts.get(pref.account_id)
        if account is None:  # pragma: no cover - a foreign key keeps it
            continue
        at: time = pref.remind_at or account.slot_times.at(pref.slot)
        moment = datetime.combine(today, at, tzinfo=zone)
        if not now - LATEST < moment <= now:
            continue
        key = (pref.account_id, pref.slot)
        if key not in due or moment < due[key][0]:
            due[key] = (moment, rx.id)
    written = 0
    for (account_id, slot), (moment, rx_id) in due.items():
        written += notify_patient(
            uow,
            tenant,
            ids=ids,
            account_id=account_id,
            kind=PatientNotificationKind.MEDICINE_DUE,
            event_key=f"medicine.due:{clinic_id}:{today.isoformat()}:{slot.value}",
            entity=("prescription", rx_id),
            link=MEDICINES_LINK,
            params={"slot": slot.value, "time": moment.strftime("%H:%M")},
            now=now,
        )
    return written
