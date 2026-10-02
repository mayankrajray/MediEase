"""Unit tests for the error envelope (NFR-12, docs/ERRORS.md)."""

from __future__ import annotations

import json

import pytest
from flask import Flask

from mediease_api.application.auth.errors import AccountLocked
from mediease_api.domain.identity.membership import LastOwnerError
from mediease_api.domain.shared.errors import DomainError, InvalidValue


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


def _raise_on(app: Flask, path: str, exc: Exception) -> None:
    def _view() -> str:
        raise exc

    app.add_url_rule(path, endpoint=path, view_func=_view)


def test_domain_errors_map_to_their_catalogued_status(app: Flask) -> None:
    _raise_on(app, "/last-owner", LastOwnerError())
    resp = app.test_client().get("/last-owner")
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CLN_LAST_OWNER"


def test_invalid_value_lists_the_field_without_the_value(app: Flask) -> None:
    _raise_on(app, "/bad-phone", InvalidValue("phone", "is not a valid phone number"))
    resp = app.test_client().get("/bad-phone")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["details"] == {
        "fields": [{"field": "phone", "reason": "is not a valid phone number"}]
    }


def test_auth_locked_sets_retry_after(app: Flask) -> None:
    _raise_on(app, "/locked", AccountLocked(120))
    resp = app.test_client().get("/locked")
    assert resp.status_code == 423
    assert resp.headers["Retry-After"] == "120"


def test_unmapped_domain_error_is_a_logged_500(
    app: Flask, capsys: pytest.CaptureFixture[str]
) -> None:
    class Unmapped(DomainError):
        code = "XYZ_NOT_CATALOGUED"

    _raise_on(app, "/unmapped", Unmapped("internal"))
    resp = app.test_client().get("/unmapped")
    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "SYS_UNEXPECTED"
    assert "app.unmapped_domain_error" in capsys.readouterr().out
