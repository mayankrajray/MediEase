"""Declarative base and column conventions for every table (docs/DATA_MODEL.md "Conventions").

- Constraint names come from one naming convention, so migrations, error
  messages and ``docs/DATA_MODEL.md`` all use the same predictable names
  (e.g. ``uq_clinic_memberships_clinic_id_user_id``).
- ``TenantOwned`` adds ``clinic_id`` with its foreign key. Every model that
  uses it must be reached only through a ``TenantScopedRepository``
  (``adapters/db/tenancy.py``); a test enforces that.
- Enums are ``text`` + ``CHECK``, built from the domain's own enum so the two
  cannot drift.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Keyed:
    """``id uuid`` primary key; values are UUIDv7 from ``IdPort``, never the database."""

    id: Mapped[UUID] = mapped_column(primary_key=True)


class Timestamps:
    """``created_at`` / ``updated_at`` as ``timestamptz``; values come from the domain."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TenantOwned(Keyed):
    """A row owned by exactly one clinic (ADR-0003)."""

    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinics.id"))


def enum_check(column: str, values: type[StrEnum]) -> CheckConstraint:
    """``CHECK (<column> IN (...))`` named ``ck_<table>_<column>``."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=column)
