"""Structured logging setup (NFR-12, CLAUDE.md "Observability Standards").

One event per line on stdout. ``APP_ENV=local`` uses a human-readable console
renderer; every other environment (test, staging, production) emits JSON.

structlog events and stdlib records (Flask, werkzeug, libraries) go through the
same formatter, so every line has the same shape: ``timestamp``, ``level``,
``event``, ``logger`` and any bound context. Correlation IDs (``request_id``,
later ``clinic_id`` and ``user_id``) live in contextvars and are merged into
every event emitted while a request is handled.

Never log PII or clinical content (CLAUDE.md). This module only wires the
pipeline; call sites are responsible for passing internal IDs and enums only.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import Processor

from mediease_api.config.settings import AppEnv, AppSettings


class _StdoutHandler(logging.Handler):
    """Write each record to whatever ``sys.stdout`` is at emit time.

    A plain ``StreamHandler`` keeps the stream it was created with; resolving it
    per record keeps logging correct when gunicorn or pytest swap ``sys.stdout``.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def configure_logging(settings: AppSettings) -> None:
    """Configure structlog and the stdlib root logger from settings.

    Safe to call more than once (each call replaces the root handlers), which
    keeps tests that build several apps independent of each other.
    """
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer_chain: list[Processor]
    if settings.APP_ENV is AppEnv.LOCAL:
        renderer_chain = [structlog.dev.ConsoleRenderer()]
    else:
        renderer_chain = [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=[
            # Level filtering reads the stdlib logger's level at call time, so a
            # later configure_logging() with another LOG_LEVEL takes effect.
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = _StdoutHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                *renderer_chain,
            ],
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)
