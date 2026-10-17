"""Prescription errors (docs/ERRORS.md "Visits and prescriptions"). Details: IDs and statuses."""

from __future__ import annotations

from uuid import UUID

from mediease_api.domain.shared.errors import DomainError


class NotDraft(DomainError):
    """R6, AC1: an issued or superseded version never changes; revise it instead."""

    code = "RX_NOT_DRAFT"

    def __init__(self, status: str) -> None:
        super().__init__("This prescription is already issued; revise it instead.", status=status)


class Empty(DomainError):
    """R4: issuing needs at least one medicine or one piece of advice."""

    code = "RX_EMPTY"

    def __init__(self) -> None:
        super().__init__("Add at least one medicine or advice.")


class DoctorIncomplete(DomainError):
    """R4, AC4: the printed doctor details are missing; ``details.fields`` names them."""

    code = "RX_DOCTOR_INCOMPLETE"

    def __init__(self, fields: list[str]) -> None:
        super().__init__(
            "The doctor's profile is missing registration details.", fields=",".join(fields)
        )


class Stale(DomainError):
    """Decision 3A: the draft was saved elsewhere since this copy was loaded."""

    code = "RX_STALE"

    def __init__(self, revision: int) -> None:
        super().__init__(
            "This prescription was changed elsewhere; reload it and try again.",
            revision=str(revision),
        )


class AlreadyExists(DomainError):
    """Decision 1A: a visit has one prescription chain; open it."""

    code = "RX_ALREADY_EXISTS"

    def __init__(self, prescription_id: UUID) -> None:
        super().__init__(
            "This visit already has a prescription.", prescription_id=str(prescription_id)
        )


class DraftExists(DomainError):
    """Decision 1A: a chain has at most one draft; continue that one."""

    code = "RX_DRAFT_EXISTS"

    def __init__(self, prescription_id: UUID) -> None:
        super().__init__(
            "A revision is already being drafted.", prescription_id=str(prescription_id)
        )


class NotLatest(DomainError):
    """R6: only the latest issued version is revised."""

    code = "RX_NOT_LATEST"

    def __init__(self, latest_id: UUID) -> None:
        super().__init__("Revise the latest version.", latest_id=str(latest_id))
