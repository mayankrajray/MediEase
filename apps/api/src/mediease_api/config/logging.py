"""Structured logging setup (NFR-12, CLAUDE.md "Observability Standards").

JSON, one event per line, with a stable set of fields. Correlation IDs
(``request_id``, ``clinic_id``, ``user_id``) are carried in contextvars so every
log line emitted while handling a request is automatically tagged — a single ID
traces a request end to end.

Never log PII or clinical content (CLAUDE.md). This module only wires the
pipeline; call sites are responsible for not passing sensitive values.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.contextvars import merge_contextvars
from structlog.types import EventDict, Processor

from mediease_api.config.settings import AppEnv, AppSettings


def configure_logging(settings: AppSettings) -> None:
    """Configure structlog + stdlib logging for JSON output.

    Idempotent: safe to call once from the composition root. In ``local`` and
    ``test`` a console renderer is used for readability; deployed environments
    always emit JSON.
    """
    level = logging.getLevelNamesMapping()[settings.LOG_LEVEL]

    shared_processors: list[Processor] = [
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _rename_event_key,
    ]

    renderer: Processor
    if settings.APP_ENV == AppEnv.LOCAL:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (Flask, werkzeug) through the same level.
    logging.basicConfig(level=level, format="%(message)s")


def _rename_event_key(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Expose the message under the stable ``event`` field name.

    CLAUDE.md requires an ``event`` field ("log events, not prose"). structlog's
    positional message already lands in ``event``; this hook is the single place
    to adjust the shape if that changes, keeping the contract in one spot.
    """
    return event_dict
