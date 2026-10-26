"""Patient link use cases (M4-P5; FR-RX-07, 08; spec prescriptions R9-R13, R19; decisions 1A-6A).

**Tokens are made from the row.** ``LinkTokens`` signs a link's claims with the key the row
names, so the clinic can show the same link again and nothing secret is stored. Checking a
token: shape, then the MAC (constant time), then the claims against the row (same clinic,
resource, expiry and key), then the row itself (revoked, expired, locked). Anything the patient
could not have caused is ``LINK_INVALID``.

**Public use cases** act as ``PATIENT_LINK`` (no user). They are rate limited in PostgreSQL in
their own transaction, so a refused request still counts: per link, 20 a minute (the spec's
figure), and per caller fingerprint, 300 a minute. The API sees the web server as the caller
until the M6 proxy forwards the patient's address, so the per-caller limit is a ceiling for the
whole patient page, not a per-patient one.

**The challenge (R10, AC3)** runs under the link's row lock, so concurrent wrong answers count
one by one and never pass five. Wrong answers are audited (at most five per link, then it is
locked and further attempts are only logged, so the table cannot be flooded).

**Staff (decision 6A)** with ``RX_PRINT``: get the link for the QR code (created here for chains
issued before M4-P5), reset a locked link, replace a link. IDs only in audit and logs.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext, RequestInfo
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.links import token as tokens
from mediease_api.domain.links.errors import (
    ChallengeFailed,
    ChallengeRequired,
    LinkInvalid,
    LinkLocked,
    LinkRateLimited,
)
from mediease_api.domain.links.link import LinkPurpose, PatientLink
from mediease_api.domain.links.token import Kind, LinkClaims, ViewClaims
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.errors import NotIssued
from mediease_api.domain.prescriptions.patient_view import PatientPage, build_patient_view
from mediease_api.domain.prescriptions.prescription import Prescription, latest_issued
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import LinkSignerPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "patient_link"
PER_LINK_PER_MINUTE = 20
PER_CALLER_PER_MINUTE = 300


# --- Tokens --------------------------------------------------------------------------------------


class LinkTokens:
    """Signs and checks link and view tokens with ``LinkSignerPort`` (R9, decision 3A)."""

    def __init__(self, signer: LinkSignerPort) -> None:
        self._signer = signer

    @property
    def current_key_id(self) -> str:
        return self._signer.current_key_id

    def _sign(self, kind: Kind, key_id: str, claims: bytes) -> str:
        signing = tokens.signing_input(kind, key_id, claims)
        mac = self._signer.mac(key_id, signing)
        if mac is None:  # the row's key was removed from the configuration
            raise LinkInvalid()
        return tokens.assemble(signing, mac)

    def _verified(self, token: str, kind: Kind) -> tokens.Unverified:
        parts = tokens.split(token)
        expected = self._signer.mac(parts.key_id, parts.signing_input)
        if parts.kind is not kind or expected is None:
            raise LinkInvalid()
        if not hmac.compare_digest(expected, parts.mac):
            raise LinkInvalid()
        return parts

    def link_token(self, link: PatientLink) -> str:
        claims = LinkClaims(
            jti=link.id,
            cid=link.clinic_id,
            rid=link.resource_id,
            purpose=link.purpose,
            exp=link.expires_at,
        )
        return self._sign(Kind.LINK, link.key_id, tokens.link_claims_bytes(claims))

    def link_claims(self, token: str) -> tuple[LinkClaims, str]:
        parts = self._verified(token, Kind.LINK)
        return tokens.read_link_claims(parts), parts.key_id

    def view_token(self, link: PatientLink, expires_at: datetime) -> str:
        claims = ViewClaims(jti=link.id, exp=expires_at.replace(microsecond=0))
        return self._sign(Kind.VIEW, self.current_key_id, tokens.view_claims_bytes(claims))

    def queue_token(self, claims: tokens.QueueClaims) -> str:
        """M6b-P6 (R69): a live-queue link, signed with the current key."""
        return self._sign(Kind.QUEUE, self.current_key_id, tokens.queue_claims_bytes(claims))

    def queue_claims(self, token: str) -> tokens.QueueClaims:
        """``LinkInvalid`` for anything that is not a live-queue link signed by a known key."""
        return tokens.read_queue_claims(self._verified(token, Kind.QUEUE))

    def check_view(self, token: str | None, link: PatientLink, now: datetime) -> None:
        if not token:
            raise ChallengeRequired()
        try:
            claims = tokens.read_view_claims(self._verified(token, Kind.VIEW))
        except LinkInvalid:
            raise ChallengeRequired() from None
        if claims.jti != link.id or claims.exp <= now:
            raise ChallengeRequired()


@dataclass(frozen=True, slots=True)
class LinkInfo:
    """What the clinic sees about a link (decision 6A): no content, no digits."""

    link: PatientLink
    token: str


@dataclass(frozen=True, slots=True)
class LinkSummary:
    clinic_name: str
    language: Language
    locked: bool
    purpose: LinkPurpose = LinkPurpose.RX_VIEW


@dataclass(frozen=True, slots=True)
class OpenedView:
    token: str
    expires_at: datetime


# --- Shared helpers ------------------------------------------------------------------------------


def new_link(
    tenant: TenantRepositories,
    first: Prescription,
    *,
    ids: IdPort,
    key_id: str,
    ttl_days: int,
    created_by: UUID,
    now: datetime,
) -> PatientLink:
    """Decision 1A: the chain's link, named by version 1 (added to the tenant here)."""
    assert first.version == 1
    link = PatientLink.create(
        id=ids.new_id(),
        clinic_id=first.clinic_id,
        patient_id=first.patient_id,
        prescription_id=first.id,
        key_id=key_id,
        ttl_days=ttl_days,
        created_by=created_by,
        now=now,
    )
    tenant.patient_links.add(link)
    return link


