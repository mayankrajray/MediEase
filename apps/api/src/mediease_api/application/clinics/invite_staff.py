"""InviteStaff and ResendStaffInvite — add somebody to a clinic (FR-ORG-04, FR-ORG-07, FR-OPS-01).

``InviteStaff`` is used by both paths that can invite: ops onboarding a clinic (which names the
clinic in the path) and an owner on the Team page (which takes it from the request context). The
``Actor`` tells the audit trail which of the two it was.

What it does, in one transaction:

1. Find the person by email or phone, or create the user — "one user, two memberships" (spec §8):
   a doctor who works at two clinics signs in once.
2. Refuse a second membership in the same clinic (I2 → ``CLN_MEMBER_EXISTS``), except for one
   that is still ``INVITED`` (a re-invite: the old link stops working) or, from M6a-P5, one that
   was ``DEACTIVATED`` (``staff.reinvited``: the person comes back with their history).
3. Deliver the invitation (M6a-P5, decision 3A):

   - **by email** when an owner invites someone with an email address. The request retires any
     earlier link and enqueues ``send_staff_invite``; the worker makes the secret at send time and
     stores only its digest (ADR-0016 decision 4), so no usable secret is ever at rest or shown;
   - **by link** otherwise (ops, or a phone-only invitation): the secret is made here, only its
     digest is stored, and the clear value is returned exactly once to be shown with *Copy link*.

4. Timestamp the checklist's first staff invite (R12) and record the audit event.

An owner's invitations are limited to 10 an hour per clinic, and *Resend* to 3 an hour per member
(the M4-P5 counter table, hour windows).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.subscriptions.plans import require_room
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.identity.membership import (
    ClinicMembership,
    MembershipStatus,
    Role,
)
from mediease_api.domain.identity.user import User
from mediease_api.domain.jobs.job import STAFF_INVITE_KIND, NewJob
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue, NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.subscriptions.subscription import Limit
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import InviteSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

from .errors import InvitesRateLimited, MemberExists

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "clinic_membership"

INVITES_PER_CLINIC_PER_HOUR = 10
RESENDS_PER_MEMBER_PER_HOUR = 3


class InviteDelivery(StrEnum):
    EMAIL = "email"
    LINK = "link"


@dataclass(frozen=True, slots=True)
class InviteStaffCommand:
    full_name: str
    role: Role
    email: str | None = None
    phone: str | None = None
    # An owner on the Team page (M6a-P5): an invitation to someone with an email is emailed, and
    # the clinic's hourly limit applies. Ops keep the shown link until M6c (FR-ONB-08).
    by_owner: bool = False
    # M6a-P6 (decision 8A): the owner also practises here, as this unlinked doctor profile
    # ("Doctor 1"). Linked in the same transaction; it counts once the owner accepts.
    doctor_id: UUID | None = None
    # M6c-P3 (FR-ONB-08): an approved application's owner is invited by email, without the
    # owner's hourly limit (that is for the Team page).
    email_delivery: bool = False


@dataclass(frozen=True, slots=True)
class StaffInvitation:
    """The invited member and how the invitation travels.

    ``token`` is the clear secret for a ``LINK`` invitation (shown once) and None for an emailed
    one, which only the worker ever sees. ``email_masked`` tells the owner where it went.
    """

    member: StaffMember
    delivery: InviteDelivery
    token: str | None = None
    email_masked: str | None = None

    def __repr__(self) -> str:
        return (
            f"StaffInvitation(member={self.member.membership_id}, delivery={self.delivery.value},"
            " token=<redacted>)"
        )


def enqueue_staff_invite(
    uow: UnitOfWork,
    *,
    ids: IdPort,
    clinic_id: UUID,
    membership_id: UUID,
    now: datetime,
    request_id: str | None,
) -> None:
    """In the caller's transaction (the outbox). IDs only: no address, no secret."""
    uow.jobs.enqueue(
        NewJob.create(
            id=ids.new_id(),
            kind=STAFF_INVITE_KIND,
            now=now,
            clinic_id=clinic_id,
            payload={"membership_id": str(membership_id)},
            request_id=request_id,
        )
    )


