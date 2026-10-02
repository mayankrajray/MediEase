"""Readiness port: can the service use its dependencies right now?

Delivery (``/ready``) depends on this interface, never on SQLAlchemy, so the
endpoint can be tested with a fake and the adapter can change without touching
HTTP code (CLAUDE.md "Ports and adapters").

The errors are part of the contract: an implementation raises exactly one of
them when a check fails, and each carries the stable code from docs/ERRORS.md.
"""

from __future__ import annotations

from typing import ClassVar, Protocol

# Every readiness check must answer within this budget (M0 design notes).
READINESS_TIMEOUT_SECONDS = 2


class ReadinessError(Exception):
    """A dependency is not usable. ``code`` is the stable error code."""

    code: ClassVar[str]


class DatabaseUnavailable(ReadinessError):
    """The database refused, dropped or could not be reached."""

    code = "READY_DB_UNAVAILABLE"


class DatabaseTimeout(ReadinessError):
    """The database did not answer within READINESS_TIMEOUT_SECONDS."""

    code = "READY_DB_TIMEOUT"


class DatabaseCheck(Protocol):
    """Prove the database can execute a query."""

    def check(self) -> None:
        """Return on success; raise DatabaseUnavailable or DatabaseTimeout otherwise."""
        ...
