"""Tenancy scoping — the one place tenant queries are built.

CLAUDE.md "Tenancy is enforced in one place", ADR-0003.

A ``TenantScopedRepository`` is constructed with a session and one
``clinic_id``. Subclasses build every query from ``_scoped_select()``, which
already carries ``WHERE clinic_id = :clinic_id``, and load single rows with
``_get_row()``. Neither takes a clinic ID, so a repository cannot be asked for
another clinic's data: such a row is "not found" (spec R8).

Rules for subclasses (reviewed, and backed by ``tests/tenancy/``):

- Never call ``session.get()`` or ``session.query()`` on a tenant model: they
  bypass the scope (``session.get`` even returns rows already in the identity
  map, whichever clinic loaded them).
- Call ``_check_owned()`` before writing an entity. An entity of another clinic
  reaching a repository is a programming error, so it raises
  ``TenancyViolation`` (→ 500 ``SYS_UNEXPECTED``), never a user-facing error.
"""

from __future__ import annotations

from typing import ClassVar, cast
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.base import TenantOwned
from mediease_api.domain.shared.errors import NotFound


class TenancyViolation(Exception):
    """Code tried to write clinic B's entity through a repository bound to clinic A."""

    def __init__(self, repository: str) -> None:
        super().__init__(f"{repository}: entity belongs to a different clinic than the repository")


class TenantScopedRepository[RowT: TenantOwned]:
    """Base for repositories of tenant-owned tables.

    Subclasses set ``model`` (the row class, the same as ``RowT``) and
    ``entity_name`` (used in ``NotFound``).
    """

    model: ClassVar[type[TenantOwned]]
    entity_name: ClassVar[str]

    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

    @property
    def clinic_id(self) -> UUID:
        return self._clinic_id

    def _scoped_select(self) -> Select[RowT]:
        """``SELECT <model> WHERE clinic_id = <this clinic>`` — the start of every query."""
        query = select(self.model).where(self.model.clinic_id == self._clinic_id)
        return cast("Select[RowT]", query)

    def _get_row(self, row_id: UUID) -> RowT | None:
        query = self._scoped_select().where(self.model.id == row_id)
        return self._session.scalars(query).one_or_none()

    def _require_row(self, row_id: UUID) -> RowT:
        """The row, or ``NotFound`` — also when it belongs to another clinic (R8)."""
        row = self._get_row(row_id)
        if row is None:
            raise NotFound(self.entity_name)
        return row

    def _delete_row(self, row_id: UUID) -> None:
        """Delete one row of this clinic; ``NotFound`` if it is not this clinic's (R8)."""
        query = delete(self.model).where(
            self.model.clinic_id == self._clinic_id, self.model.id == row_id
        )
        if self._session.execute(query).rowcount == 0:  # type: ignore[attr-defined]
            raise NotFound(self.entity_name)

    def _check_owned(self, clinic_id: UUID) -> None:
        if clinic_id != self._clinic_id:
            raise TenancyViolation(type(self).__name__)
