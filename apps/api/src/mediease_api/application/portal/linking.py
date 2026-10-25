"""Linking a patient account to a clinic's patient record (M6b-P1; FR-PRT-02, 06 b, c).

Patient portal spec R1-R8; design decisions 1A-3A, 7A, 8A.

**Staff** (``PATIENTS_MANAGE``) invite a record, see its portal status and unlink it. The invite's
secret is returned once (R1) and stored as a digest; a new invite supersedes the pending one.
A record that is already linked cannot be invited (``PRT_ALREADY_LINKED``).

**Patients** (a signed-in portal account) describe and accept an invite, link by a prescription
link's last-4 check (verified accounts only, R5), and unlink. Linking locks the patient row, so
two accounts racing for one record are serialised; the partial unique indexes answer a race the
lock cannot see (one account, two records) with the same ``PRT_ALREADY_LINKED``.

Audit (spec §7): ``patient.portal_invited`` (STAFF), ``patient.portal_linked`` (PATIENT),
``patient.portal_unlinked`` (PATIENT or STAFF), on the ``patient`` entity so the owner's audit log
shows the record's code. IDs, the method and who only; logs likewise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext, RequestInfo
from mediease_api.application.links.use_cases import ProveWithLink
from mediease_api.application.portal.scope import PortalScope
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.links.link import PatientLink
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.portal.link import (
    AlreadyLinked,
    LinkMethod,
    PatientAccountLink,
    PatientPortalInvite,
    PortalInviteInvalid,
    RevokedBy,
    UnverifiedAccount,
    check_can_link,
)
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import InviteSecrets
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "patient"
MAX_TOKEN_LENGTH = 128


class PortalStatus(StrEnum):
    NOT_LINKED = "NOT_LINKED"
    INVITED = "INVITED"
    LINKED = "LINKED"


@dataclass(frozen=True, slots=True)
class PortalInvitation:
    """A new invite: the secret appears here once and is never stored (R1)."""

    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class PatientPortalStatus:
    """R14: what staff see. Never the account's email or name."""

    status: PortalStatus
    method: LinkMethod | None = None
    linked_at: datetime | None = None
    invite_expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class InviteSummary:
    """R2: who the invite is for, as the patient sees it before accepting."""

    clinic_name: str
    patient_first_name: str
    patient_code: str


@dataclass(frozen=True, slots=True)
class LinkedRecord:
    link_id: UUID
    clinic_id: UUID
    clinic_name: str
    patient_first_name: str
    patient_code: str
    method: LinkMethod
    linked_at: datetime


def first_name(patient: Patient) -> str:
    return patient.full_name.split()[0]


def _require_patient(
    tenant: TenantRepositories, clinic_id: UUID, patient_id: UUID, *, for_update: bool = False
) -> Patient:
    patient = tenant.patients.get(patient_id, for_update=for_update)
    if patient is None:
        logger.info(
            "tenancy.not_found",
            entity="patient",
            entity_id=str(patient_id),
            clinic_id=str(clinic_id),
        )
        raise NotFound("patient")
    return patient


def _patient_event(
    uow: UnitOfWork,
    ids: IdPort,
    info: RequestInfo,
    action: AuditAction,
    link: PatientAccountLink,
    now: datetime,
    **metadata: str,
) -> None:
    """An event by the signed-in patient about their link (actor ``PATIENT``, no user)."""
    uow.audit.record(
        AuditEvent.record(
            id=ids.new_id(),
            action=action,
            actor_type=ActorType.PATIENT,
            now=now,
            clinic_id=link.clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=link.patient_id,
            request_id=info.request_id,
            ip_hash=info.ip_hash,
            metadata={
                "link_id": str(link.id),
                "account_id": str(link.account_id),
                "method": link.method.value,
                **metadata,
            },
        )
    )


