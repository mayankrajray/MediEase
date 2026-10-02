"""UUIDv7 generator (RFC 9562 §5.7) — the production ``IdPort``.

Layout of the 128 bits::

    48 bits  unix_ts_ms   milliseconds since the epoch (sorts IDs by creation time)
     4 bits  version      0b0111
    12 bits  rand_a       a counter, so IDs from the same millisecond still sort
     2 bits  variant      0b10
    62 bits  rand_b       random

Monotonic within a process (RFC 9562 §6.2, method 1): within one millisecond,
or if the wall clock steps backwards, the counter increments instead of the
timestamp moving back; on overflow the timestamp is advanced by 1 ms. The
counter starts at a random value below 2^11 so it has room to grow.

Python 3.12 has no ``uuid.uuid7`` (added in 3.14), and 30 lines here avoid a
dependency.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from uuid import UUID

_MAX_COUNTER = 0xFFF
_TIMESTAMP_MASK = (1 << 48) - 1


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class Uuid7Generator:
    """Thread-safe, monotonic UUIDv7 source."""

    def __init__(
        self,
        *,
        clock_ms: Callable[[], int] = _now_ms,
        random_bits: Callable[[int], int] = secrets.randbits,
    ) -> None:
        # Injectable so tests can pin time and randomness.
        self._clock_ms = clock_ms
        self._random_bits = random_bits
        self._lock = threading.Lock()
        self._last_ms = -1
        self._counter = 0

    def new_id(self) -> UUID:
        with self._lock:
            now = self._clock_ms()
            if now > self._last_ms:
                self._last_ms = now
                self._counter = self._random_bits(11)
            else:
                self._counter += 1
                if self._counter > _MAX_COUNTER:
                    self._last_ms += 1
                    self._counter = self._random_bits(11)
            timestamp, counter = self._last_ms, self._counter
        value = (
            (timestamp & _TIMESTAMP_MASK) << 80
            | 0x7 << 76
            | counter << 64
            | 0b10 << 62
            | self._random_bits(62)
        )
        return UUID(int=value)
