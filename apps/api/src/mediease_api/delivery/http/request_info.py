"""What delivery knows about the call itself: its ID and the caller's fingerprint.

One ``before_request`` hook builds a ``RequestInfo`` (``application/context.py``)
for every request, so use cases receive the request ID and a salted IP
fingerprint explicitly instead of reaching into Flask (apps/api/CLAUDE.md).

The address (M7e, A11; ARCHITECTURE §9 "Client address"). Every browser request
reaches the API through the web server, so ``request.remote_addr`` is the web
server, and per-address limits would be shared by every patient. The web server
therefore sends the browser's address in ``X-MediEase-Client-IP`` with the shared
``X-MediEase-Proxy-Secret``. The address is used only when the secret matches
``TRUSTED_PROXY_SECRET`` and the value is a valid IP address. In every other case
(no secret configured, a missing or wrong secret, a malformed address) the
connection's own address is used, as before A11. A browser cannot set these
headers: the web server's proxy removes them from every incoming request.
"""

from __future__ import annotations

import hmac
import ipaddress

from flask import Flask, g, request

from mediease_api.application.context import RequestInfo
from mediease_api.delivery.middleware import get_request_id
from mediease_api.ports.security import IpHasher

_REQUEST_INFO = "mediease_request_info"
CLIENT_IP_HEADER = "X-MediEase-Client-IP"
PROXY_SECRET_HEADER = "X-MediEase-Proxy-Secret"


def client_address(
    remote_addr: str | None, sent_secret: str | None, claimed: str | None, proxy_secret: str
) -> str | None:
    """The browser's address when the trusted web server vouches for it, else the connection's."""
    if not proxy_secret or not sent_secret:
        return remote_addr
    if not hmac.compare_digest(sent_secret.encode(), proxy_secret.encode()):
        return remote_addr
    try:
        return str(ipaddress.ip_address((claimed or "").strip()))
    except ValueError:
        return remote_addr


def register_request_info(app: Flask, ip_hasher: IpHasher, proxy_secret: str = "") -> None:
    """Bind the request's ID and IP fingerprint (after the request middleware)."""

    @app.before_request
    def _bind_request_info() -> None:
        address = client_address(
            request.remote_addr,
            request.headers.get(PROXY_SECRET_HEADER),
            request.headers.get(CLIENT_IP_HEADER),
            proxy_secret,
        )
        setattr(
            g,
            _REQUEST_INFO,
            RequestInfo(request_id=get_request_id(), ip_hash=ip_hasher.hash(address)),
        )


def request_info() -> RequestInfo:
    """The current request's info, or an empty one outside a bound request."""
    info = g.get(_REQUEST_INFO)
    return info if isinstance(info, RequestInfo) else RequestInfo()
