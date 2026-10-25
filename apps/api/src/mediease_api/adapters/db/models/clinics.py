"""Tables for clinics, doctors and onboarding (migrations 0002 and 0005, docs/DATA_MODEL.md)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, TenantOwned, Timestamps, enum_check
from mediease_api.domain.clinics.clinic import ClinicStatus, PaperSize
from mediease_api.domain.clinics.verification import VerificationSource
from mediease_api.domain.scheduling.mode import BookingMode


class ClinicRow(Keyed, Timestamps, Base):
    """A clinic — the tenant itself, so it has no ``clinic_id``."""

    __tablename__ = "clinics"
    __table_args__ = (
        enum_check("status", ClinicStatus),
        enum_check("booking_mode", BookingMode),
        enum_check("rx_paper_size", PaperSize),
        CheckConstraint("patient_code_prefix ~ '^[A-Z]{2,4}$'", name="patient_code_prefix_format"),
        CheckConstraint("next_patient_seq >= 1", name="next_patient_seq_positive"),
        CheckConstraint(
            "reminder_hours_before BETWEEN 0 AND 6", name="reminder_hours_before_range"
        ),
        CheckConstraint(
            "request_hold_minutes BETWEEN 30 AND 480", name="request_hold_minutes_range"
        ),
        enum_check("verification_source", VerificationSource),
        # Listed only when verified (FR-ONB-09); the rest of the requirements are checked by the
        # use case (they span tables).
        CheckConstraint("NOT listed OR verified_at IS NOT NULL", name="listed_verified"),
    )

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
    # M2 (migration 0006): patient codes are "<prefix>-<seq>"; the counter is locked to allocate.
    patient_code_prefix: Mapped[str] = mapped_column(Text)
    next_patient_seq: Mapped[int] = mapped_column(server_default=text("1"))
    # M3 (migration 0007): slot or token booking for the clinic's sessions.
    booking_mode: Mapped[str] = mapped_column(Text, server_default=text("'TOKENS'"))
    # M4-P4 (migration 0012): prescription stationery, read when a version is first rendered.
    rx_paper_size: Mapped[str] = mapped_column(Text, server_default=text("'A5'"))
    # M6a-P8 (migration 0024): appointment reminders, the evening before and hours before.
    reminder_evening_before: Mapped[bool] = mapped_column(server_default=text("true"))
    reminder_hours_before: Mapped[int] = mapped_column(SmallInteger, server_default=text("2"))
    # M6b-P4 (migration 0029): how long an online request holds its slot, and whether the
    # request form must ask age and sex.
    request_hold_minutes: Mapped[int] = mapped_column(SmallInteger, server_default=text("120"))
    request_requires_age_sex: Mapped[bool] = mapped_column(server_default=text("false"))
    # M6c-P3, P4, P5 (migration 0034): MediEase's verification, the directory listing and
    # whether search engines may index the profiles.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    verification_source: Mapped[str | None] = mapped_column(Text)
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clinic_applications.id", use_alter=True)
    )
    listed: Mapped[bool] = mapped_column(server_default=text("false"))
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_indexing: Mapped[bool] = mapped_column(server_default=text("true"))


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
        enum_check("verification_source", VerificationSource),
        CheckConstraint(
            "fee_paise IS NULL OR fee_paise BETWEEN 0 AND 1000000", name="fee_paise_range"
        ),
    )

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    display_name: Mapped[str] = mapped_column(Text)
    qualification: Mapped[str] = mapped_column(Text)
    registration_number: Mapped[str] = mapped_column(Text)
    registration_council: Mapped[str] = mapped_column(Text)
    specialty: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    # M6c-P3, P4, P5 (migration 0034): verification, directory visibility and the profile.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    verification_source: Mapped[str | None] = mapped_column(Text)
    visible: Mapped[bool] = mapped_column(server_default=text("false"))
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    fee_paise: Mapped[int | None]


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
