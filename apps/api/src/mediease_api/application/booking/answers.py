"""Answering booking requests (M6b-P5; FR-BKG-04, 05, 07, FR-PRT-06 a; spec R31-R47).

Staff accept, decline or propose another time; the patient accepts or declines a proposal.

**Exactly one answer wins (R31a).** Every answer reads the request, locks the sessions it touches
(always before the request, the order booking uses), then locks the request row and checks again
that it is still open, still on the same session and not past its deadline. The loser gets 409
``BKG_ALREADY_ANSWERED``. A proposal changes the status and moves the hold in one transaction.
Endpoints reject an expired request themselves; the sweep only writes ``EXPIRED``.

Accepting books through the same steps as a staff booking (the session lock, the slot and token
rules, every *other* live hold counted, the history, ``appointment.booked`` and the confirmation),
then links the account to the record. The reason and the staff note are never logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.appointments.common import (
    ENTITY_TYPE as APPOINTMENT_ENTITY,
)
from mediease_api.application.appointments.common import lock_sessions, place_metadata
from mediease_api.application.booking.holds import held_error, resolve_holds
from mediease_api.application.context import Actor, RequestContext, RequestInfo
from mediease_api.application.notifications.service import publish
from mediease_api.application.patients.register_patient import (
    RegisterPatientCommand,
    add_patient_record,
)
from mediease_api.application.portal.linking import link_for_booking
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.appointments.appointment import Appointment, history_entry
from mediease_api.domain.appointments.errors import (
    OutsideSchedule,
    SessionClosed,
    SessionFull,
    SlotHeld,
    SlotTaken,
)
from mediease_api.domain.appointments.status import AppointmentSource
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.booking.request import (
    AlreadyAnswered,
    BookingRequest,
    DecidedBy,
    DeclineReason,
    RequestStatus,
)
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.notifications.events import AppointmentBooked, BookingRequestAnswered
from mediease_api.domain.patients.patient import Sex
from mediease_api.domain.portal.link import AlreadyLinked
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "booking_request"
CANDIDATE_LIMIT = 10
NO_SHOW_WINDOW = timedelta(days=365)


@dataclass(frozen=True, slots=True, repr=False)
class NewRecord:
    """R37: a new record from the request; staff fill what the patient left out."""

    sex: Sex | None = None
    age_years: int | None = None
    date_of_birth: date | None = None
    full_name: str | None = None

    def __repr__(self) -> str:
        return "NewRecord(<redacted>)"


@dataclass(frozen=True, slots=True)
class RecordChoice:
    """Exactly one: an existing record of this clinic, or a new one."""

    patient_id: UUID | None = None
    new: NewRecord | None = None

    def __post_init__(self) -> None:
        if (self.patient_id is None) == (self.new is None):
            raise InvalidValue("patient", "choose a record or create a new one")


@dataclass(frozen=True, slots=True)
class AnswerResult:
    request_id: UUID
    status: RequestStatus
    patient_id: UUID | None
    appointment_id: UUID | None


@dataclass(frozen=True, slots=True, repr=False)
class Candidate:
    id: UUID
    code: str
    full_name: str
    age_years: int
    no_shows: int

    def __repr__(self) -> str:
        return f"Candidate(code={self.code!r})"


@dataclass(frozen=True, slots=True, repr=False)
class CandidateList:
    """R36. ``linked``: the account already has this clinic's record, which accept must use."""

    linked: bool
    items: tuple[Candidate, ...]
    suggested_name: str
    suggested_age_years: int | None
    suggested_sex: Sex | None

    def __repr__(self) -> str:
        return f"CandidateList(linked={self.linked}, items={len(self.items)})"


@dataclass(frozen=True, slots=True)
class _Who:
    """Who answers: staff (a user) or the patient (no user, actor PATIENT)."""

    user_id: UUID | None
    actor_type: ActorType
    info: RequestInfo
    staff: Actor | None


def _staff(ctx: RequestContext) -> _Who:
    actor = Actor.staff(ctx)
    return _Who(ctx.user_id, ActorType.STAFF, ctx.info, actor)


