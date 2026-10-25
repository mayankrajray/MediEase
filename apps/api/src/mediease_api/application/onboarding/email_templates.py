"""The words of an application's emails (M6c-P1; spec clinic-onboarding R12, R19, R23).

English only in M6c (D2). They name the reference and the clinic only: never a doctor, a
registration number or the owner's phone. The "received" email promises a reply within 2 working
days (D3), as the form does.
"""

from __future__ import annotations

import html

from mediease_api.application.auth.email_templates import Rendered

# D3: the same words on the form, the "Check your email" page and the "received" email.
REPLY_PROMISE = (
    "MediEase checks each doctor's registration by hand and will reply by email within"
    " 2 working days."
)


def _page(paragraphs: list[str], link: tuple[str, str] | None = None) -> str:
    body = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    if link is not None:
        label, url = link
        safe = html.escape(url, quote=True)
        body += (
            f'<p><a href="{safe}" style="display:inline-block;padding:10px 16px;'
            f'background:#0f766e;color:#ffffff;text-decoration:none;border-radius:8px">'
            f"{html.escape(label)}</a></p>"
            f'<p style="color:#475569;font-size:13px">Or copy this link: {safe}</p>'
        )
    return (
        '<!doctype html><html><body style="font-family:system-ui,sans-serif;color:#0f172a">'
        f'{body}<p style="color:#475569;font-size:13px">MediEase</p></body></html>'
    )


def confirm_application(name: str, clinic: str, reference: str, link: str) -> Rendered:
    hello = f"Hello {name},"
    lines = [
        f"Please confirm your email to send application {reference} for {clinic} to MediEase.",
        "The link works once and expires 48 hours after you applied.",
        "If you did not apply to join MediEase, you can ignore this email; nothing is sent"
        " without it.",
    ]
    return Rendered(
        subject=f"Confirm your MediEase application {reference}",
        text="\n\n".join([hello, lines[0], link, *lines[1:], "MediEase"]),
        html=_page([hello, *lines], ("Confirm my application", link)),
    )


def application_received(name: str, clinic: str, reference: str) -> Rendered:
    hello = f"Hello {name},"
    lines = [
        f"Thank you. We received application {reference} for {clinic}.",
        REPLY_PROMISE,
        "Please keep this reference if you write to us.",
    ]
    return Rendered(
        subject=f"We received your MediEase application {reference}",
        text="\n\n".join([hello, *lines, "MediEase"]),
        html=_page([hello, *lines]),
    )
