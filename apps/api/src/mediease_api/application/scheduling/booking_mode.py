"""Changing a clinic's booking mode (spec R19).

Every block still in force and every upcoming extra session must carry what the new mode needs
(a slot length for SLOTS, a capacity for TOKENS); otherwise ``SCH_MODE_INCOMPATIBLE`` and nothing
changes. Then each doctor's unbooked future sessions are reconciled into the new mode; booked
ones keep theirs (D4). Doctors are locked in ID order, as session generation does (R20).
"""

from __future__ import annotations

from datetime import date, datetime

import structlog

from mediease_api.application.scheduling.generation import reconcile_doctor
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.scheduling.errors import ModeIncompatible
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.ports.repositories import RowLock
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


def check_mode_supported(uow: UnitOfWork, clinic: Clinic, mode: BookingMode, today: date) -> None:
    tenant = uow.tenant(clinic.id)
    shapes = [b.shape for b in tenant.schedules.list_current(valid_since=today)]
    shapes += [e.shape for e in tenant.schedule_exceptions.list_from(today) if e.shape is not None]
    if not all(shape.supports(mode) for shape in shapes):
        raise ModeIncompatible(
            mode.value, "slot length" if mode is BookingMode.SLOTS else "capacity"
        )


def reconcile_clinic(uow: UnitOfWork, clinic: Clinic, today: date, now: datetime) -> int:
    """After the mode changed: each doctor's future sessions follow it; how many were kept."""
    tenant = uow.tenant(clinic.id)
    kept = 0
    for doctor in sorted(tenant.doctors.list(), key=lambda d: d.id):
        locked = tenant.doctors.get(doctor.id, lock=RowLock.UPDATE)
        assert locked is not None  # listed in this transaction
        kept += len(reconcile_doctor(tenant, clinic=clinic, doctor=locked, first=today, now=now))
    logger.info(
        "clinic.booking_mode_changed",
        clinic_id=str(clinic.id),
        booking_mode=clinic.booking_mode.value,
        kept_sessions=kept,
    )
    return kept
