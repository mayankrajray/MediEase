"""The worker's wiring (M5-P2): the send jobs are registered; console is refused in production."""

from __future__ import annotations

import threading

import pytest

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.engine import build_engine
from mediease_api.adapters.db.unit_of_work import build_session_factory
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.bootstrap import _messaging_handlers, build_worker
from mediease_api.config.settings import load_settings
from mediease_api.delivery.worker.loop import Worker
from mediease_api.domain.messaging.jobs import BOOKING_CONFIRMATION_KIND, RX_LINK_KIND
from tests.conftest import SetEnv


def test_m5_p2_the_worker_handles_the_send_jobs(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    set_env(valid_env)
    settings = load_settings()
    factory = build_session_factory(build_engine(settings))  # no connection is opened
    handlers = _messaging_handlers(settings, factory, SystemClock(), Uuid7Generator())
    assert set(handlers) == {BOOKING_CONFIRMATION_KIND, RX_LINK_KIND}
    assert isinstance(build_worker(settings, threading.Event()), Worker)


def test_m5_p2_the_console_provider_is_refused_in_production(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env({**valid_env, "APP_ENV": "production", "COOKIE_SECURE": "true"})
    settings = load_settings()
    factory = build_session_factory(build_engine(settings))
    with pytest.raises(ValueError, match="console"):
        _messaging_handlers(settings, factory, SystemClock(), Uuid7Generator())
