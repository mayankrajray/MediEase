"""Integration tests for /health and request correlation (NFR-12).

Acceptance (docs/milestones/M0-foundation.md):
200, body {"status":"ok"}, an X-Request-ID header is always present, and an
inbound X-Request-ID is echoed back.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask.testing import FlaskClient

from mediease_api.bootstrap import create_app
from mediease_api.config.settings import AppSettings
from tests.conftest import VALID_LOCAL_ENV


@pytest.fixture
def client(set_env) -> Iterator[FlaskClient]:  # type: ignore[no-untyped-def]
    set_env(VALID_LOCAL_ENV)
    app = create_app(AppSettings())  # type: ignore[call-arg]
    app.testing = True
    with app.test_client() as c:
        yield c


def test_health_returns_200_ok(client: FlaskClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_health_sets_request_id_header(client: FlaskClient) -> None:
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")  # non-empty, generated when absent


def test_health_echoes_inbound_request_id(client: FlaskClient) -> None:
    resp = client.get("/health", headers={"X-Request-ID": "test-123"})
    assert resp.headers.get("X-Request-ID") == "test-123"


def test_overlong_request_id_is_replaced(client: FlaskClient) -> None:
    overlong = "x" * 100
    resp = client.get("/health", headers={"X-Request-ID": overlong})
    returned = resp.headers.get("X-Request-ID")
    assert returned and returned != overlong
    assert len(returned) <= 64


def test_unknown_route_uses_error_envelope(client: FlaskClient) -> None:
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]  # correlation id present in the envelope


def test_unexpected_error_returns_sys_unexpected(set_env) -> None:  # type: ignore[no-untyped-def]
    set_env(VALID_LOCAL_ENV)
    app = create_app(AppSettings())  # type: ignore[call-arg]
    app.testing = False  # let the error handler run instead of re-raising

    @app.get("/boom")  # type: ignore[misc]
    def _boom() -> str:
        raise RuntimeError("kaboom")

    with app.test_client() as c:
        resp = c.get("/boom", headers={"X-Request-ID": "trace-boom"})
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["error"]["code"] == "SYS_UNEXPECTED"
    # The envelope correlates to the request; no stack trace leaks into the body.
    assert body["error"]["request_id"] == "trace-boom"
    assert "kaboom" not in resp.get_data(as_text=True)
