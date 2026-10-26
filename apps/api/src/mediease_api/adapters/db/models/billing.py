"""Billing tables (M6d; migration 0036 onward; docs/DATA_MODEL.md "M6d")."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.billing.fees import ServiceKind

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
