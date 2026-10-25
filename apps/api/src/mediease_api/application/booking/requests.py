"""Booking requests: the patient asks, staff see (M6b-P4; FR-PUB-02, 03, FR-BKG-01..03, 07).

A request needs a signed-in **verified** account (FR-PUB-03; no guest, no OTP). It places the soft
hold (ADR-0018) under the session's row lock, writes ``booking_request.created`` (PATIENT) and
publishes ``BookingRequested`` in one transaction. P5 answers it. The reason is clinical text:
never logged or put in a notification or error; the phone is not logged at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.appointments.common import lock_sessions
from mediease_api.application.booking.limits import limit_phone, limit_requests
from mediease_api.application.booking.public import find_public_clinic
from mediease_api.application.context import RequestContext, RequestInfo
from mediease_api.application.notifications.service import publish
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.application.scheduling.generation import generate
from mediease_api.application.scheduling.schedules import load_doctor
from mediease_api.domain.appointments.errors import (
    OutsideSchedule,
    SessionClosed,
    SessionFull,
    SlotTaken,
)
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.booking.request import (
    HORIZON_DAYS,
    MAX_OPEN_REQUESTS,
    BookingRequest,
    RequestExists,
    TooManyRequests,
)
from mediease_api.domain.notifications.events import BookingRequested
from mediease_api.domain.patients.patient import Sex
from mediease_api.domain.portal.link import UnverifiedAccount
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.repositories import RowLock
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "booking_request"
LIST_LIMIT = 100


@dataclass(frozen=True, slots=True)
class BookingRequestCommand:
    clinic_slug: str
    doctor_id: UUID
    # The session is named by its start (it may not exist yet: availability writes nothing, R8).
    session_start: datetime
    slot_start: datetime | None
    contact_phone: str
    age_years: int | None
    sex: Sex | None
    reason: str | None
    not_emergency_ack: bool


@dataclass(frozen=True, slots=True)
class RequestItem:
    """A request as the patient sees it: where, who with, when, and that it is Requested."""

    id: UUID
    clinic_id: UUID
    clinic_name: str
    clinic_slug: str
    clinic_phone_e164: str | None
    timezone: str
    doctor_name: str
    mode: BookingMode
    starts_at: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StaffRequestItem:
    """R22: what front desk needs to match or create the record, and nothing more."""

    id: UUID
    full_name: str
    age_years: int | None
    sex: Sex | None
    phone_e164: str
    reason: str | None
    doctor_name: str
    mode: BookingMode
    starts_at: datetime
    created_at: datetime
    hold_expires_at: datetime
    holding: bool
    hold_overridden: bool
    respond_by: datetime


class CreateBookingRequest:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, principal: PatientPrincipal, cmd: BookingRequestCommand, info: RequestInfo
    ) -> RequestItem:
        account = principal.account
        if not account.is_email_verified:
            raise UnverifiedAccount()
        phone = PhoneNumber.parse(cmd.contact_phone, field="contact_phone")
        limit_requests(self._uow, self._clock, info, account_id=str(account.id))
        limit_phone(self._uow, self._clock, phone.e164)

        with self._uow as uow:
            now = self._clock.now()
            clinic = find_public_clinic(uow, cmd.clinic_slug)
            tenant = uow.tenant(clinic.id)
            doctor = load_doctor(tenant, clinic.id, cmd.doctor_id, lock=RowLock.SHARE)
            if not doctor.is_active:
                raise SessionClosed()
            on_date = local_date(cmd.session_start, clinic.timezone)
            today = local_date(now, clinic.timezone)
            if on_date > today + timedelta(days=HORIZON_DAYS - 1):
                raise InvalidValue("session_start", "is more than 14 days ahead")
            if on_date >= today:
                generate(
                    tenant, clinic=clinic, doctor=doctor, on_date=on_date, ids=self._ids, now=now
                )
            chosen = next(
                (
                    s
                    for s in tenant.sessions.list_for_date(on_date, doctor_id=doctor.id)
                    if s.starts_at == cmd.session_start
                ),
                None,
            )
            if chosen is None:
                raise InvalidValue("session_start", "is not a session of this doctor")

            session = lock_sessions(tenant, clinic.id, [chosen.id]).sessions[chosen.id]
            if not session.is_open:
                raise SessionClosed()
            slot_start = cmd.slot_start
            if session.mode is BookingMode.SLOTS:
                if slot_start is None:
                    raise InvalidValue("slot_start", "is required in slot mode")
                if session.slot_at(slot_start) is None:
                    raise OutsideSchedule()
            elif slot_start is not None:
                raise InvalidValue("slot_start", "is not used in token mode")

            request = BookingRequest.create(
                id=self._ids.new_id(),
                clinic_id=clinic.id,
                doctor_id=doctor.id,
                session_id=session.id,
                slot_start=slot_start,
                starts_at=slot_start or session.starts_at,
                account_id=account.id,
                contact_phone=phone,
                age_years=cmd.age_years,
                sex=cmd.sex,
                reason=cmd.reason,
                not_emergency_ack=cmd.not_emergency_ack,
                requires_age_sex=clinic.request_requires_age_sex,
                hold_minutes=clinic.request_hold_minutes,
                now=now,
            )
            if uow.booking_request_lookup.count_open(account.id, now) >= MAX_OPEN_REQUESTS:
                raise TooManyRequests()
            if tenant.booking_requests.has_pending(account.id, session.id):
                raise RequestExists()
            # Under the session's lock: booked slots and places, then live holds (ADR-0018).
            active = tenant.appointments.list_active_for_sessions([session.id])
            holds = tenant.booking_requests.live_holds([session.id], now)
            if slot_start is not None and (
                any(a.slot_start == slot_start for a in active)
                or any(h.slot_start == slot_start for h in holds)
            ):
                raise SlotTaken()
            if session.available - len(holds) <= 0:
                raise SessionFull()

            tenant.booking_requests.add(request)
            uow.audit.record(
                AuditEvent.record(
                    id=self._ids.new_id(),
                    action=AuditAction.BOOKING_REQUEST_CREATED,
                    actor_type=ActorType.PATIENT,
                    now=now,
                    clinic_id=clinic.id,
                    entity_type=ENTITY_TYPE,
                    entity_id=request.id,
                    request_id=info.request_id,
                    ip_hash=info.ip_hash,
                    metadata={
                        "account_id": str(account.id),
                        "doctor_id": str(doctor.id),
                        "session_id": str(session.id),
                        "mode": session.mode.value,
                    },
                )
            )
            publish(
                uow,
                BookingRequested(request.id),
                clinic_id=clinic.id,
                ids=self._ids,
                now=now,
                request_id=info.request_id,
                actor_user_id=None,
            )
            item = RequestItem(
                id=request.id,
                clinic_id=clinic.id,
                clinic_name=clinic.name,
                clinic_slug=clinic.slug,
                clinic_phone_e164=clinic.phone.e164 if clinic.phone else None,
                timezone=clinic.timezone,
                doctor_name=doctor.display_name,
                mode=session.mode,
                starts_at=slot_start or session.starts_at,
                created_at=request.created_at,
            )
            uow.commit()
        logger.info(
            "booking_request.created",
            request_id=str(request.id),
            clinic_id=str(clinic.id),
            doctor_id=str(doctor.id),
            session_id=str(session.id),
        )
        return item


class ListMyBookingRequests:
    """R20: the account's open requests in every clinic, soonest first; never another account's."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, principal: PatientPrincipal) -> list[RequestItem]:
        now = self._clock.now()
        items: list[RequestItem] = []
        with self._uow as uow:
            for request in uow.booking_request_lookup.for_account(principal.account_id, limit=20):
                clinic = uow.clinics.get(request.clinic_id)
                if clinic is None or not clinic.has_public_page:
                    continue  # suspended: hidden like the rest of its records (portal scope)
                tenant = uow.tenant(request.clinic_id)
                session = tenant.sessions.get(request.session_id)
                doctor = tenant.doctors.get(request.doctor_id)
                if session is None or doctor is None:  # pragma: no cover - foreign keys
                    continue
                starts_at = request.slot_start or session.starts_at
                if starts_at <= now:
                    continue
                items.append(
                    RequestItem(
                        id=request.id,
                        clinic_id=clinic.id,
                        clinic_name=clinic.name,
                        clinic_slug=clinic.slug,
                        clinic_phone_e164=clinic.phone.e164 if clinic.phone else None,
                        timezone=clinic.timezone,
                        doctor_name=doctor.display_name,
                        mode=session.mode,
                        starts_at=starts_at,
                        created_at=request.created_at,
                    )
                )
        return sorted(items, key=lambda i: i.starts_at)


class ListBookingRequests:
    """R22: the clinic's open requests, oldest first (read-only in P4)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext) -> list[StaffRequestItem]:
        now = self._clock.now()
        items: list[StaffRequestItem] = []
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            doctors = {d.id: d.display_name for d in tenant.doctors.list()}
            for request in tenant.booking_requests.list_pending(limit=LIST_LIMIT):
                session = tenant.sessions.get(request.session_id)
                account = uow.patient_accounts.get(request.account_id)
                if session is None or account is None:  # pragma: no cover - foreign keys
                    continue
                items.append(
                    StaffRequestItem(
                        id=request.id,
                        full_name=account.full_name,
                        age_years=request.age_years,
                        sex=request.sex,
                        phone_e164=request.contact_phone.e164,
                        reason=request.reason,
                        doctor_name=doctors.get(request.doctor_id, ""),
                        mode=session.mode,
                        starts_at=request.slot_start or session.starts_at,
                        created_at=request.created_at,
                        hold_expires_at=request.hold_expires_at,
                        holding=request.is_live_hold(now),
                        hold_overridden=request.hold_overridden_at is not None,
                        respond_by=request.respond_by,
                    )
                )
        return items
