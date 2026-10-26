"""The LLM gateway port (M7a-P2; FR-AI-03; ADR-0013).

One call: messages and the tools on offer in, a reply or tool calls out, with token usage. The
provider is chosen by settings in ``bootstrap.build_llm``; nothing else knows it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mediease_api.domain.assistant.llm import ChatMessage, LlmReply, ToolSpec


class LlmPort(Protocol):
    @property
    def provider(self) -> str:
        """``console``, ``groq``, ``deepinfra`` or ``openai`` (for logs)."""
        ...

    @property
    def model(self) -> str: ...

    def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]) -> LlmReply:
        """One completion. Raises ``LlmUnavailable`` or ``LlmBusy``; never retries itself."""
        ...
