"""Applying to join MediEase (M6c-P1; FR-ONB-01, 02, 07; spec clinic-onboarding R1-R20).

``SubmitApplication`` checks the form (R2-R6) and every certificate (R7), the limits (R16), then
stores the certificates privately and the application in one transaction with its audit row and
the confirmation email's job (R9). Nothing creates a clinic, user, membership or doctor (R15).

The certificates are written before the transaction: if a write fails, nothing is kept (R10);
if the transaction fails, the files just written are deleted. An earlier unconfirmed application
of the same owner email is replaced (R13); its files are deleted after the commit.

``ConfirmApplication`` spends the emailed link (R11, R12) and queues the "received" email.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.context import RequestInfo
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.jobs.job import APPLICATION_EMAIL_KIND, NewJob
from mediease_api.domain.onboarding.application import (
    ApplicationInput,
    ApplicationRateLimited,
    ClinicApplication,
    ConfirmInvalid,
    UploadFailed,
    ValidApplication,
    format_reference,
    validate,
)
from mediease_api.domain.onboarding.certificate import Certificate
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.onboarding import Removed
from mediease_api.ports.security import RefreshTokenSecrets
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY = "clinic_application"
# R16: a day of submissions per address, owner phone and owner email; confirming per minute.
PER_IP_PER_DAY = 5
PER_PHONE_PER_DAY = 3
PER_EMAIL_PER_DAY = 3
CONFIRMS_PER_MINUTE_PER_IP = 20
DAY = timedelta(days=1)


class EmailKind:
    CONFIRM = "confirm"
    RECEIVED = "received"


@dataclass(frozen=True, slots=True)
class Receipt:
    reference: str
    email_masked: str


def enqueue_application_email(
    uow: UnitOfWork,
    *,
    ids: IdPort,
    application: ClinicApplication,
    email: str,
    now: datetime,
    request_id: str | None,
) -> None:
    """In the caller's transaction (the outbox); the payload holds IDs only."""
    uow.jobs.enqueue(
        NewJob.create(
            id=ids.new_id(),
            kind=APPLICATION_EMAIL_KIND,
            now=now,
            payload={"application_id": str(application.id), "email": email},
            request_id=request_id,
            dedupe_key=f"application_email:{application.id}:{email}",
        )
    )


def _audit(
    uow: UnitOfWork,
    ids: IdPort,
    action: AuditAction,
    application: ClinicApplication,
    now: datetime,
    info: RequestInfo,
) -> None:
    uow.audit.record(
        AuditEvent.record(
            id=ids.new_id(),
            action=action,
            actor_type=ActorType.APPLICANT,
            now=now,
            entity_type=ENTITY,
            entity_id=application.id,
            request_id=info.request_id,
            ip_hash=info.ip_hash,
            metadata={
                "application_id": str(application.id),
                "kind": application.kind.value,
                "doctors": str(len(application.doctors)),
            },
        )
    )


