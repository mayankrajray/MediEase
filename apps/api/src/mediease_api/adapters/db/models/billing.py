"""Billing tables (M6d; migration 0036 onward; docs/DATA_MODEL.md "M6d")."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.billing.bill import BillKind, BillStatus, DiscountKind
from mediease_api.domain.billing.fees import ServiceKind
from mediease_api.domain.billing.payment import PaymentKind, PaymentMode

_PRICE = "BETWEEN 0 AND 10000000"  # B1: ₹1,00,000 at most


class ClinicServiceRow(TenantOwned, Timestamps, Base):
    """One line of a clinic's fee schedule (M6d-P1, R1)."""

    __tablename__ = "clinic_services"
    __table_args__ = (
        enum_check("kind", ServiceKind),
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="name_length"),
        CheckConstraint(
            f"default_price_paise IS NULL OR default_price_paise {_PRICE}", name="price_range"
        ),
        CheckConstraint("position BETWEEN 1 AND 100", name="position_range"),
        # R3: active names are unique per clinic, ignoring case.
        Index(
            "uq_clinic_services_clinic_id_name",
            "clinic_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    default_price_paise: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    position: Mapped[int] = mapped_column(SmallInteger)


class DoctorServicePriceRow(TenantOwned, Timestamps, Base):
    """A doctor's own price for one service (M6d-P1, R4)."""

    __tablename__ = "doctor_service_prices"
    __table_args__ = (
        CheckConstraint(f"price_paise {_PRICE}", name="price_range"),
        Index(
            "uq_doctor_service_prices_service_id_doctor_id",
            "service_id",
            "doctor_id",
            unique=True,
        ),
    )

    service_id: Mapped[UUID] = mapped_column(ForeignKey("clinic_services.id"))
    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    price_paise: Mapped[int] = mapped_column(Integer)


_BILL_TOTAL = "BETWEEN 0 AND 100000000"  # B1: a bill up to ₹10,00,000


class BillRow(TenantOwned, Timestamps, Base):
    """A bill or a credit note (M6d-P2, spec billing R13-R30, ADR-0022)."""

    __tablename__ = "bills"
    __table_args__ = (
        enum_check("kind", BillKind),
        enum_check("status", BillStatus),
        enum_check("discount_kind", DiscountKind),
        CheckConstraint(f"subtotal_paise {_BILL_TOTAL}", name="subtotal_range"),
        CheckConstraint(f"total_paise {_BILL_TOTAL}", name="total_range"),
        CheckConstraint("discount_paise BETWEEN 0 AND subtotal_paise", name="discount_range"),
        CheckConstraint("discount_value >= 0", name="discount_value_range"),
        CheckConstraint(
            "credited_paise BETWEEN 0 AND total_paise AND paid_paise >= 0 AND refunded_paise >= 0",
            name="money_range",
        ),
        CheckConstraint("notes IS NULL OR char_length(notes) <= 500", name="notes_length"),
        CheckConstraint("reason IS NULL OR char_length(reason) <= 200", name="reason_length"),
        # R20: a number exactly when issued; a credit note is always issued and names its bill.
        CheckConstraint(
            "(status = 'DRAFT') = (number IS NULL)"
            " AND (number IS NULL) = (seq IS NULL)"
            " AND (number IS NULL) = (financial_year IS NULL)"
            " AND (number IS NULL) = (bill_date IS NULL)"
            " AND (number IS NULL) = (issued_at IS NULL)",
            name="numbered_when_issued",
        ),
        CheckConstraint(
            "(kind = 'CREDIT_NOTE') = (credits_bill_id IS NOT NULL)"
            " AND (kind = 'BILL' OR (status = 'ISSUED' AND reason IS NOT NULL))",
            name="credit_note_shape",
        ),
        # B5: one number per clinic, kind and financial year.
        Index(
            "uq_bills_clinic_id_kind_financial_year_seq",
            "clinic_id",
            "kind",
            "financial_year",
            "seq",
            unique=True,
        ),
        # R14: one open bill per visit (a cancelled one may be billed again).
        Index(
            "uq_bills_visit_id",
            "visit_id",
            unique=True,
            postgresql_where=text("kind = 'BILL' AND status <> 'CANCELLED'"),
        ),
        Index("ix_bills_clinic_id_created_at", "clinic_id", "created_at"),
        Index("ix_bills_clinic_id_patient_id", "clinic_id", "patient_id"),
        Index("ix_bills_credits_bill_id", "credits_bill_id"),
    )

    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    visit_id: Mapped[UUID | None] = mapped_column(ForeignKey("visits.id"))
    doctor_id: Mapped[UUID | None] = mapped_column(ForeignKey("doctors.id"))
    discount_kind: Mapped[str] = mapped_column(Text)
    discount_value: Mapped[int] = mapped_column(Integer)
    subtotal_paise: Mapped[int] = mapped_column(Integer)
    discount_paise: Mapped[int] = mapped_column(Integer)
    total_paise: Mapped[int] = mapped_column(Integer)
    credited_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    paid_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    refunded_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    number: Mapped[str | None] = mapped_column(Text)
    financial_year: Mapped[str | None] = mapped_column(Text)
    seq: Mapped[int | None] = mapped_column(Integer)
    bill_date: Mapped[date | None] = mapped_column(Date)
    credits_bill_id: Mapped[UUID | None] = mapped_column(ForeignKey("bills.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    issued_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BillLineRow(TenantOwned, Base):
    """One line of a bill or a credit note, a snapshot (B3)."""

    __tablename__ = "bill_lines"
    __table_args__ = (
        enum_check("discount_kind", DiscountKind),
        CheckConstraint("position BETWEEN 1 AND 50", name="position_range"),
        CheckConstraint("quantity BETWEEN 1 AND 99", name="quantity_range"),
        CheckConstraint(f"unit_price_paise {_PRICE}", name="unit_price_range"),
        CheckConstraint("char_length(description) BETWEEN 1 AND 80", name="description_length"),
        CheckConstraint(
            "discount_value >= 0 AND discount_paise >= 0 AND bill_discount_paise >= 0"
            " AND amount_paise >= 0"
            " AND amount_paise"
            " = unit_price_paise * quantity - discount_paise - bill_discount_paise",
            name="amounts",
        ),
        Index("uq_bill_lines_bill_id_position", "bill_id", "position", unique=True),
        # R24: a line is credited at most once.
        Index("uq_bill_lines_credits_line_id", "credits_line_id", unique=True),
    )

    bill_id: Mapped[UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("clinic_services.id"))
    description: Mapped[str] = mapped_column(Text)
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(SmallInteger)
    discount_kind: Mapped[str] = mapped_column(Text)
    discount_value: Mapped[int] = mapped_column(Integer)
    discount_paise: Mapped[int] = mapped_column(Integer)
    bill_discount_paise: Mapped[int] = mapped_column(Integer)
    amount_paise: Mapped[int] = mapped_column(Integer)
    credits_line_id: Mapped[UUID | None] = mapped_column(ForeignKey("bill_lines.id"))


class PaymentRow(TenantOwned, Base):
    """A payment or refund on a bill (M6d-P3, spec billing R31-R42)."""

    __tablename__ = "payments"
    __table_args__ = (
        enum_check("kind", PaymentKind),
        enum_check("mode", PaymentMode),
        CheckConstraint("amount_paise BETWEEN 1 AND 100000000", name="amount_range"),
        CheckConstraint(
            "reference IS NULL OR char_length(reference) <= 40", name="reference_length"
        ),
        # R35: a void has its time, its author and its reason, or none of them.
        CheckConstraint(
            "(voided_at IS NULL) = (voided_by IS NULL)"
            " AND (voided_at IS NULL) = (void_reason IS NULL)",
            name="voided_together",
        ),
        CheckConstraint(
            "void_reason IS NULL OR char_length(void_reason) <= 200", name="void_reason_length"
        ),
        Index("ix_payments_bill_id", "bill_id"),
        # P5: the day's collection.
        Index("ix_payments_clinic_id_local_date", "clinic_id", "local_date"),
    )

    bill_id: Mapped[UUID] = mapped_column(ForeignKey("bills.id"))
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    doctor_id: Mapped[UUID | None] = mapped_column(ForeignKey("doctors.id"))
    kind: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    amount_paise: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str | None] = mapped_column(Text)
    received_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    local_date: Mapped[date] = mapped_column(Date)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)
