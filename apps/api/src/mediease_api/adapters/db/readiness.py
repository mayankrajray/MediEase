"""Database readiness check — the SQLAlchemy implementation of ``DatabaseCheck``.

Runs ``SELECT 1`` inside a transaction whose ``statement_timeout`` is the
readiness budget, on an engine whose connect and pool timeouts use the same
budget. Every way the database can fail is translated into one of the two port
errors; the driver's message (which can name hosts and users) is not exposed.
"""

from __future__ import annotations

import psycopg
from sqlalchemy import Engine
from sqlalchemy import exc as sa_exc

from mediease_api.ports.readiness import (
    READINESS_TIMEOUT_SECONDS,
    DatabaseTimeout,
    DatabaseUnavailable,
)

_TIMEOUT_DRIVER_ERRORS = (psycopg.errors.ConnectionTimeout, psycopg.errors.QueryCanceled)


class SqlAlchemyDatabaseCheck:
    """``DatabaseCheck`` backed by a SQLAlchemy engine."""

    def __init__(self, engine: Engine, *, probe_sql: str = "SELECT 1") -> None:
        # probe_sql is the query that must succeed. It is a parameter only so
        # tests can prove the statement timeout with a deliberately slow query.
        self._engine = engine
        self._probe_sql = probe_sql
        self._timeout_ms = READINESS_TIMEOUT_SECONDS * 1000

    def check(self) -> None:
        try:
            with self._engine.connect() as conn:
                # SET LOCAL scopes the limit to this transaction; it ends (rolls
                # back) when the block exits, so pooled connections are unaffected.
                conn.exec_driver_sql(f"SET LOCAL statement_timeout = {self._timeout_ms}")
                conn.exec_driver_sql(self._probe_sql)
        except sa_exc.TimeoutError as exc:  # pool exhausted for pool_timeout seconds
            raise DatabaseTimeout() from exc
        except sa_exc.DBAPIError as exc:
            if isinstance(exc.orig, _TIMEOUT_DRIVER_ERRORS):
                raise DatabaseTimeout() from exc
            raise DatabaseUnavailable() from exc
        except (sa_exc.SQLAlchemyError, OSError) as exc:
            raise DatabaseUnavailable() from exc