def _chain(tenant: TenantRepositories, rx: Prescription) -> list[Prescription]:
    return list(tenant.prescriptions.list_for_visit(rx.visit_id))


def _patient_audit(
    uow: UnitOfWork,
    ids: IdPort,
    info: RequestInfo,
    action: AuditAction,
    link: PatientLink,
    now: datetime,
    actor_type: ActorType = ActorType.PATIENT_LINK,
    **metadata: str,
) -> None:
    uow.audit.record(
        AuditEvent.record(
            id=ids.new_id(),
            action=action,
            actor_type=actor_type,
            now=now,
            clinic_id=link.clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=link.id,
            request_id=info.request_id,
            ip_hash=info.ip_hash,
            metadata=metadata,
        )
    )


def check_last4(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    link: PatientLink,
    last4: str,
    *,
    ids: IdPort,
    info: RequestInfo,
    now: datetime,
    actor_type: ActorType,
) -> None:
    """R10, AC3: the last-4 check, on a link locked for update by the caller.

    A wrong answer counts (the fifth locks the link), is audited and **committed** here, then
    raises ``LINK_CHALLENGE_FAILED`` or ``LINK_LOCKED``. A right answer returns with nothing
    changed; the caller records it (an open on the page, a success in the portal, M6b-P1).
    """
    if link.is_locked:
        logger.info("patient_link.locked_attempt", link_id=str(link.id))
        raise LinkLocked()
    patient = tenant.patients.get(link.patient_id)
    assert patient is not None
    expected = patient.phone.e164[-4:].encode()
    if hmac.compare_digest(expected, last4.encode()):
        return
    left = link.record_failure(now)
    tenant.patient_links.update(link)
    attempt = str(link.failed_challenges)
    _patient_audit(
        uow,
        ids,
        info,
        AuditAction.PATIENT_LINK_CHALLENGE_FAILED,
        link,
        now,
        actor_type,
        attempt=attempt,
    )
    if link.is_locked:
        _patient_audit(uow, ids, info, AuditAction.PATIENT_LINK_LOCKED, link, now, actor_type)
    uow.commit()
    logger.info("patient_link.challenge_failed", link_id=str(link.id), attempt=attempt)
    if link.is_locked:
        logger.info("patient_link.locked", link_id=str(link.id))
        raise LinkLocked()
    raise ChallengeFailed(left)


class _Public:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, tokens: LinkTokens
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._tokens = tokens

    def _rate_limit(self, info: RequestInfo, claims: LinkClaims | None) -> None:
        now = self._clock.now()
        window = now.replace(second=0, microsecond=0)
        buckets = [(f"caller:{info.ip_hash or '-'}", PER_CALLER_PER_MINUTE)]
        if claims is not None:
            buckets.append((f"link:{claims.jti}", PER_LINK_PER_MINUTE))
        with self._uow as uow:
            counts = [(uow.rate_limits.hit(b, window_start=window), limit) for b, limit in buckets]
            uow.commit()
        if any(hits > limit for hits, limit in counts):
            retry = 60 - now.second
            logger.info("patient_link.rate_limited", retry_after=retry)
            raise LinkRateLimited(retry)

    def _claims(self, token: str, info: RequestInfo) -> LinkClaims:
        try:
            claims, _ = self._tokens.link_claims(token)
        except LinkInvalid:
            self._rate_limit(info, None)
            logger.info("patient_link.invalid")
            raise
        self._rate_limit(info, claims)
        return claims

    def _load(
        self, tenant: TenantRepositories, token: str, claims: LinkClaims, *, for_update: bool
    ) -> PatientLink:
        link = tenant.patient_links.get(claims.jti, for_update=for_update)
        if (
            link is None
            or link.resource_id != claims.rid
            or link.purpose is not claims.purpose
            or link.expires_at != claims.exp
            or self._tokens.link_token(link) != token
        ):
            logger.info("patient_link.invalid", link_id=str(claims.jti))
            raise LinkInvalid()
        link.check_usable(self._clock.now())
        return link


