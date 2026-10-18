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

    def __repr__(self) -> str:
        # Never the phone or the variables.
        return f"Message(id={self.id}, template={self.template_key}, status={self.status.value})"
