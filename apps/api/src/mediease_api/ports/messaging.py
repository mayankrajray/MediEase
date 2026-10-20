"""Sending messages to patients (M5-P2; ADR-0007; docs/ARCHITECTURE.md §8).

``MessagingPort`` is one provider (console in development, WhatsApp Cloud API from P3, SMS from
P5). It raises ``ProviderRefused`` when nothing was sent and ``ProviderOutcomeUnknown`` when it
cannot tell (``domain/messaging/errors.py``); it never retries by itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from mediease_api.domain.messaging.message import Channel, Message, StatusUpdate
from mediease_api.domain.messaging.opt_out import InboundOptOut
from mediease_api.domain.messaging.template import MessageTemplate
from mediease_api.domain.messaging.webhook import WebhookEvent
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.phone import PhoneNumber


@dataclass(frozen=True, slots=True, repr=False)
class OutboundTemplateMessage:
    """What a provider needs: values are the checked variables, including the real link."""

    idempotency_key: str
    to: PhoneNumber
    template: MessageTemplate
    language: Language
    variables: Mapping[str, str]
    # M5-P3: our message ID, echoed back by the provider in its status webhooks.
    message_id: UUID | None = None

    def __repr__(self) -> str:
        return f"OutboundTemplateMessage(template={self.template.key}, to={self.to.masked()})"


@dataclass(frozen=True, slots=True)
class ProviderAccepted:
    provider_message_id: str


class MessagingPort(Protocol):
    @property
    def channel(self) -> Channel: ...

    @property
    def provider(self) -> str:
        """A short name recorded on each message (``console``, ``whatsapp_cloud``)."""
        ...

    def send_template(self, msg: OutboundTemplateMessage) -> ProviderAccepted: ...


class TemplateCatalog(Protocol):
    def get(self, key: str) -> MessageTemplate:
        """The template; a key the catalogue lacks is a programming error (``KeyError``)."""
        ...


class PhoneCipherPort(Protocol):
    """Application-level encryption of stored phone numbers (decision 1A)."""

    def encrypt(self, phone: PhoneNumber) -> str: ...

    def decrypt(self, token: str) -> PhoneNumber: ...


class MessageRepository(Protocol):
    """``messages`` of one clinic (tenant-scoped, ADR-0003)."""

    def add(self, message: Message) -> None: ...

    def update(self, message: Message) -> None: ...

    def get_by_key(self, idempotency_key: str, *, for_update: bool = False) -> Message | None: ...

    def get(self, message_id: UUID, *, for_update: bool = False) -> Message | None: ...


class MessageLookup(Protocol):
    """Which clinic a provider status belongs to (M5-P3).

    Reviewed cross-clinic exception, like the job store: a webhook names no clinic. It returns
    the clinic and the message ID only; the message itself is then read through that clinic's
    tenant repository.
    """

    def find(
        self, *, message_id: UUID | None, provider_message_id: str
    ) -> tuple[UUID, UUID] | None: ...

    def count_unconfirmed(self, *, sent_before: datetime) -> int:
        """Messages still ``SENT`` (no delivery status) since before ``sent_before``."""
        ...


class WebhookEventRepository(Protocol):
    """Stored provider webhooks (platform data, no clinic)."""

    def add(self, event: WebhookEvent) -> bool:
        """False if the same body was stored before (a redelivery)."""
        ...

    def get(self, event_id: UUID, *, for_update: bool = False) -> WebhookEvent | None: ...

    def update(self, event: WebhookEvent) -> None: ...

    def list_unprocessed(self, *, received_before: datetime, limit: int) -> Sequence[UUID]: ...


class WebhookVerifier(Protocol):
    def verify(self, body: bytes, signature: str | None) -> bool:
        """R13: the raw body is signed with our app secret (constant-time comparison)."""
        ...


class WebhookParser(Protocol):
    """A provider's webhook format, kept out of the application layer."""

    def event_key(self, body: bytes) -> str: ...

    def redact(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """What may be stored: statuses and IDs, no text, names or phone numbers (decision 3A)."""
        ...

    def statuses(self, payload: Mapping[str, Any]) -> Sequence[StatusUpdate]: ...

    def opt_outs(self, payload: Mapping[str, Any]) -> Sequence[InboundOptOut]:
        """The STOP replies in a stored payload (M5-P5; spec R14)."""
        ...

    def forget_senders(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """The payload without the STOP senders' encrypted numbers, once they are processed."""
        ...


class OptOutLookup(Protocol):
    """Who a STOP reply opts out (M5-P5 decision 2A).

    Reviewed cross-clinic exception, like ``MessageLookup``: a reply names no clinic. It returns
    clinic and patient IDs only: in each clinic that has messaged a patient with ``phone``, every
    patient whose current number it is (a family sharing a phone, spec §8). Each patient is then
    changed through its clinic's repository.
    """

    def patients_messaged(self, phone: PhoneNumber) -> Sequence[tuple[UUID, UUID]]: ...
