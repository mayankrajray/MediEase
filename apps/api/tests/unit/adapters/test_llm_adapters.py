"""The LLM gateway adapters (M7a-P2; FR-AI-03; spec assistant R1, R2; AC1).

The OpenAI-compatible adapter is checked against a fake transport (request shape, tool calls,
failures) and once over real HTTP against a local server, so switching provider is settings only.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from pydantic import SecretStr

from mediease_api.adapters.llm.console import ASK_CLINIC, ConsoleLlm
from mediease_api.adapters.llm.openai_compatible import (
    PRESETS,
    HttpResult,
    OpenAICompatibleLlm,
)
from mediease_api.bootstrap import build_llm
from mediease_api.config.settings import AppEnv, AppSettings
from mediease_api.domain.assistant.llm import (
    ChatMessage,
    LlmBusy,
    LlmUnavailable,
    ToolCall,
    ToolSpec,
)

TOOL = ToolSpec("my_appointments", "List them", {"type": "object", "properties": {}})


class FakeTransport:
    def __init__(self, result: HttpResult | Exception) -> None:
        self.result = result
        self.sent: list[tuple[str, dict[str, Any], Mapping[str, str], float]] = []

    def __call__(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> HttpResult:
        self.sent.append((url, json.loads(body), headers, timeout))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _ok(message: dict[str, Any]) -> HttpResult:
    body = {"choices": [{"message": message}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    return HttpResult(200, json.dumps(body).encode())


def _llm(transport: FakeTransport, provider: str = "groq") -> OpenAICompatibleLlm:
    return OpenAICompatibleLlm(provider=provider, api_key="sk-test", transport=transport)


def test_ac1_the_request_is_openai_compatible_with_tools() -> None:
    transport = FakeTransport(_ok({"content": "hello"}))
    llm = _llm(transport)
    call = ToolCall("c1", "my_appointments", {})
    reply = llm.complete(
        [
            ChatMessage.system("rules"),
            ChatMessage.user("hi"),
            ChatMessage.assistant("", (call,)),
            ChatMessage.tool(call, '{"summary": "none"}'),
        ],
        [TOOL],
    )
    assert reply.content == "hello" and reply.usage.prompt_tokens == 7
    url, body, headers, timeout = transport.sent[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test" and timeout == 20.0
    assert body["model"] == PRESETS["groq"].model and body["tool_choice"] == "auto"
    assert body["tools"][0]["function"]["name"] == "my_appointments"
    assert body["messages"][2]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": '{"summary": "none"}'}


@pytest.mark.parametrize("provider", ["groq", "deepinfra", "openai"])
def test_ac1_each_provider_is_a_preset_and_overridable(provider: str) -> None:
    transport = FakeTransport(_ok({"content": "x"}))
    OpenAICompatibleLlm(
        provider=provider, api_key="k", base_url="https://llm.example/v1/", model="m", transport=transport
    ).complete([ChatMessage.user("hi")], [])
    url, body, _, _ = transport.sent[0]
    assert url == "https://llm.example/v1/chat/completions" and body["model"] == "m"
    assert "tools" not in body


def test_r2_tool_calls_are_parsed() -> None:
    message = {
        "content": None,
        "tool_calls": [
            {"id": "a", "type": "function", "function": {"name": "list_slots", "arguments": '{"doctor_id": "d"}'}}
        ],
    }
    reply = _llm(FakeTransport(_ok(message))).complete([ChatMessage.user("x")], [TOOL])
    assert reply.tool_calls == (ToolCall("a", "list_slots", {"doctor_id": "d"}),)


@pytest.mark.parametrize(
    "result",
    [
        HttpResult(500, b"oops"),
        HttpResult(401, b"{}"),
        HttpResult(200, b"not json"),
        HttpResult(200, b'{"choices": []}'),
        _ok({"tool_calls": [{"id": "a", "function": {"name": "x", "arguments": "[1]"}}]}),
        TimeoutError("slow"),
        OSError("reset"),
    ],
)
def test_r2_failures_are_unavailable(result: HttpResult | Exception) -> None:
    with pytest.raises(LlmUnavailable):
        _llm(FakeTransport(result)).complete([ChatMessage.user("x")], [])


def test_r2_the_providers_rate_limit_is_busy_with_its_retry_after() -> None:
    with pytest.raises(LlmBusy) as caught:
        _llm(FakeTransport(HttpResult(429, b"{}", "42"))).complete([ChatMessage.user("x")], [])
    assert caught.value.retry_after_seconds == 42
    with pytest.raises(LlmBusy) as default:
        _llm(FakeTransport(HttpResult(429, b"{}", "soon"))).complete([ChatMessage.user("x")], [])
    assert default.value.retry_after_seconds == 20


def test_the_adapter_refuses_unknown_providers_and_missing_keys() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleLlm(provider="console", api_key="k")
    with pytest.raises(ValueError):
        OpenAICompatibleLlm(provider="groq", api_key="")


@pytest.fixture
def server() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server's naming
            length = int(self.headers["Content-Length"])
            received.append(json.loads(self.rfile.read(length)))
            if self.path.endswith("/busy/chat/completions"):
                self.send_response(429)
                self.send_header("Retry-After", "9")
                self.end_headers()
                return
            body = json.dumps({"choices": [{"message": {"content": "over http"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            return

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", received
    finally:
        httpd.shutdown()


def test_ac1_over_real_http(server: tuple[str, list[dict[str, Any]]]) -> None:
    url, received = server
    llm = OpenAICompatibleLlm(provider="openai", api_key="k", base_url=f"{url}/v1", timeout_seconds=5)
    assert llm.complete([ChatMessage.user("hi")], []).content == "over http"
    assert received[0]["messages"] == [{"role": "user", "content": "hi"}]
    busy = OpenAICompatibleLlm(provider="openai", api_key="k", base_url=f"{url}/busy", timeout_seconds=5)
    with pytest.raises(LlmBusy) as caught:
        busy.complete([ChatMessage.user("hi")], [])
    assert caught.value.retry_after_seconds == 9


# --- The console adapter --------------------------------------------------------------------


def _specs(*names: str) -> list[ToolSpec]:
    return [ToolSpec(n, n, {"type": "object"}) for n in names]


PATIENT_TOOLS = _specs(
    "search_clinics", "list_slots", "request_booking", "my_appointments", "my_booking_requests",
    "my_prescriptions", "explain_prescription",
)


def test_console_routes_questions_to_tools_and_asks_which_clinic() -> None:
    llm = ConsoleLlm()
    assert llm.complete([ChatMessage.user("When do I take my medicine?")], PATIENT_TOOLS).tool_calls[0].name == "explain_prescription"
    one = llm.complete([ChatMessage.user("explain medicine 2")], PATIENT_TOOLS).tool_calls[0]
    assert one.arguments == {"medicine_number": 2}
    assert llm.complete([ChatMessage.user("show my appointments")], PATIENT_TOOLS).tool_calls[0].name == "my_appointments"
    assert llm.complete([ChatMessage.user("I want to book")], PATIENT_TOOLS).content == ASK_CLINIC
    follow = llm.complete(
        [ChatMessage.user("book"), ChatMessage.assistant(ASK_CLINIC), ChatMessage.user("Alpha")],
        PATIENT_TOOLS,
    ).tool_calls[0]
    assert (follow.name, follow.arguments) == ("search_clinics", {"query": "Alpha"})


def test_console_repeats_the_tools_own_summary() -> None:
    call = ToolCall("call_1", "my_appointments", {})
    reply = ConsoleLlm().complete(
        [
            ChatMessage.user("my appointments"),
            ChatMessage.assistant("", (call,)),
            ChatMessage.tool(call, json.dumps({"summary": "You have no appointments yet.", "data": {}})),
        ],
        PATIENT_TOOLS,
    )
    assert reply.content == "You have no appointments yet." and not reply.tool_calls


def test_console_turns_a_chosen_time_into_a_booking_request() -> None:
    header = "Free times with Dr. Alpha Sample at Alpha Sample Clinic:\n1. Tue\n2. Wed"
    history = [ChatMessage.assistant(header), ChatMessage.user("2, 9000000777")]
    first = ConsoleLlm().complete(history, PATIENT_TOOLS).tool_calls[0]
    assert first.name == "search_clinics"
    search = ToolCall("call_1", "search_clinics", {})
    clinics = {"clinics": [{"name": "Alpha Sample Clinic", "clinic_slug": "alpha", "doctors": [{"name": "Dr. Alpha Sample", "doctor_id": "d1"}]}]}
    history += [ChatMessage.assistant("", (search,)), ChatMessage.tool(search, json.dumps({"summary": "", "data": clinics}))]
    slots = ConsoleLlm().complete(history, PATIENT_TOOLS).tool_calls[0]
    assert (slots.name, slots.arguments) == ("list_slots", {"clinic_slug": "alpha", "doctor_id": "d1"})
    listed = ToolCall("call_2", "list_slots", {})
    times = {"clinic_slug": "alpha", "doctor_id": "d1", "times": [{"session_start": "s1"}, {"session_start": "s2", "slot_start": "t2"}]}
    history += [ChatMessage.assistant("", (listed,)), ChatMessage.tool(listed, json.dumps({"summary": "", "data": times}))]
    booking = ConsoleLlm().complete(history, PATIENT_TOOLS).tool_calls[0]
    assert booking.name == "request_booking"
    assert booking.arguments["session_start"] == "s2" and booking.arguments["slot_start"] == "t2"
    assert booking.arguments["contact_phone"] == "9000000777"


def test_console_staff_rules() -> None:
    staff = _specs("today_queue", "list_sessions", "find_patient")
    system = ChatMessage.system("Today is 2026-10-27 (Tuesday)")
    assert ConsoleLlm().complete([system, ChatMessage.user("queue please")], staff).tool_calls[0].name == "today_queue"
    sessions = ConsoleLlm().complete([system, ChatMessage.user("sessions")], staff).tool_calls[0]
    assert sessions.arguments == {"date": "2026-10-27"}
    found = ConsoleLlm().complete([system, ChatMessage.user("find patient Asha")], staff).tool_calls[0]
    assert found.arguments == {"text": "Asha"}


# --- Choosing the adapter (R1) ----------------------------------------------------------------


def _settings(**values: Any) -> AppSettings:
    base: dict[str, Any] = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "JWT_SIGNING_KEY": SecretStr("k" * 40),
        "AUDIT_IP_SALT": SecretStr("s" * 40),
    }
    base.update(values)
    return AppSettings(**base)


def test_r1_build_llm_picks_by_settings_and_refuses_unsafe_combinations() -> None:
    assert isinstance(build_llm(_settings()), ConsoleLlm)
    real = build_llm(_settings(LLM_PROVIDER="groq", LLM_API_KEY=SecretStr("k")))
    assert isinstance(real, OpenAICompatibleLlm) and real.provider == "groq"
    with pytest.raises(ValueError, match="refused in production"):
        build_llm(_settings().model_copy(update={"APP_ENV": AppEnv.PRODUCTION}))
    deployed = _settings(
        APP_ENV=AppEnv.LOCAL, LLM_PROVIDER="groq", LLM_API_KEY=SecretStr("k")
    ).model_copy(update={"APP_ENV": AppEnv.STAGING})
    with pytest.raises(ValueError, match="LLM_PATIENT_DATA_ALLOWED"):
        build_llm(deployed)


def test_r1_settings_need_a_key_for_a_real_provider_and_a_url() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        _settings(LLM_PROVIDER="groq")
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        _settings(LLM_BASE_URL="ftp://x")
