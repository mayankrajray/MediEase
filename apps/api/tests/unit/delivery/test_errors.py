"""Unit tests for the error envelope (NFR-12, docs/ERRORS.md)."""

from __future__ import annotations

import json

import pytest
from flask import Flask


def _add_failing_route(app: Flask) -> None:
    @app.get("/boom")
    def _boom() -> str:
        raise RuntimeError("internal detail that must not reach the client")


def test_nfr_12_unexpected_error_returns_sys_unexpected_with_request_id(
    app: Flask, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_failing_route(app)
    resp = app.test_client().get("/boom", headers={"X-Request-ID": "trace-boom"})

    assert resp.status_code == 500
    assert resp.headers["X-Request-ID"] == "trace-boom"
    assert resp.get_json() == {
        "error": {
            "code": "SYS_UNEXPECTED",
            "message": "An unexpected error occurred.",
            "request_id": "trace-boom",
            "details": {},
        }
    }
    assert "internal detail" not in resp.get_data(as_text=True)

    # The stack trace is in the server log, tied to the same request_id.
    events = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    error = next(e for e in events if e["event"] == "app.unexpected_error")
    assert error["request_id"] == "trace-boom"
    assert error["level"] == "error"
    assert "RuntimeError" in error["exception"]


def test_nfr_12_unknown_route_returns_req_not_found(app: Flask) -> None:
    resp = app.test_client().get("/does-not-exist")

    assert resp.status_code == 404
    error = resp.get_json()["error"]
    assert error["code"] == "REQ_NOT_FOUND"
    assert error["request_id"] == resp.headers["X-Request-ID"]
    assert error["details"] == {}


def test_nfr_12_wrong_method_returns_req_method_not_allowed_with_allow_header(app: Flask) -> None:
    resp = app.test_client().post("/health")

    assert resp.status_code == 405
    assert resp.get_json()["error"]["code"] == "REQ_METHOD_NOT_ALLOWED"
    assert "GET" in resp.headers["Allow"]
