"""Any OpenAI-compatible chat-completions API with tools (M7a-P2; FR-AI-03; ADR-0013).

Groq, DeepInfra and OpenAI all serve ``POST {base_url}/chat/completions`` with the same request
and tool-call shapes, so one adapter covers them; the provider is a setting (``PRESETS`` gives
each one's base URL and default model). The standard library does the HTTP, as for WhatsApp:
no SDK is needed for one call.

Failures: the provider's 429 is ``LlmBusy`` (with its ``Retry-After``); a timeout, a dropped
connection, any other non-2xx answer, or a body we cannot read is ``LlmUnavailable``. Nothing is
retried here (a turn is interactive; the user retries). Logged: the status and the failure kind,
never the request or the answer, which may hold a prescription's lines.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from mediease_api.domain.assistant.llm import (
    ChatMessage,
    ChatRole,
    JsonValue,
    LlmBusy,
    LlmReply,
    LlmUnavailable,
    ToolCall,
    ToolSpec,
    Usage,
)

logger = structlog.get_logger(__name__)

DEFAULT_RETRY_AFTER_SECONDS = 20
MAX_TOKENS = 700
TEMPERATURE = 0.2


@dataclass(frozen=True, slots=True)
class Preset:
    base_url: str
    model: str


# Defaults per provider; LLM_BASE_URL and LLM_MODEL override them.
PRESETS: Mapping[str, Preset] = {
    "groq": Preset("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "deepinfra": Preset("https://api.deepinfra.com/v1/openai", "meta-llama/Llama-3.3-70B-Instruct"),
    "openai": Preset("https://api.openai.com/v1", "gpt-4o-mini"),
}


@dataclass(frozen=True, slots=True)
class HttpResult:
    status: int
    body: bytes
    retry_after: str | None = None


# (url, body, headers, timeout) -> the response; raises OSError when no response came back.
Transport = Callable[[str, bytes, Mapping[str, str], float], HttpResult]

USER_AGENT = "MediEase/1.0 (+https://github.com/mayankrajray/MediEase)"


def urllib_transport(
    url: str, body: bytes, headers: Mapping[str, str], timeout: float
) -> HttpResult:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResult(response.status, response.read())
    except urllib.error.HTTPError as error:
        return HttpResult(error.code, error.read(), error.headers.get("Retry-After"))


def _message(message: ChatMessage) -> dict[str, Any]:
    if message.role is ChatRole.TOOL:
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    body: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        body["content"] = message.content or None
        body["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(dict(call.arguments))},
            }
            for call in message.tool_calls
        ]
    return body


def _tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": dict(spec.parameters),
        },
    }


def _retry_after(value: str | None) -> int:
    try:
        seconds = int(float(value)) if value else DEFAULT_RETRY_AFTER_SECONDS
    except ValueError:
        seconds = DEFAULT_RETRY_AFTER_SECONDS
    return max(1, min(seconds, 300))


def parse_reply(body: bytes) -> LlmReply:
    """The first choice's text and tool calls, and the usage; ``LlmUnavailable`` if malformed."""
    try:
        data = json.loads(body)
        message = data["choices"][0]["message"]
        calls = []
        for raw in message.get("tool_calls") or ():
            function = raw["function"]
            arguments = json.loads(function.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                raise TypeError("arguments must be an object")
            calls.append(ToolCall(str(raw["id"]), str(function["name"]), _json_object(arguments)))
        usage = data.get("usage") or {}
        return LlmReply(
            content=str(message.get("content") or ""),
            tool_calls=tuple(calls),
            usage=Usage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            ),
        )
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise LlmUnavailable("malformed") from None


def _json_object(value: dict[str, Any]) -> dict[str, JsonValue]:
    return {str(key): item for key, item in value.items()}


class OpenAICompatibleLlm:
    """``LlmPort`` over HTTP for ``groq``, ``deepinfra`` or ``openai`` (R1)."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        base_url: str = "",
        model: str = "",
        timeout_seconds: float = 20.0,
        transport: Transport = urllib_transport,
    ) -> None:
        preset = PRESETS.get(provider)
        if preset is None:
            raise ValueError(f"unknown OpenAI-compatible provider {provider!r}")
        if not api_key:
            raise ValueError("an API key is required")
        self._provider = provider
        self._api_key = api_key
        self._url = f"{(base_url or preset.base_url).rstrip('/')}/chat/completions"
        self._model = model or preset.model
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]) -> LlmReply:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [_message(m) for m in messages],
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
        }
        if tools:
            payload["tools"] = [_tool(t) for t in tools]
            payload["tool_choice"] = "auto"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Groq's edge (Cloudflare) refuses urllib's default "Python-urllib/3.x" agent with
            # 403 error 1010; a named agent is accepted. It carries no data about the caller.
            "User-Agent": USER_AGENT,
        }
        try:
            result = self._transport(
                self._url, json.dumps(payload).encode(), headers, self._timeout
            )
        except (TimeoutError, OSError) as error:
            logger.warning(
                "assistant.llm_failed", provider=self._provider, kind=type(error).__name__
            )
            raise LlmUnavailable("network") from None
        if result.status == 429:
            logger.warning("assistant.llm_failed", provider=self._provider, status=429)
            raise LlmBusy(_retry_after(result.retry_after))
        if not 200 <= result.status < 300:
            logger.warning("assistant.llm_failed", provider=self._provider, status=result.status)
            raise LlmUnavailable(f"status {result.status}")
        try:
            return parse_reply(result.body)
        except LlmUnavailable:
            logger.warning("assistant.llm_failed", provider=self._provider, kind="malformed")
            raise
