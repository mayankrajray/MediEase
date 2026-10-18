"""Sending messages to patients (M5-P2; ADR-0007; docs/ARCHITECTURE.md §8).

``MessagingPort`` is one provider (console in development, WhatsApp Cloud API from P3, SMS from
P5). It raises ``ProviderRefused`` when nothing was sent and ``ProviderOutcomeUnknown`` when it
cannot tell (``domain/messaging/errors.py``); it never retries by itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from mediease_api.domain.messaging.message import Channel, Message
from mediease_api.domain.messaging.template import MessageTemplate
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
