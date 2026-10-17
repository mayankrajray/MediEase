"""Appointments and their status history (M3-P2, migration 0008, docs/DATA_MODEL.md "M3")."""

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
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.appointments.status import (
    AppointmentSource,
    AppointmentStatus,
    CancelReason,
)

_ACTIVE = "status <> 'CANCELLED'"


class AppointmentRow(TenantOwned, Timestamps, Base):
    """One patient's place in one session. The database backs every booking rule (FR-APT-04)."""

    __tablename__ = "appointments"
    __table_args__ = (
        # One active appointment per slot (R3) and per patient in a session (D13).
        Index(
            "uq_appointments_session_id_slot_start_active",
            "session_id",
            "slot_start",
            unique=True,
            postgresql_where=text(f"{_ACTIVE} AND slot_start IS NOT NULL"),
        ),
        Index(
            "uq_appointments_session_id_patient_id_active",
            "session_id",
            "patient_id",
            unique=True,
            postgresql_where=text(_ACTIVE),
        ),
        # A token is never handed out twice in a session, cancelled or not (R4).
        UniqueConstraint("session_id", "token_number"),
        Index("ix_appointments_clinic_id_doctor_id_status", "clinic_id", "doctor_id", "status"),
        Index(
            "ix_appointments_clinic_id_patient_id_created_at",
            "clinic_id",
            "patient_id",
            text("created_at DESC"),
        ),
        enum_check("status", AppointmentStatus),
        enum_check("source", AppointmentSource),
        enum_check("cancel_reason", CancelReason),
        CheckConstraint("(slot_start IS NULL) <> (token_number IS NULL)", name="one_place"),
        CheckConstraint("token_number IS NULL OR token_number >= 1", name="token_positive"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancel_reason IS NOT NULL AND cancelled_at IS NOT NULL)",
            name="cancelled_has_reason",
        ),
        CheckConstraint("reason IS NULL OR char_length(reason) <= 120", name="reason_length"),
        CheckConstraint(
            "cancel_note IS NULL OR char_length(cancel_note) <= 200", name="cancel_note_length"
        ),
    )

    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id"))
    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    slot_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_number: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    cancel_note: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rescheduled_from_id: Mapped[UUID | None] = mapped_column(ForeignKey("appointments.id"))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class AppointmentStatusHistoryRow(TenantOwned, Base):
    """Append-only: one row per status change (FR-APT-05)."""

    __tablename__ = "appointment_status_history"
    __table_args__ = (
        Index(
            "ix_appointment_status_history_appointment_id_changed_at",
            "appointment_id",
            "changed_at",
        ),
        enum_check("from_status", AppointmentStatus),
        enum_check("to_status", AppointmentStatus),
    )

    appointment_id: Mapped[UUID] = mapped_column(ForeignKey("appointments.id"))
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[str | None] = mapped_column(Text)
