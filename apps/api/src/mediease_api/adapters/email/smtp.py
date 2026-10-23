"""Email over SMTP with the standard library (M6a-P4, ADR-0016 decision 1).

One adapter for every provider that speaks SMTP: Brevo, Resend and Amazon SES in production
(STARTTLS on 587 or implicit TLS on 465, with a login), and Mailpit on the local stack (no TLS,
allowed only in local and test by the settings). A multipart text-and-HTML message, with no
tracking headers.

Failures are sorted for the job queue: a connection problem, a timeout or a 4xx answer is worth
retrying; a refused login, a refused recipient or another 5xx is not.
"""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage as MimeMessage
from email.utils import make_msgid
from typing import Literal

import structlog

from mediease_api.ports.email import EmailFailed, EmailMessage

logger = structlog.get_logger(__name__)

SmtpSecurity = Literal["starttls", "tls", "none"]
_TIMEOUT_SECONDS = 15.0


class SmtpEmailAdapter:
    provider = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        security: SmtpSecurity,
        sender: str,
        username: str = "",
        password: str = "",
        smtp_factory: Callable[..., smtplib.SMTP] | None = None,
        ssl_factory: Callable[..., smtplib.SMTP] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._security = security
        self._sender = sender
        self._username = username
        self._password = password
        self._smtp = smtp_factory or smtplib.SMTP
        self._smtp_ssl = ssl_factory or smtplib.SMTP_SSL

    def send(self, message: EmailMessage) -> None:
        mime = self._mime(message)
        try:
            with self._connect() as client:
                if self._security == "starttls":
                    client.starttls(context=ssl.create_default_context())
                if self._username:
                    client.login(self._username, self._password)
                client.send_message(mime)
        except smtplib.SMTPAuthenticationError:
            raise EmailFailed("smtp_auth_refused", retryable=False) from None
        except smtplib.SMTPRecipientsRefused:
            raise EmailFailed("smtp_recipient_refused", retryable=False) from None
        except smtplib.SMTPResponseException as exc:
            retryable = 400 <= exc.smtp_code < 500
            raise EmailFailed(f"smtp_{exc.smtp_code}", retryable=retryable) from None
        except (TimeoutError, smtplib.SMTPException, OSError):
            raise EmailFailed("smtp_unreachable", retryable=True) from None
        logger.info("email.sent", provider=self.provider, to=message.to.masked())

    def _connect(self) -> smtplib.SMTP:
        if self._security == "tls":
            return self._smtp_ssl(
                self._host,
                self._port,
                timeout=_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            )
        return self._smtp(self._host, self._port, timeout=_TIMEOUT_SECONDS)

    def _mime(self, message: EmailMessage) -> MimeMessage:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to.value
        mime["Subject"] = message.subject
        mime["Message-ID"] = make_msgid(domain=self._sender.rpartition("@")[2].rstrip(">") or None)
        mime["Auto-Submitted"] = "auto-generated"
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")
        return mime
