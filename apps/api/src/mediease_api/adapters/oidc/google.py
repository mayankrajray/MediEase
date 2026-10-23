"""Google as an OpenID Connect provider (M6a-P3, ADR-0015 decision 3).

Authorization Code flow with PKCE (S256), run by the API: no Google script on our pages. The ID
token from the token endpoint is verified here before anything trusts it:

- the signature, RS256 only, against Google's published keys (JWKS, cached for an hour and
  re-read once when a token names a key we do not have, which is how Google rotates);
- ``iss`` (``https://accounts.google.com`` or ``accounts.google.com``), ``aud`` (our client ID),
  ``exp`` and ``iat`` with 30 seconds of leeway, and ``sub``;
- ``nonce``, against the one sealed in this sign-in's flow cookie.

Built on PyJWT (already used for our tokens) and ``urllib``; no new dependency. The HTTP
transport is injectable so tests never reach the network.
"""

from __future__ import annotations

import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

import jwt

from mediease_api.ports.oidc import OidcFailed, OidcIdentity

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
SCOPE = "openid email profile"
LEEWAY_SECONDS = 30
_JWKS_TTL_SECONDS = 3600
_TIMEOUT_SECONDS = 10.0

# (method, url, form body or None) -> (status, body). Raises OSError when there is no answer.
Transport = Callable[[str, str, Mapping[str, str] | None], tuple[int, bytes]]


def urllib_transport(method: str, url: str, form: Mapping[str, str] | None) -> tuple[int, bytes]:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return int(response.status), bytes(response.read())
    except urllib.error.HTTPError as exc:
        return int(exc.code), bytes(exc.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OSError("google unreachable") from exc


class GoogleOidcProvider:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        transport: Transport = urllib_transport,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport
        self._clock = clock
        self._keys: jwt.PyJWKSet | None = None
        self._keys_read_at = 0.0

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
        login_hint: str | None,
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        if login_hint:
            params["login_hint"] = login_hint
        return f"{AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}"

    def exchange(
        self, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OidcIdentity:
        try:
            status, body = self._transport(
                "POST",
                TOKEN_ENDPOINT,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                },
            )
        except OSError:
            raise OidcFailed("token_unreachable") from None
        if status != 200:
            raise OidcFailed("token_refused")
        payload = _json(body)
        id_token = payload.get("id_token") if payload else None
        if not isinstance(id_token, str):
            raise OidcFailed("token_malformed")
        return self.verify_id_token(id_token, nonce=nonce)

    def verify_id_token(self, id_token: str, *, nonce: str) -> OidcIdentity:
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError:
            raise OidcFailed("id_token_malformed") from None
        if header.get("alg") != "RS256":
            raise OidcFailed("id_token_algorithm")
        key = self._signing_key(header.get("kid"))
        try:
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=ISSUERS,
                leeway=LEEWAY_SECONDS,
                options={"require": ["iss", "aud", "exp", "iat", "sub"]},
            )
        except jwt.PyJWTError:
            raise OidcFailed("id_token_invalid") from None
        if not hmac.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
            raise OidcFailed("nonce_mismatch")
        subject, email = claims.get("sub"), claims.get("email")
        if not isinstance(subject, str) or not subject or not isinstance(email, str):
            raise OidcFailed("id_token_claims")
        verified = claims.get("email_verified")
        name = claims.get("name")
        return OidcIdentity(
            subject=subject,
            email=email,
            email_verified=verified is True or verified == "true",
            name=name if isinstance(name, str) else None,
        )

    def _signing_key(self, kid: object) -> Any:
        if not isinstance(kid, str) or not kid:
            raise OidcFailed("id_token_no_kid")
        stale = self._keys is None or self._clock() - self._keys_read_at > _JWKS_TTL_SECONDS
        if stale:
            self._read_keys()
        found = self._find(kid)
        if found is None and not stale:
            self._read_keys()  # Google rotated its keys since we last looked
            found = self._find(kid)
        if found is None:
            raise OidcFailed("id_token_unknown_kid")
        return found

    def _find(self, kid: str) -> Any:
        assert self._keys is not None
        for key in self._keys.keys:
            if key.key_id == kid:
                return key.key
        return None

    def _read_keys(self) -> None:
        try:
            status, body = self._transport("GET", JWKS_URI, None)
        except OSError:
            raise OidcFailed("jwks_unreachable") from None
        payload = _json(body) if status == 200 else None
        if payload is None:
            raise OidcFailed("jwks_refused")
        try:
            self._keys = jwt.PyJWKSet.from_dict(payload)
        except jwt.PyJWTError:
            raise OidcFailed("jwks_malformed") from None
        self._keys_read_at = self._clock()


def _json(body: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None
