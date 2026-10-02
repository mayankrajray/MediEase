"""One harness for the application use cases, wired to in-memory fakes.

``build_auth()`` composes sign-in, refresh, sign-out and per-request
authentication the way ``bootstrap.py`` does, so a test exercises the same
objects the app uses with none of the I/O. Shared by ``test_auth.py``
(M1-P2) and ``test_authorize.py`` (M1-P3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from mediease_api.application.auth._session import SessionIssuer
from mediease_api.application.auth.authenticate import AuthenticateRequest
from mediease_api.application.auth.refresh_session import RefreshSession
from mediease_api.application.auth.sign_in import SignIn, SignInCommand
from mediease_api.application.auth.sign_out import SignOut
from mediease_api.application.auth.views import SessionResult
from mediease_api.application.context import RequestInfo
from mediease_api.domain.audit.event import AuditEvent
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.access import ClinicAccess
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.user import User
from tests.builders import a_user, new_id
from tests.fakes import (
    FakeAccessTokens,
    FakeClock,
    FakeHasher,
    FakeIds,
    FakeRefreshSecrets,
    InMemoryUnitOfWork,
)

PASSWORD = "correct horse battery"
REFRESH_TTL = timedelta(days=14)


def cmd(identifier: str, password: str = PASSWORD) -> SignInCommand:
    return SignInCommand(identifier=identifier, password=password)


@dataclass
class Auth:
    uow: InMemoryUnitOfWork
    clock: FakeClock
    hasher: FakeHasher
    secrets: FakeRefreshSecrets
    sign_in: SignIn
    refresh: RefreshSession
    sign_out: SignOut
    authenticate: AuthenticateRequest
    info: RequestInfo

    def add_user(
        self,
        *,
        clinics: int = 1,
        role: Role = Role.OWNER,
        clinic_status: ClinicStatus = ClinicStatus.ACTIVE,
        has_doctor_profile: bool = False,
        **overrides: object,
    ) -> User:
        """A user with a password and ``clinics`` active memberships."""
        user = a_user(password_hash=self.hasher.hash(PASSWORD), **overrides)
        self.uow.committed.users[user.id] = user
        self.uow.committed.access[user.id] = [
            ClinicAccess(
                membership_id=new_id(),
                clinic_id=new_id(),
                clinic_name=f"Sample Clinic {i}",
                clinic_status=clinic_status,
                role=role,
                has_doctor_profile=has_doctor_profile,
            )
            for i in range(clinics)
        ]
        return user

    def access_of(self, user: User) -> list[ClinicAccess]:
        """The memberships a test arranged; mutate this to simulate a change (R7)."""
        return self.uow.committed.access[user.id]

    def session_of(self, user: User) -> SessionResult:
        """Sign ``user`` in by email and return the whole result (tokens included)."""
        assert user.email is not None
        return self.sign_in.execute(cmd(user.email.value), self.info)

    def signed_in(self, user: User) -> str:
        """The access token delivery would put in the ``me_access`` cookie."""
        return self.session_of(user).tokens.access_token

    def events(self) -> list[AuditEvent]:
        """The audit events committed so far (the table is append-only)."""
        return list(self.uow.committed.audit_events)

    def stored(self, user: User) -> User:
        return self.uow.committed.users[user.id]

    def clinic_ids(self, user: User) -> list[UUID]:
        return [a.clinic_id for a in self.access_of(user)]


def build_auth(*, audit_fails: bool = False) -> Auth:
    uow, clock, hasher, secrets = (
        InMemoryUnitOfWork(audit_fails=audit_fails),
        FakeClock(),
        FakeHasher(),
        FakeRefreshSecrets(),
    )
    ids = FakeIds()
    access_tokens = FakeAccessTokens()
    sessions = SessionIssuer(
        ids=ids, secrets=secrets, access_tokens=access_tokens, refresh_ttl=REFRESH_TTL
    )
    return Auth(
        uow=uow,
        clock=clock,
        hasher=hasher,
        secrets=secrets,
        sign_in=SignIn(
            uow=uow,
            clock=clock,
            ids=ids,
            hasher=hasher,
            sessions=sessions,
            dummy_password_hash=hasher.hash("dummy-password-never-used"),
        ),
        refresh=RefreshSession(uow=uow, clock=clock, ids=ids, secrets=secrets, sessions=sessions),
        sign_out=SignOut(uow=uow, clock=clock, ids=ids, secrets=secrets),
        authenticate=AuthenticateRequest(uow=uow, clock=clock, access_tokens=access_tokens),
        # What delivery would pass in: a request ID and an already-hashed IP.
        info=RequestInfo(request_id="01J8Z5W6X4K7Q2N3R5T8V9Y0AB", ip_hash="a" * 32),
    )