def _create_link(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    *,
    ids: IdPort,
    info: RequestInfo,
    patient_id: UUID,
    account_id: UUID,
    method: LinkMethod,
    created_by_user_id: UUID | None,
    now: datetime,
) -> PatientAccountLink:
    """R4: lock the record, refuse a second link either way, add the link and audit it."""
    tenant.patients.get(patient_id, for_update=True)
    try:
        check_can_link(
            record_link=tenant.portal_links.active_for_patient(patient_id),
            account_link=tenant.portal_links.active_for_account(account_id),
        )
        link = PatientAccountLink.create(
            id=ids.new_id(),
            clinic_id=tenant.clinic_id,
            patient_id=patient_id,
            account_id=account_id,
            method=method,
            created_by_user_id=created_by_user_id,
            now=now,
        )
        tenant.portal_links.add(link)
    except AlreadyLinked:
        logger.info("portal.link_refused", reason=AlreadyLinked.code)
        raise
    _patient_event(uow, ids, info, AuditAction.PATIENT_PORTAL_LINKED, link, now)
    return link


def link_for_booking(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    *,
    ids: IdPort,
    info: RequestInfo,
    patient_id: UUID,
    account_id: UUID,
    staff: Actor | None,
    now: datetime,
) -> PatientAccountLink | None:
    """M6b-P5 (FR-PRT-06 a, spec R34, R42): link the account to the record an accepted request
    was booked for, in the caller's transaction. Nothing to do if they are already linked; a
    second link either way is ``PRT_ALREADY_LINKED``. ``staff`` is the accepting member (actor
    STAFF), or None when the patient takes a proposal (actor PATIENT)."""
    current = tenant.portal_links.active_for_account(account_id)
    if current is not None and current.patient_id == patient_id:
        return None
    if staff is None:
        return _create_link(
            uow,
            tenant,
            ids=ids,
            info=info,
            patient_id=patient_id,
            account_id=account_id,
            method=LinkMethod.BOOKING,
            created_by_user_id=None,
            now=now,
        )
    tenant.patients.get(patient_id, for_update=True)
    try:
        check_can_link(
            record_link=tenant.portal_links.active_for_patient(patient_id), account_link=current
        )
        link = PatientAccountLink.create(
            id=ids.new_id(),
            clinic_id=tenant.clinic_id,
            patient_id=patient_id,
            account_id=account_id,
            method=LinkMethod.BOOKING,
            created_by_user_id=staff.user_id,
            now=now,
        )
        tenant.portal_links.add(link)
    except AlreadyLinked:
        logger.info("portal.link_refused", reason=AlreadyLinked.code)
        raise
    record_event(
        uow,
        event_id=ids.new_id(),
        action=AuditAction.PATIENT_PORTAL_LINKED,
        actor=staff,
        now=now,
        clinic_id=tenant.clinic_id,
        entity_type=ENTITY_TYPE,
        entity_id=patient_id,
        metadata={
            "link_id": str(link.id),
            "account_id": str(account_id),
            "method": LinkMethod.BOOKING.value,
        },
    )
    return link


def _linked_record(link: PatientAccountLink, clinic_name: str, patient: Patient) -> LinkedRecord:
    return LinkedRecord(
        link_id=link.id,
        clinic_id=link.clinic_id,
        clinic_name=clinic_name,
        patient_first_name=first_name(patient),
        patient_code=patient.code,
        method=link.method,
        linked_at=link.created_at,
    )


# --- Staff ---------------------------------------------------------------------------------------


class _Staff:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids


class InviteToPortal(_Staff):
    """``POST /patients/{id}/portal-invite`` (R1, decision 2A)."""

    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: InviteSecrets
    ) -> None:
        super().__init__(uow=uow, clock=clock, ids=ids)
        self._secrets = secrets

    def execute(self, ctx: RequestContext, patient_id: UUID) -> PortalInvitation:
        now = self._clock.now()
        token = self._secrets.generate()
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            _require_patient(tenant, ctx.clinic_id, patient_id, for_update=True)
            check_can_link(
                record_link=tenant.portal_links.active_for_patient(patient_id), account_link=None
            )
            old = tenant.portal_invites.pending_for_patient(patient_id, for_update=True)
            if old is not None and old.supersede(now):
                tenant.portal_invites.update(old)
            invite = PatientPortalInvite.create(
                id=self._ids.new_id(),
                clinic_id=ctx.clinic_id,
                patient_id=patient_id,
                token_hash=self._secrets.digest(token),
                created_by=ctx.user_id,
                now=now,
            )
            tenant.portal_invites.add(invite)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.PATIENT_PORTAL_INVITED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=patient_id,
                metadata={
                    "invite_id": str(invite.id),
                    "expires_at": invite.expires_at.isoformat(),
                    **({"superseded_id": str(old.id)} if old is not None else {}),
                },
            )
            uow.commit()
        logger.info("portal.invite_created", invite_id=str(invite.id), patient_id=str(patient_id))
        return PortalInvitation(token, invite.expires_at)


class GetPortalStatus(_Staff):
    """``GET /patients/{id}/portal`` (R14)."""

    def execute(self, ctx: RequestContext, patient_id: UUID) -> PatientPortalStatus:
        now = self._clock.now()
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            _require_patient(tenant, ctx.clinic_id, patient_id)
            link = tenant.portal_links.active_for_patient(patient_id)
            if link is not None:
                return PatientPortalStatus(
                    PortalStatus.LINKED, method=link.method, linked_at=link.created_at
                )
            invite = tenant.portal_invites.pending_for_patient(patient_id)
        if invite is not None and invite.is_usable(now):
            return PatientPortalStatus(PortalStatus.INVITED, invite_expires_at=invite.expires_at)
        return PatientPortalStatus(PortalStatus.NOT_LINKED)


class UnlinkPatient(_Staff):
    """``DELETE /patients/{id}/portal-link`` (R8): staff end the record's link."""

    def execute(self, ctx: RequestContext, patient_id: UUID) -> None:
        now = self._clock.now()
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            _require_patient(tenant, ctx.clinic_id, patient_id)
            link = tenant.portal_links.active_for_patient(patient_id, for_update=True)
            if link is None:
                raise NotFound("portal link")
            link.revoke(RevokedBy.STAFF, now)
            tenant.portal_links.update(link)
            # M6b-P3 (R39): an ended link keeps no medicine-reminder choices.
            tenant.reminder_prefs.delete_for_link(link.account_id, patient_id)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.PATIENT_PORTAL_UNLINKED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=patient_id,
                metadata={
                    "link_id": str(link.id),
                    "account_id": str(link.account_id),
                    "method": link.method.value,
                    "by": RevokedBy.STAFF.value,
                },
            )
            uow.commit()
        logger.info("portal.unlinked", link_id=str(link.id), by=RevokedBy.STAFF.value)


# --- Patients ------------------------------------------------------------------------------------


class _Invites:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: InviteSecrets
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def _invite(
        self, uow: UnitOfWork, token: str, *, for_update: bool
    ) -> tuple[TenantRepositories, PatientPortalInvite, str]:
        """The usable invite, its clinic's repositories and name; else ``PRT_INVITE_INVALID``."""
        digest = self._secrets.digest(token) if 0 < len(token) <= MAX_TOKEN_LENGTH else None
        clinic_id = uow.portal_lookup.invite_clinic(digest) if digest else None
        clinic = uow.clinics.get(clinic_id) if clinic_id else None
        if digest is None or clinic is None or clinic.status is ClinicStatus.SUSPENDED:
            logger.info("portal.invite_invalid")
            raise PortalInviteInvalid()
        tenant = uow.tenant(clinic.id)
        invite = tenant.portal_invites.get_by_digest(digest, for_update=for_update)
        if invite is None or not invite.is_usable(self._clock.now()):
            logger.info("portal.invite_invalid", invite_id=str(invite.id) if invite else None)
            raise PortalInviteInvalid()
        return tenant, invite, clinic.name