class DescribeLink(_Public):
    """``GET /public/links/{token}``: the clinic's name and whether the link is locked."""

    def execute(self, token: str, info: RequestInfo) -> LinkSummary:
        claims = self._claims(token, info)
        with self._uow as uow:
            tenant = uow.tenant(claims.cid)
            link = self._load(tenant, token, claims, for_update=False)
            patient = tenant.patients.get(link.patient_id)
            assert patient is not None
            clinic = load_clinic(uow, link.clinic_id)
        return LinkSummary(clinic.name, patient.language, link.is_locked, link.purpose)


class VerifyChallenge(_Public):
    """``POST /public/links/{token}/verify``: the last-4 check (R10, R13, AC3)."""

    def execute(self, token: str, last4: str, info: RequestInfo) -> OpenedView:
        claims = self._claims(token, info)
        with self._uow as uow:
            tenant = uow.tenant(claims.cid)
            link = self._load(tenant, token, claims, for_update=True)
            now = self._clock.now()
            check_last4(
                uow,
                tenant,
                link,
                last4,
                ids=self._ids,
                info=info,
                now=now,
                actor_type=ActorType.PATIENT_LINK,
            )
            link.record_open(now)
            tenant.patient_links.update(link)
            if link.purpose is LinkPurpose.RECEIPT:
                # M6d-P4 (billing R50): a receipt link opened; the bill, nothing else.
                _patient_audit(
                    uow,
                    self._ids,
                    info,
                    AuditAction.RECEIPT_LINK_OPENED,
                    link,
                    now,
                    bill_id=str(link.resource_id),
                )
            else:
                latest = latest_issued(_chain(tenant, _first(tenant, link)))
                assert latest is not None
                _patient_audit(
                    uow,
                    self._ids,
                    info,
                    AuditAction.PATIENT_LINK_OPENED,
                    link,
                    now,
                    version=str(latest.version),
                    prescription_id=str(latest.id),
                )
            uow.commit()
        logger.info("patient_link.opened", link_id=str(link.id))
        expires = link.view_expiry(now).replace(microsecond=0)
        return OpenedView(self._tokens.view_token(link, expires), expires)


class ViewPrescription(_Public):
    """``GET /public/links/{token}/prescription``: the page's content, after the challenge."""

    def execute(
        self, token: str, view: str | None, language: Language | None, info: RequestInfo
    ) -> PatientPage:
        claims = self._claims(token, info)
        with self._uow as uow:
            tenant = uow.tenant(claims.cid)
            link = self._load(tenant, token, claims, for_update=False)
            link.check_unlocked()
            self._tokens.check_view(view, link, self._clock.now())
            patient = tenant.patients.get(link.patient_id)
            assert patient is not None
            clinic = load_clinic(uow, link.clinic_id)
            chain = _chain(tenant, _first(tenant, link))
        page = build_patient_view(
            chain, language=language or patient.language, timezone=clinic.timezone
        )
        if page is None:  # a link exists only for an issued chain, which stays issued
            raise LinkInvalid()
        return page


def _first(tenant: TenantRepositories, link: PatientLink) -> Prescription:
    rx = tenant.prescriptions.get(link.rx_id)
    assert rx is not None  # the foreign key keeps it
    return rx


