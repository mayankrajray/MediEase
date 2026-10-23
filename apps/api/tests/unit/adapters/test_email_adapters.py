"""The SMTP adapter against a fake smtplib, and the email wiring (M6a-P4, ADR-0016 1, 3)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage as MimeMessage
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from mediease_api.adapters.email.console import ConsoleEmailAdapter
from mediease_api.adapters.email.smtp import SmtpEmailAdapter
from mediease_api.application.auth import email_templates
from mediease_api.bootstrap import build_email
from mediease_api.config.settings import AppSettings
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.ports.email import EmailFailed, EmailMessage
from tests.conftest import SetEnv

LINK = "https://app.example/reset-password/secret-token-value"
MESSAGE = EmailMessage(
    to=EmailAddress.parse("asha@example.test"),
    subject="Reset your MediEase password",
    text=f"Hello\n\n{LINK}",
    html=f'<a href="{LINK}">Reset</a>',
)


class FakeSmtp:
    """Records what the adapter asked of smtplib; ``next_failure`` raises at ``send_message``."""

    instances: ClassVar[list[FakeSmtp]] = []
    next_failure: ClassVar[Exception | None] = None

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.calls: list[str] = []
        self.sent: list[MimeMessage] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kwargs: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}")

    def send_message(self, message: MimeMessage) -> None:
        if FakeSmtp.next_failure is not None:
            raise FakeSmtp.next_failure
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _reset() -> None:
    FakeSmtp.instances.clear()
    FakeSmtp.next_failure = None


def _adapter(security: str = "starttls", username: str = "apikey") -> SmtpEmailAdapter:
    return SmtpEmailAdapter(
        host="smtp-relay.example",
        port=587,
        security=security,  # type: ignore[arg-type]
        sender="MediEase <no-reply@mediease.example>",
        username=username,
        password="synthetic-smtp-password",  # gitleaks:allow
        smtp_factory=FakeSmtp,  # type: ignore[arg-type]
        ssl_factory=FakeSmtp,  # type: ignore[arg-type]
    )


def test_adr_0016_starttls_login_then_a_text_and_html_message() -> None:
    _adapter().send(MESSAGE)
    smtp = FakeSmtp.instances[0]
    assert (smtp.host, smtp.port) == ("smtp-relay.example", 587)
    assert smtp.calls == ["starttls", "login:apikey", "quit"]
    sent = smtp.sent[0]
    assert sent["To"] == "asha@example.test"
    assert sent["From"] == "MediEase <no-reply@mediease.example>"
    assert sent["Auto-Submitted"] == "auto-generated"
    assert [p.get_content_type() for p in sent.iter_parts()] == ["text/plain", "text/html"]


def test_mailpit_needs_neither_tls_nor_a_login() -> None:
    _adapter(security="none", username="").send(MESSAGE)
    assert FakeSmtp.instances[0].calls == ["quit"]


@pytest.mark.parametrize(
    ("failure", "reason", "retryable"),
    [
        (smtplib.SMTPAuthenticationError(535, b"bad"), "smtp_auth_refused", False),
        (
            smtplib.SMTPRecipientsRefused({"a@example.test": (550, b"no")}),
            "smtp_recipient_refused",
            False,
        ),
        (smtplib.SMTPDataError(451, b"try later"), "smtp_451", True),
        (smtplib.SMTPDataError(554, b"rejected"), "smtp_554", False),
        (smtplib.SMTPServerDisconnected("gone"), "smtp_unreachable", True),
        (TimeoutError("slow"), "smtp_unreachable", True),
    ],
)
def test_adr_0016_failures_are_sorted_for_the_job_queue(
    failure: Exception, reason: str, retryable: bool
) -> None:
    FakeSmtp.next_failure = failure
    with pytest.raises(EmailFailed) as raised:
        _adapter().send(MESSAGE)
    assert (raised.value.reason, raised.value.retryable) == (reason, retryable)


def test_no_log_line_or_repr_carries_the_link(json_logs: Any) -> None:
    _adapter().send(MESSAGE)
    ConsoleEmailAdapter().send(MESSAGE)
    lines = str(json_logs())
    assert "secret-token-value" not in lines
    assert "asha@example.test" not in lines  # masked: a***@example.test
    assert "secret-token-value" not in repr(MESSAGE)


def test_templates_escape_names_and_carry_no_clinical_words() -> None:
    rendered = email_templates.reset_password("<b>Asha</b>", LINK)
    assert "<b>Asha</b>" not in rendered.html
    assert "&lt;b&gt;Asha&lt;/b&gt;" in rendered.html
    assert LINK in rendered.text and LINK in rendered.html
    changed = email_templates.password_changed("Asha")
    assert "http" not in changed.text  # no link to click in a "your password changed" email


def test_adr_0016_console_is_refused_in_production(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env({**valid_env, "APP_ENV": "test"})
    assert isinstance(build_email(AppSettings()), ConsoleEmailAdapter)  # type: ignore[call-arg]
    set_env({"APP_ENV": "production", "COOKIE_SECURE": "true"})
    with pytest.raises(ValueError, match="EMAIL_PROVIDER=console"):
        build_email(AppSettings())  # type: ignore[call-arg]


def test_smtp_needs_a_host_and_tls_when_deployed(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env({**valid_env, "EMAIL_PROVIDER": "smtp"})
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        AppSettings()  # type: ignore[call-arg]
    set_env(
        {
            "SMTP_HOST": "smtp-relay.example",
            "SMTP_SECURITY": "none",
            "APP_ENV": "staging",
            "COOKIE_SECURE": "true",
        }
    )
    with pytest.raises(ValidationError, match="SMTP_SECURITY"):
        AppSettings()  # type: ignore[call-arg]
    set_env({"SMTP_SECURITY": "starttls"})
    assert isinstance(build_email(AppSettings()), SmtpEmailAdapter)  # type: ignore[call-arg]
