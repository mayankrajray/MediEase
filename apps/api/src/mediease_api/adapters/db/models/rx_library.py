"""A doctor's favourites and templates (M4-P3, migration 0011, docs/DATA_MODEL.md "M4")."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps


def _library_args(table: str) -> tuple[Any, ...]:
    return (
        # Names are unique per doctor, ignoring case (M4-P3); RX_NAME_TAKEN.
        Index(f"uq_{table}_doctor_id_name", "doctor_id", text("lower(name)"), unique=True),
        CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="name_length"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("use_count >= 0", name="use_count_positive"),
    )


class _Library(TenantOwned, Timestamps):
    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    name: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    use_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RxFavouriteRow(_Library, Base):
    """One medicine line with the doctor's usual instructions."""

    __tablename__ = "rx_favourites"
    __table_args__ = _library_args("rx_favourites")

    item: Mapped[dict[str, Any]] = mapped_column(JSONB)


class RxTemplateRow(_Library, Base):
    """A whole prescription body."""

    __tablename__ = "rx_templates"
    __table_args__ = (
        *_library_args("rx_templates"),
        CheckConstraint(
            "follow_up_days IS NULL OR follow_up_days BETWEEN 1 AND 365",
            name="follow_up_days_range",
        ),
    )

    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    advice: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    follow_up_days: Mapped[int | None] = mapped_column(SmallInteger)
