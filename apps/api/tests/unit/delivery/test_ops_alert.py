"""``ops_alert`` sends the watch's alerts to OPS_ALERT_EMAIL (M9-P2; RUNBOOK §41).

Synthetic addresses only; the email adapter is replaced by the console one, which keeps what it
was given.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from mediease_api.adapters.email.console import ConsoleEmailAdapter
from mediease_api.config.settings import AppSettings
from mediease_api.delivery.cli import config_check, ops_alert
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.ports.email import EmailFailed, EmailMessage


def _settings(**values: Any) -> AppSettings:
    base: dict[str, Any] = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "JWT_SIGNING_KEY": SecretStr("x" * 40),
        "AUDIT_IP_SALT": SecretStr("y" * 40),
        "PUBLIC_BASE_URL": "https://mediease.example.test",
        "OPS_ALERT_EMAIL": "ops.alerts@example.test",
    }
    base.update(values)
    return AppSettings(**base)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> ConsoleEmailAdapter:
    adapter = ConsoleEmailAdapter()
    monkeypatch.setattr(ops_alert, "build_email", lambda _settings: adapter)
    monkeypatch.setattr(ops_alert, "configure_logging", lambda _settings: None)
    return adapter


def _use(monkeypatch: pytest.MonkeyPatch, settings: AppSettings) -> None:
    monkeypatch.setattr(ops_alert, "load_settings", lambda: settings)


def test_m9_p2_a_test_alert_reaches_the_ops_address(
    monkeypatch: pytest.MonkeyPatch, outbox: ConsoleEmailAdapter, capsys: pytest.CaptureFixture[str]
) -> None:
    _use(monkeypatch, _settings())
    assert ops_alert.main(["--test"]) == 0
    [message] = outbox.sent
    assert message.to.value == "ops.alerts@example.test"
    assert message.subject == "[MediEase alert] Test alert"
    assert "make alert-test" in message.text and "mediease.example.test" in message.text
    assert "o***@example.test" in capsys.readouterr().out  # masked, never the full address


def test_m9_p2_the_watch_body_comes_on_stdin_printable_and_bounded(
    monkeypatch: pytest.MonkeyPatch, outbox: ConsoleEmailAdapter
) -> None:
    _use(monkeypatch, _settings())
    body = "New problems:\n  - [critical] api is not running\x1b[31m\x00\n" + "x" * 20_000
    assert ops_alert.main(["--subject", "1 new\r\nBcc: someone"], stdin=io.StringIO(body)) == 0
    [message] = outbox.sent
    assert (
        message.subject == "[MediEase alert] 1 new  Bcc: someone"
    )  # one line: no header injection
    assert "\x1b" not in message.text and "\x00" not in message.text
    assert "[critical] api is not running" in message.text
    assert len(message.text) < ops_alert.MAX_BODY + 200


def test_m9_p2_the_html_part_escapes_the_body() -> None:
    to = EmailAddress.parse("ops.alerts@example.test")
    message = ops_alert.message_for(to, "s", "<b>x</b>", "h")
    assert "&lt;b&gt;x&lt;/b&gt;" in message.html and "<b>" not in message.html


def test_m9_p2_without_an_address_nothing_is_sent(
    monkeypatch: pytest.MonkeyPatch, outbox: ConsoleEmailAdapter, capsys: pytest.CaptureFixture[str]
) -> None:
    _use(monkeypatch, _settings(OPS_ALERT_EMAIL=""))
    assert ops_alert.main(["--test"]) == 3
    assert outbox.sent == []
    assert "OPS_ALERT_EMAIL is not set" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["--test", "--subject", "x"]])
def test_m9_p2_either_a_subject_or_the_test(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, outbox: ConsoleEmailAdapter
) -> None:
    _use(monkeypatch, _settings())
    assert ops_alert.main(argv) == 2
    assert outbox.sent == []


def test_m9_p2_a_refusing_provider_fails_the_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Refusing:
        provider = "smtp"

        def send(self, message: EmailMessage) -> None:
            raise EmailFailed("smtp_unreachable", retryable=True)

    _use(monkeypatch, _settings())
    monkeypatch.setattr(ops_alert, "build_email", lambda _settings: Refusing())
    monkeypatch.setattr(ops_alert, "configure_logging", lambda _settings: None)
    assert ops_alert.main(["--test"]) == 1
    assert "smtp_unreachable" in capsys.readouterr().err


def test_m9_p2_the_console_adapter_is_refused_in_production(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings()
    monkeypatch.setattr(ops_alert, "load_settings", lambda: settings)
    monkeypatch.setattr(ops_alert, "configure_logging", lambda _settings: None)

    def refuse(_settings: AppSettings) -> Any:
        raise ValueError("EMAIL_PROVIDER=console sends nothing; refused in production")

    monkeypatch.setattr(ops_alert, "build_email", refuse)
    assert ops_alert.main(["--test"]) == 1
    assert "refused in production" in capsys.readouterr().err


@pytest.mark.parametrize(
    "raw", ["two@example.test,three@example.test", "Ops <ops@example.test>", "no-at-sign", "a@b"]
)
def test_m9_p2_ops_alert_email_is_one_plain_address(raw: str) -> None:
    with pytest.raises(ValidationError, match="OPS_ALERT_EMAIL"):
        _settings(OPS_ALERT_EMAIL=raw)


def test_m9_p2_config_check_shows_the_alert_address_masked() -> None:
    text = "\n".join(" ".join(line) for line in config_check.describe(_settings()))
    assert "alerts OPS_ALERT_EMAIL o***@example.test" in text
    assert "ops.alerts@" not in text
    unset = "\n".join(
        " ".join(line) for line in config_check.describe(_settings(OPS_ALERT_EMAIL=""))
    )
    assert "alerts OPS_ALERT_EMAIL NOT SET" in unset
