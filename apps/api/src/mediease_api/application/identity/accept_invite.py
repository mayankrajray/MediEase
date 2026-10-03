"""Accepting a staff invitation (FR-ORG-04, FR-AUTH-01; spec I1, R11).

Two public use cases, for a person who has no session yet:

- ``DescribeInvite`` — what this link is for, so the page can say "Join Sample
  Clinic as the front desk" before asking for a password.
- ``AcceptInvite`` — set a password, activate the membership, and sign in.
  Accepting an owner's invitation also activates an ``ONBOARDING`` clinic:
  invariant I1 (an active clinic has an active owner) becomes satisfiable at
  exactly that moment, and it saves ops a step in the 60-minute onboarding.

Everything happens in one transaction, audit rows included (R11): a member who
can sign in always has a ``staff.accepted`` event to show for it.

An unknown secret is ``CLN_INVITE_INVALID`` (404). One the API knows but
cannot accept says why — expired or already used — because the invitee holds
the link and needs to know whether to ask for a new one; guessing the 256-bit
secret is not the threat the message would help with.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.auth._session import SessionIssuer, session_result
from mediease_api.application.auth.errors import AccountDisabled
from mediease_api.application.auth.views import SessionResult
from mediease_api.application.clinics.errors import InviteExpired, InviteInvalid, InviteUsed
from mediease_api.application.context import Actor, RequestInfo
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus
from mediease_api.domain.identity.membership import ClinicMembership, InviteState, Role
from mediease_api.domain.identity.password import validate_password
from mediease_api.domain.identity.user import User
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import InviteSecrets, PasswordHasher
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "clinic_membership"


@dataclass(frozen=True, slots=True)
class InviteView:
    """What the acceptance page may show before anyone is authenticated."""

    clinic_name: str
    full_name: str
    role: Role
    expires_at: datetime | None
    # True when the user already has a password (a second clinic inviting them).
    has_password: bool


class DescribeInvite:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, secrets: InviteSecrets) -> None:
        self._uow = uow
        self._clock = clock
        self._secrets = secrets

    def execute(self, token: str) -> InviteView:
        with self._uow as uow:
            membership, clinic, user = _load(uow, self._secrets.digest(token), self._clock.now())
            return InviteView(
                clinic_name=clinic.name,
                full_name=user.full_name,
                role=membership.role,
                expires_at=membership.invite_expires_at,
                has_password=user.password_hash is not None,
            )


class AcceptInvite:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        hasher: PasswordHasher,
        secrets: InviteSecrets,
        sessions: SessionIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._hasher = hasher
        self._secrets = secrets
        self._sessions = sessions

    def execute(self, token: str, password: str, info: RequestInfo | None = None) -> SessionResult:
        info = info or RequestInfo()
        validate_password(password)
        digest = self._secrets.digest(token)
        with self._uow as uow:
            now = self._clock.now()
            membership, clinic, user = _load(uow, digest, now)
            actor = Actor.for_user(user, info)

            user.set_password_hash(self._hasher.hash(password), now=now)
            user.record_successful_sign_in(now=now)
            uow.users.update(user)

            membership.accept_invite(now=now)
            staff = uow.tenant(clinic.id).memberships
            staff.update(membership)

            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.STAFF_ACCEPTED,
                actor=actor,
                now=now,
                clinic_id=clinic.id,
                entity_type=ENTITY_TYPE,
                entity_id=membership.id,
                metadata={"role": membership.role.value},
            )
            if membership.role is Role.OWNER and clinic.status is ClinicStatus.ONBOARDING:
                # I1 is satisfiable now: the clinic has its first active owner.
                clinic.activate(active_owner_count=staff.count_active_owners(), now=now)
                uow.clinics.update(clinic)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.CLINIC_ACTIVATED,
                    actor=actor,
                    now=now,
                    clinic_id=clinic.id,
                    metadata={"reason": "owner_accepted"},
                )

            access = list(uow.clinic_access.list_active_for_user(user.id))
            family_id = self._ids.new_id()
            _, tokens = self._sessions.issue(uow, user_id=user.id, family_id=family_id, now=now)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.AUTH_SIGNED_IN,
                actor=actor,
                now=now,
                metadata={"session_id": str(family_id), "via": "invite"},
            )
            uow.commit()

        logger.info(
            "staff.accepted",
            clinic_id=str(clinic.id),
            membership_id=str(membership.id),
            user_id=str(user.id),
            session_id=str(family_id),
        )
        return session_result(user, access, tokens)


def _load(uow: UnitOfWork, digest: str, now: datetime) -> tuple[ClinicMembership, Clinic, User]:
    """The membership this secret belongs to, with its clinic and user, or an error."""
    membership = uow.staff_invites.get_by_invite_digest(digest)
    if membership is None:
        logger.info("staff.invite_rejected", reason="unknown")
        raise InviteInvalid()

    state = membership.invite_state(now)
    if state is InviteState.EXPIRED:
        logger.info("staff.invite_rejected", reason="expired", membership_id=str(membership.id))
        raise InviteExpired()
    if state is InviteState.ACCEPTED:
        logger.info("staff.invite_rejected", reason="used", membership_id=str(membership.id))
        raise InviteUsed()
    if state is not InviteState.PENDING:  # pragma: no cover - a digest implies a state
        raise InviteInvalid()

    clinic = uow.clinics.get(membership.clinic_id)
    user = uow.users.get(membership.user_id)
    if clinic is None or user is None:  # pragma: no cover - foreign keys prevent this
        raise InviteInvalid()
    if not user.is_active:
        logger.info("staff.invite_rejected", reason="account_disabled", user_id=str(user.id))
        raise AccountDisabled()
    return membership, clinic, user
