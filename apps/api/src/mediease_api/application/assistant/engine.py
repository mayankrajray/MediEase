"""One assistant turn, and confirming a proposal (M7a-P3; FR-AI-01..04; spec assistant R3-R12).

``AssistantEngine.turn``:

1. The last user message passes the before-model guard rail or gets the fixed referral; the model
   is not called (R4).
2. The model gets our system prompt, the visible conversation and the tools this caller may use
   (R6). Read tools run as the caller and their results go back to the model, for at most
   ``MAX_ROUNDS`` rounds. A write tool stops the turn with a signed proposal (R7).
3. The reply passes the after-model guard rails (R5). After ``explain_prescription`` it may use
   only numbers from the turn's tool results and the user's words, else the record's own text is
   returned (R10).

``AssistantEngine.confirm`` checks a proposal token and runs its write once (R8).

Logs carry the reply kind, tool names, rounds, provider, model, latency and token counts: never
the messages, arguments or results (R12).
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import structlog

from mediease_api.application.assistant.tools import (
    Args,
    Tool,
    ToolArgumentError,
    ToolKind,
    ToolResult,
)
from mediease_api.domain.assistant.explain import Explanation
from mediease_api.domain.assistant.guard_rails import (
    REFERRAL,
    numbers_in,
    referral_reason,
    reply_is_grounded,
    reply_is_safe,
)
from mediease_api.domain.assistant.llm import ChatMessage, LlmReply, ToolCall, ToolSpec
from mediease_api.domain.assistant.proposal import (
    CallerKind,
    Proposal,
    ProposalInvalid,
    ProposalUsed,
)
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.ports.assistant import ProposalSignerPort
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.llm import LlmPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 2000
MAX_ROUNDS = 4

_UNFINISHED = {
    Language.EN: (
        "Sorry, I could not finish that. Please ask in a different way, or call your clinic."
    ),
    Language.HI: "माफ़ कीजिए, मैं यह पूरा नहीं कर सका। कृपया दूसरे तरीके से पूछें या क्लिनिक को फ़ोन करें।",
}


class ReplyKind(StrEnum):
    ANSWER = "ANSWER"
    REFERRAL = "REFERRAL"
    CONFIRM = "CONFIRM"
    UNAVAILABLE = "UNAVAILABLE"
    DONE = "DONE"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class TurnMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class ProposalView:
    token: str
    summary: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TurnReply:
    kind: ReplyKind
    reply: str
    proposal: ProposalView | None = None
    tools_used: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Caller:
    kind: CallerKind
    subject: UUID
    clinic_id: UUID | None = None

    @property
    def bucket(self) -> str:
        return f"assistant:{self.kind.value}:{self.subject}"


def check_messages(messages: Sequence[TurnMessage]) -> None:
    """R3: 1-20 messages of 1-2,000 characters, the last from the user."""
    if not 1 <= len(messages) <= MAX_MESSAGES:
        raise InvalidValue("messages", f"must have 1-{MAX_MESSAGES} messages")
    if any(not 1 <= len(m.content.strip()) <= MAX_MESSAGE_CHARS for m in messages):
        raise InvalidValue("messages", f"each message must have 1-{MAX_MESSAGE_CHARS} characters")
    if messages[-1].role is not MessageRole.USER:
        raise InvalidValue("messages", "the last message must be the user's")


def _result_json(result: ToolResult) -> str:
    return json.dumps({"summary": result.summary, "data": dict(result.data)}, ensure_ascii=False)


def _error_json(code: str, message: str) -> str:
    return json.dumps({"error": code, "message": message}, ensure_ascii=False)


class AssistantEngine:
    def __init__(
        self,
        *,
        llm: LlmPort,
        signer: ProposalSignerPort,
        clock: ClockPort,
        ids: IdPort,
        uow: UnitOfWork,
    ) -> None:
        self._llm = llm
        self._signer = signer
        self._clock = clock
        self._ids = ids
        self._uow = uow

    # --- A turn ---------------------------------------------------------------------------------

    def turn(
        self,
        *,
        caller: Caller,
        messages: Sequence[TurnMessage],
        language: Language,
        system_prompt: str,
        tools: Sequence[Tool],
        context_ids: Mapping[str, str] | None = None,
    ) -> TurnReply:
        check_messages(messages)
        last = messages[-1].content
        reason = referral_reason(last)
        if reason is not None:
            logger.info("assistant.referred", reason=reason.value, caller=caller.kind.value)
            return TurnReply(ReplyKind.REFERRAL, REFERRAL[language])

        by_name = {t.name: t for t in tools}
        chat = [ChatMessage.system(system_prompt)]
        for m in messages:
            text = m.content.strip()
            chat.append(
                ChatMessage.user(text)
                if m.role is MessageRole.USER
                else ChatMessage.assistant(text)
            )
        specs = [t.spec for t in tools]
        used: list[str] = []
        explanation: Explanation | None = None
        allowed = set(numbers_in(last))
        final: str | None = None

        for _ in range(MAX_ROUNDS):
            reply = self._complete(chat, specs)
            if not reply.tool_calls:
                final = reply.content.strip()
                break
            chat.append(ChatMessage.assistant(reply.content, reply.tool_calls))
            for call in reply.tool_calls:
                tool = by_name.get(call.name)
                used.append(call.name)
                if tool is None:
                    chat.append(
                        ChatMessage.tool(call, _error_json("UNKNOWN_TOOL", "No such tool."))
                    )
                    continue
                if tool.kind is ToolKind.WRITE:
                    proposed = self._propose(caller, tool, call)
                    if isinstance(proposed, TurnReply):
                        self._log(caller, proposed, used, context_ids)
                        return proposed
                    chat.append(ChatMessage.tool(call, proposed))
                    continue
                content, result = self._run(tool, call)
                if result is not None:
                    allowed |= numbers_in(content)
                    if result.explanation is not None:
                        explanation = result.explanation
                chat.append(ChatMessage.tool(call, content))
        outcome = self._finish(final, explanation, frozenset(allowed), language, used)
        self._log(caller, outcome, used, context_ids)
        return outcome

    def _complete(self, chat: list[ChatMessage], specs: list[ToolSpec]) -> LlmReply:
        started = time.monotonic()
        reply = self._llm.complete(chat, specs)
        logger.info(
            "assistant.llm_called",
            provider=self._llm.provider,
            model=self._llm.model,
            latency_ms=round((time.monotonic() - started) * 1000),
            prompt_tokens=reply.usage.prompt_tokens,
            completion_tokens=reply.usage.completion_tokens,
            tool_calls=[c.name for c in reply.tool_calls],
        )
        return reply

    def _run(self, tool: Tool, call: ToolCall) -> tuple[str, ToolResult | None]:
        assert tool.run is not None
        try:
            result = tool.run(Args(call.arguments))
        except ToolArgumentError as error:
            return _error_json("BAD_ARGUMENTS", str(error)), None
        except DomainError as error:
            # The use case's own answer (not found, closed session, ...): the model explains it.
            return _error_json(error.code, error.message), None
        return _result_json(result), result

    def _propose(self, caller: Caller, tool: Tool, call: ToolCall) -> TurnReply | str:
        """R7: a write becomes a signed proposal, or an error for the model to explain."""
        assert tool.prepare is not None
        try:
            prepared = tool.prepare(Args(call.arguments))
        except ToolArgumentError as error:
            return _error_json("BAD_ARGUMENTS", str(error))
        except DomainError as error:
            return _error_json(error.code, error.message)
        proposal = Proposal.create(
            jti=self._ids.new_id(),
            caller=caller.kind,
            subject=caller.subject,
            clinic_id=caller.clinic_id,
            action=tool.name,
            args=prepared.args,
            now=self._clock.now(),
        )
        token = self._signer.sign(proposal.encode())
        return TurnReply(
            ReplyKind.CONFIRM,
            prepared.summary,
            ProposalView(token, prepared.summary, proposal.expires_at),
            (tool.name,),
        )

    def _finish(
        self,
        final: str | None,
        explanation: Explanation | None,
        allowed: frozenset[str],
        language: Language,
        used: list[str],
    ) -> TurnReply:
        tools_used = tuple(used)
        if not final:
            if explanation is not None:
                return TurnReply(ReplyKind.ANSWER, explanation.text, tools_used=tools_used)
            return TurnReply(ReplyKind.UNAVAILABLE, _UNFINISHED[language], tools_used=tools_used)
        own = explanation.own_words if explanation is not None else frozenset()
        if not reply_is_safe(final, own_words=own):
            logger.warning("assistant.reply_replaced", reason="advice")
            if explanation is not None:
                return TurnReply(ReplyKind.ANSWER, explanation.text, tools_used=tools_used)
            return TurnReply(ReplyKind.REFERRAL, REFERRAL[language], tools_used=tools_used)
        if explanation is not None and not reply_is_grounded(final, allowed):
            logger.warning("assistant.reply_replaced", reason="ungrounded")
            return TurnReply(ReplyKind.ANSWER, explanation.text, tools_used=tools_used)
        return TurnReply(ReplyKind.ANSWER, final, tools_used=tools_used)

    def _log(
        self,
        caller: Caller,
        outcome: TurnReply,
        used: list[str],
        context_ids: Mapping[str, str] | None,
    ) -> None:
        logger.info(
            "assistant.turn_completed",
            caller=caller.kind.value,
            kind=outcome.kind.value,
            tools=used,
            **dict(context_ids or {}),
        )

    # --- Rate limit (R11) and confirmation (R8) -------------------------------------------------

    def limit(self, caller: Caller, per_minute: int) -> int | None:
        """Count a turn; the seconds to wait if over the limit, else ``None``."""
        now = self._clock.now()
        with self._uow as uow:
            hits = uow.rate_limits.hit(
                caller.bucket, window_start=now.replace(second=0, microsecond=0)
            )
            uow.commit()
        return 60 - now.second if hits > per_minute else None

    def confirm(self, *, caller: Caller, token: str, tools: Sequence[Tool]) -> TurnReply:
        payload = self._signer.open(token)
        if payload is None:
            logger.info("assistant.proposal_refused", reason="signature")
            raise ProposalInvalid()
        proposal = Proposal.decode(payload)
        now = self._clock.now()
        try:
            proposal.check(
                caller=caller.kind, subject=caller.subject, clinic_id=caller.clinic_id, now=now
            )
        except ProposalInvalid:
            logger.info("assistant.proposal_refused", reason="caller_or_expiry")
            raise
        tool = next((t for t in tools if t.name == proposal.action), None)
        if tool is None or tool.kind is not ToolKind.WRITE or tool.perform is None:
            logger.info("assistant.proposal_refused", reason="action")
            raise ProposalInvalid()
        with self._uow as uow:
            # One use per proposal: the bucket is the proposal's own, in its issue minute, and
            # windows outlive the 10-minute expiry (they are kept an hour).
            uses = uow.rate_limits.hit(
                f"assistant-proposal:{proposal.jti}",
                window_start=proposal.issued_at.replace(second=0),
            )
            uow.commit()
        if uses > 1:
            logger.info("assistant.proposal_refused", reason="used")
            raise ProposalUsed()
        done = tool.perform(proposal.args)
        logger.info("assistant.confirmed", caller=caller.kind.value, action=proposal.action)
        return TurnReply(ReplyKind.DONE, done, tools_used=(proposal.action,))
