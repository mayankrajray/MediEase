"""Accepting a staff invitation (FR-ORG-04, FR-AUTH-01; spec I1, R11).

Two public use cases, for a person who has no session yet:

- ``DescribeInvite`` — what this link is for, so the page can say "Join Sample
  Clinic as the front desk" before asking for a password.
- ``AcceptInvite`` — activate the membership and sign in. What the ``password``
  means depends on the account (spec R13):

  * a **new** account (no password yet) *sets* it, subject to the password policy;
  * an account that **already has** a password must *prove* it by presenting the
    current one, and it is never changed. Whoever holds the link is not
    necessarily the account holder (an owner who invites an existing user's
    email receives the link), so the link alone must not be able to take the
    account over. Wrong attempts count towards the same lockout as sign-in.

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
from mediease_api.application.auth.errors import AccountDisabled, AccountLocked, InvalidCredentials
from mediease_api.application.auth.views import SessionResult
from mediease_api.application.clinics.errors import InviteExpired, InviteInvalid, InviteUsed
from mediease_api.application.context import Actor, RequestInfo
from mediease_api.application.notifications.service import publish
from mediease_api.application.subscriptions.plans import require_room, start_trial
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus
from mediease_api.domain.identity.membership import ClinicMembership, InviteState, Role
from mediease_api.domain.identity.password import validate_password
from mediease_api.domain.identity.user import User
from mediease_api.domain.notifications.events import StaffJoined
from mediease_api.domain.subscriptions.subscription import Limit
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
        digest = self._secrets.digest(token)
        with self._uow as uow:
            now = self._clock.now()
            # The user row is locked: wrong passwords on an existing account are counted one by one.
            membership, clinic, user = _load(uow, digest, now, lock_user=True)
            actor = Actor.for_user(user, info)

            if user.password_hash is None:
                validate_password(password)
                user.set_password_hash(self._hasher.hash(password), now=now)
                account = "new"
            else:
                self._prove_current_password(uow, user, password, info, now)
                account = "existing"
            user.record_successful_sign_in(now=now)
            uow.users.update(user)

            # M6d-P7 (R4): the seat must still fit the plan (it may have changed since).
            require_room(uow, clinic.id, Limit.USERS, adding=0, now=now)
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
                metadata={"role": membership.role.value, "account": account},
            )
            # M6a-P7: the clinic's owners are told someone joined (in-app).
            publish(
                uow,
                StaffJoined(membership.id),
                clinic_id=clinic.id,
                ids=self._ids,
                now=now,
                request_id=info.request_id,
                actor_user_id=user.id,
            )
            if membership.role is Role.OWNER and clinic.status is ClinicStatus.ONBOARDING:
                # I1 is satisfiable now: the clinic has its first active owner.
                clinic.activate(active_owner_count=staff.count_active_owners(), now=now)
                uow.clinics.update(clinic)
                # M6d-P7 (R3): the 14-day trial starts with the clinic.
                start_trial(uow, clinic.id, now)
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

    def _prove_current_password(
        self, uow: UnitOfWork, user: User, password: str, info: RequestInfo, now: datetime
    ) -> None:
        """Existing account: the caller must know its password (R13). Never changes it.

        The same rules as sign-in: a locked account is refused without checking, and a
        wrong password is counted (the fifth locks) and audited before the error, so
        this endpoint is not a way around the lockout.
        """
        assert user.password_hash is not None
        if user.is_locked(now):
            assert user.locked_until is not None
            logger.info("staff.invite_rejected", reason="locked", user_id=str(user.id))
            raise AccountLocked(max(1, int((user.locked_until - now).total_seconds())))

        if not self._hasher.verify(user.password_hash, password):
            locked_now = user.record_failed_sign_in(now=now)
            uow.users.update(user)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.AUTH_SIGN_IN_FAILED,
                actor=Actor.for_user(user, info),
                now=now,
                metadata={
                    "reason": "wrong_password",
                    "locked": str(locked_now).lower(),
                    "via": "invite",
                },
            )
            uow.commit()
            logger.info("staff.invite_rejected", reason="wrong_password", user_id=str(user.id))
            if locked_now:
                logger.warning("auth.locked", user_id=str(user.id))
            raise InvalidCredentials()

        if self._hasher.needs_rehash(user.password_hash):
            user.set_password_hash(self._hasher.hash(password), now=now)


def _load(
    uow: UnitOfWork, digest: str, now: datetime, *, lock_user: bool = False
) -> tuple[ClinicMembership, Clinic, User]:
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
    user = uow.users.get(membership.user_id, for_update=lock_user)
    if clinic is None or user is None:  # pragma: no cover - foreign keys prevent this
        raise InviteInvalid()
    if not user.is_active:
        logger.info("staff.invite_rejected", reason="account_disabled", user_id=str(user.id))
        raise AccountDisabled()
    return membership, clinic, user
