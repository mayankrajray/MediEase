"""Audit port: where a recorded action goes (FR-AUD-01, spec R11).

The writer is obtained from the unit of work (``uow.audit``), so the row lands
in the same transaction as the change it describes: commit both, or neither.
There is no read method here — nothing in the application reads the audit log
yet (FR-AUD-03 is a later, owner-facing feature), and nothing anywhere may
change one (FR-AUD-02).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mediease_api.domain.audit.event import AuditEvent


class AuditWriter(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Append the event. Fails loudly: an unaudited change must not commit."""
        ...

    def record_many(self, events: Sequence[AuditEvent]) -> None:
        """Append several events in one round trip (the ops import, M2-P4). Same guarantees."""
        ...
