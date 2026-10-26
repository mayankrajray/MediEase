"""What goes to and comes from a model (M7a-P2; FR-AI-03; ADR-0013).

Provider-neutral shapes for one chat completion with tools: the adapters translate them to a
provider's wire format. Nothing here knows Groq, OpenAI or HTTP.

Text in these objects may be clinical (a tool result carries a prescription's lines), so they are
never logged: logs carry the provider, the model, tool names and token counts only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from mediease_api.domain.shared.errors import DomainError

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """The model asks for ``name`` with JSON ``arguments``; ``id`` pairs it with its result."""

    id: str
    name: str
    arguments: Mapping[str, JsonValue] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    # On a TOOL message: the call it answers, and the tool's name.
    tool_call_id: str | None = None
    name: str | None = None

    @classmethod
    def system(cls, content: str) -> ChatMessage:
        return cls(ChatRole.SYSTEM, content)

    @classmethod
    def user(cls, content: str) -> ChatMessage:
        return cls(ChatRole.USER, content)

    @classmethod
    def assistant(cls, content: str, tool_calls: tuple[ToolCall, ...] = ()) -> ChatMessage:
        return cls(ChatRole.ASSISTANT, content, tool_calls)

    @classmethod
    def tool(cls, call: ToolCall, content: str) -> ChatMessage:
        return cls(ChatRole.TOOL, content, tool_call_id=call.id, name=call.name)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool offered to the model: its name, what it does, and a JSON Schema for its arguments."""

    name: str
    description: str
    parameters: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LlmReply:
    """Either text for the user, or tool calls to run first (or both)."""

    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)


class LlmUnavailable(DomainError):
    """The provider timed out, failed, or answered something we could not read (R2)."""

    code = "AI_UNAVAILABLE"

    def __init__(self, reason: str = "unavailable") -> None:
        super().__init__("The assistant is not available right now. Please try again later.")
        self.reason = reason


class LlmBusy(DomainError):
    """The provider's own rate limit (R2): try again after ``retry_after_seconds``."""

    code = "AI_PROVIDER_BUSY"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("The assistant is busy. Please try again in a minute.")
        self.retry_after_seconds = retry_after_seconds
