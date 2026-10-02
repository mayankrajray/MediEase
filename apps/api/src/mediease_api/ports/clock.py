"""Clock port: the only source of "now" (CLAUDE.md "Inject a clock port")."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime:
        """The current instant as a timezone-aware UTC datetime."""
        ...