class InviteStaff:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: InviteSecrets
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def execute(self, *, clinic_id: UUID, actor: Actor, cmd: InviteStaffCommand) -> StaffInvitation:
        with self._uow as uow:
            invitation = self.in_transaction(
                uow, clinic_id=clinic_id, actor=actor, cmd=cmd, now=self._clock.now()
            )
            uow.commit()
        return invitation

    def in_transaction(
        self,
        uow: UnitOfWork,
        *,
        clinic_id: UUID,
        actor: Actor,
        cmd: InviteStaffCommand,
        now: datetime,
    ) -> StaffInvitation:
        """The whole invitation inside the caller's transaction (M6c-P3: approval uses it)."""
        email, phone = _parse_identifiers(cmd)
        if uow.clinics.get(clinic_id) is None:
            raise NotFound("clinic")
        if cmd.by_owner:
            _limit(uow, f"staff-invite:{clinic_id}", INVITES_PER_CLINIC_PER_HOUR, now)

        user = self._find_or_create_user(uow, cmd, email, phone, now)
        staff = uow.tenant(clinic_id).memberships
        membership = staff.get_for_user(user.id)
        action = AuditAction.STAFF_INVITED
        is_new = membership is None
        if membership is None or membership.status is MembershipStatus.DEACTIVATED:
            # M6d-P7 (R4): a new or returning member takes a seat on the plan.
            require_room(uow, clinic_id, Limit.USERS, adding=1, now=now)
        if membership is None:
            membership = ClinicMembership.invite(
                id=self._ids.new_id(),
                clinic_id=clinic_id,
                user_id=user.id,
                role=cmd.role,
                now=now,
            )
        elif membership.status is MembershipStatus.INVITED:
            # Re-invite: the new delivery below retires the previous link.
            membership.role = cmd.role
        elif membership.status is MembershipStatus.DEACTIVATED:
            membership.reinvite(cmd.role, now=now)
            action = AuditAction.STAFF_REINVITED
        else:
            raise MemberExists()

        delivery = (
            InviteDelivery.EMAIL
            if (cmd.by_owner or cmd.email_delivery) and user.email is not None
            else InviteDelivery.LINK
        )
        token = _prepare_delivery(membership, delivery, self._secrets, now)
        if is_new:
            staff.add(membership)
        else:
            staff.update(membership)
        if delivery is InviteDelivery.EMAIL:
            enqueue_staff_invite(
                uow,
                ids=self._ids,
                clinic_id=clinic_id,
                membership_id=membership.id,
                now=now,
                request_id=actor.info.request_id,
            )

        self._record_first_invite(uow, clinic_id, now)
        metadata = {
            "target_user_id": str(user.id),
            "role": cmd.role.value,
            "delivery": delivery.value,
        }
        if cmd.doctor_id is not None:
            self._link_doctor(uow, clinic_id, actor, cmd, user, now)
            metadata["doctor_id"] = str(cmd.doctor_id)
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=action,
            actor=actor,
            now=now,
            clinic_id=clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=membership.id,
            metadata=metadata,
        )
        member = _member(uow, clinic_id, membership.id)

        logger.info(
            action.value,
            clinic_id=str(clinic_id),
            membership_id=str(membership.id),
            role=cmd.role.value,
            delivery=delivery.value,
        )
        return _invitation(member, delivery, token, user)

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

    def _link_doctor(
        self,
        uow: UnitOfWork,
        clinic_id: UUID,
        actor: Actor,
        cmd: InviteStaffCommand,
        user: User,
        now: datetime,
    ) -> None:
        """Owner as Doctor 1 (FR-ORG-03, FR-ONB-08): link the named profile to the invitee.

        The one place a profile is linked to a member who is not ``ACTIVE`` yet: the invited
        owner's user exists, and an ``INVITED`` membership grants nothing until it is accepted,
        so ``CLINICAL_WRITE`` starts exactly when they join.
        """
        assert cmd.doctor_id is not None
        if cmd.role is not Role.OWNER:
            raise InvalidValue("doctor_id", "only an owner's invitation can name a doctor profile")
        doctors = uow.tenant(clinic_id).doctors
        doctor = doctors.get(cmd.doctor_id)
        if doctor is None or not doctor.is_active:
            raise InvalidValue("doctor_id", "must be an active doctor of this clinic")
        if doctor.user_id is not None and doctor.user_id != user.id:
            raise InvalidValue("doctor_id", "is already linked to someone else")
        linked = doctors.get_for_user(user.id)
        if linked is not None and linked.id != doctor.id:
            raise InvalidValue("doctor_id", "this person already has a doctor profile here")
        if doctor.user_id == user.id:
            return
        doctor.update_details(now=now, user_id=user.id)
        doctors.update(doctor)
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=AuditAction.DOCTOR_UPDATED,
            actor=actor,
            now=now,
            clinic_id=clinic_id,
            entity_type="doctor",
            entity_id=doctor.id,
            metadata={"fields": "user_id", "is_active": "true", "via": "owner_invite"},
        )

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


