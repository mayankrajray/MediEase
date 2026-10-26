"""Test doubles for the assistant (M7a): a scripted, recording model and a world wired to it."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mediease_api.domain.assistant.llm import (
    ChatMessage,
    ChatRole,
    JsonValue,
    LlmReply,
    ToolCall,
    ToolSpec,
)
from tests.conftest import World, make_db_app
from tests.integration.test_portal_http import portal_csrf
from tests.portal_helpers import PORTAL, staff_csrf

Step = LlmReply | Callable[[Sequence[ChatMessage]], LlmReply] | Exception


@dataclass
class ScriptedLlm:
    """Answers each call with the next step, and records every message and tool it was sent."""

    steps: list[Step] = field(default_factory=list)
    calls: list[tuple[list[ChatMessage], list[ToolSpec]]] = field(default_factory=list)

    @property
    def provider(self) -> str:
        return "scripted"

    @property
    def model(self) -> str:
        return "scripted-1"

    def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]) -> LlmReply:
        self.calls.append((list(messages), list(tools)))
        if not self.steps:
            return LlmReply(content="(no more steps)")
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(messages) if callable(step) else step

    def seen_text(self) -> str:
        """Everything the model was ever sent, as one string (for leak checks)."""
        return "\n".join(m.content for messages, _ in self.calls for m in messages)

    def tool_results(self) -> list[dict[str, Any]]:
        out = []
        for messages, _ in self.calls:
            for m in messages:
                if m.role is ChatRole.TOOL:
                    out.append(json.loads(m.content))
        return out


def say(text: str) -> LlmReply:
    return LlmReply(content=text)


def call(name: str, **arguments: JsonValue) -> LlmReply:
    return LlmReply(content="", tool_calls=(ToolCall(f"c-{name}", name, arguments),))


def with_llm(world: World, llm: Any) -> World:
    """The same database and people, on an app whose model is ``llm``."""
    url = world.app.config["SETTINGS"].DATABASE_URL
    return replace(world, app=make_db_app(url, llm=llm))


def user(text: str) -> dict[str, str]:
    return {"role": "user", "content": text}


def bot(text: str) -> dict[str, str]:
    return {"role": "assistant", "content": text}


def patient_turn(client: FlaskClient, *messages: dict[str, str], **body: Any) -> TestResponse:
    return client.post(
        f"{PORTAL}/assistant/turns",
        json={"messages": list(messages), **body},
        headers=portal_csrf(client),
    )


def patient_confirm(client: FlaskClient, token: str) -> TestResponse:
    return client.post(
        f"{PORTAL}/assistant/confirm", json={"token": token}, headers=portal_csrf(client)
    )


def staff_turn(client: FlaskClient, clinic_id: str, *messages: dict[str, str]) -> TestResponse:
    return client.post(
        "/api/v1/assistant/turns",
        json={"messages": list(messages)},
        headers={**staff_csrf(client), "X-Clinic-ID": clinic_id},
    )


def staff_confirm(client: FlaskClient, clinic_id: str, token: str) -> TestResponse:
    return client.post(
        "/api/v1/assistant/confirm",
        json={"token": token},
        headers={**staff_csrf(client), "X-Clinic-ID": clinic_id},
    )
