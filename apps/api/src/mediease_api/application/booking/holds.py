"""Soft holds under a session's row lock (M6b-P4, ADR-0018; spec booking-requests R17-R19).

Every write that takes a place reads the session's live holds under its ``FOR UPDATE`` lock:
``Appointment.book`` refuses a held slot, or the last free place when the others are held. Staff
may book anyway only with ``override_hold`` (R18a): the blocking hold ends in the same
transaction and ``appointment.hold_overridden`` is audited. Patients can never block the clinic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor
from mediease_api.domain.appointments.errors import SlotHeld
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.booking.request import BookingRequest, newest_first
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork


@dataclass(frozen=True, slots=True)
class HoldResolution:
    """The holds that still stand for this booking, and the ones staff chose to end."""

    holds: tuple[BookingRequest, ...]
    released: tuple[BookingRequest, ...]


def resolve_holds(
    tenant: TenantRepositories,
    session: Session,
    *,
    slot_start: datetime | None,
    override: bool,
    actor: Actor,
    now: datetime,
) -> HoldResolution:
    """Read the session's live holds; with ``override``, end the ones that block this booking.

    A hold blocks if it is on the chosen slot, or (token mode, or a session whose free places are
    all held) if it is what keeps the last place: then the newest hold ends. Without ``override``
    nothing changes and ``Appointment.book`` decides.
    """
    holds = list(tenant.booking_requests.live_holds([session.id], now))
    if not override or not holds:
        return HoldResolution(tuple(holds), ())
    released = [h for h in holds if slot_start is not None and h.slot_start == slot_start]
    remaining = [h for h in holds if h not in released]
    if session.available > 0:
        for newest in newest_first(remaining):
            if session.available - len(remaining) > 0:
                break
            remaining.remove(newest)
            released.append(newest)
    for hold in released:
        hold.override_hold(by=actor.user_id, now=now)
        tenant.booking_requests.update(hold)
    return HoldResolution(tuple(remaining), tuple(released))


def held_error(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    session: Session,
    slot_start: datetime | None,
    now: datetime,
) -> SlotHeld:
    """The refusal staff see: when the hold ends and the requester's first name, for the
    confirmation of an override. Never the phone, age, sex or reason."""
    holds = tenant.booking_requests.live_holds([session.id], now)
    blocking = next(
        (h for h in holds if slot_start is not None and h.slot_start == slot_start),
        min(holds, key=lambda h: h.hold_expires_at) if holds else None,
    )
    if blocking is None:  # pragma: no cover - raised only when a hold exists
        return SlotHeld(now)
    account = uow.patient_accounts.get(blocking.account_id)
    first = (account.full_name.split() or [""])[0] if account is not None else None
    return SlotHeld(blocking.hold_expires_at, first)


def record_override(
    uow: UnitOfWork,
    *,
    ids_new_id: UUID,
    actor: Actor,
    now: datetime,
    clinic_id: UUID,
    appointment_id: UUID,
    session_id: UUID,
    released: tuple[BookingRequest, ...],
) -> None:
    """R18a: IDs only; the requester is not named in the audit trail."""
    if not released:
        return
    record_event(
        uow,
        event_id=ids_new_id,
        action=AuditAction.APPOINTMENT_HOLD_OVERRIDDEN,
        actor=actor,
        now=now,
        clinic_id=clinic_id,
        entity_type="appointment",
        entity_id=appointment_id,
        metadata={
            "session_id": str(session_id),
            "request_ids": ",".join(str(h.id) for h in released),
        },
    )
