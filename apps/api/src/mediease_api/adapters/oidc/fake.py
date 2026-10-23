"""A stand-in for Google on the local stack and in tests (M6a-P3, ADR-0015 decision 6).

``GOOGLE_OIDC_PROVIDER=fake`` is allowed only with ``APP_ENV`` ``local`` or ``test``: the
composition root refuses to start with it anywhere else (``bootstrap.build_oidc``).

It skips Google: the "authorization URL" goes straight back to our callback, on the same origin
the browser is on, with a code that carries the ``login_hint`` email and the nonce. The callback
then runs exactly the same checks, matching and cookie code as with Google, and ``exchange``
returns a synthetic *verified* identity for that email. Without a ``login_hint`` the code is
refused, so the person sees the usual "Google sign-in did not work" message.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.parse

from mediease_api.ports.oidc import OidcFailed, OidcIdentity

_PREFIX = "fake."


class FakeOidcProvider:
    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
        login_hint: str | None,
    ) -> str:
        payload = json.dumps({"email": login_hint or "", "nonce": nonce}).encode()
        code = _PREFIX + base64.urlsafe_b64encode(payload).decode().rstrip("=")
        # Path only: the browser stays on whichever origin it used (localhost, or web:3000 in e2e).
        path = urllib.parse.urlsplit(redirect_uri).path
        return f"{path}?{urllib.parse.urlencode({'state': state, 'code': code})}"

    def exchange(
        self, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OidcIdentity:
        if not code.startswith(_PREFIX):
            raise OidcFailed("fake_code_malformed")
        encoded = code.removeprefix(_PREFIX)
        try:
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            email, sent_nonce = str(payload["email"]), str(payload["nonce"])
        except (ValueError, KeyError, TypeError):
            raise OidcFailed("fake_code_malformed") from None
        if not hmac.compare_digest(sent_nonce.encode(), nonce.encode()):
            raise OidcFailed("nonce_mismatch")
        if not email:
            raise OidcFailed("fake_login_hint_missing")
        normalised = email.strip().lower()
        local = normalised.partition("@")[0]
        return OidcIdentity(
            subject="fake-" + hashlib.sha256(normalised.encode()).hexdigest()[:32],
            email=normalised,
            email_verified=True,
            name=" ".join(part.capitalize() for part in local.replace("_", ".").split(".") if part)
            or None,
        )
