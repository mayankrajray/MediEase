"""Visit errors (docs/ERRORS.md "Visits"). Details carry IDs, statuses and times, never text."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from mediease_api.domain.shared.errors import DomainError


class VisitAlreadyExists(DomainError):
    """R1: the appointment already has its visit; the caller gets its ID to open it."""

    code = "VIS_ALREADY_EXISTS"

    def __init__(self, visit_id: UUID) -> None:
        super().__init__("This consultation already has a visit.", visit_id=str(visit_id))
        self.visit_id = visit_id


class VisitNotStartable(DomainError):
    """R1: a visit starts only from an appointment that is in consultation."""

    code = "VIS_NOT_STARTABLE"

    def __init__(self, status: str) -> None:
        super().__init__("Start the consultation on the queue first.", status=status)


class VisitNotYours(DomainError):
    """§2: only the visit's (the session's) doctor writes it."""

    code = "VIS_NOT_YOURS"

    def __init__(self) -> None:
        super().__init__("Only the visit's doctor can change it.")


class VisitLocked(DomainError):
    """R3, AC6: 24 hours after completion the record is read-only; add an addendum instead."""

    code = "VIS_LOCKED"

    def __init__(self, locked_at: datetime) -> None:
        super().__init__("This visit is locked; add an addendum.", locked_at=locked_at.isoformat())


class VisitStale(DomainError):
    """M4-P1 decision 4: the edit was made on an older copy of the visit (another tab)."""

    code = "VIS_STALE"

    def __init__(self, revision: int) -> None:
        super().__init__(
            "This visit was changed elsewhere; reload it and try again.", revision=str(revision)
        )
        self.revision = revision


class VisitNotCompleted(DomainError):
    """R3: addenda are for completed visits; an open visit is edited directly."""

    code = "VIS_NOT_COMPLETED"

    def __init__(self) -> None:
        super().__init__("Edit the visit directly until it is completed.")
