"""Send one operational alert email to OPS_ALERT_EMAIL (M9-P2; RUNBOOK §41).

Used by ``scripts/watch.sh`` on the VM, and by ``make alert-test`` to check delivery:

    python -m mediease_api.delivery.cli.ops_alert --subject "1 problem" < body.txt
    python -m mediease_api.delivery.cli.ops_alert --test

The body comes on stdin. It is the watch's own summary: service names, counts and error codes,
never a name, phone number or clinical detail (NFR-07). As a second guard, only printable
characters are kept and the body is cut at 8,000 characters. Sent through the same email settings
as account emails (``EMAIL_PROVIDER``, ``SMTP_*``).

Exit codes: 0 sent; 1 the provider refused or could not be reached; 2 a usage problem;
3 ``OPS_ALERT_EMAIL`` is not set (nothing was sent).
"""

from __future__ import annotations

import argparse
import html
import sys
from collections.abc import Sequence
from typing import TextIO

from mediease_api.bootstrap import build_email
from mediease_api.config.logging import configure_logging
from mediease_api.config.settings import load_settings
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.ports.email import EmailFailed, EmailMessage

SUBJECT_PREFIX = "[MediEase alert] "
MAX_SUBJECT = 120
MAX_BODY = 8000
_PRE = '<pre style="font: 14px/1.5 monospace; white-space: pre-wrap">'
TEST_SUBJECT = "Test alert"
TEST_BODY = (
    "This is a test from make alert-test. If you can read it, MediEase can reach you with alerts.\n"
)


def clean(text: str, limit: int, *, lines: bool) -> str:
    """Printable characters only (tabs and, for the body, newlines kept), cut at ``limit``."""
    keep = "\n\t" if lines else ""
    kept = "".join(c if c.isprintable() or c in keep else " " for c in text)
    return kept[:limit].strip()


def message_for(to: EmailAddress, subject: str, body: str, host: str) -> EmailMessage:
    subject = clean(subject, MAX_SUBJECT, lines=False) or "Alert"
    body = clean(body, MAX_BODY, lines=True)
    footer = f"\n\n-- \nSent by the MediEase watch on {host}. RUNBOOK §41 explains each alert.\n"
    text = body + footer
    return EmailMessage(
        to=to,
        subject=SUBJECT_PREFIX + subject,
        text=text,
        html=f"{_PRE}{html.escape(text)}</pre>",
    )


def main(argv: Sequence[str] | None = None, *, stdin: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--subject", help="the alert's subject (the body comes on stdin)")
    parser.add_argument("--test", action="store_true", help="send a fixed test message")
    args = parser.parse_args(argv)
    if args.test == bool(args.subject):
        print("ops-alert: give either --subject (body on stdin) or --test", file=sys.stderr)
        return 2

    settings = load_settings()
    configure_logging(settings)
    if not settings.OPS_ALERT_EMAIL:
        print("ops-alert: OPS_ALERT_EMAIL is not set; nothing sent", file=sys.stderr)
        return 3
    try:
        to = EmailAddress.parse(settings.OPS_ALERT_EMAIL, field="OPS_ALERT_EMAIL")
    except InvalidValue:
        print("ops-alert: OPS_ALERT_EMAIL is not a valid address; nothing sent", file=sys.stderr)
        return 2

    subject, body = (
        (TEST_SUBJECT, TEST_BODY) if args.test else (args.subject, (stdin or sys.stdin).read())
    )
    host = settings.PUBLIC_BASE_URL.split("://", 1)[-1].rstrip("/") or settings.APP_ENV.value
    try:
        build_email(settings).send(message_for(to, subject, body, host))
    except ValueError as exc:  # e.g. EMAIL_PROVIDER=console in production
        print(f"ops-alert: {exc}; nothing sent", file=sys.stderr)
        return 1
    except EmailFailed as exc:
        print(f"ops-alert: the email provider refused it ({exc.reason})", file=sys.stderr)
        return 1
    print(f"ops-alert: sent to {to.masked()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
