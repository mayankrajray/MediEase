"""``make config-check`` reports real configuration without its secrets (M7c-P6).

Synthetic values only. The live checks are exercised with their network calls replaced.
"""

from __future__ import annotations

import io
import json
import smtplib
import urllib.error
from typing import Any, ClassVar

import pytest
from pydantic import SecretStr

from mediease_api.config.settings import AppSettings
from mediease_api.delivery.cli import config_check
from mediease_api.domain.assistant.llm import LlmReply

SECRETS = {
    "WHATSAPP_ACCESS_TOKEN": "EAAG-synthetic-token-123",
    "WHATSAPP_APP_SECRET": "synthetic-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "synthetic-verify-token",
    "SMTP_PASSWORD": "synthetic-smtp-password",
    "GOOGLE_CLIENT_SECRET": "synthetic-google-secret",
    "LLM_API_KEY": "nvapi-synthetic-key",
}


def _settings(**values: Any) -> AppSettings:
    base: dict[str, Any] = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "JWT_SIGNING_KEY": SecretStr("x" * 40),
        "AUDIT_IP_SALT": SecretStr("y" * 40),
    }
    base.update(values)
    return AppSettings(**base)


def _real() -> AppSettings:
    return _settings(
        MESSAGING_PROVIDER="whatsapp_cloud",
        WHATSAPP_PHONE_NUMBER_ID="100000000004321",
        EMAIL_PROVIDER="smtp",
        SMTP_HOST="smtp-relay.example.test",
        SMTP_PORT=587,
        SMTP_SECURITY="starttls",
        SMTP_USERNAME="relay-user",
        EMAIL_FROM="MediEase <no-reply@example.test>",
        GOOGLE_OIDC_PROVIDER="google",
        GOOGLE_CLIENT_ID="synthetic.apps.googleusercontent.com",
        LLM_PROVIDER="nvidia",
        **{k: SecretStr(v) for k, v in SECRETS.items()},
    )


def test_m7c_p6_the_report_names_each_service_and_never_a_secret() -> None:
    lines = config_check.describe(_real())
    text = "\n".join(" ".join(line) for line in lines)
    for secret in SECRETS.values():
        assert secret not in text
    assert "MESSAGING_PROVIDER whatsapp_cloud" in text and "…4321" in text
    assert "http://localhost:3000/api/v1/auth/google/callback" in text
    assert "integrate.api.nvidia.com" in text and "meta/llama-3.3-70b-instruct" in text
    assert "SMTP_PASSWORD set" in text


def test_m7c_p6_console_settings_skip_every_live_check() -> None:
    s = _settings(EMAIL_PROVIDER="console")
    for check in (
        config_check.check_whatsapp,
        config_check.check_email,
        config_check.check_google,
        config_check.check_llm,
    ):
        assert check(s).startswith("skipped")
    assert config_check.send_email(s, "a@example.test").startswith("skipped")
    assert config_check.send_whatsapp(s, "9000000101").startswith("skipped")


def test_m7c_p6_whatsapp_reads_the_number_and_reports_metas_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str | None]] = []
    answers = [
        (200, {"verified_name": "Sample Clinic", "display_phone_number": "+91 90000 00101"}),
        (401, {"error": {"type": "OAuthException", "code": 190, "message": "expired"}}),
    ]

    def fake_get(url: str, token: str | None = None) -> tuple[int, dict[str, object]]:
        seen.append((url, token))
        return answers.pop(0)

    monkeypatch.setattr(config_check, "_get", fake_get)
    assert config_check.check_whatsapp(_real()).startswith("ok: Sample Clinic, number …0101")
    assert "100000000004321?fields=" in seen[0][0]
    assert seen[0][1] == SECRETS["WHATSAPP_ACCESS_TOKEN"]
    assert config_check.check_whatsapp(_real()) == (
        "FAILED: HTTP 401 (OAuthException code 190: expired)"
    )


def test_m7c_p6_google_and_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config_check, "_get", lambda url, token=None: (200, {"authorization_endpoint": "x"})
    )
    assert config_check.check_google(_real()).startswith("ok")

    class Model:
        provider, model = "nvidia", "m"

        def complete(self, messages: Any, tools: Any) -> LlmReply:
            return LlmReply(content="OK")

    monkeypatch.setattr(config_check, "build_llm", lambda s: Model())
    assert config_check.check_llm(_real()) == "ok: nvidia m answered (2 characters)"


class FakeSmtp:
    sent: ClassVar[list[Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def starttls(self, **kwargs: Any) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        if password != SECRETS["SMTP_PASSWORD"]:
            raise smtplib.SMTPAuthenticationError(535, b"bad login")

    def noop(self) -> None:
        pass

    def send_message(self, message: Any) -> None:
        FakeSmtp.sent.append(message)


def test_m7c_p6_email_logs_in_and_sends_one_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_check.smtplib, "SMTP", FakeSmtp)
    assert config_check.check_email(_real()) == "ok: logged in to smtp-relay.example.test"
    out = config_check.send_email(_real(), "owner@example.test")
    assert out.startswith("sent to o***@example.test")
    assert FakeSmtp.sent[-1]["To"] == "owner@example.test"
    wrong = _real().model_copy(update={"SMTP_PASSWORD": SecretStr("nope")})
    assert config_check.check_email(wrong).startswith("FAILED: SMTPAuthenticationError")


def test_m7c_p6_whatsapp_test_send(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies: list[dict[str, Any]] = []

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    def accept(request: Any, timeout: float) -> Response:
        bodies.append(json.loads(request.data))
        return Response(b'{"messages": [{"id": "wamid.x"}]}')

    monkeypatch.setattr(config_check.urllib.request, "urlopen", accept)
    out = config_check.send_whatsapp(_real(), "9000000101")
    assert out.startswith("accepted by Meta") and "9000000101" not in out
    assert bodies[0]["to"] == "919000000101"
    assert bodies[0]["template"]["name"] == "hello_world"

    def refuse(request: Any, timeout: float) -> Response:
        raise urllib.error.HTTPError(
            "u", 400, "bad", {}, io.BytesIO(b'{"error": {"type": "T", "code": 131030}}')
        )

    monkeypatch.setattr(config_check.urllib.request, "urlopen", refuse)
    assert config_check.send_whatsapp(_real(), "9000000101").startswith("FAILED: HTTP 400")


def test_m7c_p6_main_prints_and_fails_on_a_failed_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(config_check, "load_settings", _real)
    monkeypatch.setattr(config_check, "check_whatsapp", lambda s: "FAILED: HTTP 401")
    monkeypatch.setattr(config_check, "check_email", lambda s: "ok")
    monkeypatch.setattr(config_check, "check_google", lambda s: "ok")
    monkeypatch.setattr(config_check, "check_llm", lambda s: "ok")
    assert config_check.main([]) == 0
    assert config_check.main(["--live"]) == 1
    out = capsys.readouterr().out
    assert "Live checks:" in out
    assert all(secret not in out for secret in SECRETS.values())
