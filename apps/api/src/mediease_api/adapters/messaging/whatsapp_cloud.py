"""The WhatsApp Cloud API provider (M5-P3; ADR-0007; spec R7; decision 1A: the standard library).

One call: ``POST {graph}/{version}/{phone-number-id}/messages`` with the approved template, its
language and the body parameters in the template's order, and our message ID as
``biz_opaque_callback_data`` so every status webhook can find the row even if the worker died
before it saved Meta's ID. A service-category template (the opt-out reply, P5) is a plain text
message inside the window the patient opened.

Outcomes (``domain/messaging/errors.py``): a 2xx with a message ID is accepted; an error response
is a *refusal* (nothing sent), mapped by ``whatsapp_errors``; a timeout, a dropped connection or a
response we cannot read is an *unknown* outcome and is never retried (decision 4A of P2). The only
network failure counted as a refusal is one where the request cannot have left: the connection
was refused or the name did not resolve.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import structlog

from mediease_api.adapters.messaging.whatsapp_errors import map_meta_error
from mediease_api.domain.messaging.errors import (
    MSG_PROVIDER_AUTH,
    MSG_PROVIDER_UNAVAILABLE,
    ProviderOutcomeUnknown,
    ProviderRefused,
)
from mediease_api.domain.messaging.message import Channel
from mediease_api.domain.messaging.template import TemplateCategory
from mediease_api.ports.messaging import OutboundTemplateMessage, ProviderAccepted

logger = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 10.0  # spec R7


@dataclass(frozen=True, slots=True)
class HttpResult:
    status: int
    body: bytes


# (url, body, headers, timeout) -> the response, raising OSError when no response came back.
Transport = Callable[[str, bytes, Mapping[str, str], float], HttpResult]


class RequestNeverSent(OSError):
    """The connection was never made, so nothing reached the provider."""


def urllib_transport(
    url: str, body: bytes, headers: Mapping[str, str], timeout: float
) -> HttpResult:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResult(response.status, response.read())
    except urllib.error.HTTPError as error:
        return HttpResult(error.code, error.read())
    except urllib.error.URLError as error:
        if isinstance(error.reason, ConnectionRefusedError | socket.gaierror):
            raise RequestNeverSent(type(error.reason).__name__) from None
        raise


class WhatsAppCloudAdapter:
    def __init__(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        api_version: str,
        graph_url: str = "https://graph.facebook.com",
        transport: Transport = urllib_transport,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        self._url = f"{graph_url.rstrip('/')}/{api_version}/{phone_number_id}/messages"
        self._token = access_token
        self._transport = transport
        self._timeout = timeout

    @property
    def channel(self) -> Channel:
        return Channel.WHATSAPP

    @property
    def provider(self) -> str:
        return "whatsapp_cloud"

    def send_template(self, msg: OutboundTemplateMessage) -> ProviderAccepted:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        body = json.dumps(request_body(msg), ensure_ascii=False).encode("utf-8")
        try:
            result = self._transport(self._url, body, headers, self._timeout)
        except RequestNeverSent:
            raise ProviderRefused(MSG_PROVIDER_UNAVAILABLE) from None
        except (TimeoutError, OSError):
            raise ProviderOutcomeUnknown() from None
        return _outcome(result, msg)


def request_body(msg: OutboundTemplateMessage) -> dict[str, Any]:
    """The Cloud API request for one message (exposed for tests)."""
    body: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": msg.to.e164.lstrip("+"),
    }
    if msg.message_id is not None:
        body["biz_opaque_callback_data"] = str(msg.message_id)
    localised = msg.template.body(msg.language)
    if msg.template.category is TemplateCategory.SERVICE:
        body["type"] = "text"
        body["text"] = {"body": msg.template.render(msg.language, msg.variables)}
        return body
    body["type"] = "template"
    body["template"] = {
        "name": localised.provider_name,
        "language": {"code": msg.language.value},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": msg.variables[v.name]} for v in msg.template.variables
                ],
            }
        ],
    }
    return body


def _outcome(result: HttpResult, msg: OutboundTemplateMessage) -> ProviderAccepted:
    try:
        document = json.loads(result.body or b"{}")
    except ValueError:
        document = None
    if 200 <= result.status < 300:
        try:
            return ProviderAccepted(provider_message_id=str(document["messages"][0]["id"]))
        except (TypeError, KeyError, IndexError):
            # Accepted, but we cannot say which message ID: treat like a lost answer.
            raise ProviderOutcomeUnknown() from None
    if result.status >= 500 and not _has_error(document):
        raise ProviderRefused(MSG_PROVIDER_UNAVAILABLE)
    error = document.get("error", {}) if isinstance(document, dict) else {}
    code = map_meta_error(error.get("code"))
    if result.status == 401:
        code = MSG_PROVIDER_AUTH
    log = logger.error if code == MSG_PROVIDER_AUTH else logger.warning
    # The Meta code and HTTP status only: Meta's message text can echo the parameters.
    log(
        "messaging.whatsapp_refused",
        http_status=result.status,
        meta_code=error.get("code"),
        meta_subcode=error.get("error_subcode"),
        error_code=code,
        template=msg.template.key,
    )
    raise ProviderRefused(code)


def _has_error(document: object) -> bool:
    return isinstance(document, dict) and isinstance(document.get("error"), dict)
