"""The live token link (M6b-P6; FR-QUE-06; portal spec R69-R72; ADR-0019).

A signed link per appointment (token kind ``QUEUE``: clinic, appointment, valid-from, expiry),
valid from the start of its session's day until 2 hours after the session ends. It is stateless:
nothing is stored, and cancelling or moving the appointment changes what it shows.

**Issued** only to its own clinic's staff, or to the account linked to the appointment's record
(anything else is 404). **Read** with no sign-in, because it shows only what a waiting-room display
shows (ADR-0019): the clinic, the doctor, the patient's own token or slot, how many are ahead,
which token or slot is being seen, and a state. Never a name, phone, reason or age, nor anything
about other patients. Rate limited per caller and per link, like the prescription link.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.context import RequestContext, RequestInfo
from mediease_api.application.links.use_cases import LinkTokens
from mediease_api.application.portal.scope import PortalScope
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.live import LiveView, live_view
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.links.errors import LinkExpired, LinkInvalid, LinkRateLimited
from mediease_api.domain.links.token import QueueClaims
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_day_start
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

AFTER_SESSION = timedelta(hours=2)
PER_CALLER_PER_MINUTE = 120
PER_LINK_PER_MINUTE = 30


@dataclass(frozen=True, slots=True)
class LiveLink:
    url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LiveQueue:
    clinic_name: str
    doctor_name: str
    timezone: str
    mode: BookingMode
    view: LiveView
    session_starts_at: datetime


def _issue(
    tokens: LinkTokens,
    base_url: str,
    *,
    clinic_id: UUID,
    timezone: str,
    appointment: Appointment,
    session: Session,
    now: datetime,
) -> LiveLink:
    if appointment.status is AppointmentStatus.CANCELLED:
        raise InvalidValue("appointment", "is cancelled")
    expires = session.ends_at + AFTER_SESSION
    if expires <= now:
        raise InvalidValue("appointment", "has ended")
    claims = QueueClaims(
        cid=clinic_id,
        aid=appointment.id,
        nbf=local_day_start(session.on_date, timezone).replace(microsecond=0),
        exp=expires.replace(microsecond=0),
    )
    return LiveLink(
        url=f"{base_url.rstrip('/')}/q/{tokens.queue_token(claims)}", expires_at=expires
    )


def _load(tenant: TenantRepositories, appointment_id: UUID) -> tuple[Appointment, Session]:
    appointment = tenant.appointments.get(appointment_id)
    if appointment is None:
        raise NotFound("appointment")
    session = tenant.sessions.get(appointment.session_id)
    assert session is not None  # a foreign key keeps it
    return appointment, session


class IssueStaffLiveLink:
    """``GET /appointments/{id}/live-link`` (R69): for staff to send by hand."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, tokens: LinkTokens, base_url: str):
        self._uow = uow
        self._clock = clock
        self._tokens = tokens
        self._base = base_url

    def execute(self, ctx: RequestContext, appointment_id: UUID) -> LiveLink:
        with self._uow as uow:
            clinic = uow.clinics.get(ctx.clinic_id)
            assert clinic is not None
            appointment, session = _load(uow.tenant(ctx.clinic_id), appointment_id)
            return _issue(
                self._tokens,
                self._base,
                clinic_id=clinic.id,
                timezone=clinic.timezone,
                appointment=appointment,
                session=session,
                now=self._clock.now(),
            )


class IssuePortalLiveLink:
    """``GET /portal/appointments/{id}/live-link`` (R69): only for the account's own records."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, tokens: LinkTokens, base_url: str):
        self._uow = uow
        self._clock = clock
        self._tokens = tokens
        self._base = base_url

    def execute(self, principal: PatientPrincipal, appointment_id: UUID) -> LiveLink:
        with self._uow as uow:
            for entry in PortalScope.read(uow, principal.account_id):
                appointment = entry.tenant.appointments.get(appointment_id)
                if appointment is None or appointment.patient_id != entry.patient_id:
                    continue
                session = entry.tenant.sessions.get(appointment.session_id)
                assert session is not None
                return _issue(
                    self._tokens,
                    self._base,
                    clinic_id=entry.clinic.id,
                    timezone=entry.clinic.timezone,
                    appointment=appointment,
                    session=session,
                    now=self._clock.now(),
                )
        logger.info("portal.not_found", entity="appointment")
        raise NotFound("appointment")


class GetLiveQueue:
    """``GET /public/queue/{token}`` (R70, R71): no sign-in; 404 invalid, 410 expired."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, tokens: LinkTokens) -> None:
        self._uow = uow
        self._clock = clock
        self._tokens = tokens

    def _rate_limit(self, info: RequestInfo, claims: QueueClaims | None) -> None:
        now = self._clock.now()
        window = now.replace(second=0, microsecond=0)
        buckets = [(f"queue-caller:{info.ip_hash or '-'}", PER_CALLER_PER_MINUTE)]
        if claims is not None:
            buckets.append((f"queue-link:{claims.aid}", PER_LINK_PER_MINUTE))
        with self._uow as uow:
            counts = [(uow.rate_limits.hit(b, window_start=window), limit) for b, limit in buckets]
            uow.commit()
        if any(hits > limit for hits, limit in counts):
            retry = 60 - now.second
            logger.info("live_queue.rate_limited", retry_after=retry)
            raise LinkRateLimited(retry)

    def execute(self, token: str, info: RequestInfo) -> LiveQueue:
        try:
            claims = self._tokens.queue_claims(token)
        except LinkInvalid:
            self._rate_limit(info, None)
            logger.info("live_queue.invalid")
            raise
        self._rate_limit(info, claims)
        now = self._clock.now()
        if now < claims.nbf or now >= claims.exp:
            raise LinkExpired()
        with self._uow as uow:
            clinic = uow.clinics.get(claims.cid)
            if clinic is None or not clinic.has_public_page:
                raise LinkInvalid()
            tenant = uow.tenant(clinic.id)
            appointment = tenant.appointments.get(claims.aid)
            if appointment is None:
                raise LinkInvalid()
            session = tenant.sessions.get(appointment.session_id)
            doctor = tenant.doctors.get(appointment.doctor_id)
            assert session is not None and doctor is not None
            everyone = tenant.appointments.list_for_sessions([session.id])
            view = live_view(appointment, session, everyone, now)
            return LiveQueue(
                clinic_name=clinic.name,
                doctor_name=doctor.display_name,
                timezone=clinic.timezone,
                mode=session.mode,
                view=view,
                session_starts_at=session.starts_at,
            )
