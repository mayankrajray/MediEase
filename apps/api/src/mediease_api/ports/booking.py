"""Booking requests (M6b-P4, ADR-0018; spec booking-requests)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.booking.request import BookingRequest


class BookingRequestRepository(Protocol):
    """``booking_requests`` of one clinic (tenant-scoped, ADR-0003)."""

    def add(self, request: BookingRequest) -> None:
        """Insert; a concurrent second open request for the same account and session is
        ``PRT_REQUEST_EXISTS``."""
        ...

    def update(self, request: BookingRequest) -> None:
        """Save the hold's end (a staff override)."""
        ...

    def get(self, request_id: UUID) -> BookingRequest | None: ...

    def live_holds(self, session_ids: Collection[UUID], now: datetime) -> Sequence[BookingRequest]:
        """Pending requests whose hold has not ended, oldest first. Read under the session lock."""
        ...

    def session_ids_with_pending(self, session_ids: Collection[UUID]) -> set[UUID]:
        """Sessions a pending request points at, held or not: never deleted or retired."""
        ...

    def has_pending(self, account_id: UUID, session_id: UUID) -> bool: ...

    def list_pending(self, *, limit: int) -> Sequence[BookingRequest]:
        """The clinic's open requests, oldest first (staff list, R22)."""
        ...


class BookingRequestLookup(Protocol):
    """The patient's own requests in every clinic (reviewed cross-clinic exception).

    A portal caller names no clinic. It selects by account alone; every clinic, doctor and session
    is then read through that clinic's tenant repositories.
    """

    def count_open(self, account_id: UUID, now: datetime) -> int:
        """Pending requests whose response deadline has not passed (FR-BKG-07: at most 5)."""
        ...

    def for_account(self, account_id: UUID, *, limit: int) -> Sequence[BookingRequest]:
        """Newest first."""
        ...

    def count_for_phone(self, e164: str, since: datetime) -> int:
        """Requests made with this number since ``since``, in any clinic (R15)."""
        ...
