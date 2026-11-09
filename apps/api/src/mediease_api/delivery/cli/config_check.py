"""Which real services this configuration uses, and whether their credentials work (M7c-P6).

``make config-check`` prints, per service, the adapter the settings select and the non-secret
details (hosts, models, the Google redirect URI to register). It never prints a secret: keys,
tokens and passwords are reported only as set or not set. This lets the developer and the agent
check real configuration without anyone opening ``.env``.

``--live`` also calls each real service once without changing anything: Meta's Graph API reads
the WhatsApp number's name and quality rating, the SMTP relay is logged in to (nothing is sent),
the model is asked for one word, and Google's sign-in discovery document is fetched.

``--email-to`` and ``--whatsapp-to`` send one test message (an email, or Meta's approved
``hello_world`` template) to an address or number the developer types; it is masked in the output
and stored nowhere.
"""

from __future__ import annotations

import argparse
import json
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from email.message import EmailMessage

from mediease_api.adapters.llm.openai_compatible import PRESETS, USER_AGENT
from mediease_api.bootstrap import build_llm
from mediease_api.config.settings import AppSettings, load_settings
from mediease_api.domain.assistant.llm import ChatMessage, LlmBusy, LlmUnavailable
from mediease_api.domain.shared.phone import PhoneNumber

_GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"
_TIMEOUT = 15.0

Line = tuple[str, str, str]  # (service, what, value)


def _set(secret: object) -> str:
    raw = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
    return "set" if raw else "NOT SET"


def _last4(value: str) -> str:
    return f"…{value[-4:]}" if len(value) > 4 else ("set" if value else "NOT SET")


def describe(s: AppSettings) -> list[Line]:
    """What the settings select, without any secret value."""
    lines: list[Line] = [
        ("app", "APP_ENV", s.APP_ENV.value),
        ("app", "PUBLIC_BASE_URL", s.PUBLIC_BASE_URL),
        ("app", "COOKIE_SECURE", str(s.COOKIE_SECURE).lower()),
        ("storage", "BLOB_STORAGE", s.BLOB_STORAGE),
        ("whatsapp", "MESSAGING_PROVIDER", s.MESSAGING_PROVIDER),
    ]
    if s.MESSAGING_PROVIDER == "whatsapp_cloud":
        lines += [
            ("whatsapp", "WHATSAPP_PHONE_NUMBER_ID", _last4(s.WHATSAPP_PHONE_NUMBER_ID)),
            ("whatsapp", "WHATSAPP_ACCESS_TOKEN", _set(s.WHATSAPP_ACCESS_TOKEN)),
            ("whatsapp", "WHATSAPP_APP_SECRET", _set(s.WHATSAPP_APP_SECRET)),
            ("whatsapp", "WHATSAPP_VERIFY_TOKEN", _set(s.WHATSAPP_VERIFY_TOKEN)),
            ("whatsapp", "Graph API", f"{s.WHATSAPP_GRAPH_URL}/{s.WHATSAPP_API_VERSION}"),
            ("whatsapp", "webhook URL to register", "<public API URL>/webhooks/whatsapp"),
        ]
    lines.append(("sms", "MESSAGING_SMS_FALLBACK_ENABLED", str(s.MESSAGING_SMS_FALLBACK_ENABLED)))
    lines.append(("email", "EMAIL_PROVIDER", s.EMAIL_PROVIDER))
    if s.EMAIL_PROVIDER == "smtp":
        lines += [
            ("email", "SMTP", f"{s.SMTP_HOST}:{s.SMTP_PORT} ({s.SMTP_SECURITY})"),
            ("email", "SMTP_USERNAME", "set" if s.SMTP_USERNAME else "NOT SET"),
            ("email", "SMTP_PASSWORD", _set(s.SMTP_PASSWORD)),
            ("email", "EMAIL_FROM", s.EMAIL_FROM),
        ]
    lines.append(("google", "GOOGLE_OIDC_PROVIDER", s.GOOGLE_OIDC_PROVIDER))
    if s.GOOGLE_OIDC_PROVIDER == "google":
        lines += [
            ("google", "GOOGLE_CLIENT_ID", "set" if s.GOOGLE_CLIENT_ID else "NOT SET"),
            ("google", "GOOGLE_CLIENT_SECRET", _set(s.GOOGLE_CLIENT_SECRET)),
            (
                "google",
                "redirect URI to register",
                f"{s.PUBLIC_BASE_URL.rstrip('/')}/api/v1/auth/google/callback",
            ),
        ]
    lines.append(("llm", "LLM_PROVIDER", s.LLM_PROVIDER))
    preset = PRESETS.get(s.LLM_PROVIDER)
    if preset is not None:
        lines += [
            ("llm", "base URL", s.LLM_BASE_URL or preset.base_url),
            ("llm", "model", s.LLM_MODEL or preset.model),
            ("llm", "LLM_API_KEY", _set(s.LLM_API_KEY)),
            ("llm", "LLM_PATIENT_DATA_ALLOWED", str(s.LLM_PATIENT_DATA_ALLOWED).lower()),
        ]
    return lines