class ProveWithLink(_Public):
    """M6b-P1 (patient portal spec R6): the page's own last-4 check, for linking an account.

    The same token checks, rate limits, row lock, counter and lockout as ``VerifyChallenge``; a
    wrong answer is audited as the signed-in ``PATIENT``. A right answer clears the count (no
    open is counted: the page was not shown) and runs ``then`` in the same transaction, which
    commits only if ``then`` returns.
    """

    def execute[T](
        self,
        token: str,
        last4: str,
        info: RequestInfo,
        then: Callable[[UnitOfWork, TenantRepositories, PatientLink], T],
    ) -> T:
        claims = self._claims(token, info)
        with self._uow as uow:
            tenant = uow.tenant(claims.cid)
            link = self._load(tenant, token, claims, for_update=True)
            # Only a prescription link links an account (a receipt link does not, M6d-P4).
            link.rx_id  # noqa: B018 - raises LinkInvalid for any other link
            now = self._clock.now()
            check_last4(
                uow,
                tenant,
                link,
                last4,
                ids=self._ids,
                info=info,
                now=now,
                actor_type=ActorType.PATIENT,
            )
            link.record_success(now)
            tenant.patient_links.update(link)
            result = then(uow, tenant, link)
            uow.commit()
        return result


# --- Staff (decision 6A) -------------------------------------------------------------------------


class _Staff:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        tokens: LinkTokens,
        ttl_days: int,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._tokens = tokens
        self._ttl_days = ttl_days

    def _first_issued(
        self, tenant: TenantRepositories, ctx: RequestContext, rx_id: UUID
    ) -> Prescription:
        rx = tenant.prescriptions.get(rx_id)
        if rx is None:
            logger.info(
                "tenancy.not_found",
                entity="prescription",
                entity_id=str(rx_id),
                clinic_id=str(ctx.clinic_id),
            )
            raise NotFound("prescription")
        chain = _chain(tenant, rx)
        if latest_issued(chain) is None:
            raise NotIssued(rx.status.value)
        return chain[0]

    def _audit(
        self,
        uow: UnitOfWork,
        ctx: RequestContext,
        action: AuditAction,
        link: PatientLink,
        **meta: str,
    ) -> None:
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=action,
            actor=Actor.staff(ctx),
            now=self._clock.now(),
            clinic_id=ctx.clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=link.id,
            metadata={"prescription_id": str(link.rx_id), **meta},
        )

    def _new(
        self, tenant: TenantRepositories, ctx: RequestContext, first: Prescription
    ) -> PatientLink:
        return new_link(
            tenant,
            first,
            ids=self._ids,
            key_id=self._tokens.current_key_id,
            ttl_days=self._ttl_days,
            created_by=ctx.user_id,
            now=self._clock.now(),
        )


class GetLink(_Staff):
    """The chain's link for the QR code and copy button; made now for chains issued before P5."""

    def execute(self, ctx: RequestContext, *, rx_id: UUID) -> LinkInfo:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            first = self._first_issued(tenant, ctx, rx_id)
            link = tenant.patient_links.active_for_prescription(first.id)
            if link is None:
                # Lock version 1 so two first requests make one link (the unique index agrees).
                tenant.prescriptions.get(first.id, for_update=True)
                link = tenant.patient_links.active_for_prescription(first.id)
            if link is None:
                link = self._new(tenant, ctx, first)
                self._audit(uow, ctx, AuditAction.PATIENT_LINK_CREATED, link)
                uow.commit()
                logger.info("patient_link.created", link_id=str(link.id))
        return LinkInfo(link, self._tokens.link_token(link))


class ResetLink(_Staff):
    """Unlock a link after five wrong answers (R10); ``LINK_NOT_LOCKED`` otherwise."""

    def execute(self, ctx: RequestContext, *, rx_id: UUID) -> LinkInfo:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            first = self._first_issued(tenant, ctx, rx_id)
            link = tenant.patient_links.active_for_prescription(first.id, for_update=True)
            if link is None:
                raise NotFound("patient link")
            link.reset(self._clock.now())
            tenant.patient_links.update(link)
            self._audit(uow, ctx, AuditAction.PATIENT_LINK_RESET, link)
            uow.commit()
        logger.info("patient_link.reset", link_id=str(link.id))
        return LinkInfo(link, self._tokens.link_token(link))


class ReplaceLink(_Staff):
    """Revoke the chain's link and make a new one (expired, forwarded or lost)."""

    def execute(self, ctx: RequestContext, *, rx_id: UUID) -> LinkInfo:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            first = self._first_issued(tenant, ctx, rx_id)
            old = tenant.patient_links.active_for_prescription(first.id, for_update=True)
            if old is None:
                tenant.prescriptions.get(first.id, for_update=True)
            else:
                old.revoke(self._clock.now())
                tenant.patient_links.update(old)
            link = self._new(tenant, ctx, first)
            self._audit(
                uow,
                ctx,
                AuditAction.PATIENT_LINK_REPLACED,
                link,
                **({"replaced_id": str(old.id)} if old else {}),
            )
            uow.commit()
        logger.info("patient_link.replaced", link_id=str(link.id))
        return LinkInfo(link, self._tokens.link_token(link))
