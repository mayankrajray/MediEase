"""Provider webhooks: receive, process statuses, reconcile (M5-P3; spec R12, R13, R15; AC6).

Receive (in the request, decision 2A): rate limit by caller, verify the signature on the raw body
*before* parsing (R13, AC6: a bad one is refused and nothing is stored), store the redacted body
once (a redelivery is recognised by its hash) and enqueue its processing in the same transaction;
answer at once.

Process (a job): each status finds its message by our echoed ID or the provider's, through the
reviewed cross-clinic lookup, and then only through that clinic's tenant repository. Statuses only
move forward. A status with no message yet (the webhook can beat our own commit) makes the job
retry with the usual back-off; after the last attempt the event records ``WH_UNMATCHED``. M5-P5:
STOP replies are applied first (``opt_out.py``), and the stored payload loses the senders'
encrypted numbers once the event is processed.

Reconcile (hourly; R15 as rewritten for WhatsApp, which has no status lookup): re-enqueue stored
events that never processed, and report how many messages are still unconfirmed after a day.
"""

from __future__ import annotations

import hmac
import json
import re
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.context import RequestInfo
from mediease_api.application.messaging.opt_out import OptOutByReply
from mediease_api.domain.jobs.job import WEBHOOK_KIND, ClaimedJob, NewJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.messaging.errors import (
    MSG_OUTCOME_UNKNOWN,
    WH_STOP_UNMATCHED,
    WH_UNMATCHED,
    WebhookRateLimited,
    WebhookSignatureInvalid,
    WebhookVerifyFailed,
)
from mediease_api.domain.messaging.message import SourceType, StatusUpdate
from mediease_api.domain.messaging.webhook import WebhookEvent
from mediease_api.domain.prescriptions.prescription import LinkDelivery
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.messaging import WebhookParser, WebhookVerifier
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# Decision 5A: generous for Meta's bursts, a ceiling for anyone else.
PER_CALLER_PER_MINUTE = 600
_CHALLENGE = re.compile(r"[A-Za-z0-9_-]{1,200}")
# Reconciliation: an event this old and still unprocessed lost its job; at most this many a run.
STUCK_AFTER = timedelta(minutes=10)
RECONCILE_BATCH = 100
UNCONFIRMED_AFTER = timedelta(hours=24)


def webhook_dedupe_key(event_id: UUID, attempt: int = 0) -> str:
    return f"{WEBHOOK_KIND}:{event_id}" + (f":{attempt}" if attempt else "")


class VerifyWebhookSubscription:
    """R12: Meta's ``GET`` challenge; answers the challenge only for our verify token."""

    def __init__(self, *, verify_token: str) -> None:
        self._token = verify_token

    def execute(self, *, mode: str | None, token: str | None, challenge: str | None) -> str:
        ok = (
            bool(self._token)
            and mode == "subscribe"
            and token is not None
            and hmac.compare_digest(token.encode(), self._token.encode())
            and challenge is not None
            and _CHALLENGE.fullmatch(challenge) is not None
        )
        if not ok:
            logger.warning("webhook.verify_failed", mode=(mode or "")[:20])
            raise WebhookVerifyFailed()
        assert challenge is not None
        logger.info("webhook.verified")
        return challenge


class ReceiveWebhook:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        verifier: WebhookVerifier,
        parser: WebhookParser,
        provider: str,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._verifier = verifier
        self._parser = parser
        self._provider = provider

    def execute(self, body: bytes, signature: str | None, info: RequestInfo) -> bool:
        """True if the body was new and stored; False for a redelivery or an unreadable body."""
        now = self._clock.now()
        self._rate_limit(info, now)
        if not self._verifier.verify(body, signature):
            logger.warning(
                "webhook.signature_invalid", provider=self._provider, signed=bool(signature)
            )
            raise WebhookSignatureInvalid()
        try:
            document = json.loads(body)
        except ValueError:
            document = None
        if not isinstance(document, dict):
            logger.warning("webhook.unreadable", provider=self._provider)
            return False
        event = WebhookEvent.receive(
            id=self._ids.new_id(),
            provider=self._provider,
            event_key=self._parser.event_key(body),
            payload=self._parser.redact(document),
            now=now,
        )
        with self._uow as uow:
            stored = uow.webhook_events.add(event)
            if stored:
                uow.jobs.enqueue(_process_job(self._ids, event.id, now, info.request_id))
            uow.commit()
        logger.info(
            "webhook.received",
            provider=self._provider,
            event_id=str(event.id) if stored else None,
            duplicate=not stored,
            statuses=len(self._parser.statuses(event.payload)),
            opt_outs=len(self._parser.opt_outs(event.payload)),
        )
        return stored

    def _rate_limit(self, info: RequestInfo, now: datetime) -> None:
        window = now.replace(second=0, microsecond=0)
        with self._uow as uow:
            hits = uow.rate_limits.hit(f"webhook:{info.ip_hash or '-'}", window_start=window)
            uow.commit()
        if hits > PER_CALLER_PER_MINUTE:
            logger.info("webhook.rate_limited", provider=self._provider)
            raise WebhookRateLimited(60 - now.second)


