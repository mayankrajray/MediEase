"""Send one message at most once (spec R5-R8, AC4; decisions 1A, 4A, 5A).

Three short transactions and no lock held over the provider call:

1. Look up the message by its idempotency key. A settled row (sent or failed) ends the job; a row
   still marked as started means an earlier attempt died during the call, so the outcome is
   unknown and it is closed as ``FAILED`` (``MSG_OUTCOME_UNKNOWN``) and never sent again. Else
   the handler's *plan* re-reads consent and the facts at send time (R5) and either skips (no
   row; or the refused row is closed) or names the template and values. Values are checked
   against the template (R8), the phone number is encrypted, and the row is written as started
   and committed *before* the call (R6).
2. Call the provider.
3. Record the outcome: accepted (``SENT``, plus the handler's after-step in the same
   transaction), refused (retryable: not started again, so the retry calls once more; permanent
   or out of attempts: ``FAILED``) or unknown (``FAILED``, never retried).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.messaging.errors import (
    MSG_OUTCOME_UNKNOWN,
    ProviderOutcomeUnknown,
    ProviderRefused,
    TemplateParamsInvalid,
)
from mediease_api.domain.messaging.message import Message, MessageStatus, SourceType
from mediease_api.domain.patients.patient import Patient
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.messaging import (
    MessagingPort,
    OutboundTemplateMessage,
    PhoneCipherPort,
    TemplateCatalog,
)
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Send:
    """Send ``template_key`` to ``patient`` with these values (checked against the template)."""

    patient: Patient
    template_key: str
    variables: Mapping[str, str]
    source_type: SourceType
    source_id: UUID


@dataclass(frozen=True, slots=True)
class Skip:
    """Send nothing. ``reason`` is logged; ``code`` closes a refused row that no longer applies."""

    reason: str
    code: str


Plan = Callable[[UnitOfWork, TenantRepositories, datetime], Send | Skip]
AfterSent = Callable[[UnitOfWork, TenantRepositories, datetime], None]
Change = Callable[[Message, datetime], None]


class MessageSender:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        messaging: MessagingPort,
        templates: TemplateCatalog,
        phones: PhoneCipherPort,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._messaging = messaging
        self._templates = templates
        self._phones = phones

    def send(
        self, job: ClaimedJob, *, key: str, plan: Plan, after_sent: AfterSent | None = None
    ) -> None:
        if job.clinic_id is None:  # pragma: no cover - messaging kinds are never system kinds
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False)
        clinic_id = job.clinic_id
        prepared = self._prepare(job, clinic_id, key, plan, after_sent)
        if prepared is None:
            return
        message, outbound = prepared
        log = logger.bind(
            clinic_id=str(clinic_id),
            message_id=str(message.id),
            template=message.template_key,
            job_id=str(job.id),
        )
        try:
            accepted = self._messaging.send_template(outbound)
        except ProviderRefused as refusal:
            final = not refusal.retryable or job.attempts >= job.max_attempts
            code = refusal.code
            self._finish(
                clinic_id, key, (lambda m, now: m.fail(code, now)) if final else _refused(code)
            )
            log.warning("message.failed" if final else "message.refused", error_code=code)
            raise JobFailure(code, retryable=refusal.retryable) from None
        except Exception as error:
            # A timeout, a dropped connection or a bug: it may have been accepted (decision 4A).
            self._finish(clinic_id, key, lambda m, now: m.fail(MSG_OUTCOME_UNKNOWN, now))
            log.warning(
                "message.outcome_unknown",
                error_code=MSG_OUTCOME_UNKNOWN,
                error_type=type(error).__name__,
                expected=isinstance(error, ProviderOutcomeUnknown),
            )
            raise JobFailure(MSG_OUTCOME_UNKNOWN, retryable=False) from None
        provider_id = accepted.provider_message_id
        self._finish(
            clinic_id,
            key,
            lambda m, now: m.accepted(provider_message_id=provider_id, now=now),
            after_sent,
        )
        log.info("message.sent", channel=message.channel.value, provider=message.provider)

    def _prepare(
        self,
        job: ClaimedJob,
        clinic_id: UUID,
        key: str,
        plan: Plan,
        after_sent: AfterSent | None,
    ) -> tuple[Message, OutboundTemplateMessage] | None:
        with self._uow as uow:
            tenant = uow.tenant(clinic_id)
            now = self._clock.now()
            existing = tenant.messages.get_by_key(key, for_update=True)
            if existing is not None and existing.status is not MessageStatus.QUEUED:
                if existing.is_accepted and after_sent is not None:
                    after_sent(uow, tenant, now)
                    uow.commit()
                logger.info(
                    "message.already_settled",
                    message_id=str(existing.id),
                    status=existing.status.value,
                )
                return None
            if existing is not None and existing.outcome_unknown:
                existing.fail(MSG_OUTCOME_UNKNOWN, now)
                tenant.messages.update(existing)
                uow.commit()
                logger.warning(
                    "message.outcome_unknown",
                    message_id=str(existing.id),
                    error_code=MSG_OUTCOME_UNKNOWN,
                )
                raise JobFailure(MSG_OUTCOME_UNKNOWN, retryable=False)

            decision = plan(uow, tenant, now)
            if isinstance(decision, Skip):
                if existing is not None:
                    existing.fail(decision.code, now)
                    tenant.messages.update(existing)
                uow.commit()
                logger.info(
                    "message.skipped",
                    reason=decision.reason,
                    job_id=str(job.id),
                    job_kind=job.kind,
                )
                return None

            template = self._templates.get(decision.template_key)
            try:
                values = template.check(decision.variables)
            except TemplateParamsInvalid as error:
                logger.warning(
                    "message.params_invalid", template=error.template_key, reason=error.reason
                )
                raise JobFailure(error.code, retryable=False) from None
            patient = decision.patient
            ciphertext = self._phones.encrypt(patient.phone)
            stored = template.stored(values)
            if existing is not None:
                existing.restart(
                    variables=stored, to_phone_encrypted=ciphertext, job_id=job.id, now=now
                )
                tenant.messages.update(existing)
                message = existing
            else:
                message = Message.prepare(
                    id=self._ids.new_id(),
                    clinic_id=clinic_id,
                    patient_id=patient.id,
                    source_type=decision.source_type,
                    source_id=decision.source_id,
                    channel=self._messaging.channel,
                    provider=self._messaging.provider,
                    template_key=template.key,
                    template_version=template.version,
                    language=patient.language,
                    variables=stored,
                    to_phone_encrypted=ciphertext,
                    idempotency_key=key,
                    request_id=job.request_id,
                    job_id=job.id,
                    now=now,
                )
                tenant.messages.add(message)
            uow.commit()
        return message, OutboundTemplateMessage(
            idempotency_key=key,
            to=patient.phone,
            template=template,
            language=patient.language,
            variables=values,
            message_id=message.id,
        )

    def _finish(
        self, clinic_id: UUID, key: str, change: Change, after: AfterSent | None = None
    ) -> None:
        with self._uow as uow:
            tenant = uow.tenant(clinic_id)
            now = self._clock.now()
            message = tenant.messages.get_by_key(key, for_update=True)
            assert message is not None, "written before the call"
            change(message, now)
            tenant.messages.update(message)
            if after is not None:
                after(uow, tenant, now)
            uow.commit()


def _refused(code: str) -> Change:
    def change(message: Message, now: datetime) -> None:
        message.refused(code, now)

    return change
