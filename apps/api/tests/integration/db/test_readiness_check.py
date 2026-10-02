"""Integration tests for SqlAlchemyDatabaseCheck against a real PostgreSQL (NFR-12).

Readiness must reflect truth (CLAUDE.md "Testing Expectations"): ok when the
database answers, READY_DB_UNAVAILABLE when it cannot be reached, and
READY_DB_TIMEOUT when it does not answer within the 2-second budget — whether
the connection or the query is what hangs.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from mediease_api.adapters.db.engine import build_engine
from mediease_api.adapters.db.readiness import SqlAlchemyDatabaseCheck
from mediease_api.config.settings import AppEnv, AppSettings
from mediease_api.ports.readiness import (
    READINESS_TIMEOUT_SECONDS,
    DatabaseTimeout,
    DatabaseUnavailable,
)

# Allowance over the 2 s budget for process scheduling on slow CI runners.
_SLACK_SECONDS = 1.5


def _engine(url: str) -> Engine:
    # LOCAL because the target is a developer/CI database: the compose db's
    # password is the change-me placeholder from .env.example, which only
    # APP_ENV=local accepts. The settings object only carries the URL here.
    return build_engine(AppSettings(APP_ENV=AppEnv.LOCAL, DATABASE_URL=url))


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    eng = _engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def silent_server() -> Iterator[int]:
    """A TCP port that accepts connections but never speaks, like a hung server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(8)  # the kernel completes the handshake; nobody ever replies
        yield sock.getsockname()[1]


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])  # released on exit: connections are refused


def test_nfr_12_check_passes_when_database_answers(engine: Engine) -> None:
    SqlAlchemyDatabaseCheck(engine).check()


def test_nfr_12_check_leaves_no_statement_timeout_on_pooled_connection(engine: Engine) -> None:
    SqlAlchemyDatabaseCheck(engine).check()
    with engine.connect() as conn:  # same pool, so the same physical connection
        assert conn.exec_driver_sql("SHOW statement_timeout").scalar() == "0"


def test_nfr_12_refused_connection_is_unavailable(database_url: str) -> None:
    url = make_url(database_url).set(host="127.0.0.1", port=_closed_port())
    eng = _engine(url.render_as_string(hide_password=False))
    started = time.monotonic()
    with pytest.raises(DatabaseUnavailable):
        SqlAlchemyDatabaseCheck(eng).check()
    assert time.monotonic() - started < READINESS_TIMEOUT_SECONDS + _SLACK_SECONDS
    eng.dispose()


def test_nfr_12_wrong_password_is_unavailable(database_url: str) -> None:
    url = make_url(database_url).set(password="definitely-not-the-password")
    eng = _engine(url.render_as_string(hide_password=False))
    with pytest.raises(DatabaseUnavailable) as excinfo:
        SqlAlchemyDatabaseCheck(eng).check()
    assert excinfo.value.code == "READY_DB_UNAVAILABLE"
    eng.dispose()


def test_nfr_12_hung_connection_times_out_within_budget(
    database_url: str, silent_server: int
) -> None:
    url = make_url(database_url).set(host="127.0.0.1", port=silent_server)
    eng = _engine(url.render_as_string(hide_password=False))
    started = time.monotonic()
    with pytest.raises(DatabaseTimeout) as excinfo:
        SqlAlchemyDatabaseCheck(eng).check()
    elapsed = time.monotonic() - started
    assert excinfo.value.code == "READY_DB_TIMEOUT"
    assert elapsed < READINESS_TIMEOUT_SECONDS + _SLACK_SECONDS
    eng.dispose()


def test_nfr_12_slow_query_times_out_within_budget(engine: Engine) -> None:
    check = SqlAlchemyDatabaseCheck(engine, probe_sql="SELECT pg_sleep(10)")
    started = time.monotonic()
    with pytest.raises(DatabaseTimeout):
        check.check()
    assert time.monotonic() - started < READINESS_TIMEOUT_SECONDS + _SLACK_SECONDS
