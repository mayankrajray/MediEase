"""SQLAlchemy unit of work — one session and one transaction per command.

``with uow:`` opens a session; every repository it hands out shares that
session. Leaving the block without ``commit()`` rolls back, including when an
exception escapes, and the session is always closed. A unit of work can be
entered again afterwards (a use case keeps one and enters it per ``execute``),
but not while it is already open, and it is not shared between threads: the
composition root creates one per request (M1-P2).
"""

from __future__ import annotations

from types import TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.db.audit import SqlAlchemyAuditWriter
from mediease_api.adapters.db.repositories import (
    SqlAlchemyChecklistRepository,
    SqlAlchemyClinicAccessRepository,
    SqlAlchemyClinicRepository,
    SqlAlchemyDoctorRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyStaffInviteRepository,
    SqlAlchemyUserRepository,
)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Sessions for units of work.

    ``expire_on_commit=False``: entities are mapped out of rows before commit,
    so nothing needs reloading after it; ``autoflush=False``: repositories
    flush explicitly at the call that changed something.
    """
    return sessionmaker(engine, expire_on_commit=False, autoflush=False)


class SqlAlchemyTenantRepositories:
    """The tenant repositories for one clinic, sharing the unit of work's session."""

    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._clinic_id = clinic_id
        self._doctors = SqlAlchemyDoctorRepository(session, clinic_id)
        self._memberships = SqlAlchemyMembershipRepository(session, clinic_id)
        self._checklist = SqlAlchemyChecklistRepository(session, clinic_id)

    @property
    def clinic_id(self) -> UUID:
        return self._clinic_id

    @property
    def doctors(self) -> SqlAlchemyDoctorRepository:
        return self._doctors

    @property
    def memberships(self) -> SqlAlchemyMembershipRepository:
        return self._memberships

    @property
    def checklist(self) -> SqlAlchemyChecklistRepository:
        return self._checklist


class _OpenUnit:
    """The session and platform repositories of one open unit of work."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.clinics = SqlAlchemyClinicRepository(session)
        self.users = SqlAlchemyUserRepository(session)
        self.refresh_tokens = SqlAlchemyRefreshTokenRepository(session)
        self.clinic_access = SqlAlchemyClinicAccessRepository(session)
        self.staff_invites = SqlAlchemyStaffInviteRepository(session)
        # Shares the session, so an audit row commits with the change (R11).
        self.audit = SqlAlchemyAuditWriter(session)


class SqlAlchemyUnitOfWork:
    """``UnitOfWork`` over a SQLAlchemy session factory."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._open: _OpenUnit | None = None

    def __enter__(self) -> Self:
        if self._open is not None:
            raise RuntimeError("unit of work is already open")
        self._open = _OpenUnit(self._session_factory())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_open().session
        try:
            # Anything not committed is discarded — on success and on error alike.
            session.rollback()
        finally:
            session.close()
            self._open = None

    @property
    def clinics(self) -> SqlAlchemyClinicRepository:
        return self._require_open().clinics

    @property
    def users(self) -> SqlAlchemyUserRepository:
        return self._require_open().users

    @property
    def refresh_tokens(self) -> SqlAlchemyRefreshTokenRepository:
        return self._require_open().refresh_tokens

    @property
    def clinic_access(self) -> SqlAlchemyClinicAccessRepository:
        return self._require_open().clinic_access

    @property
    def staff_invites(self) -> SqlAlchemyStaffInviteRepository:
        return self._require_open().staff_invites

    @property
    def audit(self) -> SqlAlchemyAuditWriter:
        return self._require_open().audit

    def tenant(self, clinic_id: UUID) -> SqlAlchemyTenantRepositories:
        return SqlAlchemyTenantRepositories(self._require_open().session, clinic_id)

    def commit(self) -> None:
        self._require_open().session.commit()

    def rollback(self) -> None:
        self._require_open().session.rollback()

    def _require_open(self) -> _OpenUnit:
        if self._open is None:
            raise RuntimeError("unit of work is not open; use it in a `with` block")
        return self._open
