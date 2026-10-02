"""What delivery knows about the call itself: its ID and the caller's fingerprint.

One ``before_request`` hook builds a ``RequestInfo`` (``application/context.py``)
for every request, so use cases receive the request ID and a salted IP
fingerprint explicitly instead of reaching into Flask (apps/api/CLAUDE.md).

The address comes from ``request.remote_addr``. Behind a reverse proxy that is
the proxy, not the client; trusting ``X-Forwarded-For`` only makes sense once a
proxy we control is in front of the API, which is M6-P1 (ARCHITECTURE §11).
Until then an on-premise clinic's requests fingerprint as their gateway, which
is still the useful "same place?" answer.
"""

from __future__ import annotations

from flask import Flask, g, request

from mediease_api.application.context import RequestInfo
from mediease_api.delivery.middleware import get_request_id
from mediease_api.ports.security import IpHasher

_REQUEST_INFO = "mediease_request_info"


def register_request_info(app: Flask, ip_hasher: IpHasher) -> None:
    """Bind the request's ID and IP fingerprint (after the request middleware)."""

    @app.before_request
    def _bind_request_info() -> None:
        setattr(
            g,
            _REQUEST_INFO,
            RequestInfo(
                request_id=get_request_id(),
                ip_hash=ip_hasher.hash(request.remote_addr),
            ),
        )


def request_info() -> RequestInfo:
    """The current request's info, or an empty one outside a bound request."""
    info = g.get(_REQUEST_INFO)
    return info if isinstance(info, RequestInfo) else RequestInfo()
