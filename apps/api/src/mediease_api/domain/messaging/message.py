"""One outbound message (spec R6, R7; docs/DATA_MODEL.md ``messages``).

The row is written *before* the provider is called, with a unique ``idempotency_key``, and
``sending_started_at`` marks that a call may be under way. Afterwards it is ``SENT`` (accepted),
back to not-started (the provider refused, so a retry may call again) or ``FAILED``. A row found
still started at a retry means the previous attempt died mid-call: the outcome is unknown and it
is never sent again (decision 4A, at most once).

The phone number is stored encrypted (``to_phone_encrypted``, decision 1A) and variables are
stored as the template's ``stored`` form, without the signed link (decision 5A).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from mediease_api.domain.messaging.errors import MSG_OUTCOME_UNKNOWN, MSG_PROVIDER_REJECTED
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import InvalidTransition
from mediease_api.domain.shared.time import require_utc


class Channel(StrEnum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    CONSOLE = "CONSOLE"


class MessageStatus(StrEnum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"


ACCEPTED_STATUSES = frozenset({MessageStatus.SENT, MessageStatus.DELIVERED, MessageStatus.READ})
# Statuses only move forward (spec R13).
_RANK = {MessageStatus.SENT: 1, MessageStatus.DELIVERED: 2, MessageStatus.READ: 3}


@dataclass(frozen=True, slots=True)
class StatusUpdate:
    """One status from a provider's webhook, already mapped to our terms.

    ``message_id`` is our own ID echoed back by the provider (WhatsApp's
    ``biz_opaque_callback_data``); it finds the row even when the provider's ID was never saved.
    """

    provider_message_id: str
    message_id: UUID | None
    status: MessageStatus
    at: datetime
    error_code: str | None = None
    pricing_category: str | None = None


class SourceType(StrEnum):
    """What the message is about, so P6 can show it on the appointment or prescription."""

    APPOINTMENT = "APPOINTMENT"
    PRESCRIPTION = "PRESCRIPTION"


@dataclass(slots=True, repr=False)
class Message:
    id: UUID
    clinic_id: UUID
    patient_id: UUID
    source_type: SourceType
    source_id: UUID
    channel: Channel
    provider: str
    template_key: str
    template_version: int
    language: Language
    variables: Mapping[str, str]
    to_phone_encrypted: str
    idempotency_key: str
    status: MessageStatus
    error_code: str | None
    provider_message_id: str | None
    request_id: str | None
    job_id: UUID | None
    sending_started_at: datetime | None
    sent_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # M5-P3: from the provider's status webhooks.
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    pricing_category: str | None = None

    @classmethod
    def prepare(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        source_type: SourceType,
        source_id: UUID,
        channel: Channel,
        provider: str,
        template_key: str,
        template_version: int,
        language: Language,
        variables: Mapping[str, str],
        to_phone_encrypted: str,
        idempotency_key: str,
        request_id: str | None,
        job_id: UUID | None,
        now: datetime,
    ) -> Message:
        """A new row, marked as about to be sent (R6)."""
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            source_type=source_type,
            source_id=source_id,
            channel=channel,
            provider=provider,
            template_key=template_key,
            template_version=template_version,
            language=language,
            variables=MappingProxyType(dict(variables)),
            to_phone_encrypted=to_phone_encrypted,
            idempotency_key=idempotency_key,
            status=MessageStatus.QUEUED,
            error_code=None,
            provider_message_id=None,
            request_id=request_id,
            job_id=job_id,
            sending_started_at=now,
            sent_at=None,
            failed_at=None,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_accepted(self) -> bool:
        return self.status in ACCEPTED_STATUSES

    @property
    def outcome_unknown(self) -> bool:
        """Queued and started: a previous attempt may have reached the provider."""
        return self.status is MessageStatus.QUEUED and self.sending_started_at is not None

    def restart(
        self,
        *,
        variables: Mapping[str, str],
        to_phone_encrypted: str,
        job_id: UUID | None,
        now: datetime,
    ) -> None:
        """Send again after a refusal: only a queued row that is not started (R7)."""
        self._require_queued("restart")
        if self.sending_started_at is not None:
            raise InvalidTransition("message", "SENDING", "restart")
        now = require_utc(now, "now")
        self.variables = MappingProxyType(dict(variables))
        self.to_phone_encrypted = to_phone_encrypted
        self.job_id = job_id
        self.sending_started_at = now
        self.updated_at = now

    def refused(self, code: str, now: datetime) -> None:
        """The provider said no and sent nothing; a retry may call again."""
        self._require_queued("refuse")
        self.error_code = code
        self.sending_started_at = None
        self.updated_at = require_utc(now, "now")

    def accepted(self, *, provider_message_id: str, now: datetime) -> None:
        self._require_queued("accept")
        now = require_utc(now, "now")
        self.status = MessageStatus.SENT
        self.provider_message_id = provider_message_id
        self.error_code = None
        self.sending_started_at = None
        self.sent_at = now
        self.updated_at = now

    def fail(self, code: str, now: datetime) -> None:
        self._require_queued("fail")
        now = require_utc(now, "now")
        self.status = MessageStatus.FAILED
        self.error_code = code
        self.sending_started_at = None
        self.failed_at = now
        self.updated_at = now

    def _require_queued(self, action: str) -> None:
        if self.status is not MessageStatus.QUEUED:
            raise InvalidTransition("message", self.status.value, action)

    # --- Status webhooks (M5-P3; spec R13; decision 4A) -------------------------------------------

    def apply_status(self, update: StatusUpdate, now: datetime) -> bool:
        """Move the status forward only; True if anything changed.

        ``SENT -> DELIVERED -> READ``; an older or repeated status changes nothing, and a real
        ``FAILED`` is final. Two cases learn of an acceptance only from the webhook: a row still
        ``QUEUED`` (the worker died before recording the call) and a row failed as
        ``MSG_OUTCOME_UNKNOWN`` (decision 4A); the provider's status proves the call was accepted,
        so it is corrected.
        """
        now = require_utc(now, "now")
        if update.pricing_category and self.pricing_category != update.pricing_category:
            self.pricing_category = update.pricing_category
            changed = True
        else:
            changed = False
        unknown = self.status is MessageStatus.FAILED and self.error_code == MSG_OUTCOME_UNKNOWN
        if self.status is MessageStatus.FAILED and not unknown:
            return self._touch(changed, now)
        if self.status is MessageStatus.QUEUED or unknown:
            self.status = MessageStatus.SENT
            self.provider_message_id = self.provider_message_id or update.provider_message_id
            self.error_code = None
            self.failed_at = None
            self.sending_started_at = None
            self.sent_at = self.sent_at or update.at
            changed = True
        if update.status is MessageStatus.FAILED:
            if self.status is MessageStatus.SENT:
                self.status = MessageStatus.FAILED
                self.error_code = update.error_code or MSG_PROVIDER_REJECTED
                self.failed_at = update.at
                changed = True
            return self._touch(changed, now)
        if _RANK.get(update.status, 0) > _RANK[self.status]:
            self.status = update.status
            if update.status is MessageStatus.DELIVERED:
                self.delivered_at = update.at
            elif update.status is MessageStatus.READ:
                self.read_at = update.at
                self.delivered_at = self.delivered_at or update.at
            changed = True
        return self._touch(changed, now)

    def _touch(self, changed: bool, now: datetime) -> bool:
        if changed:
            self.updated_at = now
        return changed

    def __repr__(self) -> str:
        # Never the phone or the variables.
        return f"Message(id={self.id}, template={self.template_key}, status={self.status.value})"