class SubmitApplication:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, storage: BlobStoragePort
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._storage = storage

    def execute(
        self,
        data: ApplicationInput,
        files: Mapping[int, bytes],
        info: RequestInfo,
        *,
        honeypot: str = "",
    ) -> Receipt:
        valid = validate(data)
        application_id = self._ids.new_id()
        certificates = {
            d.position: Certificate.of(application_id, d.position, files.get(d.position, b""))
            for d in valid.doctors
        }
        now = self._clock.now()
        if honeypot.strip():
            # R8: a bot gets the same answer as a person, and nothing is kept.
            logger.info("application.rejected_input", reason="honeypot")
            fake = format_reference(now.year, secrets.randbelow(9000) + 1000)
            return Receipt(fake, valid.owner_email.masked())
        self._check_limits(valid, info, now)
        self._store(certificates, {d.position: files[d.position] for d in valid.doctors})
        try:
            application, removed = self._save(valid, application_id, certificates, info, now)
        except BaseException:
            self._delete(c.key for c in certificates.values())
            raise
        for gone in removed:
            self._delete(gone.certificate_keys)
        logger.info(
            "application.submitted",
            application_id=str(application.id),
            reference=application.reference,
            kind=application.kind.value,
            doctors=len(application.doctors),
            replaced=len(removed),
        )
        if application.possible_duplicate:
            logger.info(
                "application.duplicate_flagged",
                application_id=str(application.id),
                matches=len(application.duplicate_of),
            )
        return Receipt(application.reference, application.owner_email.masked())

    def _check_limits(self, valid: ValidApplication, info: RequestInfo, now: datetime) -> None:
        since = now - DAY
        with self._uow as uow:
            repo = uow.applications
            by_ip = repo.count_by_ip_since(info.ip_hash, since) if info.ip_hash else 0
            checks = (
                ("ip", by_ip >= PER_IP_PER_DAY),
                ("phone", repo.count_by_phone_since(valid.owner_phone, since) >= PER_PHONE_PER_DAY),
                ("email", repo.count_by_email_since(valid.owner_email, since) >= PER_EMAIL_PER_DAY),
            )
        for bucket, over in checks:
            if over:
                logger.info("application.rate_limited", bucket=bucket)
                raise ApplicationRateLimited(3600)

    def _store(self, certificates: Mapping[int, Certificate], files: Mapping[int, bytes]) -> None:
        written: list[str] = []
        try:
            for position, certificate in certificates.items():
                self._storage.put(
                    certificate.key, files[position], content_type=certificate.content_type
                )
                written.append(certificate.key)
        except Exception:
            logger.warning("application.upload_failed", written=len(written))
            self._delete(written)
            raise UploadFailed() from None

    def _save(
        self,
        valid: ValidApplication,
        application_id: UUID,
        certificates: dict[int, Certificate],
        info: RequestInfo,
        now: datetime,
    ) -> tuple[ClinicApplication, list[Removed]]:
        with self._uow as uow:
            repo = uow.applications
            removed = repo.remove_unconfirmed_for_email(valid.owner_email)
            registrations = [(d.council, d.registration_number) for d in valid.doctors]
            application = ClinicApplication.submit(
                id=application_id,
                reference=repo.next_reference(now.year),
                application=valid,
                certificates=certificates,
                doctor_ids=tuple(self._ids.new_id() for _ in valid.doctors),
                now=now,
                ip_hash=info.ip_hash,
                duplicate_of=tuple(repo.registration_matches(registrations)),
            )
            repo.add(application)
            _audit(uow, self._ids, AuditAction.APPLICATION_SUBMITTED, application, now, info)
            enqueue_application_email(
                uow,
                ids=self._ids,
                application=application,
                email=EmailKind.CONFIRM,
                now=now,
                request_id=info.request_id,
            )
            uow.commit()
        return application, removed

    def _delete(self, keys: Iterable[str]) -> None:
        for key in keys:
            try:
                self._storage.delete(key)
            except Exception:
                # The purge cannot find an orphan file later, so this is logged loudly.
                logger.error("application.file_not_deleted", key_kind="certificate")


class ConfirmApplication:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        secrets: RefreshTokenSecrets,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def execute(self, token: str, info: RequestInfo) -> str:
        now = self._clock.now()
        self._limit(info, now)
        digest = self._secrets.digest(token)
        with self._uow as uow:
            found = uow.applications.get_by_confirm_digest(digest)
            if found is None:
                logger.info("application.confirm_invalid", reason="unknown")
                raise ConfirmInvalid()
            try:
                confirmed = found.confirm(now=now)
            except ConfirmInvalid:
                logger.info("application.confirm_invalid", reason="expired")
                raise
            uow.applications.update(confirmed)
            _audit(uow, self._ids, AuditAction.APPLICATION_EMAIL_VERIFIED, confirmed, now, info)
            enqueue_application_email(
                uow,
                ids=self._ids,
                application=confirmed,
                email=EmailKind.RECEIVED,
                now=now,
                request_id=info.request_id,
            )
            uow.commit()
        logger.info(
            "application.email_verified",
            application_id=str(confirmed.id),
            reference=confirmed.reference,
        )
        return confirmed.reference

    def _limit(self, info: RequestInfo, now: datetime) -> None:
        window = now.replace(second=0, microsecond=0)
        with self._uow as uow:
            hits = uow.rate_limits.hit(f"app-confirm:{info.ip_hash or '-'}", window_start=window)
            uow.commit()
        if hits > CONFIRMS_PER_MINUTE_PER_IP:
            logger.info("application.rate_limited", bucket="confirm")
            raise ApplicationRateLimited(max(60 - now.second, 1))
