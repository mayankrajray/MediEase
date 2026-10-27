"""Verifying an identified prescription against the database and the uploader's access (M7b-P9).

Spec prescription-uploads R10-R16; FR-UPL-04; ADR-0023 §4.

- **Own record (R10).** The ID is looked up only inside the account's ``PortalScope``, accepting
  an issued or superseded version of a linked record. No other lookup happens on this path.
- **Anyone else (R11, R12).** Not the account's, whether or not it exists: ``NEEDS_CHALLENGE``,
  and nothing about it is said. ``AnswerChallenge`` then finds the clinic through the reviewed
  IDs-only lookup and checks the last 4 digits against the chain's patient link with its own
  rule and lockout (``check_last4``, FR-RX-08). Every failure, real or not, counts on the upload
  and answers the same way.
- **Superseded (R15).** Verified as the exact version; a current one is selected, an older one
  waits for ``ChooseVersion``. Nothing is substituted.

The views say only what the uploader may now see: nothing about the prescription before it is
verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.context import RequestInfo
from mediease_api.application.links.use_cases import check_last4
from mediease_api.application.portal.records import version_in_scope
from mediease_api.application.portal.scope import PortalScope
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.links.errors import ChallengeFailed as LinkChallengeFailed
from mediease_api.domain.links.errors import LinkLocked
from mediease_api.domain.links.link import PatientLink
from mediease_api.domain.portal.link import UnverifiedAccount
from mediease_api.domain.prescriptions.prescription import (
    Prescription,
    PrescriptionStatus,
    latest_issued,
)
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.uploads.errors import (
    ChallengeFailed,
    NotAwaitingChallenge,
    NotVerified,
    UploadRateLimited,
)
from mediease_api.domain.uploads.upload import (
    Access,
    Choice,
    PrescriptionUpload,
    Rejection,
    UploadState,
)
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "prescription_upload"
UPLOADS_PER_HOUR_PER_ACCOUNT = 10
UPLOADS_PER_HOUR_PER_CALLER = 30
CHALLENGES_PER_HOUR_PER_ACCOUNT = 20


# --- Views ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UploadVerification:
    access: Access
    clinic_name: str
    doctor_name: str
    version: int
    issued_at: datetime
    superseded: bool
    latest_version: int | None
    latest_issued_at: datetime | None
    selected: Choice | None
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class UploadView:
    id: UUID
    state: UploadState
    source: str
    rejection_code: Rejection | None
    attempts_left: int | None
    created_at: datetime
    verification: UploadVerification | None = None


def _chain_of(tenant: TenantRepositories, rx: Prescription) -> list[Prescription]:
    return list(tenant.prescriptions.list_for_visit(rx.visit_id))


def view_of(uow: UnitOfWork, upload: PrescriptionUpload) -> UploadView:
    """What the uploader may see now (R11: nothing about the prescription before verification)."""
    verification = None
    if upload.state is UploadState.VERIFIED:
        assert upload.clinic_id and upload.prescription_id and upload.access and upload.expires_at
        clinic = uow.clinics.get(upload.clinic_id)
        tenant = uow.tenant(upload.clinic_id)
        rx = tenant.prescriptions.get(upload.prescription_id)
        assert clinic is not None and rx is not None and rx.issued_at and rx.doctor_snapshot
        latest = latest_issued(_chain_of(tenant, rx))
        superseded = rx.status is PrescriptionStatus.SUPERSEDED and latest is not None
        selected: Choice | None = None
        if upload.selected_id == rx.id:
            selected = Choice.UPLOADED
        elif latest is not None and upload.selected_id == latest.id:
            selected = Choice.LATEST
        verification = UploadVerification(
            access=upload.access,
            clinic_name=clinic.name,
            doctor_name=rx.doctor_snapshot.display_name,
            version=rx.version,
            issued_at=rx.issued_at,
            superseded=superseded,
            latest_version=latest.version if superseded and latest else None,
            latest_issued_at=latest.issued_at if superseded and latest else None,
            selected=selected,
            expires_at=upload.expires_at,
        )
    return UploadView(
        id=upload.id,
        state=upload.state,
        source=upload.source.value,
        rejection_code=upload.rejection_code,
        attempts_left=(
            upload.attempts_left if upload.state is UploadState.NEEDS_CHALLENGE else None
        ),
        created_at=upload.created_at,
        verification=verification,
    )


# --- Shared steps --------------------------------------------------------------------------------


def audit_upload(
    uow: UnitOfWork,
    ids: IdPort,
    action: AuditAction,
    upload: PrescriptionUpload,
    now: datetime,
    *,
    info: RequestInfo | None = None,
    clinic_id: UUID | None = None,
    **metadata: str,
) -> None:
    uow.audit.record(
        AuditEvent.record(
            id=ids.new_id(),
            action=action,
            actor_type=ActorType.PATIENT,
            now=now,
            clinic_id=clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=upload.id,
            request_id=info.request_id if info else None,
            ip_hash=info.ip_hash if info else None,
            metadata={"account_id": str(upload.account_id), **metadata},
        )
    )


def resolve_identified(
    uow: UnitOfWork,
    ids: IdPort,
    upload: PrescriptionUpload,
    candidate: UUID,
    now: datetime,
    info: RequestInfo | None = None,
) -> None:
    """R10, R11: verified as one of the account's own records, else the last-4 check."""
    found = version_in_scope(PortalScope.read(uow, upload.account_id), candidate)
    if found is None:
        upload.needs_challenge(candidate, now)
        logger.info("upload.needs_challenge", upload_id=str(upload.id))
        return
    entry, rx = found
    upload.verify(
        access=Access.OWN,
        clinic_id=entry.clinic.id,
        prescription_id=rx.id,
        current=rx.status is PrescriptionStatus.ISSUED,
        now=now,
    )
    audit_upload(
        uow,
        ids,
        AuditAction.PRESCRIPTION_UPLOAD_VERIFIED,
        upload,
        now,
        info=info,
        clinic_id=entry.clinic.id,
        prescription_id=str(rx.id),
        access=Access.OWN.value,
    )
    logger.info("upload.verified", upload_id=str(upload.id), access=Access.OWN.value)


