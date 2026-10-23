"""The ``send_staff_invite`` job handler: an owner's emailed invitation (M6a-P5, decision 3A).

The request enqueued the membership's ID only. The worker re-reads the membership and, if it is
still ``INVITED``:

1. makes a new secret and stores its digest on the membership, retiring any earlier one, in one
   committed transaction (ADR-0016 decision 4);
2. sends the email with the secret in the ``/invite/<secret>`` link.

A failed send retries with yet another secret, so the link in an unsent email is already dead and
no usable secret is ever at rest. A member deactivated, or an account disabled, since the request
gets nothing.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from mediease_api.application.auth import email_templates
from mediease_api.domain.identity.membership import MembershipStatus, Role
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.email import EmailFailed, EmailMessage, EmailPort
from mediease_api.ports.security import InviteSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# How the email names the role ("... as a doctor").
ROLE_IN_EMAIL = {
    Role.OWNER: "an owner",
    Role.DOCTOR: "a doctor",
    Role.FRONT_DESK: "front desk staff",
}


class SendStaffInvite:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        secrets: InviteSecrets,
        email: EmailPort,
        public_base_url: str,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._secrets = secrets
        self._email = email
        self._base = public_base_url.rstrip("/")

    def __call__(self, job: ClaimedJob) -> None:
        try:
            if job.clinic_id is None:
                raise ValueError("a staff invitation belongs to a clinic")
            clinic_id = job.clinic_id
            membership_id = UUID(str(job.payload["membership_id"]))
        except (KeyError, ValueError):
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False) from None

        message = self._prepare(clinic_id, membership_id)
        if message is None:
            return
        try:
            self._email.send(message)
        except EmailFailed as failure:
            logger.warning(
                "email.failed",
                email="staff_invite",
                reason=failure.reason,
                retryable=failure.retryable,
                attempt=job.attempts,
            )
            raise JobFailure(
                f"EMAIL_{failure.reason.upper()}", retryable=failure.retryable
            ) from None
        logger.info(
            "email.staff_invite_sent",
            clinic_id=str(clinic_id),
            membership_id=str(membership_id),
            to=message.to.masked(),
        )

    def _prepare(self, clinic_id: UUID, membership_id: UUID) -> EmailMessage | None:
        with self._uow as uow:
            now = self._clock.now()
            clinic = uow.clinics.get(clinic_id)
            staff = uow.tenant(clinic_id).memberships
            membership = staff.get(membership_id)
            user = uow.users.get(membership.user_id) if membership is not None else None
            skip = None
            if clinic is None or membership is None or user is None:
                skip = "membership_gone"
            elif membership.status is not MembershipStatus.INVITED:
                skip = "not_invited"
            elif user.email is None:
                skip = "no_email"
            elif not user.is_active or user.is_platform_ops:
                skip = "not_eligible"
            if skip is not None:
                logger.info(
                    "email.skipped",
                    email="staff_invite",
                    membership_id=str(membership_id),
                    reason=skip,
                )
                return None
            assert clinic is not None and membership is not None and user is not None
            assert user.email is not None

            value = self._secrets.generate()
            membership.issue_invite(self._secrets.digest(value), now=now)
            staff.update(membership)
            uow.commit()
            rendered = email_templates.staff_invite(
                user.full_name,
                clinic.name,
                ROLE_IN_EMAIL[membership.role],
                f"{self._base}/invite/{value}",
            )
            address = user.email
        return EmailMessage(
            to=address, subject=rendered.subject, text=rendered.text, html=rendered.html
        )
