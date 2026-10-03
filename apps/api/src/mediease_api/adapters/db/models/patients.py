"""The ``patients`` table (M2-P1, migration 0006, docs/DATA_MODEL.md "M2")."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.patients.patient import Language, Sex


class PatientRow(TenantOwned, Timestamps, Base):
    """A patient of one clinic. Reached only through ``SqlAlchemyPatientRepository``."""

    __tablename__ = "patients"
    __table_args__ = (
        # I3: a code is unique within a clinic; this index also serves exact code lookup.
        UniqueConstraint("clinic_id", "code"),
        # Exact phone lookup and the duplicate-phone check (families share phones).
        Index("ix_patients_clinic_id_phone_e164", "clinic_id", "phone_e164"),
        # Case-insensitive name *prefix* lookup: text_pattern_ops lets LIKE 'ab%' use the index.
        # SQLAlchemy has no way to attach an operator class to an expression, so it is in the
        # text, and Alembic cannot compare this one index (it warns); the lookup test plans the
        # repository's own SQL with sequential scans off, which fails if the index stops matching.
        Index(
            "ix_patients_clinic_id_lower_full_name",
            "clinic_id",
            text("lower(full_name) text_pattern_ops"),
        ),
        enum_check("sex", Sex),
        enum_check("language", Language),
        # I1 / I4: a date of birth or a recorded age, never neither, never both.
        CheckConstraint(
            "(date_of_birth IS NOT NULL) <> (age_years_at_registration IS NOT NULL)",
            name="age_known",
        ),
        CheckConstraint(
            "age_years_at_registration IS NULL OR age_years_at_registration BETWEEN 0 AND 120",
            name="age_years_at_registration_range",
        ),
        # R6: a consent flag can only be true if someone recorded it.
        CheckConstraint(
            "(NOT whatsapp_consent AND NOT sms_consent) OR consent_recorded_at IS NOT NULL",
            name="consent_recorded",
        ),
    )

    code: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    # The contact of record; for a minor, the guardian's number (spec D1).
    phone_e164: Mapped[str] = mapped_column(Text)
    sex: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column()
    age_years_at_registration: Mapped[int | None] = mapped_column()
    registered_on: Mapped[date] = mapped_column()
    guardian_name: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, server_default=text("'en'"))
    whatsapp_consent: Mapped[bool] = mapped_column(server_default=text("false"))
    sms_consent: Mapped[bool] = mapped_column(server_default=text("false"))
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_recorded_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