class ResendStaffInvite:
    """*Resend* on the Team page (M6a-P5): a new invitation for a member still ``INVITED``.

    Emailed again when the member has an email address, otherwise a new link to show once. Either
    way the previous link stops working at once. Recorded as ``staff.invited`` with
    ``resent=true``.
    """

    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: InviteSecrets
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def execute(self, ctx: RequestContext, membership_id: UUID) -> StaffInvitation:
        with self._uow as uow:
            now = self._clock.now()
            staff = uow.tenant(ctx.clinic_id).memberships
            membership = staff.get(membership_id)
            if membership is None:
                logger.info(
                    "tenancy.not_found",
                    entity="membership",
                    entity_id=str(membership_id),
                    clinic_id=str(ctx.clinic_id),
                )
                raise NotFound("membership")
            if membership.status is not MembershipStatus.INVITED:
                raise InvalidTransition("membership", membership.status, "resend the invitation of")
            _limit(uow, f"staff-invite-resend:{membership.id}", RESENDS_PER_MEMBER_PER_HOUR, now)

            user = uow.users.get(membership.user_id)
            if user is None:  # pragma: no cover - a foreign key keeps the user
                raise NotFound("membership")
            delivery = InviteDelivery.EMAIL if user.email is not None else InviteDelivery.LINK
            token = _prepare_delivery(membership, delivery, self._secrets, now)
            staff.update(membership)
            if delivery is InviteDelivery.EMAIL:
                enqueue_staff_invite(
                    uow,
                    ids=self._ids,
                    clinic_id=ctx.clinic_id,
                    membership_id=membership.id,
                    now=now,
                    request_id=ctx.info.request_id,
                )
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.STAFF_INVITED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=membership.id,
                metadata={
                    "target_user_id": str(user.id),
                    "role": membership.role.value,
                    "delivery": delivery.value,
                    "resent": "true",
                },
            )
            member = _member(uow, ctx.clinic_id, membership.id)
            uow.commit()

        logger.info(
            "staff.invite_resent",
            clinic_id=str(ctx.clinic_id),
            membership_id=str(membership_id),
            delivery=delivery.value,
        )
        return _invitation(member, delivery, token, user)


def _prepare_delivery(
    membership: ClinicMembership,
    delivery: InviteDelivery,
    secrets: InviteSecrets,
    now: datetime,
) -> str | None:
    """A link invitation gets its secret now; an emailed one retires the old link now."""
    if delivery is InviteDelivery.EMAIL:
        membership.withdraw_invite(now=now)
        return None
    token = secrets.generate()
    membership.issue_invite(secrets.digest(token), now=now)
    return token


def _limit(uow: UnitOfWork, bucket: str, limit: int, now: datetime) -> None:
    """One more for ``bucket`` this hour; refuse over ``limit`` (a refusal is rolled back)."""
    window = now.replace(minute=0, second=0, microsecond=0)
    if uow.rate_limits.hit(bucket, window_start=window) > limit:
        retry = max(1, 3600 - (now.minute * 60 + now.second))
        logger.info("staff.invite_rate_limited", bucket=bucket.split(":", 1)[0], retry_after=retry)
        raise InvitesRateLimited(retry)


def _member(uow: UnitOfWork, clinic_id: UUID, membership_id: UUID) -> StaffMember:
    # Read in the same transaction: a clinic has a handful of members.
    found = [
        m
        for m in uow.tenant(clinic_id).memberships.list_staff()
        if m.membership_id == membership_id
    ]
    if not found:  # pragma: no cover - the row was just written in this transaction
        raise NotFound("membership")
    return found[0]


def _invitation(
    member: StaffMember, delivery: InviteDelivery, token: str | None, user: User
) -> StaffInvitation:
    masked = user.email.masked() if delivery is InviteDelivery.EMAIL and user.email else None
    return StaffInvitation(member=member, delivery=delivery, token=token, email_masked=masked)


def _parse_identifiers(cmd: InviteStaffCommand) -> tuple[EmailAddress | None, PhoneNumber | None]:
    """At least one way to reach them, because that is how they sign in (R1)."""
    email = EmailAddress.parse(cmd.email, field="email") if cmd.email else None
    phone = PhoneNumber.parse(cmd.phone, field="phone") if cmd.phone else None
    if email is None and phone is None:
        raise InvalidValue("email", "an email address or a phone number is required")
    return email, phone
