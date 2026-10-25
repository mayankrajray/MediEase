"""The email of a booking answer (M6b-P6; portal spec R63).

One job per notice (``patient_email:<account>:<event_key>``), enqueued with it. At send time the
account is read again: still verified, the email switch still on. The email names the clinic and
the outcome and links to the portal; never the reason, the staff note, the doctor or a phone.
"""

from __future__ import annotations

import html
from uuid import UUID

import structlog

from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.portal.notifications import (
    BOOKING_KINDS,
    Names,
    PatientChannel,
    PatientNotificationKind,
    booking_email,
)
from mediease_api.ports.email import EmailFailed, EmailMessage, EmailPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class SendPatientEmail:
    def __init__(self, *, uow: UnitOfWork, email: EmailPort, public_base_url: str) -> None:
        self._uow = uow
        self._email = email
        self._base = public_base_url.rstrip("/")

    def __call__(self, job: ClaimedJob) -> None:
        try:
            account_id = UUID(str(job.payload["account_id"]))
            kind = PatientNotificationKind(str(job.payload["kind"]))
        except (KeyError, ValueError):
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False) from None
        if kind not in BOOKING_KINDS or job.clinic_id is None:
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False)
        message = self._prepare(account_id, kind, job.clinic_id)
        if message is None:
            return
        try:
            self._email.send(message)
        except EmailFailed as failure:
            logger.warning("email.failed", email=kind.value, reason=failure.reason)
            raise JobFailure(
                f"EMAIL_{failure.reason.upper()}", retryable=failure.retryable
            ) from None
        logger.info("email.patient_sent", email=kind.value, to=message.to.masked())

    def _prepare(
        self, account_id: UUID, kind: PatientNotificationKind, clinic_id: UUID
    ) -> EmailMessage | None:
        with self._uow as uow:
            account = uow.patient_accounts.get(account_id)
            clinic = uow.clinics.get(clinic_id)
            if account is None or clinic is None or not account.is_email_verified:
                logger.info("email.patient_skipped", email=kind.value, reason="unverified")
                return None
            if uow.patient_preferences.is_off(account_id, kind, PatientChannel.EMAIL):
                logger.info("email.patient_skipped", email=kind.value, reason="turned_off")
                return None
            words = booking_email(
                kind,
                Names(clinic.name, None, clinic.timezone),
                account.language,
                f"{self._base}/portal/appointments",
            )
        body = "".join(f"<p>{html.escape(line)}</p>" for line in words.text.splitlines() if line)
        return EmailMessage(to=account.email, subject=words.subject, text=words.text, html=body)