def limit(
    uow: UnitOfWork, clock: ClockPort, info: RequestInfo, account_id: UUID, kind: str
) -> None:
    """R2: hourly windows per account and per caller, committed before the work."""
    now = clock.now()
    window = now.replace(minute=0, second=0, microsecond=0)
    retry = max(int((window + timedelta(hours=1) - now).total_seconds()), 1)
    per_account = (
        CHALLENGES_PER_HOUR_PER_ACCOUNT if kind == "challenge" else UPLOADS_PER_HOUR_PER_ACCOUNT
    )
    with uow as open_uow:
        by_account = open_uow.rate_limits.hit(f"upl-{kind}:{account_id}", window_start=window)
        by_caller = open_uow.rate_limits.hit(f"upl-ip:{info.ip_hash or '-'}", window_start=window)
        open_uow.commit()
    if by_account > per_account or by_caller > UPLOADS_PER_HOUR_PER_CALLER:
        logger.info("upload.rate_limited", kind=kind, retry_after=retry)
        raise UploadRateLimited(retry)


def own_upload(
    uow: UnitOfWork, principal: PatientPrincipal, upload_id: UUID, *, for_update: bool = False
) -> PrescriptionUpload:
    upload = uow.prescription_uploads.get_for_account(
        upload_id, principal.account_id, for_update=for_update
    )
    if upload is None:
        logger.info("portal.not_found", entity="upload", entity_id=str(upload_id))
        raise NotFound("upload")
    return upload


# --- Use cases -----------------------------------------------------------------------------------


class GetUpload:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, principal: PatientPrincipal, upload_id: UUID) -> UploadView:
        with self._uow as uow:
            return view_of(uow, own_upload(uow, principal, upload_id))


