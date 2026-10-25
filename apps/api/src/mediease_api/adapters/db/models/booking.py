"""Booking requests (migration 0029, M6b-P4, ADR-0018, docs/DATA_MODEL.md "M6b").

Tenant data. A request is also the soft hold on its slot; it holds no clinic patient record until
P5 accepts it. The reason is clinical text (C3): never logged.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.booking.request import RequestStatus
from mediease_api.domain.patients.patient import Sex


class BookingRequestRow(TenantOwned, Timestamps, Base):
    __tablename__ = "booking_requests"
    __table_args__ = (
        enum_check("status", RequestStatus),
        enum_check("sex", Sex),
        CheckConstraint("age_years IS NULL OR age_years BETWEEN 0 AND 120", name="age_range"),
        CheckConstraint(
            "reason IS NULL OR char_length(reason) BETWEEN 1 AND 200", name="reason_length"
        ),
        CheckConstraint("hold_expires_at <= respond_by", name="hold_within_deadline"),
        CheckConstraint(
            "(hold_overridden_at IS NULL) = (hold_overridden_by IS NULL)",
            name="override_together",
        ),
        # One open request per account and session (R14). Not per slot: a lapsed hold must not
        # stop the next request, so the session lock guards the slot (ADR-0018).
        Index(
            "uq_booking_requests_account_session_pending",
            "account_id",
            "session_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("ix_booking_requests_session_id", "session_id"),
        Index(
            "ix_booking_requests_clinic_id_status_created_at", "clinic_id", "status", "created_at"
        ),
        Index("ix_booking_requests_account_id", "account_id"),
    )

    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"))
    slot_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id"))
    contact_phone: Mapped[str] = mapped_column(Text)
    age_years: Mapped[int | None] = mapped_column(SmallInteger)
    sex: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    hold_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    respond_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hold_overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hold_overridden_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
