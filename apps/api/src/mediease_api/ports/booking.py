"""Booking requests (M6b-P4, ADR-0018; spec booking-requests)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.booking.request import BookingRequest


@dataclass(frozen=True, slots=True)
class RequestCounts:
    """R45, R46: open now; answered by staff and expired unanswered over a window."""

    open: int
    answered: int
    expired: int


class BookingRequestRepository(Protocol):
    """``booking_requests`` of one clinic (tenant-scoped, ADR-0003)."""

    def add(self, request: BookingRequest) -> None:
        """Insert; a concurrent second open request for the same account and session is
        ``PRT_REQUEST_EXISTS``."""
        ...

    def update(self, request: BookingRequest) -> None:
        """Save the request (a hold override, an answer, a proposal or its expiry). A proposal onto
        a session the account already has an open request for is ``PRT_REQUEST_EXISTS``."""
        ...

    def get(self, request_id: UUID, *, for_update: bool = False) -> BookingRequest | None:
        """``for_update`` takes the row lock every answer needs (R31a)."""
        ...

    def live_holds(self, session_ids: Collection[UUID], now: datetime) -> Sequence[BookingRequest]:
        """Open requests whose hold has not ended, oldest first. Read under the session lock."""
        ...

    def session_ids_with_pending(self, session_ids: Collection[UUID]) -> set[UUID]:
        """Sessions a pending request points at, held or not: never deleted or retired."""
        ...

    def has_pending(self, account_id: UUID, session_id: UUID) -> bool: ...

    def list_open(self, now: datetime, *, limit: int) -> Sequence[BookingRequest]:
        """Open and not past the deadline, oldest first (the inbox, R44)."""
        ...

    def list_answered(self, now: datetime, *, limit: int) -> Sequence[BookingRequest]:
        """Final in the last 7 days, and open ones past their deadline; newest first (R44)."""
        ...

    def list_overdue_ids(self, now: datetime, *, limit: int) -> Sequence[UUID]:
        """Open requests past their deadline, for the expiry job (R32)."""
        ...

    def counts(self, now: datetime, *, days: int) -> RequestCounts: ...


class BookingRequestLookup(Protocol):
    """The patient's own requests in every clinic (reviewed cross-clinic exception).

    A portal caller names no clinic. It selects by account alone; every clinic, doctor and session
    is then read through that clinic's tenant repositories.
    """

    def count_open(self, account_id: UUID, now: datetime) -> int:
        """Pending requests whose response deadline has not passed (FR-BKG-07: at most 5)."""
        ...

    def for_account(
        self, account_id: UUID, now: datetime, *, limit: int
    ) -> Sequence[BookingRequest]:
        """Open, or declined or expired in the last 7 days; newest first (R48)."""
        ...

    def find_for_account(self, account_id: UUID, request_id: UUID) -> BookingRequest | None:
        """The account's own request by ID, in any clinic; None for anyone else's."""
        ...

    def clinics_with_overdue(self, now: datetime) -> Sequence[UUID]:
        """Active clinics with open requests past their deadline (IDs only; the sweep, R32)."""
        ...

    def count_for_phone(self, e164: str, since: datetime) -> int:
        """Requests made with this number since ``since``, in any clinic (R15)."""
        ...