def _audit(
    uow: UnitOfWork,
    ids: IdPort,
    who: _Who,
    action: AuditAction,
    *,
    now: datetime,
    clinic_id: UUID,
    entity_type: str,
    entity_id: UUID,
    metadata: dict[str, str],
) -> None:
    uow.audit.record(
        AuditEvent.record(
            id=ids.new_id(),
            action=action,
            actor_type=who.actor_type,
            actor_user_id=who.user_id,
            now=now,
            clinic_id=clinic_id,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=who.info.request_id,
            ip_hash=who.info.ip_hash,
            metadata=metadata,
        )
    )


def _peek(tenant: TenantRepositories, request_id: UUID) -> BookingRequest:
    request = tenant.booking_requests.get(request_id)
    if request is None:
        raise NotFound("booking request")
    return request


def _relock(
    tenant: TenantRepositories, peek: BookingRequest, now: datetime, status: RequestStatus
) -> BookingRequest:
    """R31a: the row lock, then the same checks again: open, this status, the same session."""
    request = tenant.booking_requests.get(peek.id, for_update=True)
    if (
        request is None
        or not request.is_open(now)
        or request.status is not status
        or request.session_id != peek.session_id
    ):
        raise AlreadyAnswered()
    return request


def _require_answerable(request: BookingRequest, now: datetime, status: RequestStatus) -> None:
    if not request.is_open(now) or request.status is not status:
        raise AlreadyAnswered()


def _resolve_record(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    clinic: Clinic,
    request: BookingRequest,
    choice: RecordChoice,
    *,
    ids: IdPort,
    actor: Actor,
    now: datetime,
) -> UUID:
    """R36-R38: the record the request is for. Never chosen by phone alone."""
    linked = tenant.portal_links.active_for_account(request.account_id)
    if linked is not None:
        if choice.patient_id != linked.patient_id:
            raise AlreadyLinked()  # the account already has this clinic's record: use it
        return linked.patient_id
    if choice.patient_id is not None:
        if tenant.patients.get(choice.patient_id) is None:
            raise NotFound("patient")
        if tenant.portal_links.active_for_patient(choice.patient_id) is not None:
            raise AlreadyLinked()
        return choice.patient_id
    new = choice.new
    assert new is not None
    sex = new.sex or request.sex
    if sex is None:
        raise InvalidValue("sex", "is required for a new record")
    age = None if new.date_of_birth is not None else (new.age_years or request.age_years)
    if new.date_of_birth is None and age is None:
        raise InvalidValue("age_years", "or a date of birth is required for a new record")
    account = uow.patient_accounts.get(request.account_id)
    name = new.full_name or (account.full_name if account is not None else "")
    shared = bool(tenant.patients.find_by_phone(request.contact_phone, limit=1))
    patient = add_patient_record(
        uow,
        clinic,
        RegisterPatientCommand(
            full_name=name,
            phone=request.contact_phone.e164,
            sex=sex,
            date_of_birth=new.date_of_birth,
            age_years=age,
            confirm_new=True,
        ),
        phone=request.contact_phone,
        ids=ids,
        actor=actor,
        shared_phone=shared,
        now=now,
    )
    return patient.id


def _book(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    request: BookingRequest,
    session: Session,
    patient_id: UUID,
    *,
    who: _Who,
    ids: IdPort,
    now: datetime,
) -> Appointment:
    """R34, R35: book the request's time; its own hold excluded, every other one counted."""
    holds = resolve_holds(
        tenant,
        session,
        slot_start=request.slot_start,
        override=False,
        actor=None,
        now=now,
        exclude=request.id,
    ).holds
    try:
        appointment = Appointment.book(
            session,
            id=ids.new_id(),
            patient_id=patient_id,
            active=tenant.appointments.list_active_for_sessions([session.id]),
            now=now,
            slot_start=request.slot_start,
            source=AppointmentSource.PUBLIC_PAGE,
            created_by=who.user_id,
            holds=holds,
        )
    except SlotHeld:
        raise held_error(uow, tenant, session, request.slot_start, now) from None
    tenant.sessions.update(session)
    tenant.appointments.add(appointment)
    tenant.appointment_history.add(
        history_entry(
            appointment,
            id=ids.new_id(),
            from_status=None,
            changed_by=who.user_id,
            request_id=who.info.request_id,
        )
    )
    _audit(
        uow,
        ids,
        who,
        AuditAction.APPOINTMENT_BOOKED,
        now=now,
        clinic_id=request.clinic_id,
        entity_type=APPOINTMENT_ENTITY,
        entity_id=appointment.id,
        metadata={**place_metadata(appointment, session), "booking_request_id": str(request.id)},
    )
    publish(
        uow,
        AppointmentBooked(appointment.id),
        clinic_id=request.clinic_id,
        ids=ids,
        now=now,
        request_id=who.info.request_id,
        actor_user_id=who.user_id,
    )
    return appointment


