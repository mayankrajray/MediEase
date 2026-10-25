"""An application's emails and the deletion of unconfirmed ones (M6c-P1; spec R11-R14, R21).

``SendApplicationEmail`` (``send_application_email``, a system job): ``confirm`` mints the
link's secret at send time, as the account emails do (ADR-0016): the digest is stored and
committed first, then the email goes out with the value, so no usable secret is ever at rest and
a retry simply replaces the link. ``received`` is sent once the email is confirmed.

``PurgeApplications`` (``purge_applications``, hourly): applications never confirmed within 72
hours are deleted with their certificates.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from mediease_api.application.onboarding import email_templates
from mediease_api.application.onboarding.submit import EmailKind
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.onboarding.application import (
    UNCONFIRMED_RETENTION,
    ApplicationStatus,
)
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.email import EmailFailed, EmailMessage, EmailPort
from mediease_api.ports.onboarding import ApplicationSummary
from mediease_api.ports.security import RefreshTokenSecrets
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class SendApplicationEmail:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        secrets: RefreshTokenSecrets,
        email: EmailPort,
        public_base_url: str,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._secrets = secrets
        self._email = email
        self._base = public_base_url.rstrip("/")

    def __call__(self, job: ClaimedJob) -> None:
        try:
            application_id = UUID(str(job.payload["application_id"]))
            kind = str(job.payload["email"])
        except (KeyError, ValueError):
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False) from None
        if kind not in (EmailKind.CONFIRM, EmailKind.RECEIVED):
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False)
        message = self._prepare(application_id, kind)
        if message is None:
            return
        try:
            self._email.send(message)
        except EmailFailed as failure:
            logger.warning("email.failed", email=f"application_{kind}", reason=failure.reason)
            raise JobFailure(
                f"EMAIL_{failure.reason.upper()}", retryable=failure.retryable
            ) from None
        logger.info(
            "email.application_sent",
            email=kind,
            application_id=str(application_id),
            to=message.to.masked(),
        )

    def _prepare(self, application_id: UUID, kind: str) -> EmailMessage | None:
        with self._uow as uow:
            now = self._clock.now()
            application = uow.applications.get(application_id, for_update=True)
            if application is None:
                logger.info("email.skipped", email=f"application_{kind}", reason="gone")
                return None
            if kind == EmailKind.RECEIVED:
                if not application.is_confirmed:
                    return None
                rendered = email_templates.application_received(
                    application.owner_name, application.clinic_name, application.reference
                )
            else:
                if (
                    application.is_confirmed
                    or application.status is not ApplicationStatus.PENDING
                    or now >= application.confirm_expires_at
                ):
                    logger.info("email.skipped", email="application_confirm", reason="not_due")
                    return None
                value = self._secrets.generate()
                uow.applications.update(
                    application.with_confirm_digest(self._secrets.digest(value), now=now)
                )
                uow.commit()
                rendered = email_templates.confirm_application(
                    application.owner_name,
                    application.clinic_name,
                    application.reference,
                    f"{self._base}/apply/confirm/{value}",
                )
        return EmailMessage(
            to=application.owner_email,
            subject=rendered.subject,
            text=rendered.text,
            html=rendered.html,
        )


class PurgeApplications:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, storage: BlobStoragePort) -> None:
        self._uow = uow
        self._clock = clock
        self._storage = storage

    def execute(self) -> int:
        cutoff = self._clock.now() - UNCONFIRMED_RETENTION
        with self._uow as uow:
            removed = uow.applications.remove_unconfirmed_before(cutoff)
            uow.commit()
        failed = 0
        for gone in removed:
            for key in gone.certificate_keys:
                try:
                    self._storage.delete(key)
                except Exception:
                    failed += 1
        if failed:
            logger.error("application.file_not_deleted", count=failed)
        logger.info("application.purged", count=len(removed))
        return len(removed)

    def __call__(self, job: ClaimedJob) -> None:
        self.execute()


class ListApplications:
    """R18: confirmed applications for ops, oldest first, summary only."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self) -> list[ApplicationSummary]:
        with self._uow as uow:
            return list(uow.applications.list_confirmed())
