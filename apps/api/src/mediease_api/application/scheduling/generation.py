"""Generating and reconciling sessions — shared by every scheduling use case.

``generate`` inserts the sessions a date should have and does not (spec R1). ``reconcile_doctor``
runs after a change to the rules: for every already-generated date in the range it deletes the
sessions that no longer match and have no bookings, and returns the booked ones it kept (D4). It
never creates: the next read of a date fills in what is missing.

Callers hold the doctor's row lock (R20): ``UPDATE`` for a change, ``SHARE`` for generation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.scheduling.sessions import PlannedSession, Session, plan_day, reconcile
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories


def plan_for(
    tenant: TenantRepositories, clinic: Clinic, doctor_id: UUID, on_date: date
) -> list[PlannedSession]:
    """The date's planned sessions from the rules as they are now in this transaction."""
    return plan_day(
        doctor_id=doctor_id,
        on_date=on_date,
        timezone=clinic.timezone,
        mode=clinic.booking_mode,
        blocks=tenant.schedules.list_for_doctor(doctor_id, valid_since=on_date),
        exceptions=tenant.schedule_exceptions.list_for_doctor(
            doctor_id, first=on_date, last=on_date
        ),
    )


def generate(
    tenant: TenantRepositories,
    *,
    clinic: Clinic,
    doctor: Doctor,
    on_date: date,
    ids: IdPort,
    now: datetime,
) -> int:
    """R1: insert the missing sessions of ``on_date`` for an active doctor; how many were new."""
    if not doctor.is_active:
        return 0
    existing = {s.key for s in tenant.sessions.list_for_date(on_date, doctor_id=doctor.id)}
    missing = [
        Session.from_plan(plan, id=ids.new_id(), clinic_id=clinic.id, now=now)
        for plan in plan_for(tenant, clinic, doctor.id, on_date)
        if plan.key not in existing
    ]
    return tenant.sessions.add_missing(missing)


def reconcile_doctor(
    tenant: TenantRepositories,
    *,
    clinic: Clinic,
    doctor: Doctor,
    first: date,
    last: date | None = None,
) -> tuple[Session, ...]:
    """D4: delete unbooked sessions that the rules no longer plan; return the booked ones kept."""
    sessions = tenant.sessions.list_for_doctor(doctor.id, first=first, last=last)
    kept: list[Session] = []
    for on_date in sorted({s.on_date for s in sessions}):
        outcome = reconcile(
            [s for s in sessions if s.on_date == on_date],
            plan_for(tenant, clinic, doctor.id, on_date),
        )
        for stale in outcome.to_delete:
            tenant.sessions.delete(stale.id)
        kept.extend(outcome.kept)
    return tuple(kept)


def neighbours(on_date: date) -> tuple[date, date, date]:
    """The day before, the day and the day after: an overnight block reaches into the next day."""
    return on_date - timedelta(days=1), on_date, on_date + timedelta(days=1)
