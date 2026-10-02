"""In-memory fakes of the ports, for application unit tests (apps/api/CLAUDE.md "Tests").

``InMemoryUnitOfWork`` keeps a committed store and gives each ``with`` block a
private copy, so tests can prove what a use case committed — and what it
rolled back — without a database.
"""

from __future__ import annotations

import copy
import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID

from mediease_api.domain.identity.access import ClinicAccess
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.identity.user import User
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.security import AccessClaims, InvalidAccessToken, IssuedAccessToken
from tests.builders import NOW, new_id

# --- Clock, IDs, security ------------------------------------------------------------------


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)


class FakeIds:
    def new_id(self) -> UUID:
        return new_id()


class FakeHasher:
    """``hash:<password>``; counts verifications so tests can prove the dummy path runs."""

    def __init__(self) -> None:
        self.verifications = 0
        self.outdated: set[str] = set()

    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        self.verifications += 1
        return password_hash == f"hash:{password}"

    def needs_rehash(self, password_hash: str) -> bool:
        return password_hash in self.outdated


class FakeAccessTokens:
    def __init__(self, ttl: timedelta = timedelta(minutes=15)) -> None:
        self._ttl = ttl
        self._issued: dict[str, AccessClaims] = {}
        self._counter = itertools.count(1)

    def issue(self, *, user_id: UUID, session_id: UUID, now: datetime) -> IssuedAccessToken:
        value = f"access-{next(self._counter)}"
        claims = AccessClaims(user_id=user_id, session_id=session_id, expires_at=now + self._ttl)
        self._issued[value] = claims
        return IssuedAccessToken(value=value, expires_at=claims.expires_at)

    def verify(self, token: str, *, now: datetime) -> AccessClaims:
        claims = self._issued.get(token)
        if claims is None or now >= claims.expires_at:
            raise InvalidAccessToken()
        return claims


class FakeRefreshSecrets:
    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def generate(self) -> str:
        return f"refresh-{next(self._counter)}"

    def digest(self, token: str) -> str:
        return f"digest:{token}"


# --- Unit of work --------------------------------------------------------------------------


@dataclass
class Store:
    users: dict[UUID, User] = field(default_factory=dict)
    refresh_tokens: dict[UUID, RefreshToken] = field(default_factory=dict)
    # Not owned by the use cases under test: arranged by tests, read-only here.
    access: dict[UUID, list[ClinicAccess]] = field(default_factory=dict)


class _Users:
    def __init__(self, store: Store) -> None:
        self._store = store

    def add(self, user: User) -> None:
        self._store.users[user.id] = copy.deepcopy(user)

    def get(self, user_id: UUID) -> User | None:
        return copy.deepcopy(self._store.users.get(user_id))

    def get_by_email(self, email: EmailAddress, *, for_update: bool = False) -> User | None:
        return self._find(lambda u: u.email == email)

    def get_by_phone(self, phone: PhoneNumber, *, for_update: bool = False) -> User | None:
        return self._find(lambda u: u.phone == phone)

    def update(self, user: User) -> None:
        if user.id not in self._store.users:
            raise NotFound("user")
        self._store.users[user.id] = copy.deepcopy(user)

    def _find(self, match: object) -> User | None:
        found = [u for u in self._store.users.values() if match(u)]  # type: ignore[operator]
        return copy.deepcopy(found[0]) if found else None


class _RefreshTokens:
    def __init__(self, store: Store) -> None:
        self._store = store

    def add(self, token: RefreshToken) -> None:
        self._store.refresh_tokens[token.id] = copy.deepcopy(token)

    def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> RefreshToken | None:
        found = [t for t in self._store.refresh_tokens.values() if t.token_hash == token_hash]
        return copy.deepcopy(found[0]) if found else None

    def update(self, token: RefreshToken) -> None:
        if token.id not in self._store.refresh_tokens:
            raise NotFound("refresh token")
        self._store.refresh_tokens[token.id] = copy.deepcopy(token)

    def revoke_family(self, family_id: UUID, *, now: datetime) -> int:
        live = [
            t
            for t in self._store.refresh_tokens.values()
            if t.family_id == family_id and t.revoked_at is None
        ]
        for token in live:
            token.revoked_at = token.updated_at = now
        return len(live)

    def is_family_live(self, family_id: UUID, *, now: datetime) -> bool:
        return any(
            t.family_id == family_id and t.revoked_at is None and now < t.expires_at
            for t in self._store.refresh_tokens.values()
        )


class _ClinicAccess:
    def __init__(self, store: Store) -> None:
        self._store = store

    def list_active_for_user(self, user_id: UUID) -> Sequence[ClinicAccess]:
        return list(self._store.access.get(user_id, []))


class InMemoryUnitOfWork:
    """Implements the parts of ``UnitOfWork`` the auth use cases use."""

    def __init__(self, store: Store | None = None) -> None:
        self.committed = store or Store()
        self._working: Store | None = None
        self.commits = 0

    def __enter__(self) -> Self:
        if self._working is not None:
            raise RuntimeError("unit of work is already open")
        self._working = copy.deepcopy(self.committed)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._working = None

    def commit(self) -> None:
        self.committed = copy.deepcopy(self._open())
        self.commits += 1

    def rollback(self) -> None:
        self._working = copy.deepcopy(self.committed)

    @property
    def users(self) -> _Users:
        return _Users(self._open())

    @property
    def refresh_tokens(self) -> _RefreshTokens:
        return _RefreshTokens(self._open())

    @property
    def clinic_access(self) -> _ClinicAccess:
        return _ClinicAccess(self._open())

    def _open(self) -> Store:
        if self._working is None:
            raise RuntimeError("unit of work is not open")
        return self._working