# --- Live checks (nothing is changed or stored) ---------------------------------------------------


def _get(url: str, token: str | None = None) -> tuple[int, dict[str, object]]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read() or b"{}")
        except ValueError:
            body = {}
        return error.code, body


def _graph_error(body: dict[str, object]) -> str:
    error = body.get("error")
    if isinstance(error, dict):
        return f"{error.get('type', '')} code {error.get('code', '')}: {error.get('message', '')}"
    return "no detail"


def check_whatsapp(s: AppSettings) -> str:
    if s.MESSAGING_PROVIDER != "whatsapp_cloud":
        return "skipped (MESSAGING_PROVIDER=console)"
    url = (
        f"{s.WHATSAPP_GRAPH_URL}/{s.WHATSAPP_API_VERSION}/{s.WHATSAPP_PHONE_NUMBER_ID}"
        "?fields=verified_name,display_phone_number,quality_rating"
    )
    status, body = _get(url, s.WHATSAPP_ACCESS_TOKEN.get_secret_value())
    if status != 200:
        return f"FAILED: HTTP {status} ({_graph_error(body)})"
    number = str(body.get("display_phone_number", ""))
    return (
        f"ok: {body.get('verified_name', '?')}, number {_last4(number.replace(' ', ''))}, "
        f"quality {body.get('quality_rating', '?')}"
    )


def check_email(s: AppSettings) -> str:
    if s.EMAIL_PROVIDER != "smtp":
        return "skipped (EMAIL_PROVIDER=console)"
    try:
        with _smtp(s) as smtp:
            smtp.noop()
    except (OSError, smtplib.SMTPException) as error:
        return f"FAILED: {type(error).__name__}: {error}"
    return f"ok: logged in to {s.SMTP_HOST}" if s.SMTP_USERNAME else f"ok: {s.SMTP_HOST} answers"


def _smtp(s: AppSettings) -> smtplib.SMTP:
    context = ssl.create_default_context()
    smtp: smtplib.SMTP
    if s.SMTP_SECURITY == "tls":
        smtp = smtplib.SMTP_SSL(s.SMTP_HOST, s.SMTP_PORT, timeout=_TIMEOUT, context=context)
    else:
        smtp = smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=_TIMEOUT)
        if s.SMTP_SECURITY == "starttls":
            smtp.starttls(context=context)
    if s.SMTP_USERNAME:
        smtp.login(s.SMTP_USERNAME, s.SMTP_PASSWORD.get_secret_value())
    return smtp


def check_google(s: AppSettings) -> str:
    if s.GOOGLE_OIDC_PROVIDER != "google":
        return "skipped (GOOGLE_OIDC_PROVIDER=fake)"
    status, body = _get(_GOOGLE_DISCOVERY)
    if status != 200 or "authorization_endpoint" not in body:
        return f"FAILED: Google discovery answered HTTP {status}"
    return (
        "ok: Google reachable; the client ID and secret are checked by a real sign-in "
        "(Continue with Google on the sign-in page)"
    )


