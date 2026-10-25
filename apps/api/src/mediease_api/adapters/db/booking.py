"""``booking_requests`` repositories (M6b-P4, ports/booking.py).

``SqlAlchemyBookingRequestRepository`` is tenant-scoped. ``SqlAlchemyBookingRequestLookup`` is a
reviewed cross-clinic exception: it selects a patient account's own requests by account alone
(a portal caller names no clinic), and counts requests by phone for the rate limit. Nothing else
reads ``booking_requests`` across clinics.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.booking import BookingRequestRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.booking.request import BookingRequest, RequestExists, RequestStatus
from mediease_api.domain.patients.patient import Sex
from mediease_api.domain.shared.phone import PhoneNumber


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _request(row: BookingRequestRow) -> BookingRequest:
    return BookingRequest(
        id=row.id,
        clinic_id=row.clinic_id,
        doctor_id=row.doctor_id,
        session_id=row.session_id,
        slot_start=_utc(row.slot_start) if row.slot_start else None,
        account_id=row.account_id,
        contact_phone=PhoneNumber(row.contact_phone),
        age_years=row.age_years,
        sex=Sex(row.sex) if row.sex else None,
        reason=row.reason,
        status=RequestStatus(row.status),
        hold_expires_at=_utc(row.hold_expires_at),
        respond_by=_utc(row.respond_by),
        hold_overridden_at=_utc(row.hold_overridden_at) if row.hold_overridden_at else None,
        hold_overridden_by=row.hold_overridden_by,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


class SqlAlchemyBookingRequestRepository(TenantScopedRepository[BookingRequestRow]):
    model = BookingRequestRow
    entity_name = "booking request"

    def add(self, request: BookingRequest) -> None:
        self._check_owned(request.clinic_id)
        row = BookingRequestRow(
            id=request.id,
            clinic_id=self.clinic_id,
            doctor_id=request.doctor_id,
            session_id=request.session_id,
            slot_start=request.slot_start,
            account_id=request.account_id,
            contact_phone=request.contact_phone.e164,
            age_years=request.age_years,
            sex=request.sex.value if request.sex else None,
            reason=request.reason,
            status=request.status.value,
            hold_expires_at=request.hold_expires_at,
            respond_by=request.respond_by,
            hold_overridden_at=request.hold_overridden_at,
            hold_overridden_by=request.hold_overridden_by,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            if "uq_booking_requests_account_session_pending" in str(exc.orig):
                raise RequestExists() from None
            raise

    def update(self, request: BookingRequest) -> None:
        self._check_owned(request.clinic_id)
        row = self._require_row(request.id)
        row.hold_expires_at = request.hold_expires_at
        row.hold_overridden_at = request.hold_overridden_at
        row.hold_overridden_by = request.hold_overridden_by
        row.status = request.status.value
        row.updated_at = request.updated_at
        self._session.flush()

    def get(self, request_id: UUID) -> BookingRequest | None:
        row = self._get_row(request_id)
        return _request(row) if row else None

    def live_holds(self, session_ids: Collection[UUID], now: datetime) -> Sequence[BookingRequest]:
        ids = sorted(set(session_ids))
        if not ids:
            return []
        query = (
            self._scoped_select()
            .where(
                BookingRequestRow.session_id.in_(ids),
                BookingRequestRow.status == RequestStatus.PENDING.value,
                BookingRequestRow.hold_expires_at > now,
            )
            .order_by(BookingRequestRow.created_at, BookingRequestRow.id)
        )
        return [_request(row) for row in self._session.scalars(query)]

    def session_ids_with_pending(self, session_ids: Collection[UUID]) -> set[UUID]:
        ids = sorted(set(session_ids))
        if not ids:
            return set()
        query = (
            select(BookingRequestRow.session_id)
            .where(
                BookingRequestRow.clinic_id == self.clinic_id,
                BookingRequestRow.session_id.in_(ids),
                BookingRequestRow.status == RequestStatus.PENDING.value,
            )
            .distinct()
        )
        return set(self._session.scalars(query))

    def has_pending(self, account_id: UUID, session_id: UUID) -> bool:
        query = self._scoped_select().where(
            BookingRequestRow.account_id == account_id,
            BookingRequestRow.session_id == session_id,
            BookingRequestRow.status == RequestStatus.PENDING.value,
        )
        return self._session.scalars(query).first() is not None

    def list_pending(self, *, limit: int) -> Sequence[BookingRequest]:
        query = (
            self._scoped_select()
            .where(BookingRequestRow.status == RequestStatus.PENDING.value)
            .order_by(BookingRequestRow.created_at, BookingRequestRow.id)
            .limit(limit)
        )
        return [_request(row) for row in self._session.scalars(query)]


class SqlAlchemyBookingRequestLookup:
    def __init__(self, session: Session) -> None:
        self._session = session

    def count_open(self, account_id: UUID, now: datetime) -> int:
        query = select(func.count()).where(
            BookingRequestRow.account_id == account_id,
            BookingRequestRow.status == RequestStatus.PENDING.value,
            BookingRequestRow.respond_by > now,
        )
        return int(self._session.scalar(query) or 0)

    def for_account(self, account_id: UUID, *, limit: int) -> Sequence[BookingRequest]:
        query = (
            select(BookingRequestRow)
            .where(
                BookingRequestRow.account_id == account_id,
                BookingRequestRow.status == RequestStatus.PENDING.value,
            )
            .order_by(BookingRequestRow.created_at.desc(), BookingRequestRow.id)
            .limit(limit)
        )
        return [_request(row) for row in self._session.scalars(query)]

    def count_for_phone(self, e164: str, since: datetime) -> int:
        query = select(func.count()).where(
            BookingRequestRow.contact_phone == e164, BookingRequestRow.created_at >= since
        )
        return int(self._session.scalar(query) or 0)
