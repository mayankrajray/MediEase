"""Schedules, exceptions and sessions (M3-P1, migration 0007, docs/DATA_MODEL.md "M3")."""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.scheduling.exceptions import ExceptionKind
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import SessionStatus


class DoctorScheduleRow(TenantOwned, Timestamps, Base):
    """One weekly block. Closed (``valid_to``) rather than deleted once it has been in force."""

    __tablename__ = "doctor_schedules"
    __table_args__ = (
        Index("ix_doctor_schedules_clinic_id_doctor_id", "clinic_id", "doctor_id"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("start_time <> end_time", name="not_empty"),
        CheckConstraint(
            "slot_minutes IS NULL OR slot_minutes BETWEEN 5 AND 120", name="slot_range"
        ),
        CheckConstraint("capacity IS NULL OR capacity BETWEEN 1 AND 500", name="capacity_range"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_window"),
    )

    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    slot_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    capacity: Mapped[int | None] = mapped_column(SmallInteger)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class ScheduleExceptionRow(TenantOwned, Timestamps, Base):
    """A whole-day leave or an extra block on one clinic-local date."""

    __tablename__ = "schedule_exceptions"
    __table_args__ = (
        Index(
            "ix_schedule_exceptions_clinic_id_doctor_id_on_date",
            "clinic_id",
            "doctor_id",
            "on_date",
        ),
        # One leave per doctor and date (R17).
        Index(
            "uq_schedule_exceptions_doctor_id_on_date_leave",
            "doctor_id",
            "on_date",
            unique=True,
            postgresql_where=text("kind = 'LEAVE'"),
        ),
        enum_check("kind", ExceptionKind),
        CheckConstraint(
            "(kind = 'LEAVE' AND start_time IS NULL AND end_time IS NULL"
            " AND slot_minutes IS NULL AND capacity IS NULL)"
            " OR (kind = 'EXTRA' AND start_time IS NOT NULL AND end_time IS NOT NULL"
            " AND start_time <> end_time)",
            name="shape_by_kind",
        ),
        CheckConstraint(
            "slot_minutes IS NULL OR slot_minutes BETWEEN 5 AND 120", name="slot_range"
        ),
        CheckConstraint("capacity IS NULL OR capacity BETWEEN 1 AND 500", name="capacity_range"),
    )

    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    on_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(Text)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    slot_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    capacity: Mapped[int | None] = mapped_column(SmallInteger)
    note: Mapped[str | None] = mapped_column(Text)


class SessionRow(TenantOwned, Timestamps, Base):
    """A generated session; ``booked_count`` and ``next_token`` change under a row lock (P2)."""

    __tablename__ = "sessions"
    __table_args__ = (
        # Generation is idempotent on this (R1): ON CONFLICT DO NOTHING.
        UniqueConstraint("doctor_id", "starts_at"),
        Index("ix_sessions_clinic_id_on_date_doctor_id", "clinic_id", "on_date", "doctor_id"),
        enum_check("mode", BookingMode),
        enum_check("status", SessionStatus),
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        # No overbooking in M3 (D6): the database refuses it whatever the code does.
        CheckConstraint("booked_count BETWEEN 0 AND capacity", name="booked_within_capacity"),
        CheckConstraint("capacity BETWEEN 1 AND 500", name="capacity_range"),
        CheckConstraint("next_token >= 1", name="next_token_positive"),
        CheckConstraint(
            "(mode = 'SLOTS') = (slot_minutes IS NOT NULL)", name="slot_minutes_by_mode"
        ),
    )

    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    on_date: Mapped[date] = mapped_column(Date)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(Text)
    slot_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    capacity: Mapped[int] = mapped_column(SmallInteger)
    booked_count: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    next_token: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'OPEN'"))