def check_llm(s: AppSettings) -> str:
    if s.LLM_PROVIDER == "console":
        return "skipped (LLM_PROVIDER=console)"
    try:
        llm = build_llm(s)
        reply = llm.complete(
            [ChatMessage.system("Reply with one word."), ChatMessage.user("Say OK.")], []
        )
    except LlmBusy as busy:
        return f"FAILED: the provider is rate limiting (retry after {busy.retry_after_seconds} s)"
    except (LlmUnavailable, ValueError) as error:
        return f"FAILED: {error} (make logs shows assistant.llm_failed with the status)"
    return f"ok: {llm.provider} {llm.model} answered ({len(reply.content)} characters)"


# --- Test sends -------------------------------------------------------------------------------


def _mask_email(address: str) -> str:
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}"


def send_email(s: AppSettings, to: str) -> str:
    if s.EMAIL_PROVIDER != "smtp":
        return "skipped (EMAIL_PROVIDER=console)"
    message = EmailMessage()
    message["From"] = s.EMAIL_FROM
    message["To"] = to
    message["Subject"] = "MediEase configuration test"
    message.set_content("This is a test message from `make config-check`. No action is needed.")
    try:
        with _smtp(s) as smtp:
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        return f"FAILED: {type(error).__name__}: {error}"
    return f"sent to {_mask_email(to)}; check the inbox and the spam folder"


def send_whatsapp(s: AppSettings, to: str) -> str:
    if s.MESSAGING_PROVIDER != "whatsapp_cloud":
        return "skipped (MESSAGING_PROVIDER=console)"
    phone = PhoneNumber.parse(to, field="whatsapp_to")
    payload = {
        "messaging_product": "whatsapp",
        "to": phone.e164.lstrip("+"),
        "type": "template",
        "template": {"name": "hello_world", "language": {"code": "en_US"}},
    }
    url = f"{s.WHATSAPP_GRAPH_URL}/{s.WHATSAPP_API_VERSION}/{s.WHATSAPP_PHONE_NUMBER_ID}/messages"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {s.WHATSAPP_ACCESS_TOKEN.get_secret_value()}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            body = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            failed = json.loads(error.read() or b"{}")
        except ValueError:
            failed = {}
        return f"FAILED: HTTP {error.code} ({_graph_error(failed)})"
    except OSError as error:
        return f"FAILED: {type(error).__name__}"
    accepted = bool(body.get("messages"))
    return (
        f"accepted by Meta for {phone.masked()}; check the phone" if accepted else "FAILED: no id"
    )


def _print(lines: Sequence[Line]) -> None:
    width = max(len(f"{service} {what}") for service, what, _ in lines)
    for service, what, value in lines:
        print(f"  {f'{service} {what}':<{width}}  {value}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="call each real service once")
    parser.add_argument("--email-to", help="send one test email to this address")
    parser.add_argument("--whatsapp-to", help="send Meta's hello_world template to this number")
    args = parser.parse_args(argv)

    settings = load_settings()
    print("Configuration (secrets are shown only as set / NOT SET):")
    _print(describe(settings))
    failed = False
    checks: list[tuple[str, Callable[[], str]]] = []
    if args.live:
        checks += [
            ("whatsapp", lambda: check_whatsapp(settings)),
            ("email", lambda: check_email(settings)),
            ("google", lambda: check_google(settings)),
            ("llm", lambda: check_llm(settings)),
        ]
    if args.email_to:
        checks.append(("email send", lambda: send_email(settings, args.email_to)))
    if args.whatsapp_to:
        checks.append(("whatsapp send", lambda: send_whatsapp(settings, args.whatsapp_to)))
    if checks:
        print("Live checks:")
        results: list[Line] = []
        for name, run in checks:
            outcome = run()
            failed = failed or outcome.startswith("FAILED")
            results.append((name, "", outcome))
        _print(results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