def _accept(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    peek: BookingRequest,
    *,
    status: RequestStatus,
    record: UUID | RecordChoice,
    clinic: Clinic,
    who: _Who,
    ids: IdPort,
    now: datetime,
) -> AnswerResult:
    """One transaction: lock, re-check, book, link, mark accepted, audit (R34, R42)."""
    locked = lock_sessions(tenant, clinic.id, [peek.session_id])
    session = locked.sessions[peek.session_id]
    if not locked.doctors[session.doctor_id].is_active:
        raise SessionClosed()
    request = _relock(tenant, peek, now, status)
    if isinstance(record, RecordChoice):
        assert who.staff is not None
        patient_id = _resolve_record(
            uow, tenant, clinic, request, record, ids=ids, actor=who.staff, now=now
        )
    else:
        patient_id = record
    appointment = _book(uow, tenant, request, session, patient_id, who=who, ids=ids, now=now)
    link_for_booking(
        uow,
        tenant,
        ids=ids,
        info=who.info,
        patient_id=patient_id,
        account_id=request.account_id,
        staff=who.staff,
        now=now,
    )
    by = DecidedBy.STAFF if who.staff is not None else DecidedBy.PATIENT
    request.accept(
        patient_id=patient_id, appointment_id=appointment.id, by=by, user_id=who.user_id, now=now
    )
    tenant.booking_requests.update(request)
    _audit(
        uow,
        ids,
        who,
        AuditAction.BOOKING_REQUEST_ACCEPTED,
        now=now,
        clinic_id=clinic.id,
        entity_type=ENTITY_TYPE,
        entity_id=request.id,
        metadata={
            "appointment_id": str(appointment.id),
            "patient_id": str(patient_id),
            "account_id": str(request.account_id),
        },
    )
    _announce(uow, request, who=who, ids=ids, now=now)
    return AnswerResult(request.id, request.status, patient_id, appointment.id)


def _announce(
    uow: UnitOfWork, request: BookingRequest, *, who: _Who, ids: IdPort, now: datetime
) -> None:
    """M6b-P6 (portal R57): the requester hears of the answer, in this transaction."""
    publish(
        uow,
        BookingRequestAnswered(request.id),
        clinic_id=request.clinic_id,
        ids=ids,
        now=now,
        request_id=who.info.request_id,
        actor_user_id=who.user_id,
    )


def _log(event: str, result: AnswerResult, clinic_id: UUID) -> None:
    logger.info(
        event,
        request_id=str(result.request_id),
        clinic_id=str(clinic_id),
        status=result.status.value,
    )


class _UseCase:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids


class AcceptBookingRequest(_UseCase):
    """``POST /booking-requests/{id}/accept`` (R34-R38)."""

    def execute(self, ctx: RequestContext, request_id: UUID, choice: RecordChoice) -> AnswerResult:
        with self._uow as uow:
            now = self._clock.now()
            tenant = uow.tenant(ctx.clinic_id)
            peek = _peek(tenant, request_id)
            _require_answerable(peek, now, RequestStatus.PENDING)
            clinic = uow.clinics.get(ctx.clinic_id, for_update=choice.new is not None)
            if clinic is None:  # pragma: no cover - the context names an existing clinic
                raise NotFound("clinic")
            result = _accept(
                uow,
                tenant,
                peek,
                status=RequestStatus.PENDING,
                record=choice,
                clinic=clinic,
                who=_staff(ctx),
                ids=self._ids,
                now=now,
            )
            uow.commit()
        _log("booking_request.accepted", result, ctx.clinic_id)
        return result


