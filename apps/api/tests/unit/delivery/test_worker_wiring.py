"""The worker's wiring (M5-P2, P3): the jobs are registered; the provider follows the settings."""

from __future__ import annotations

import threading

import pytest

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.engine import build_engine
from mediease_api.adapters.db.unit_of_work import build_session_factory
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.messaging.console import ConsoleMessagingAdapter
from mediease_api.adapters.messaging.console_sms import ConsoleSmsAdapter
from mediease_api.adapters.messaging.whatsapp_cloud import WhatsAppCloudAdapter
from mediease_api.bootstrap import _messaging_handlers, build_messaging, build_sms, build_worker
from mediease_api.config.settings import load_settings
from mediease_api.delivery.worker.loop import Worker
from mediease_api.domain.jobs.job import (
    EXPIRE_REQUESTS_KIND,
    MARK_NO_SHOWS_KIND,
    MEDICINE_DUE_SWEEP_KIND,
    NO_SHOW_SWEEP_KIND,
    NOTIFY_MEDICINE_DUE_KIND,
    RECONCILE_KIND,
    REQUEST_EXPIRY_SWEEP_KIND,
    WEBHOOK_KIND,
)
from mediease_api.domain.messaging.jobs import (
    BOOKING_CONFIRMATION_KIND,
    CANCELLATION_NOTICE_KIND,
    OPT_OUT_CONFIRMATION_KIND,
    REMINDER_KIND,
    RX_LINK_KIND,
    SMS_FALLBACK_KIND,
)
from tests.conftest import SetEnv
from tests.unit.config.test_settings import WHATSAPP


def test_m5_the_worker_handles_the_messaging_jobs(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env(valid_env)
    settings = load_settings()
    factory = build_session_factory(build_engine(settings))  # no connection is opened
    handlers = _messaging_handlers(settings, factory, SystemClock(), Uuid7Generator())
    assert set(handlers) == {
        BOOKING_CONFIRMATION_KIND,
        CANCELLATION_NOTICE_KIND,
        RX_LINK_KIND,
        WEBHOOK_KIND,
        RECONCILE_KIND,
        REMINDER_KIND,
        NO_SHOW_SWEEP_KIND,
        MARK_NO_SHOWS_KIND,
        # M6b-P5: the expiry of unanswered booking requests.
        REQUEST_EXPIRY_SWEEP_KIND,
        EXPIRE_REQUESTS_KIND,
        # M6b-P6: medicine-due notices.
        MEDICINE_DUE_SWEEP_KIND,
        NOTIFY_MEDICINE_DUE_KIND,
        OPT_OUT_CONFIRMATION_KIND,
        SMS_FALLBACK_KIND,
    }
    assert isinstance(build_messaging(settings), ConsoleMessagingAdapter)
    assert build_sms(settings) is None  # FR-REM-06: off by default
    assert isinstance(build_worker(settings, threading.Event()), Worker)


def test_m5_p5_the_sms_fallback_uses_the_console_and_is_refused_in_production(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env({**valid_env, "MESSAGING_SMS_FALLBACK_ENABLED": "true"})
    assert isinstance(build_sms(load_settings()), ConsoleSmsAdapter)
    set_env(
        {
            **valid_env,
            **WHATSAPP,
            "APP_ENV": "production",
            "COOKIE_SECURE": "true",
            "MESSAGING_SMS_FALLBACK_ENABLED": "true",
        }
    )
    with pytest.raises(ValueError, match="SMS"):
        build_sms(load_settings())


def test_m5_p3_the_whatsapp_provider_is_chosen_by_settings(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env({**valid_env, **WHATSAPP, "APP_ENV": "production", "COOKIE_SECURE": "true"})
    adapter = build_messaging(load_settings())
    assert isinstance(adapter, WhatsAppCloudAdapter)


def test_m5_p2_the_console_provider_is_refused_in_production(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env({**valid_env, "APP_ENV": "production", "COOKIE_SECURE": "true"})
    settings = load_settings()
    factory = build_session_factory(build_engine(settings))
    with pytest.raises(ValueError, match="console"):
        _messaging_handlers(settings, factory, SystemClock(), Uuid7Generator())
