"""Per-caller limits on the public sign-in routes (M6a-P3, decision 7).

The M4-P5 limiter: a count per bucket and minute in ``public_rate_limits``, committed in its own
short transaction before the work, so a refused attempt costs no password hash. The caller is
the salted IP fingerprint (``RequestInfo.ip_hash``).
"""

from __future__ import annotations

import structlog

from mediease_api.application.auth.errors import AuthRateLimited
from mediease_api.application.context import RequestInfo
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# Generous for a family on one connection, tight for a script.
SIGN_UP_PER_MINUTE = 10
SIGN_IN_PER_MINUTE = 30
GOOGLE_PER_MINUTE = 30


def enforce_rate_limit(
    uow: UnitOfWork,
    clock: ClockPort,
    info: RequestInfo,
    *,
    bucket: str,
    limit: int,
) -> None:
    """Count one attempt for ``bucket:<caller>``; raise ``AuthRateLimited`` over ``limit``.

    Opens and closes ``uow`` on its own, so call it before the use case's main transaction.
    """
    now = clock.now()
    window = now.replace(second=0, microsecond=0)
    with uow as open_uow:
        hits = open_uow.rate_limits.hit(f"{bucket}:{info.ip_hash or '-'}", window_start=window)
        open_uow.commit()
    if hits > limit:
        retry = 60 - now.second
        logger.info("auth.rate_limited", bucket=bucket, retry_after=retry)
        raise AuthRateLimited(retry)