class AnswerChallenge:
    """R11, R12: a representative's last-4 answer for a prescription not in their account."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, principal: PatientPrincipal, upload_id: UUID, last4: str, info: RequestInfo
    ) -> UploadView:
        if not principal.account.is_email_verified:
            raise UnverifiedAccount()
        limit(self._uow, self._clock, info, principal.account_id, "challenge")
        passed = False
        with self._uow as uow:
            upload = own_upload(uow, principal, upload_id, for_update=True)
            if upload.state is not UploadState.NEEDS_CHALLENGE:
                raise NotAwaitingChallenge()
            assert upload.candidate_id is not None
            candidate = upload.candidate_id
            now = self._clock.now()
            target = self._target(uow, candidate)
            if target is not None:
                tenant, rx, link = target
                try:
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
                except (LinkChallengeFailed, LinkLocked):
                    pass  # counted on the link (and committed); counted on the upload below
                else:
                    passed = True
                    upload.verify(
                        access=Access.REPRESENTATIVE,
                        clinic_id=tenant.clinic_id,
                        prescription_id=rx.id,
                        current=rx.status is PrescriptionStatus.ISSUED,
                        now=now,
                    )
                    uow.prescription_uploads.update(upload)
                    audit_upload(
                        uow,
                        self._ids,
                        AuditAction.PRESCRIPTION_UPLOAD_VERIFIED,
                        upload,
                        now,
                        info=info,
                        clinic_id=tenant.clinic_id,
                        prescription_id=str(rx.id),
                        access=Access.REPRESENTATIVE.value,
                    )
                    uow.commit()
                    logger.info(
                        "upload.verified",
                        upload_id=str(upload.id),
                        access=Access.REPRESENTATIVE.value,
                    )
                    return view_of(uow, upload)
        assert not passed
        return self._failed(principal, upload_id, info)

    def _target(
        self, uow: UnitOfWork, candidate: UUID
    ) -> tuple[TenantRepositories, Prescription, PatientLink] | None:
        """The chain's usable patient link, or ``None`` (unknown, draft, suspended, no link)."""
        clinic_id = uow.prescription_lookup.clinic_of(candidate)
        if clinic_id is None:
            return None
        clinic = uow.clinics.get(clinic_id)
        if clinic is None or clinic.status is ClinicStatus.SUSPENDED:
            return None
        tenant = uow.tenant(clinic_id)
        rx = tenant.prescriptions.get(candidate)
        if rx is None or rx.status not in (
            PrescriptionStatus.ISSUED,
            PrescriptionStatus.SUPERSEDED,
        ):
            return None
        first = next((p for p in _chain_of(tenant, rx) if p.version == 1), None)
        if first is None:
            return None
        link = tenant.patient_links.active_for_prescription(first.id, for_update=True)
        if link is None:
            return None
        return tenant, rx, link

    def _failed(
        self, principal: PatientPrincipal, upload_id: UUID, info: RequestInfo
    ) -> UploadView:
        """R12: one answer for every failure, from the upload's own count."""
        with self._uow as uow:
            upload = own_upload(uow, principal, upload_id, for_update=True)
            if upload.state is not UploadState.NEEDS_CHALLENGE:
                raise NotAwaitingChallenge()
            now = self._clock.now()
            left = upload.challenge_failed(now)
            uow.prescription_uploads.update(upload)
            audit_upload(
                uow,
                self._ids,
                AuditAction.PRESCRIPTION_UPLOAD_CHALLENGE_FAILED,
                upload,
                now,
                info=info,
                attempt=str(upload.failed_challenges),
            )
            uow.commit()
        logger.info("upload.challenge_failed", upload_id=str(upload_id), attempts_left=left)
        if left == 0:
            logger.info("upload.rejected", upload_id=str(upload_id), code=Rejection.LOCKED.value)
        raise ChallengeFailed(left)


class ChooseVersion:
    """R15: the uploaded (historical) version or the latest, chosen by the user."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, principal: PatientPrincipal, upload_id: UUID, choice: Choice) -> UploadView:
        with self._uow as uow:
            upload = own_upload(uow, principal, upload_id, for_update=True)
            if (
                upload.state is not UploadState.VERIFIED
                or upload.clinic_id is None
                or upload.prescription_id is None
            ):
                raise NotVerified()
            tenant = uow.tenant(upload.clinic_id)
            rx = tenant.prescriptions.get(upload.prescription_id)
            assert rx is not None  # issued rows are never deleted
            latest = latest_issued(_chain_of(tenant, rx)) or rx
            upload.choose(choice, latest_id=latest.id, now=self._clock.now())
            uow.prescription_uploads.update(upload)
            uow.commit()
            logger.info("upload.version_chosen", upload_id=str(upload.id), choice=choice.value)
            return view_of(uow, upload)


class WithdrawUpload:
    """R17: the user deletes the upload: its file (if still there) and any grant."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, storage: BlobStoragePort) -> None:
        self._uow = uow
        self._clock = clock
        self._storage = storage

    def execute(self, principal: PatientPrincipal, upload_id: UUID) -> None:
        with self._uow as uow:
            upload = own_upload(uow, principal, upload_id, for_update=True)
            key = upload.quarantine_key
            if key is not None:
                self._storage.delete(key)  # first: a failure here keeps the row pointing at it
            upload.withdraw(self._clock.now())
            uow.prescription_uploads.update(upload)
            uow.commit()
        logger.info("upload.withdrawn", upload_id=str(upload_id), file_deleted=key is not None)
