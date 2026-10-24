"""Patient account links and portal invites (M6b-P1, migration 0025, docs/DATA_MODEL.md "M6b").

Both are tenant tables: a link and an invite belong to the clinic whose record they name, and are
reached through scoped repositories. The one cross-clinic read (an account's active links, and
which clinic an invite digest belongs to) is ``SqlAlchemyPortalLookup``, a reviewed exception.
"""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.portal.doses import DoseState
from mediease_api.domain.portal.link import LinkMethod, RevokedBy
from mediease_api.domain.prescriptions.schedule import Slot


class PatientAccountLinkRow(TenantOwned, Base):
    __tablename__ = "patient_account_links"
    __table_args__ = (
        enum_check("method", LinkMethod),
        enum_check("revoked_by", RevokedBy),
        CheckConstraint("(revoked_at IS NULL) = (revoked_by IS NULL)", name="revoked_together"),
        # Decision 1A: one active link per record, and one per account in a clinic.
        Index(
            "uq_patient_account_links_patient_active",
            "clinic_id",
            "patient_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "uq_patient_account_links_account_active",
            "clinic_id",
            "account_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # The portal scope: an account's active links in every clinic.
        Index(
            "ix_patient_account_links_account_id_active",
            "account_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id"))
    method: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(Text)


class PatientPortalInviteRow(TenantOwned, Base):
    """A single-use invite, stored as the SHA-256 digest of its secret (R1)."""

    __tablename__ = "patient_portal_invites"
    __table_args__ = (
        CheckConstraint("(used_at IS NULL) = (used_by_account_id IS NULL)", name="used_together"),
        CheckConstraint("used_at IS NULL OR superseded_at IS NULL", name="used_or_superseded"),
        # One pending invite per record: a new one supersedes the old first.
        Index(
            "uq_patient_portal_invites_patient_pending",
            "clinic_id",
            "patient_id",
            unique=True,
            postgresql_where=text("used_at IS NULL AND superseded_at IS NULL"),
        ),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("patient_accounts.id"))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MedicineReminderPrefRow(TenantOwned, Timestamps, Base):
    """M6b-P3 (migration 0027, R37-R40): one account's reminder choice for one line and slot.

    Stored only (delivery is M6b-P6). Never a change to the prescription; removed on unlink.
    """

    __tablename__ = "medicine_reminder_prefs"
    __table_args__ = (
        # The column-named default would pass 63 characters.
        UniqueConstraint(
            "account_id",
            "prescription_id",
            "item_id",
            "slot",
            name="uq_medicine_reminder_prefs_line_slot",
        ),
        Index("ix_medicine_reminder_prefs_clinic_id_patient_id", "clinic_id", "patient_id"),
        enum_check("slot", Slot),
        CheckConstraint(
            "remind_at IS NULL OR remind_at BETWEEN '05:00' AND '23:30'", name="remind_at_range"
        ),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id"))
    prescription_id: Mapped[UUID] = mapped_column(ForeignKey("prescriptions.id"))
    # No foreign key: an issued version's items cannot be deleted (trigger, migration 0010), and
    # a key would stand in front of that trigger (prescriptions AC1). Checked by the use case.
    item_id: Mapped[UUID] = mapped_column()
    slot: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean)
    remind_at: Mapped[time | None] = mapped_column(Time)


class DoseRecordRow(TenantOwned, Timestamps, Base):
    """M6b-P3b (migration 0028, R45-R54): one account's Taken / Skipped mark for one dose.

    Health data (C3), patient routes only. Not recorded is never stored; no reason, no text.
    """

    __tablename__ = "dose_records"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "prescription_id",
            "item_id",
            "on_date",
            "slot",
            name="uq_dose_records_dose",
        ),
        Index("ix_dose_records_account_id_prescription_id", "account_id", "prescription_id"),
        Index("ix_dose_records_keep_until", "keep_until"),
        enum_check("slot", Slot),
        enum_check("state", DoseState),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id"))
    prescription_id: Mapped[UUID] = mapped_column(ForeignKey("prescriptions.id"))
    # No foreign key, as for reminder choices: issued items are never deleted.
    item_id: Mapped[UUID] = mapped_column()
    on_date: Mapped[date] = mapped_column(Date)
    slot: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    keep_until: Mapped[date] = mapped_column(Date)
