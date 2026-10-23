"""The words of the account emails (M6a-P4, ADR-0016 decision 8).

Plain text plus a minimal HTML version, in English. No clinical content, no images, no tracking.
Every link points at ``PUBLIC_BASE_URL``. Names are HTML-escaped.
"""

from __future__ import annotations

import html
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rendered:
    subject: str
    text: str
    html: str


def _page(paragraphs: list[str], link: tuple[str, str] | None) -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
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


def verify_email(name: str, link: str) -> Rendered:
    hello = f"Hello {name},"
    lines = [
        "Please confirm this is your email address for your MediEase health account.",
        "The link works once and expires in 24 hours.",
        "If you did not create a MediEase account, you can ignore this email.",
    ]
    return Rendered(
        subject="Confirm your email for MediEase",
        text="\n\n".join([hello, lines[0], link, *lines[1:], "MediEase"]),
        html=_page([html.escape(hello), *lines], ("Confirm my email", link)),
    )


def reset_password(name: str, link: str) -> Rendered:
    hello = f"Hello {name},"
    lines = [
        "Someone asked to reset the password of your MediEase account.",
        "The link works once and expires in 30 minutes. Signing in elsewhere ends when you"
        " choose a new password.",
        "If this was not you, ignore this email: your password stays the same.",
    ]
    return Rendered(
        subject="Reset your MediEase password",
        text="\n\n".join([hello, lines[0], link, *lines[1:], "MediEase"]),
        html=_page([html.escape(hello), *lines], ("Choose a new password", link)),
    )


def reset_google_only(name: str, sign_in_link: str) -> Rendered:
    hello = f"Hello {name},"
    lines = [
        "Someone asked to reset the password of your MediEase account, but this account signs"
        " in with Google and has no password.",
        "Use Continue with Google on the sign-in page.",
        "If this was not you, you can ignore this email.",
    ]
    return Rendered(
        subject="Your MediEase account signs in with Google",
        text="\n\n".join([hello, *lines, sign_in_link, "MediEase"]),
        html=_page([html.escape(hello), *lines], ("Go to sign-in", sign_in_link)),
    )


def password_changed(name: str) -> Rendered:
    hello = f"Hello {name},"
    lines = [
        "The password of your MediEase account was just changed, and every other signed-in"
        " session was ended.",
        "If this was not you, reset your password again at once and tell MediEase support.",
    ]
    return Rendered(
        subject="Your MediEase password was changed",
        text="\n\n".join([hello, *lines, "MediEase"]),
        html=_page([html.escape(hello), *lines], None),
    )


def staff_invite(name: str, clinic_name: str, role_label: str, link: str) -> Rendered:
    """M6a-P5: an owner's invitation to join their clinic (FR-AUTH-08)."""
    hello = f"Hello {name},"
    invited = f"You have been invited to join {clinic_name} on MediEase as {role_label}."
    lines = [
        "Open the link to set up your account. If you already use MediEase, sign in with your"
        " current password to add this clinic.",
        "The link works once and expires in 7 days. If it has expired, ask the clinic to send"
        " the invitation again.",
        "If you were not expecting this, you can ignore this email.",
    ]
    return Rendered(
        subject=f"Join {clinic_name} on MediEase",
        text="\n\n".join([hello, invited, link, *lines, "MediEase"]),
        html=_page(
            [html.escape(hello), html.escape(invited), *lines], ("Accept the invitation", link)
        ),
    )
