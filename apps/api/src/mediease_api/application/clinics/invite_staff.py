"""InviteStaff — add somebody to a clinic (FR-ORG-04, FR-OPS-01; spec I2, R12).

Used by both paths that can invite: ops onboarding a clinic (which names the
clinic in the path) and an owner managing their own staff (which takes it from
the request context). The only difference is the ``Actor``, so the audit trail
shows which of the two it was.

What it does, in one transaction:

1. Find the person by email or phone, or create the user — "one user, two
   memberships" (spec §8): a doctor who works at two clinics signs in once.
2. Refuse a second membership in the same clinic (I2 → ``CLN_MEMBER_EXISTS``),
   except for one that is still ``INVITED``: that is a re-invite, and a new
   secret retires the old link.
3. Attach a single-use secret, timestamp the checklist's first staff invite
   (R12) and record ``staff.invited``.

The clear secret is returned exactly once, in the result. Nothing stores it,
so a leaked database cannot be used to take over a pending invitation;
delivery turns it into the acceptance URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.identity.membership import (
    ClinicMembership,
    MembershipStatus,
    Role,
)
from mediease_api.domain.identity.user import User
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import InviteSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

from .errors import MemberExists

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "clinic_membership"


@dataclass(frozen=True, slots=True)
class InviteStaffCommand:
    full_name: str
    role: Role
    email: str | None = None
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class StaffInvitation:
    """The new member, plus the secret that lets them accept (shown once)."""

    member: StaffMember
    token: str

    def __repr__(self) -> str:
        return f"StaffInvitation(member={self.member.membership_id}, token=<redacted>)"


class InviteStaff:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: InviteSecrets
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def execute(self, *, clinic_id: UUID, actor: Actor, cmd: InviteStaffCommand) -> StaffInvitation:
        email, phone = _parse_identifiers(cmd)
        token = self._secrets.generate()
        with self._uow as uow:
            now = self._clock.now()
            if uow.clinics.get(clinic_id) is None:
                raise NotFound("clinic")

            user = self._find_or_create_user(uow, cmd, email, phone, now)
            staff = uow.tenant(clinic_id).memberships
            membership = staff.get_for_user(user.id)
            if membership is None:
                membership = ClinicMembership.invite(
                    id=self._ids.new_id(),
                    clinic_id=clinic_id,
                    user_id=user.id,
                    role=cmd.role,
                    now=now,
                )
                membership.issue_invite(self._secrets.digest(token), now=now)
                staff.add(membership)
            elif membership.status is MembershipStatus.INVITED:
                # Re-invite: a new secret retires the previous link.
                membership.role = cmd.role
                membership.issue_invite(self._secrets.digest(token), now=now)
                staff.update(membership)
            else:
                raise MemberExists()

            self._record_first_invite(uow, clinic_id, now)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.STAFF_INVITED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=membership.id,
                metadata={"target_user_id": str(user.id), "role": cmd.role.value},
            )
            uow.commit()

        logger.info(
            "staff.invited",
            clinic_id=str(clinic_id),
            membership_id=str(membership.id),
            role=cmd.role.value,
        )
        return StaffInvitation(
            member=StaffMember(
                membership_id=membership.id,
                user_id=user.id,
                full_name=user.full_name,
                role=membership.role,
                status=membership.status,
            ),
            token=token,
        )

    def _find_or_create_user(
        self,
        uow: UnitOfWork,
        cmd: InviteStaffCommand,
        email: EmailAddress | None,
        phone: PhoneNumber | None,
        now: datetime,
    ) -> User:
        existing = None
        if email is not None:
            existing = uow.users.get_by_email(email)
        if existing is None and phone is not None:
            existing = uow.users.get_by_phone(phone)
        if existing is not None:
            # Their account, their name: an invite never renames somebody.
            return existing
        user = User.create(
            id=self._ids.new_id(),
            full_name=cmd.full_name,
            email=email,
            phone=phone,
            now=now,
        )
        uow.users.add(user)
        return user

    def _record_first_invite(self, uow: UnitOfWork, clinic_id: UUID, now: datetime) -> None:
        checklist = uow.tenant(clinic_id).checklist
        recorded = checklist.get()
        if recorded is None:
            recorded = OnboardingChecklist.start(
                id=self._ids.new_id(), clinic_id=clinic_id, now=now
            )
            recorded.record(OnboardingStep.STAFF_INVITED, now=now)
            checklist.add(recorded)
            return
        if recorded.record(OnboardingStep.STAFF_INVITED, now=now):
            checklist.update(recorded)


def _parse_identifiers(cmd: InviteStaffCommand) -> tuple[EmailAddress | None, PhoneNumber | None]:
    """At least one way to reach them, because that is how they sign in (R1)."""
    email = EmailAddress.parse(cmd.email, field="email") if cmd.email else None
    phone = PhoneNumber.parse(cmd.phone, field="phone") if cmd.phone else None
    if email is None and phone is None:
        raise InvalidValue("email", "an email address or a phone number is required")
    return email, phone
