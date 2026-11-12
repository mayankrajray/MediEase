"""M7e (booking-requests R15): the public read limit follows PUBLIC_READS_PER_MINUTE."""

from __future__ import annotations

import pytest

from mediease_api.application.booking.limits import READS_PER_MINUTE_PER_IP, limit_reads
from mediease_api.application.context import RequestInfo
from mediease_api.domain.booking.request import BookingRateLimited
from tests.builders import NOW
from tests.conftest import UowFactory
from tests.fakes import FakeClock


def _read(uow_factory: UowFactory, clock: FakeClock, ip_hash: str, per_minute: int) -> None:
    limit_reads(uow_factory(), clock, RequestInfo(ip_hash=ip_hash), per_minute=per_minute)


def test_m7e_r15_the_limit_is_the_configured_reads_a_minute(uow_factory: UowFactory) -> None:
    clock = FakeClock(NOW.replace(second=5))
    for _ in range(3):
        _read(uow_factory, clock, "addr-a", 3)
    with pytest.raises(BookingRateLimited) as refused:
        _read(uow_factory, clock, "addr-a", 3)
    assert 1 <= refused.value.retry_after_seconds <= 60


def test_m7e_a11_each_address_has_its_own_budget(uow_factory: UowFactory) -> None:
    clock = FakeClock(NOW.replace(second=5))
    for _ in range(3):
        _read(uow_factory, clock, "addr-a", 3)
    # Another patient (another address once the web server forwards it) is not refused.
    _read(uow_factory, clock, "addr-b", 3)


def test_m7e_the_default_is_still_60(uow_factory: UowFactory) -> None:
    assert READS_PER_MINUTE_PER_IP == 60
    clock = FakeClock(NOW.replace(second=5))
    for _ in range(60):
        limit_reads(uow_factory(), clock, RequestInfo(ip_hash="addr-c"))
    with pytest.raises(BookingRateLimited):
        limit_reads(uow_factory(), clock, RequestInfo(ip_hash="addr-c"))
