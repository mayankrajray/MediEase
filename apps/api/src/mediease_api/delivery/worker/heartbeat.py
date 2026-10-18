"""The worker's heartbeat file and its container health check (spec R11a).

The container's root filesystem is read-only, so the file lives in a small tmpfs at ``/tmp``. The
worker rewrites it only after a poll iteration that reached the database; a worker whose
connection is dead stops rewriting it, the file goes stale, and the health check fails.

This module imports nothing heavy on purpose: the health check starts a fresh interpreter every
few seconds.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HEARTBEAT_PATH = Path("/tmp/mediease-worker-heartbeat")
# Older than this and the worker counts as stuck: several poll intervals and one slow handler's
# worth of lock renewals, well under the compose health check's retries.
MAX_AGE_SECONDS = 90.0


def beat(path: Path = HEARTBEAT_PATH) -> None:
    """Record that a poll iteration just succeeded."""
    path.write_text(str(int(time.time())), encoding="ascii")
    os.utime(path)


def age_seconds(path: Path = HEARTBEAT_PATH, now: float | None = None) -> float | None:
    """Seconds since the last beat, or ``None`` if there has been none."""
    try:
        modified = path.stat().st_mtime
    except OSError:
        return None
    return (time.time() if now is None else now) - modified


def is_healthy(path: Path = HEARTBEAT_PATH, now: float | None = None) -> bool:
    age = age_seconds(path, now)
    return age is not None and age < MAX_AGE_SECONDS


def main() -> int:
    """Exit status for the container health check: 0 healthy, 1 not."""
    if is_healthy():
        return 0
    print("worker heartbeat is missing or stale", file=sys.stderr)
    return 1
