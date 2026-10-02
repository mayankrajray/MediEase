"""Unit tests for /ready with a fake database check (NFR-12).

Readiness reports the database truthfully; liveness never depends on it.
"""

from __future__ import annotations

import json

import pytest
from flask.testing import FlaskClient

from mediease_api.ports.readiness import DatabaseTimeout, DatabaseUnavailable, ReadinessError
from tests.conftest import FakeDatabaseCheck


def test_nfr_12_ready_returns_200_when_database_ok(
    client: FlaskClient, database_check: FakeDatabaseCheck
) -> None:
    resp = client.get("/ready", headers={"X-Request-ID": "ready-ok"})

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ready", "checks": {"database": "ok"}}
    assert resp.headers["X-Request-ID"] == "ready-ok"
    assert database_check.calls == 1


@pytest.mark.parametrize(
    ("error", "code"),
    [(DatabaseUnavailable(), "READY_DB_UNAVAILABLE"), (DatabaseTimeout(), "READY_DB_TIMEOUT")],
    ids=["unavailable", "timeout"],
)
def test_nfr_12_ready_returns_503_with_code_when_database_fails(
    client: FlaskClient, database_check: FakeDatabaseCheck, error: ReadinessError, code: str
) -> None:
    database_check.error = error

    resp = client.get("/ready", headers={"X-Request-ID": "ready-down"})

    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == "ready-down"
    assert body["error"]["message"]
    assert body["error"]["details"] == {}


def test_nfr_12_health_stays_200_when_database_is_down(
    client: FlaskClient, database_check: FakeDatabaseCheck
) -> None:
    database_check.error = DatabaseUnavailable()

    assert client.get("/health").status_code == 200
    assert database_check.calls == 0  # liveness never touches the database


def test_nfr_12_failed_check_is_logged_as_warning_without_driver_message(
    client: FlaskClient, database_check: FakeDatabaseCheck, capsys: pytest.CaptureFixture[str]
) -> None:
    error = DatabaseUnavailable()
    error.__cause__ = ConnectionError('could not connect to host "db-secret-host"')
    database_check.error = error

    client.get("/ready", headers={"X-Request-ID": "ready-log"})

    out = capsys.readouterr().out
    assert "db-secret-host" not in out
    events = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    failure = next(e for e in events if e["event"] == "ready.check_failed")
    assert failure["level"] == "warning"
    assert failure["code"] == "READY_DB_UNAVAILABLE"
    assert failure["cause"] == "ConnectionError"
    assert failure["request_id"] == "ready-log"
