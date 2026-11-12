"""M7e, A11: the caller's address comes from the trusted web server only (ARCHITECTURE §9)."""

from __future__ import annotations

import pytest
from flask import Flask, jsonify

from mediease_api.delivery.http.request_info import (
    CLIENT_IP_HEADER,
    PROXY_SECRET_HEADER,
    client_address,
    register_request_info,
    request_info,
)

SECRET = "a-trusted-proxy-secret-of-at-least-32-chars"
WEB = "172.18.0.5"


class _PlainHasher:
    """Shows which address was fingerprinted."""

    def hash(self, ip_address: str | None) -> str | None:
        return None if ip_address is None else f"h:{ip_address}"


def _app(secret: str) -> Flask:
    app = Flask(__name__)
    register_request_info(app, _PlainHasher(), proxy_secret=secret)

    @app.get("/who")
    def who() -> object:
        return jsonify(ip_hash=request_info().ip_hash)

    return app


def _who(app: Flask, headers: dict[str, str]) -> str | None:
    response = app.test_client().get("/who", headers=headers, environ_base={"REMOTE_ADDR": WEB})
    value = response.get_json()["ip_hash"]
    return None if value is None else str(value)


def test_a11_the_browser_address_is_used_when_the_web_server_vouches_for_it() -> None:
    app = _app(SECRET)
    headers = {PROXY_SECRET_HEADER: SECRET, CLIENT_IP_HEADER: "203.0.113.7"}
    assert _who(app, headers) == "h:203.0.113.7"
    headers[CLIENT_IP_HEADER] = "2001:db8::1"
    assert _who(app, headers) == "h:2001:db8::1"


@pytest.mark.parametrize(
    "headers",
    [
        {},  # an ordinary request
        {CLIENT_IP_HEADER: "203.0.113.7"},  # an address without the secret (a browser's attempt)
        {PROXY_SECRET_HEADER: "wrong", CLIENT_IP_HEADER: "203.0.113.7"},
        {PROXY_SECRET_HEADER: SECRET[:-1], CLIENT_IP_HEADER: "203.0.113.7"},
        {PROXY_SECRET_HEADER: SECRET, CLIENT_IP_HEADER: "not-an-address"},
        {PROXY_SECRET_HEADER: SECRET, CLIENT_IP_HEADER: "203.0.113.7, 10.0.0.1"},
        {PROXY_SECRET_HEADER: SECRET},
    ],
)
def test_a11_otherwise_the_connection_address_is_used(headers: dict[str, str]) -> None:
    assert _who(_app(SECRET), headers) == f"h:{WEB}"


def test_a11_without_a_configured_secret_the_headers_are_ignored_as_before() -> None:
    headers = {PROXY_SECRET_HEADER: "", CLIENT_IP_HEADER: "203.0.113.7"}
    assert _who(_app(""), headers) == f"h:{WEB}"
    assert client_address(WEB, "x", "203.0.113.7", "") == WEB


def test_a11_an_address_is_normalised_before_it_is_fingerprinted() -> None:
    assert client_address(WEB, SECRET, " 2001:DB8:0:0::1 ", SECRET) == "2001:db8::1"
