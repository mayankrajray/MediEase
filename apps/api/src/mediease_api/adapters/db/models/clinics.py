"""Tables for clinics, doctors and onboarding (migrations 0002 and 0005, docs/DATA_MODEL.md)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, TenantOwned, Timestamps, enum_check
from mediease_api.domain.clinics.clinic import ClinicStatus


class ClinicRow(Keyed, Timestamps, Base):
    """A clinic — the tenant itself, so it has no ``clinic_id``."""

    __tablename__ = "clinics"
    __table_args__ = (enum_check("status", ClinicStatus),)

    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    timezone: Mapped[str] = mapped_column(Text, server_default=text("'Asia/Kolkata'"))
    status: Mapped[str] = mapped_column(Text)
    phone_e164: Mapped[str | None] = mapped_column(Text)
    address_line: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    pincode: Mapped[str | None] = mapped_column(Text)
    specialties: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))


class DoctorRow(TenantOwned, Timestamps, Base):
    """A doctor profile at one clinic, optionally linked to a user who signs in."""

    __tablename__ = "doctors"
    __table_args__ = (
        Index("ix_doctors_clinic_id", "clinic_id"),
        # One doctor profile per user per clinic (spec §8: owner who is also a doctor).
        Index(
            "uq_doctors_clinic_id_user_id",
            "clinic_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    display_name: Mapped[str] = mapped_column(Text)
    qualification: Mapped[str] = mapped_column(Text)
    registration_number: Mapped[str] = mapped_column(Text)
    registration_council: Mapped[str] = mapped_column(Text)
    specialty: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))


class OnboardingChecklistRow(TenantOwned, Base):
    """When each onboarding step first happened, one row per clinic (M1-P5, R12).

    No ``updated_at``: every column is itself a timestamp, written once.
    """

    __tablename__ = "onboarding_checklists"
    __table_args__ = (UniqueConstraint("clinic_id"),)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    clinic_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    doctors_added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staff_invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Written by M2-M4; the columns exist now so the G4 measurement is not retrofitted.
    patients_imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_appointment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_prescription_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
