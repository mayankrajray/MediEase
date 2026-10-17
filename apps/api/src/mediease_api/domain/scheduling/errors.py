"""Scheduling errors (docs/ERRORS.md "Schedules"). Messages and details carry no personal data."""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError


class InvalidBlock(DomainError):
    """R14: a block's times, length or slot/capacity do not make a bookable session."""

    code = "SCH_INVALID_BLOCK"

    def __init__(self, reason: str, *, index: int | None = None) -> None:
        details = {"reason": reason}
        if index is not None:
            details["index"] = str(index)
        super().__init__(f"This block cannot be scheduled: {reason}.", **details)
        self.reason = reason


class ScheduleOverlap(DomainError):
    """R15: two blocks of one doctor overlap, possibly across midnight or the week."""

    code = "SCH_OVERLAP"

    def __init__(self, *, first: int | None = None, second: int | None = None) -> None:
        details = {}
        if first is not None and second is not None:
            details = {"first": str(first), "second": str(second)}
        super().__init__("Two of this doctor's blocks overlap.", **details)


class LeaveExists(DomainError):
    """R17: the doctor already has leave on that date."""

    code = "SCH_LEAVE_EXISTS"

    def __init__(self) -> None:
        super().__init__("The doctor already has leave on that date.")


class ModeIncompatible(DomainError):
    """R19: a block lacks the value the booking mode needs (slot length or capacity)."""

    code = "SCH_MODE_INCOMPATIBLE"

    def __init__(self, mode: str, needs: str) -> None:
        super().__init__(
            f"Every current block needs a {needs} for {mode} booking.", mode=mode, needs=needs
        )
