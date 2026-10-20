"""WhatsApp webhook signature, redaction and status parsing (M5-P3; spec R12, R13; decision 3A).

Signature: ``X-Hub-Signature-256: sha256=<hex>``, HMAC-SHA256 of the *raw* body with the app
secret, compared in constant time before the body is parsed. An empty secret verifies nothing.

Redaction: only what the status processor needs is stored — for each status its ID, status,
time, our echoed message ID, the error codes and the pricing category; for each inbound message
only its ID, type and time. Message text, profile names and every phone number (``from``,
``recipient_id``, ``wa_id``, the business number) are dropped (spec R14: inbound text is not
stored). M5-P5 (decision 1A): a STOP reply is recognised here, before redaction, and is the one
exception — it also keeps ``stop: true``, the sender's number *encrypted* with the messages' phone
keys, and the ID of our message it replied to; the processing job removes the number again.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from mediease_api.adapters.messaging.whatsapp_errors import map_meta_error
from mediease_api.domain.messaging.message import MessageStatus, StatusUpdate
from mediease_api.domain.messaging.opt_out import InboundOptOut, is_stop_keyword
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.messaging import PhoneCipherPort

logger = structlog.get_logger(__name__)

PROVIDER = "whatsapp_cloud"
SIGNATURE_HEADER = "X-Hub-Signature-256"
_PREFIX = "sha256="
_STATUSES = {
    "sent": MessageStatus.SENT,
    "delivered": MessageStatus.DELIVERED,
    "read": MessageStatus.READ,
    "failed": MessageStatus.FAILED,
}


class HmacWebhookVerifier:
    def __init__(self, app_secret: str) -> None:
        self._secret = app_secret.encode("utf-8")

    def verify(self, body: bytes, signature: str | None) -> bool:
        if not self._secret or not signature or not signature.startswith(_PREFIX):
            return False
        expected = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature[len(_PREFIX) :].strip().lower())


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status(raw: Mapping[str, Any]) -> dict[str, Any]:
    kept: dict[str, Any] = {k: raw[k] for k in ("id", "status", "timestamp") if k in raw}
    if "biz_opaque_callback_data" in raw:
        kept["biz_opaque_callback_data"] = raw["biz_opaque_callback_data"]
    errors = [{"code": _dict(e).get("code")} for e in _list(raw.get("errors"))]
    if errors:
        kept["errors"] = errors
    category = _dict(raw.get("pricing")).get("category")
    if category:
        kept["pricing"] = {"category": category}
    return kept


class WhatsAppWebhookParser:
    """``phones`` encrypts a STOP sender's number for the stored payload (M5-P5 decision 1A)."""

    def __init__(self, phones: PhoneCipherPort) -> None:
        self._phones = phones

    def event_key(self, body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def redact(self, document: Mapping[str, Any]) -> dict[str, Any]:
        entries = []
        for entry in _list(document.get("entry")):
            changes = []
            for change in _list(_dict(entry).get("changes")):
                value = _dict(_dict(change).get("value"))
                kept: dict[str, Any] = {}
                statuses = [_status(_dict(s)) for s in _list(value.get("statuses"))]
                if statuses:
                    kept["statuses"] = statuses
                messages = [self._inbound(_dict(m)) for m in _list(value.get("messages"))]
                if messages:
                    kept["messages"] = messages
                changes.append({"field": _dict(change).get("field"), "value": kept})
            entries.append({"changes": changes})
        return {"object": document.get("object"), "entry": entries}

    def _inbound(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        """ID, type and time; a STOP reply also keeps its sender, encrypted, and its context."""
        kept: dict[str, Any] = {k: raw[k] for k in ("id", "type", "timestamp") if k in raw}
        body = _dict(raw.get("text")).get("body")
        if raw.get("type") != "text" or not isinstance(body, str) or not is_stop_keyword(body):
            return kept
        kept["stop"] = True
        sender = raw.get("from")
        if isinstance(sender, str) and sender.isdigit():
            try:
                kept["from_encrypted"] = self._phones.encrypt(PhoneNumber(f"+{sender}"))
            except InvalidValue:
                logger.info("webhook.stop_sender_invalid")
        context = _dict(raw.get("context")).get("id")
        if isinstance(context, str) and context:
            kept["context_id"] = context
        return kept

    def statuses(self, payload: Mapping[str, Any]) -> Sequence[StatusUpdate]:
        updates: list[StatusUpdate] = []
        for value in _values(payload):
            for raw in _list(value.get("statuses")):
                update = _update(_dict(raw))
                if update is not None:
                    updates.append(update)
        return updates

    def opt_outs(self, payload: Mapping[str, Any]) -> Sequence[InboundOptOut]:
        found: list[InboundOptOut] = []
        for value in _values(payload):
            for raw in map(_dict, _list(value.get("messages"))):
                provider_id = raw.get("id")
                if raw.get("stop") is not True or not isinstance(provider_id, str):
                    continue
                at = _time(raw.get("timestamp"))
                if at is None:
                    continue
                phone = raw.get("from_encrypted")
                context = raw.get("context_id")
                found.append(
                    InboundOptOut(
                        provider_message_id=provider_id,
                        at=at,
                        phone_encrypted=phone if isinstance(phone, str) else None,
                        context_id=context if isinstance(context, str) else None,
                    )
                )
        return found

    def forget_senders(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        copy: dict[str, Any] = json.loads(json.dumps(payload))
        for value in _values(copy):
            for raw in map(_dict, _list(value.get("messages"))):
                raw.pop("from_encrypted", None)
        return copy


def _values(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        _dict(_dict(change).get("value"))
        for entry in _list(payload.get("entry"))
        for change in _list(_dict(entry).get("changes"))
    ]


def _time(raw: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(str(raw)), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _update(raw: Mapping[str, Any]) -> StatusUpdate | None:
    status = _STATUSES.get(str(raw.get("status")))
    provider_id = raw.get("id")
    if status is None or not isinstance(provider_id, str) or not provider_id:
        logger.info("webhook.status_ignored", status=str(raw.get("status"))[:20])
        return None
    at = _time(raw.get("timestamp"))
    if at is None:
        return None
    try:
        message_id: UUID | None = UUID(str(raw["biz_opaque_callback_data"]))
    except (KeyError, ValueError):
        message_id = None
    errors = _list(raw.get("errors"))
    code = map_meta_error(_dict(errors[0]).get("code")) if errors else None
    category = _dict(raw.get("pricing")).get("category")
    return StatusUpdate(
        provider_message_id=provider_id,
        message_id=message_id,
        status=status,
        at=at,
        error_code=code if status is MessageStatus.FAILED else None,
        pricing_category=str(category)[:40] if category else None,
    )
