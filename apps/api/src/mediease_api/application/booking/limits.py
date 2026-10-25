"""Abuse limits on the public page and booking requests (M6b-P4; FR-BKG-07, NFR-19; spec R15).

Fixed windows in ``public_rate_limits`` (the M4-P5 limiter), committed in a short transaction of
their own before the work, so a refused attempt costs nothing else. The caller is the salted IP
fingerprint; no address, phone or account ID is stored in a bucket's name except the account's
own opaque ID. The phone limit counts real requests instead (``count_for_phone``): the limiter
keeps windows an hour only, and a phone number never belongs in a bucket name.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog

from mediease_api.application.context import RequestInfo
from mediease_api.domain.booking.request import BookingRateLimited
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

READS_PER_MINUTE_PER_IP = 60
REQUESTS_PER_HOUR_PER_ACCOUNT = 5
REQUESTS_PER_HOUR_PER_IP = 20
REQUESTS_PER_DAY_PER_PHONE = 5


def _count(uow: UnitOfWork, bucket: str, window: datetime) -> int:
    hits = uow.rate_limits.hit(bucket, window_start=window)
    return hits


def limit_reads(uow: UnitOfWork, clock: ClockPort, info: RequestInfo) -> None:
    """The page and availability: 60 a minute per address (R15)."""
    now = clock.now()
    window = now.replace(second=0, microsecond=0)
    with uow as open_uow:
        hits = _count(open_uow, f"pub-read:{info.ip_hash or '-'}", window)
        open_uow.commit()
    if hits > READS_PER_MINUTE_PER_IP:
        _refuse("pub-read", 60 - now.second)


def limit_requests(
    uow: UnitOfWork, clock: ClockPort, info: RequestInfo, *, account_id: str
) -> None:
    """A request: 5 an hour per account and 20 an hour per address (R15)."""
    now = clock.now()
    window = now.replace(minute=0, second=0, microsecond=0)
    retry = int((window + timedelta(hours=1) - now).total_seconds())
    with uow as open_uow:
        by_account = _count(open_uow, f"bkreq-account:{account_id}", window)
        by_ip = _count(open_uow, f"bkreq-ip:{info.ip_hash or '-'}", window)
        open_uow.commit()
    if by_account > REQUESTS_PER_HOUR_PER_ACCOUNT:
        _refuse("bkreq-account", retry)
    if by_ip > REQUESTS_PER_HOUR_PER_IP:
        _refuse("bkreq-ip", retry)


def limit_phone(uow: UnitOfWork, clock: ClockPort, e164: str) -> None:
    """5 requests a day per phone number, across clinics (R15)."""
    now = clock.now()
    with uow as open_uow:
        made = open_uow.booking_request_lookup.count_for_phone(e164, now - timedelta(days=1))
    if made >= REQUESTS_PER_DAY_PER_PHONE:
        _refuse("bkreq-phone", 3600)


def _refuse(bucket: str, retry_after: int) -> None:
    logger.info("booking.rate_limited", bucket=bucket, retry_after=retry_after)
    raise BookingRateLimited(max(retry_after, 1))
