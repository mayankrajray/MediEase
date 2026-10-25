"""Clinic applications (migration 0032, M6c-P1; spec clinic-onboarding; ADR-0020).

Platform tables: an application belongs to no clinic until approval (FR-ONB-02), so there is no
``clinic_id`` and these are deliberately not ``TenantOwned``. Personal data (C2): the owner's
contact details and each doctor's registration; certificates live in private blob storage and
only their key, type, size and hash are here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, enum_check
from mediease_api.domain.onboarding.application import (
    ApplicationKind,
    ApplicationStatus,
    CheckResult,
    RejectReason,
)

# R9: references are MA-<year>-NNNN from one sequence, never reused.
APPLICATION_REFERENCE_SEQUENCE = Sequence(
    "clinic_application_reference_seq", metadata=Base.metadata
)


class ClinicApplicationRow(Keyed, Base):
    __tablename__ = "clinic_applications"
    __table_args__ = (
        enum_check("kind", ApplicationKind),
        enum_check("status", ApplicationStatus),
        CheckConstraint("pincode ~ '^[1-9][0-9]{5}$'", name="pincode_format"),
        # A spent or confirmed link leaves no digest behind.
        CheckConstraint(
            "email_verified_at IS NULL OR confirm_digest IS NULL", name="confirmed_no_digest"
        ),
        # Only a confirmed application can be reviewed.
        CheckConstraint(
            "status = 'PENDING' OR email_verified_at IS NOT NULL", name="reviewed_confirmed"
        ),
        enum_check("decision_reason", RejectReason),
        # R33, R41: a decision has its reviewer and time; a rejection its reason.
        CheckConstraint(
            "(status IN ('APPROVED', 'REJECTED')) = (decided_at IS NOT NULL)", name="decided"
        ),
        CheckConstraint(
            "(status = 'REJECTED') = (decision_reason IS NOT NULL)", name="rejected_reason"
        ),
        UniqueConstraint("reference"),
        UniqueConstraint("confirm_digest"),
        Index("ix_clinic_applications_owner_email", "owner_email"),
        Index("ix_clinic_applications_owner_phone_e164", "owner_phone_e164"),
        Index("ix_clinic_applications_ip_hash", "ip_hash"),
        Index("ix_clinic_applications_submitted_at", "submitted_at"),
    )

    reference: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    clinic_name: Mapped[str] = mapped_column(Text)
    address_line: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    pincode: Mapped[str] = mapped_column(Text)
    clinic_phone_e164: Mapped[str] = mapped_column(Text)
    specialties: Mapped[list[str]] = mapped_column(ARRAY(Text))
    owner_name: Mapped[str] = mapped_column(Text)
    owner_phone_e164: Mapped[str] = mapped_column(Text)
    owner_email: Mapped[str] = mapped_column(Text)
    owner_practises: Mapped[bool] = mapped_column(Boolean)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirm_digest: Mapped[str | None] = mapped_column(Text)
    duplicate_of: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    ip_hash: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # M6c-P2 (migration 0033, R27, R33): who took it and how it was decided; P3 the clinic.
    taken_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decision_message: Mapped[str | None] = mapped_column(Text)
    # P3: the clinic an approval created (not ``clinic_id``: still not a tenant row).
    created_clinic_id: Mapped[UUID | None] = mapped_column(ForeignKey("clinics.id"))


class ClinicApplicationCheckRow(Keyed, Base):
    """R29, R30: a reviewer's check of one application doctor (one row, replaced)."""

    __tablename__ = "clinic_application_checks"
    __table_args__ = (
        enum_check("result", CheckResult),
        CheckConstraint(
            "result = 'NOT_VERIFIED' OR (register_checked AND certificate_matches)",
            name="verified_needs_both",
        ),
        UniqueConstraint("doctor_id"),
    )

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinic_applications.id", ondelete="CASCADE")
    )
    doctor_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinic_application_doctors.id", ondelete="CASCADE")
    )
    checked_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    register_checked: Mapped[bool] = mapped_column(Boolean)
    certificate_matches: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class ClinicApplicationDoctorRow(Keyed, Base):
    __tablename__ = "clinic_application_doctors"
    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 10", name="position_range"),
        CheckConstraint("certificate_size BETWEEN 1 AND 5242880", name="certificate_size_range"),
        CheckConstraint(
            "certificate_content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="certificate_content_type",
        ),
        UniqueConstraint("application_id", "position"),
        # Named by hand: the generated name would pass PostgreSQL's 63-character limit.
        UniqueConstraint(
            "application_id",
            "registration_council",
            "registration_number",
            name="uq_clinic_application_doctors_registration",
        ),
        # R17: the duplicate check, by council and number.
        Index(
            "ix_clinic_application_doctors_registration",
            "registration_council",
            "registration_number",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("clinic_applications.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(Text)
    qualification: Mapped[str] = mapped_column(Text)
    registration_council: Mapped[str] = mapped_column(Text)
    registration_number: Mapped[str] = mapped_column(Text)
    is_owner: Mapped[bool] = mapped_column(Boolean)
    certificate_key: Mapped[str] = mapped_column(Text)
    certificate_content_type: Mapped[str] = mapped_column(Text)
    certificate_size: Mapped[int] = mapped_column(Integer)
    certificate_sha256: Mapped[str] = mapped_column(Text)
