"""SQLAlchemy engine built from validated settings.

One engine per process, created by the composition root. Creating it opens no
connection, so building the app has no side effects; the first connection is
made by the first query (or readiness check).
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine

from mediease_api.config.settings import AppSettings
from mediease_api.ports.readiness import READINESS_TIMEOUT_SECONDS


def build_engine(settings: AppSettings) -> Engine:
    """Return the process-wide engine for ``settings.DATABASE_URL``."""
    return create_engine(
        settings.DATABASE_URL,
        # Never log SQL, and never put bound parameters into exception messages:
        # parameters can hold patient data (CLAUDE.md "Safety Rules").
        echo=False,
        hide_parameters=True,
        # Replace connections the server closed (restart, idle timeout) before use.
        pool_pre_ping=True,
        # Waiting for a free pooled connection is bounded like everything else.
        pool_timeout=READINESS_TIMEOUT_SECONDS,
        # libpq connect timeout in whole seconds (its minimum is 2).
        connect_args={"connect_timeout": READINESS_TIMEOUT_SECONDS},
    )
