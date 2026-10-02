"""Unit tests for structured logging (NFR-12).

Every request produces JSON log lines (outside APP_ENV=local) that carry the
request's ``request_id``, and the access log reports route and duration.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from flask.testing import FlaskClient


def _json_lines(out: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in out.splitlines() if line.startswith("{")]


def test_nfr_12_access_log_is_json_with_request_id(
    client: FlaskClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()  # drop start-up lines
    client.get("/health", headers={"X-Request-ID": "log-trace-1"})

    access = [e for e in _json_lines(capsys.readouterr().out) if e["event"] == "http.access"]
    assert len(access) == 1
    entry = access[0]
    assert entry["request_id"] == "log-trace-1"
    assert entry["route"] == "/health"
    assert entry["method"] == "GET"
    assert entry["status"] == 200
    assert isinstance(entry["duration_ms"], float)
    assert entry["level"] == "info"
    assert "timestamp" in entry


def test_nfr_12_request_id_does_not_leak_into_next_request(
    client: FlaskClient, capsys: pytest.CaptureFixture[str]
) -> None:
    client.get("/health", headers={"X-Request-ID": "first"})
    client.get("/health", headers={"X-Request-ID": "second"})

    ids = [
        e["request_id"] for e in _json_lines(capsys.readouterr().out) if e["event"] == "http.access"
    ]
    assert ids == ["first", "second"]


def test_nfr_12_unknown_route_logs_no_raw_path(
    client: FlaskClient, capsys: pytest.CaptureFixture[str]
) -> None:
    client.get("/patients/ME-0142")

    out = capsys.readouterr().out
    assert "ME-0142" not in out
    access = [e for e in _json_lines(out) if e["event"] == "http.access"]
    assert access[0]["route"] is None
