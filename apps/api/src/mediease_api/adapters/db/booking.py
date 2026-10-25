"""``booking_requests`` repositories (M6b-P4, ports/booking.py).

``SqlAlchemyBookingRequestRepository`` is tenant-scoped. ``SqlAlchemyBookingRequestLookup`` is a
reviewed cross-clinic exception: it selects a patient account's own requests by account alone
(a portal caller names no clinic), and counts requests by phone for the rate limit. Nothing else
reads ``booking_requests`` across clinics.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.booking import BookingRequestRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.booking.request import (
    OPEN_STATUSES,
    BookingRequest,
    DecidedBy,
    DeclineReason,
    RequestExists,
    RequestStatus,
)
from mediease_api.domain.patients.patient import Sex
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.booking import RequestCounts


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _opt(value: datetime | None) -> datetime | None:
    return _utc(value) if value is not None else None


_OPEN = sorted(s.value for s in OPEN_STATUSES)
# Final requests shown on the patient's and staff's "answered" lists (R44, R48).
ANSWERED_DAYS = 7


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
        patient_id=row.patient_id,
        appointment_id=row.appointment_id,
        answered_at=_opt(row.answered_at),
        answered_by=row.answered_by,
        decided_at=_opt(row.decided_at),
        decided_by_type=DecidedBy(row.decided_by_type) if row.decided_by_type else None,
        decline_reason=DeclineReason(row.decline_reason) if row.decline_reason else None,
        decline_note=row.decline_note,
        original_session_id=row.original_session_id,
        original_slot_start=_opt(row.original_slot_start),
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
        row.session_id = request.session_id
        row.slot_start = request.slot_start
        row.hold_expires_at = request.hold_expires_at
        row.respond_by = request.respond_by
        row.hold_overridden_at = request.hold_overridden_at
        row.hold_overridden_by = request.hold_overridden_by
        row.status = request.status.value
        row.updated_at = request.updated_at
        row.patient_id = request.patient_id
        row.appointment_id = request.appointment_id
        row.answered_at = request.answered_at
        row.answered_by = request.answered_by
        row.decided_at = request.decided_at
        row.decided_by_type = request.decided_by_type.value if request.decided_by_type else None
        row.decline_reason = request.decline_reason.value if request.decline_reason else None
        row.decline_note = request.decline_note
        row.original_session_id = request.original_session_id
        row.original_slot_start = request.original_slot_start
        try:
            with self._session.begin_nested():
                self._session.flush()
        except IntegrityError as exc:  # a proposal onto a session the account already asked for
            if "uq_booking_requests_account_session_pending" in str(exc.orig):
                raise RequestExists() from None
            raise

    def get(self, request_id: UUID, *, for_update: bool = False) -> BookingRequest | None:
        """R31a: ``for_update`` locks the row, so exactly one answer can win."""
        query = self._scoped_select().where(BookingRequestRow.id == request_id)
        if for_update:
            query = query.with_for_update()
        row = self._session.scalars(query).one_or_none()
        return _request(row) if row else None

    def live_holds(self, session_ids: Collection[UUID], now: datetime) -> Sequence[BookingRequest]:
        ids = sorted(set(session_ids))
        if not ids:
            return []
        query = (
            self._scoped_select()
            .where(
                BookingRequestRow.session_id.in_(ids),
                BookingRequestRow.status.in_(_OPEN),
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
                BookingRequestRow.status.in_(_OPEN),
            )
            .distinct()
        )
        return set(self._session.scalars(query))

    def has_pending(self, account_id: UUID, session_id: UUID) -> bool:
        query = self._scoped_select().where(
            BookingRequestRow.account_id == account_id,
            BookingRequestRow.session_id == session_id,
            BookingRequestRow.status.in_(_OPEN),
        )
        return self._session.scalars(query).first() is not None

    def list_open(self, now: datetime, *, limit: int) -> Sequence[BookingRequest]:
        query = (
            self._scoped_select()
            .where(BookingRequestRow.status.in_(_OPEN), BookingRequestRow.respond_by > now)
            .order_by(BookingRequestRow.created_at, BookingRequestRow.id)
            .limit(limit)
        )
        return [_request(row) for row in self._session.scalars(query)]

    def list_answered(self, now: datetime, *, limit: int) -> Sequence[BookingRequest]:
        """Final in the last 7 days, or open past the deadline (expired before the sweep)."""
        since = now - timedelta(days=ANSWERED_DAYS)
        final = BookingRequestRow.status.not_in(_OPEN) & (BookingRequestRow.decided_at >= since)
        overdue = BookingRequestRow.status.in_(_OPEN) & (BookingRequestRow.respond_by <= now)
        query = (
            self._scoped_select()
            .where(final | (overdue & (BookingRequestRow.respond_by >= since)))
            .order_by(
                func.coalesce(BookingRequestRow.decided_at, BookingRequestRow.respond_by).desc(),
                BookingRequestRow.id,
            )
            .limit(limit)
        )
        return [_request(row) for row in self._session.scalars(query)]

    def list_overdue_ids(self, now: datetime, *, limit: int) -> Sequence[UUID]:
        query = (
            select(BookingRequestRow.id)
            .where(
                BookingRequestRow.clinic_id == self.clinic_id,
                BookingRequestRow.status.in_(_OPEN),
                BookingRequestRow.respond_by <= now,
            )
            .order_by(BookingRequestRow.respond_by, BookingRequestRow.id)
            .limit(limit)
        )
        return list(self._session.scalars(query))

    def counts(self, now: datetime, *, days: int) -> RequestCounts:
        """R45, R46: open now; over ``days``, answered by staff and expired unanswered."""
        since = now - timedelta(days=days)
        row = self._session.execute(
            text(
                "SELECT"
                " count(*) FILTER (WHERE status IN ('PENDING', 'PROPOSED') AND respond_by > :now)"
                "   AS open,"
                " count(*) FILTER (WHERE created_at >= :since AND answered_at IS NOT NULL)"
                "   AS answered,"
                " count(*) FILTER (WHERE created_at >= :since AND answered_at IS NULL"
                "   AND (status = 'EXPIRED' OR (status IN ('PENDING', 'PROPOSED')"
                "   AND respond_by <= :now))) AS expired"
                " FROM booking_requests WHERE clinic_id = :clinic"
            ),
            {"now": now, "since": since, "clinic": self.clinic_id},
        ).one()
        return RequestCounts(open=row.open, answered=row.answered, expired=row.expired)


class SqlAlchemyBookingRequestLookup:
    def __init__(self, session: Session) -> None:
        self._session = session

    def count_open(self, account_id: UUID, now: datetime) -> int:
        query = select(func.count()).where(
            BookingRequestRow.account_id == account_id,
            BookingRequestRow.status.in_(_OPEN),
            BookingRequestRow.respond_by > now,
        )
        return int(self._session.scalar(query) or 0)

    def find_for_account(self, account_id: UUID, request_id: UUID) -> BookingRequest | None:
        """R42, R43: the account's own request, in whichever clinic (else None: a 404)."""
        query = select(BookingRequestRow).where(
            BookingRequestRow.id == request_id, BookingRequestRow.account_id == account_id
        )
        row = self._session.scalars(query).one_or_none()
        return _request(row) if row else None

    def clinics_with_overdue(self, now: datetime) -> Sequence[UUID]:
        """R32: active clinics with open requests past their deadline (IDs only, for the sweep)."""
        rows = self._session.execute(
            text(
                "SELECT DISTINCT b.clinic_id FROM booking_requests b"
                " JOIN clinics c ON c.id = b.clinic_id"
                " WHERE b.status IN ('PENDING', 'PROPOSED') AND b.respond_by <= :now"
                " AND c.status = 'ACTIVE' ORDER BY b.clinic_id"
            ),
            {"now": now},
        )
        return [row.clinic_id for row in rows]

    def for_account(
        self, account_id: UUID, now: datetime, *, limit: int
    ) -> Sequence[BookingRequest]:
        """R48: open, or final in the last 7 days (not accepted: the appointment shows instead)."""
        since = now - timedelta(days=ANSWERED_DAYS)
        recent = BookingRequestRow.status.in_(
            [RequestStatus.DECLINED.value, RequestStatus.EXPIRED.value]
        ) & (BookingRequestRow.decided_at >= since)
        query = (
            select(BookingRequestRow)
            .where(
                BookingRequestRow.account_id == account_id,
                BookingRequestRow.status.in_(_OPEN) | recent,
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
