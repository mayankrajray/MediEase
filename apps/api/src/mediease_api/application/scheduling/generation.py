"""Generating and reconciling sessions — shared by every scheduling use case.

``generate`` inserts the sessions a date should have and does not (spec R1), and revives a
retired session the rules plan again. ``reconcile_doctor`` runs after a change to the rules: for
every already-generated date in the range it removes the unbooked sessions that no longer match
(deleted, or retired when cancelled appointments still point at them), closes the booked ones
(D10), reopens closed ones planned again, resizes booked ones whose capacity alone changed (D11),
and returns the booked sessions it closed (D4). It never creates: the next read of a date fills in
what is missing.

Callers hold the doctor's row lock (R20): ``UPDATE`` for a change, ``SHARE`` for generation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.scheduling.sessions import (
    PlannedSession,
    Session,
    SessionStatus,
    plan_day,
    reconcile,
)
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
    """R1: the missing sessions of ``on_date`` for an active doctor; how many were new."""
    if not doctor.is_active:
        return 0
    existing = {
        s.key: s
        for s in tenant.sessions.list_for_date(on_date, doctor_id=doctor.id, include_retired=True)
    }
    missing: list[Session] = []
    revived = 0
    for plan in plan_for(tenant, clinic, doctor.id, on_date):
        found = existing.get(plan.key)
        if found is None:
            missing.append(Session.from_plan(plan, id=ids.new_id(), clinic_id=clinic.id, now=now))
        elif found.status is SessionStatus.CANCELLED:
            found.revive(plan, now)
            tenant.sessions.update(found)
            revived += 1
    return tenant.sessions.add_missing(missing) + revived


def reconcile_doctor(
    tenant: TenantRepositories,
    *,
    clinic: Clinic,
    doctor: Doctor,
    first: date,
    now: datetime,
    last: date | None = None,
) -> tuple[Session, ...]:
    """D4, D10, D11: apply the new rules to existing sessions; return the booked ones closed."""
    sessions = tenant.sessions.list_for_doctor(doctor.id, first=first, last=last)
    # ADR-0018: a session an online request points at is closed, never deleted or retired.
    protected = tenant.booking_requests.session_ids_with_pending([s.id for s in sessions])
    kept: list[Session] = []
    for on_date in sorted({s.on_date for s in sessions}):
        outcome = reconcile(
            [s for s in sessions if s.on_date == on_date],
            plan_for(tenant, clinic, doctor.id, on_date),
            protected,
        )
        for stale in outcome.to_delete:
            if tenant.appointments.exists_for_session(stale.id):
                # Cancelled appointments still point at it: keep the row, out of play.
                stale.retire(now)
                tenant.sessions.update(stale)
            else:
                tenant.sessions.delete(stale.id)
        for session in outcome.to_close:
            session.close(now)
            tenant.sessions.update(session)
        for session in outcome.to_reopen:
            session.reopen(now)
            tenant.sessions.update(session)
        for session, capacity in outcome.to_resize:
            session.resize(capacity, now)
            tenant.sessions.update(session)
        kept.extend(outcome.kept)
    return tuple(kept)


def neighbours(on_date: date) -> tuple[date, date, date]:
    """The day before, the day and the day after: an overnight block reaches into the next day."""
    return on_date - timedelta(days=1), on_date, on_date + timedelta(days=1)
