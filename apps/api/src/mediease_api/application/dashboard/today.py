"""*Today*: the first screen of every clinic role (M6-P1, decisions 5A and 6A).

``GetToday`` answers "how is today going?" with counts, computed in PostgreSQL in the clinic's
zone. It is shaped by who asks:

- A **doctor** sees their own sessions, their next patients and their own counts
  (``scope = DOCTOR``). A doctor account with no doctor profile sees the clinic, like an owner.
  From M6a-P6 a **practising owner** (an owner with a doctor profile) sees the same with
  ``view=doctor``, the Doctor workspace of their switch.
- **Front desk** and **owners** see the whole clinic (``scope = CLINIC``), with today's failed
  messages.
- The **7-day strip** comes only with ``USAGE_METRICS_VIEW`` (owners and doctors), for the same
  scope; a doctor's has no message count, because messages belong to the clinic.

Pending follow-ups are the clinic's, as ``/follow-ups`` lists them. Nothing here is clinical:
codes, first names, times, statuses and numbers only. Like the queue, reading today generates
today's sessions first, so the two screens always agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.application.clinics.errors import NoDoctorProfile
from mediease_api.application.context import RequestContext
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.application.scheduling.sessions import sessions_for_date
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.time import local_date, local_day_start
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.dashboard import DayTotals, NextPatient, StatusCounts
from mediease_api.ports.ids import IdPort
from mediease_api.ports.repositories import DoctorRepository
from mediease_api.ports.unit_of_work import UnitOfWork

NEXT_LIMIT = 3
WEEK_DAYS = 7


class Scope(StrEnum):
    CLINIC = "CLINIC"
    DOCTOR = "DOCTOR"


class View(StrEnum):
    """What the caller asks to see (M6a-P6): the clinic, or their own doctor's day."""

    CLINIC = "clinic"
    DOCTOR = "doctor"


@dataclass(frozen=True, slots=True)
class TodaySession:
    session: Session
    doctor_name: str
    counts: StatusCounts


@dataclass(frozen=True, slots=True)
class TodayView:
    on_date: date
    scope: Scope
    doctor_id: UUID | None
    counts: StatusCounts
    sessions: tuple[TodaySession, ...]
    next_patients: tuple[NextPatient, ...]
    follow_ups_pending: int
    # M6a-P8 (FR-APT-09): live bookings in closed sessions from today on; scope CLINIC only.
    bookings_to_move: int | None
    # CLINIC scope only; None for a doctor.
    messages_failed: int | None
    # USAGE_METRICS_VIEW only, oldest first, ending today.
    week: tuple[DayTotals, ...] | None


class GetToday:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, view: View | None = None) -> TodayView:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            now = self._clock.now()
            today = local_date(now, clinic.timezone)

            doctor_id = _doctor_view(tenant.doctors, ctx, view)
            scope = Scope.DOCTOR if doctor_id is not None else Scope.CLINIC

            sessions, _ = sessions_for_date(
                tenant, clinic, today, doctor_id=doctor_id, ids=self._ids, now=now
            )
            reads = tenant.dashboard
            names = {d.id: d.display_name for d in tenant.doctors.list()}
            ids = [s.id for s in sessions]
            by_session = reads.status_counts_by_session(ids)
            per_session = tuple(
                TodaySession(s, names.get(s.doctor_id, ""), by_session.get(s.id, StatusCounts()))
                for s in sessions
            )
            today_view = TodayView(
                on_date=today,
                scope=scope,
                doctor_id=doctor_id,
                counts=StatusCounts.sum(by_session.values()),
                sessions=per_session,
                next_patients=tuple(reads.next_patients(ids, limit=NEXT_LIMIT)),
                follow_ups_pending=reads.pending_follow_up_count(
                    today=today, timezone=clinic.timezone
                ),
                bookings_to_move=(
                    tenant.appointments.count_to_move(from_date=today)
                    if scope is Scope.CLINIC
                    else None
                ),
                messages_failed=(
                    reads.failed_message_count(
                        since=local_day_start(today, clinic.timezone),
                        until=local_day_start(today + timedelta(days=1), clinic.timezone),
                    )
                    if scope is Scope.CLINIC
                    else None
                ),
                week=(
                    tuple(
                        reads.week(
                            first=today - timedelta(days=WEEK_DAYS - 1),
                            last=today,
                            doctor_id=doctor_id,
                            timezone=clinic.timezone,
                        )
                    )
                    if ctx.allows(Permission.USAGE_METRICS_VIEW)
                    else None
                ),
            )
            # Generating today's sessions may have inserted rows; keep them, as the queue does.
            uow.commit()
        return today_view


def _doctor_view(doctors: DoctorRepository, ctx: RequestContext, view: View | None) -> UUID | None:
    """Whose sessions Today shows: a doctor profile's ID, or None for the whole clinic.

    M6a-P6 (decision 4A): a ``DOCTOR`` with a profile always gets their own day. An owner with an
    active profile (a practising owner) gets it when they ask for ``view=doctor``, the switch's
    Doctor workspace. Asking for it without a profile, or as front desk, is refused.
    """
    if ctx.role is Role.DOCTOR:
        profile = doctors.get_for_user(ctx.user_id)
        if profile is not None:
            return profile.id
    elif ctx.role is Role.OWNER and view is View.DOCTOR:
        profile = doctors.get_for_user(ctx.user_id)
        if profile is not None and profile.is_active:
            return profile.id
    if view is View.DOCTOR:
        raise NoDoctorProfile()
    return None
