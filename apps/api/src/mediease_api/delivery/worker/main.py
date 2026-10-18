"""Process entry for the worker: settings, signals, then the loop (M5-P1)."""

from __future__ import annotations

import signal
import threading
from types import FrameType

from mediease_api.bootstrap import build_worker
from mediease_api.config.settings import load_settings


def main() -> int:
    settings = load_settings()
    stop = threading.Event()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        # Finish the job in hand, give back the rest, then leave (exit status 0).
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    build_worker(settings, stop).run()
    return 0