class DeclineBookingRequest(_UseCase):
    """``POST /booking-requests/{id}/decline`` (R39). Ends the hold at once."""

    def execute(
        self, ctx: RequestContext, request_id: UUID, reason: DeclineReason, note: str | None
    ) -> AnswerResult:
        with self._uow as uow:
            now = self._clock.now()
            tenant = uow.tenant(ctx.clinic_id)
            _peek(tenant, request_id)
            request = tenant.booking_requests.get(request_id, for_update=True)
            assert request is not None
            request.decline(
                reason=reason, note=note, by=DecidedBy.STAFF, user_id=ctx.user_id, now=now
            )
            tenant.booking_requests.update(request)
            _audit(
                uow,
                self._ids,
                _staff(ctx),
                AuditAction.BOOKING_REQUEST_DECLINED,
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=request.id,
                metadata={"reason": reason.value, "account_id": str(request.account_id)},
            )
            _announce(uow, request, who=_staff(ctx), ids=self._ids, now=now)
            result = AnswerResult(request.id, request.status, request.patient_id, None)
            uow.commit()
        _log("booking_request.declined", result, ctx.clinic_id)
        return result


class ProposeBookingTime(_UseCase):
    """``POST /booking-requests/{id}/propose`` (R40, R41): the hold moves with the status."""

    def execute(
        self,
        ctx: RequestContext,
        request_id: UUID,
        *,
        session_id: UUID,
        slot_start: datetime | None,
        choice: RecordChoice,
    ) -> AnswerResult:
        with self._uow as uow:
            now = self._clock.now()
            tenant = uow.tenant(ctx.clinic_id)
            peek = _peek(tenant, request_id)
            _require_answerable(peek, now, RequestStatus.PENDING)
            clinic = uow.clinics.get(ctx.clinic_id, for_update=choice.new is not None)
            if clinic is None:  # pragma: no cover
                raise NotFound("clinic")
            locked = lock_sessions(tenant, ctx.clinic_id, {peek.session_id, session_id})
            target = locked.sessions[session_id]
            if target.doctor_id != peek.doctor_id:
                raise InvalidValue("session_id", "must be with the same doctor")
            if not locked.doctors[target.doctor_id].is_active or not target.is_open:
                raise SessionClosed()
            if target.mode is BookingMode.SLOTS:
                if slot_start is None:
                    raise InvalidValue("slot_start", "is required in slot mode")
                if target.slot_at(slot_start) is None:
                    raise OutsideSchedule()
            elif slot_start is not None:
                raise InvalidValue("slot_start", "is not used in token mode")
            request = _relock(tenant, peek, now, RequestStatus.PENDING)

            # The proposed time must be free of bookings and of other patients' holds.
            active = tenant.appointments.list_active_for_sessions([target.id])
            others = [
                h
                for h in tenant.booking_requests.live_holds([target.id], now)
                if h.id != request.id
            ]
            if slot_start is not None:
                if any(a.slot_start == slot_start for a in active):
                    raise SlotTaken()
                if any(h.slot_start == slot_start for h in others):
                    raise held_error(uow, tenant, target, slot_start, now)
            if target.available <= 0:
                raise SessionFull()
            if target.available - len(others) <= 0:
                raise held_error(uow, tenant, target, None, now)

            who = _staff(ctx)
            assert who.staff is not None
            patient_id = _resolve_record(
                uow, tenant, clinic, request, choice, ids=self._ids, actor=who.staff, now=now
            )
            request.propose(
                session_id=target.id,
                slot_start=slot_start,
                starts_at=slot_start or target.starts_at,
                patient_id=patient_id,
                hold_minutes=clinic.request_hold_minutes,
                user_id=ctx.user_id,
                now=now,
            )
            tenant.booking_requests.update(request)
            _audit(
                uow,
                self._ids,
                who,
                AuditAction.BOOKING_REQUEST_PROPOSED,
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=request.id,
                metadata={
                    "session_id": str(target.id),
                    "original_session_id": str(peek.session_id),
                    "patient_id": str(patient_id),
                },
            )
            _announce(uow, request, who=who, ids=self._ids, now=now)
            result = AnswerResult(request.id, request.status, patient_id, None)
            uow.commit()
        _log("booking_request.proposed", result, ctx.clinic_id)
        return result


