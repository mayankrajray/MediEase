"""OpenID Connect port: Google sign-in through the API (M6a-P3, ADR-0015 decision 3).

The application decides *who* a verified identity is (``application/auth/google.py``); the
adapter decides *how* to talk to the provider: the authorization URL, the code exchange and the
ID token checks (signature against the provider's keys, ``iss``, ``aud``, ``exp``, ``nonce``).
``GOOGLE_OIDC_PROVIDER`` chooses Google or the local-only fake (decision 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mediease_api.domain.shared.errors import DomainError


@dataclass(frozen=True, slots=True)
class OidcIdentity:
    """What a verified ID token proves. ``email`` is as the provider sent it, not yet parsed."""

    subject: str
    email: str
    email_verified: bool
    name: str | None

    def __repr__(self) -> str:
        return f"OidcIdentity(subject=<redacted>, email_verified={self.email_verified})"


class OidcFailed(DomainError):
    """The provider refused, or its answer did not verify. ``reason`` is an enum for the log."""

    code = "AUTH_GOOGLE_FAILED"

    def __init__(self, reason: str) -> None:
        super().__init__("Google sign-in did not work. Try again.", reason=reason)
        self.reason = reason


class OidcPort(Protocol):
    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
        login_hint: str | None,
    ) -> str:
        """Where to send the browser (PKCE S256 ``code_challenge``)."""
        ...

    def exchange(
        self, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OidcIdentity:
        """Swap the code for a verified identity, or raise ``OidcFailed``."""
        ...