def _process_job(
    ids: IdPort, event_id: UUID, now: datetime, request_id: str | None, attempt: int = 0
) -> NewJob:
    return NewJob.create(
        id=ids.new_id(),
        kind=WEBHOOK_KIND,
        now=now,
        payload={"event_id": str(event_id)},
        request_id=request_id,
        dedupe_key=webhook_dedupe_key(event_id, attempt),
    )


class ProcessWebhookEvent:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        parser: WebhookParser,
        opt_outs: OptOutByReply,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._parser = parser
        self._opt_outs = opt_outs

    def __call__(self, job: ClaimedJob) -> None:
        event_id = UUID(str(job.payload["event_id"]))
        with self._uow as uow:
            event = uow.webhook_events.get(event_id, for_update=True)
            if event is None or event.processed_at is not None:
                return
            now = self._clock.now()
            # M5-P5: STOP replies first, so a retry for an unmatched status never delays an
            # opt-out; repeating them on a retry changes nothing (idempotent, deduplicated jobs).
            stops = self._parser.opt_outs(event.payload)
            stops_unmatched = sum(
                0 if self._opt_outs.apply(uow, s, request_id=job.request_id, now=now) else 1
                for s in stops
            )
            updates = self._parser.statuses(event.payload)
            unmatched = sum(0 if self._apply(uow, u) else 1 for u in updates)
            if unmatched and job.attempts < job.max_attempts:
                uow.commit()  # the statuses that matched are kept; the retry repeats harmlessly
                logger.info("webhook.unmatched", event_id=str(event_id), unmatched=unmatched)
                raise JobFailure(WH_UNMATCHED)
            event.processed_at = now
            if stops:
                event.payload = self._parser.forget_senders(event.payload)
            if unmatched:
                event.error_code = WH_UNMATCHED
            else:
                event.error_code = WH_STOP_UNMATCHED if stops_unmatched else None
            uow.webhook_events.update(event)
            uow.commit()
        logger.info(
            "webhook.processed",
            event_id=str(event_id),
            statuses=len(updates),
            unmatched=unmatched,
            opt_outs=len(stops),
            opt_outs_unmatched=stops_unmatched,
        )

    def _apply(self, uow: UnitOfWork, update: StatusUpdate) -> bool:
        found = uow.message_lookup.find(
            message_id=update.message_id, provider_message_id=update.provider_message_id
        )
        if found is None:
            return False
        clinic_id, message_id = found
        tenant = uow.tenant(clinic_id)
        message = tenant.messages.get(message_id, for_update=True)
        if message is None:  # pragma: no cover - the lookup just found it
            return False
        before, was_accepted = message.status, message.is_accepted
        was_unknown = message.error_code == MSG_OUTCOME_UNKNOWN
        now = self._clock.now()
        if not message.apply_status(update, now):
            return True
        tenant.messages.update(message)
        if not was_accepted and message.is_accepted:
            logger.info(
                "message.acceptance_learned",
                message_id=str(message.id),
                was_outcome_unknown=was_unknown,
            )
            if message.source_type is SourceType.PRESCRIPTION:
                rx = tenant.prescriptions.get(message.source_id, for_update=True)
                if rx is not None and rx.link_delivery is LinkDelivery.PENDING:
                    rx.link_sent(now)
                    tenant.prescriptions.update(rx)
        logger.info(
            "message.status_changed",
            clinic_id=str(clinic_id),
            message_id=str(message.id),
            from_status=before.value,
            to_status=message.status.value,
            error_code=message.error_code,
        )
        return True


class ReconcileMessages:
    """R15 for WhatsApp: no status lookup exists, so repair our side and report."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def __call__(self, job: ClaimedJob) -> None:
        now = self._clock.now()
        requeued = 0
        with self._uow as uow:
            stuck = uow.webhook_events.list_unprocessed(
                received_before=now - STUCK_AFTER, limit=RECONCILE_BATCH
            )
            for event_id in stuck:
                # A per-hour key: a dead processing job does not block this one, a live one does.
                attempt = int(now.timestamp()) // 3600
                if uow.jobs.enqueue(
                    _process_job(self._ids, event_id, now, job.request_id, attempt)
                ):
                    requeued += 1
            unconfirmed = uow.message_lookup.count_unconfirmed(sent_before=now - UNCONFIRMED_AFTER)
            uow.commit()
        log = logger.warning if unconfirmed else logger.info
        log("messages.reconciled", webhook_events_requeued=requeued, unconfirmed_24h=unconfirmed)