class DescribePortalInvite(_Invites):
    """``GET /portal/invites/{token}`` (R2)."""

    def execute(self, principal: PatientPrincipal, token: str) -> InviteSummary:
        with self._uow as uow:
            tenant, invite, clinic_name = self._invite(uow, token, for_update=False)
            patient = _require_patient(tenant, tenant.clinic_id, invite.patient_id)
        return InviteSummary(clinic_name, first_name(patient), patient.code)


class AcceptPortalInvite(_Invites):
    """``POST /portal/invites/{token}/accept`` (R3, R4): one transaction, the invite locked."""

    def execute(self, principal: PatientPrincipal, token: str, info: RequestInfo) -> LinkedRecord:
        now = self._clock.now()
        with self._uow as uow:
            tenant, invite, clinic_name = self._invite(uow, token, for_update=True)
            link = _create_link(
                uow,
                tenant,
                ids=self._ids,
                info=info,
                patient_id=invite.patient_id,
                account_id=principal.account_id,
                method=LinkMethod.INVITE,
                created_by_user_id=invite.created_by,
                now=now,
            )
            invite.use(principal.account_id, now)
            tenant.portal_invites.update(invite)
            patient = _require_patient(tenant, tenant.clinic_id, invite.patient_id)
            uow.commit()
        logger.info("portal.linked", link_id=str(link.id), method=link.method.value)
        return _linked_record(link, clinic_name, patient)


class LinkByPrescription:
    """``POST /portal/links/prescription`` (R5, R6): a verified account and the page's check."""

    def __init__(self, *, clock: ClockPort, ids: IdPort, proof: ProveWithLink) -> None:
        self._clock = clock
        self._ids = ids
        self._proof = proof

    def execute(
        self, principal: PatientPrincipal, token: str, last4: str, info: RequestInfo
    ) -> LinkedRecord:
        if not principal.account.is_email_verified:
            logger.info("portal.link_refused", reason=UnverifiedAccount.code)
            raise UnverifiedAccount()

        def link_it(
            uow: UnitOfWork, tenant: TenantRepositories, rx_link: PatientLink
        ) -> LinkedRecord:
            clinic = uow.clinics.get(rx_link.clinic_id)
            assert clinic is not None
            link = _create_link(
                uow,
                tenant,
                ids=self._ids,
                info=info,
                patient_id=rx_link.patient_id,
                account_id=principal.account_id,
                method=LinkMethod.RX_LINK,
                created_by_user_id=None,
                now=self._clock.now(),
            )
            patient = _require_patient(tenant, tenant.clinic_id, rx_link.patient_id)
            return _linked_record(link, clinic.name, patient)

        record = self._proof.execute(token, last4, info, link_it)
        logger.info("portal.linked", link_id=str(record.link_id), method=record.method.value)
        return record


class UnlinkPortal:
    """``DELETE /portal/links/{link_id}`` (R8): the patient ends one of their links."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, principal: PatientPrincipal, link_id: UUID, info: RequestInfo) -> datetime:
        now = self._clock.now()
        with self._uow as uow:
            entry = PortalScope.read(uow, principal.account_id).link(link_id)
            link = entry.tenant.portal_links.get(link_id, for_update=True)
            if link is None or not link.revoke(RevokedBy.PATIENT, now):
                raise NotFound("portal link")  # revoked by staff a moment ago
            entry.tenant.portal_links.update(link)
            # M6b-P3 (R39): an ended link keeps no medicine-reminder choices.
            entry.tenant.reminder_prefs.delete_for_link(link.account_id, link.patient_id)
            _patient_event(
                uow,
                self._ids,
                info,
                AuditAction.PATIENT_PORTAL_UNLINKED,
                link,
                now,
                by=RevokedBy.PATIENT.value,
            )
            uow.commit()
        logger.info("portal.unlinked", link_id=str(link_id), by=RevokedBy.PATIENT.value)
        return now
