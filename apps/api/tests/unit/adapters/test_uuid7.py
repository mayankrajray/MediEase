"""UUIDv7 generator: format, ordering and monotonicity (AGENTS.md "IDs: UUIDv7")."""

from __future__ import annotations

import threading
from uuid import UUID

from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.ports.ids import IdPort


def _timestamp_ms(value: UUID) -> int:
    return value.int >> 80


def _counter(value: UUID) -> int:
    return (value.int >> 64) & 0xFFF


def test_ids_are_rfc_9562_version_7() -> None:
    generator: IdPort = Uuid7Generator()
    value = generator.new_id()
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_timestamp_holds_the_clock_milliseconds() -> None:
    generator = Uuid7Generator(clock_ms=lambda: 1_790_000_000_123)
    assert _timestamp_ms(generator.new_id()) == 1_790_000_000_123


def test_ids_within_one_millisecond_still_increase() -> None:
    generator = Uuid7Generator(clock_ms=lambda: 1_790_000_000_000)
    ids = [generator.new_id() for _ in range(1_000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_clock_stepping_back_does_not_break_ordering() -> None:
    times = iter([2_000, 1_000, 1_000])
    generator = Uuid7Generator(clock_ms=lambda: next(times))
    first, second, third = (generator.new_id() for _ in range(3))
    assert first < second < third
    assert _timestamp_ms(second) == 2_000


def test_counter_overflow_advances_the_timestamp() -> None:
    # Counter starts at the top of its 11-bit start range: 0x7FF + 0x800 more IDs overflow it.
    generator = Uuid7Generator(clock_ms=lambda: 5_000, random_bits=lambda bits: (1 << bits) - 1)
    first = generator.new_id()
    assert _counter(first) == 0x7FF
    ids = [generator.new_id() for _ in range(0x801)]
    assert _timestamp_ms(ids[-1]) == 5_001
    assert [first, *ids] == sorted([first, *ids])


def test_ids_are_unique_across_threads() -> None:
    generator = Uuid7Generator()
    results: list[UUID] = []
    lock = threading.Lock()

    def worker() -> None:
        batch = [generator.new_id() for _ in range(500)]
        with lock:
            results.extend(batch)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(results)) == 4_000