class _PatientAnswer(_UseCase):
    def _load(
        self, uow: UnitOfWork, principal: PatientPrincipal, request_id: UUID, now: datetime
    ) -> tuple[Clinic, TenantRepositories, BookingRequest]:
        peek = uow.booking_request_lookup.find_for_account(principal.account_id, request_id)
        clinic = uow.clinics.get(peek.clinic_id) if peek is not None else None
        if peek is None or clinic is None or not clinic.has_public_page:
            raise NotFound("booking request")
        _require_answerable(peek, now, RequestStatus.PROPOSED)
        return clinic, uow.tenant(clinic.id), peek


def _patient(info: RequestInfo) -> _Who:
    return _Who(None, ActorType.PATIENT, info, None)


class AcceptProposal(_PatientAnswer):
    """``POST /portal/booking-requests/{id}/accept-proposal`` (R42): books and links as R34."""

    def execute(
        self, principal: PatientPrincipal, request_id: UUID, info: RequestInfo
    ) -> AnswerResult:
        with self._uow as uow:
            now = self._clock.now()
            clinic, tenant, peek = self._load(uow, principal, request_id, now)
            assert peek.patient_id is not None
            result = _accept(
                uow,
                tenant,
                peek,
                status=RequestStatus.PROPOSED,
                record=peek.patient_id,
                clinic=clinic,
                who=_patient(info),
                ids=self._ids,
                now=now,
            )
            uow.commit()
        _log("booking_request.accepted", result, clinic.id)
        return result


class DeclineProposal(_PatientAnswer):
    """``POST /portal/booking-requests/{id}/decline-proposal`` (R43): *No thanks*."""

    def execute(
        self, principal: PatientPrincipal, request_id: UUID, info: RequestInfo
    ) -> AnswerResult:
        with self._uow as uow:
            now = self._clock.now()
            clinic, tenant, peek = self._load(uow, principal, request_id, now)
            request = _relock(tenant, peek, now, RequestStatus.PROPOSED)
            request.decline(
                reason=DeclineReason.PATIENT_DECLINED,
                note=None,
                by=DecidedBy.PATIENT,
                user_id=None,
                now=now,
            )
            tenant.booking_requests.update(request)
            _audit(
                uow,
                self._ids,
                _patient(info),
                AuditAction.BOOKING_REQUEST_DECLINED,
                now=now,
                clinic_id=clinic.id,
                entity_type=ENTITY_TYPE,
                entity_id=request.id,
                metadata={
                    "reason": DeclineReason.PATIENT_DECLINED.value,
                    "account_id": str(request.account_id),
                },
            )
            result = AnswerResult(request.id, request.status, request.patient_id, None)
            uow.commit()
        _log("booking_request.declined", result, clinic.id)
        return result


class ListRequestCandidates(_UseCase):
    """``GET /booking-requests/{id}/candidates`` (R36, R47): read only, not audited."""

    def execute(self, ctx: RequestContext, request_id: UUID) -> CandidateList:
        with self._uow as uow:
            now = self._clock.now()
            clinic = uow.clinics.get(ctx.clinic_id)
            if clinic is None:  # pragma: no cover
                raise NotFound("clinic")
            tenant = uow.tenant(ctx.clinic_id)
            request = _peek(tenant, request_id)
            today = local_date(now, clinic.timezone)
            link = tenant.portal_links.active_for_account(request.account_id)
            if link is not None:
                linked = tenant.patients.get(link.patient_id)
                patients = [linked] if linked is not None else []
            else:
                patients = list(
                    tenant.patients.find_by_phone(request.contact_phone, limit=CANDIDATE_LIMIT)
                )
            no_shows = tenant.appointments.count_no_shows(
                [p.id for p in patients], now - NO_SHOW_WINDOW
            )
            account = uow.patient_accounts.get(request.account_id)
            return CandidateList(
                linked=link is not None,
                items=tuple(
                    Candidate(p.id, p.code, p.full_name, p.age_years(today), no_shows.get(p.id, 0))
                    for p in patients
                ),
                suggested_name=account.full_name if account is not None else "",
                suggested_age_years=request.age_years,
                suggested_sex=request.sex,
            )
