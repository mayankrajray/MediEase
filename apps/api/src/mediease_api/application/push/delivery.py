"""Web push delivery (M7e-E3, ADR-0025; spec web-push R30-R37).

**Enqueue (outbox).** When a notice is given (``notify_patient`` for a patient, the in-app
dispatch for staff), one ``send_push`` job is enqueued per active device of the person, in the
notice's transaction, unless they turned push off for that kind. The key is the device and the
notice's event key, so a replayed event enqueues nothing, and a retry of one device never sends
again to the others.

**Send.** The worker reads the device again (it may be gone, disabled or another person's now),
the preference again, and for staff the membership; then decrypts the endpoint and keys, and
hands the push service a generic message (``domain/push/message.py``). The answer:

- accepted: the device's last success is recorded;
- 404 or 410: the browser unsubscribed, so the device is disabled (``EXPIRED``) and the job ends;
- 429, 5xx or no answer: the job is retried on its backoff;
- anything else: the job is dead with the code (never retried).

**Quiet hours (R38).** A push of a kind that waits for them, enqueued between 21:00 and 08:00
clinic time, runs at 08:00. The in-app notice is there at once either way.

Logs carry the device ID, the owner kind and the notice kind; never the endpoint, the keys or the
message.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.domain.identity.membership import MembershipStatus
from mediease_api.domain.jobs.job import PUSH_KIND, ClaimedJob, NewJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.notifications.notification import Channel, NotificationKind
from mediease_api.domain.portal.notifications import PatientChannel, PatientNotificationKind
from mediease_api.domain.push.message import (
    LINK_MAX,
    PushMessage,
    patient_message,
    staff_message,
    waits_for_quiet_hours,
)
from mediease_api.domain.push.subscription import (
    DisabledReason,
    OwnerKind,
    PushOwner,
    PushSubscription,
    check_endpoint,
)
from mediease_api.domain.reminders.rules import outside_quiet_hours
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.push import (
    PushFailed,
    PushFailure,
    PushTarget,
    TextCipherPort,
    WebPushPort,
)
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


def push_key(device_id: UUID, event_key: str) -> str:
    """One push per device per notice. The event key is hashed: keys are at most 200 chars."""
    digest = hashlib.sha256(event_key.encode("utf-8")).hexdigest()[:32]
    return f"push:{device_id}:{digest}"


def enqueue_push(
    uow: UnitOfWork,
    *,
    ids: IdPort,
    devices: Sequence[PushSubscription],
    clinic_id: UUID,
    notice: PatientNotificationKind | NotificationKind,
    event_key: str,
    link: str,
    now: datetime,
    request_id: str | None = None,
) -> int:
    """R30, R31: a job per active device, in the caller's transaction. R38: a kind that waits for
    the quiet hours runs at the next 08:00, clinic time, if it is night there."""
    devices = [d for d in devices if d.is_active]
    if not devices:
        return 0
    run_at = now
    if waits_for_quiet_hours(notice):
        clinic = uow.clinics.get(clinic_id)
        if clinic is not None:
            run_at = outside_quiet_hours(now, clinic.timezone)
    for device in devices:
        uow.jobs.enqueue(
            NewJob.create(
                id=ids.new_id(),
                kind=PUSH_KIND,
                now=now,
                run_at=run_at,
                clinic_id=clinic_id,
                payload={
                    "owner_kind": device.owner.kind.value,
                    "owner_id": str(device.owner.id),
                    "device_id": str(device.id),
                    "notice": notice.value,
                    "link": link if len(link) <= LINK_MAX else None,
                },
                request_id=request_id,
                dedupe_key=push_key(device.id, event_key),
            )
        )
    return len(devices)


def _owner(payload_kind: str, owner_id: str) -> PushOwner:
    return PushOwner(OwnerKind(payload_kind), UUID(owner_id))


class SendPush:
    """The ``send_push`` job handler."""

    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, push: WebPushPort, cipher: TextCipherPort
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._push = push
        self._cipher = cipher

    def __call__(self, job: ClaimedJob) -> None:
        try:
            owner = _owner(str(job.payload["owner_kind"]), str(job.payload["owner_id"]))
            device_id = UUID(str(job.payload["device_id"]))
            notice = str(job.payload["notice"])
            link = job.payload.get("link")
            if owner.kind is OwnerKind.PATIENT:
                PatientNotificationKind(notice)
            else:
                NotificationKind(notice)
        except (KeyError, ValueError):
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False) from None
        if job.clinic_id is None:
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False)
        prepared = self._prepare(
            owner, device_id, notice, link if isinstance(link, str) else None, job.clinic_id
        )
        if prepared is None:
            return
        target, message = prepared
        log = logger.bind(owner_kind=owner.kind.value, device_id=str(device_id), notice=notice)
        try:
            self._push.send(target, message.encode(), ttl=message.ttl)
        except PushFailed as failed:
            if failed.failure is PushFailure.GONE:
                self._record(owner, device_id, gone=True)
                log.info("push.device_expired", status=failed.status)
                return
            log.warning("push.failed", code=failed.failure.value, status=failed.status)
            raise JobFailure(failed.failure.value, retryable=failed.failure.retryable) from None
        self._record(owner, device_id, gone=False)
        log.info("push.sent", provider=self._push.provider)

    def _prepare(
        self,
        owner: PushOwner,
        device_id: UUID,
        notice: str,
        link: str | None,
        clinic_id: UUID,
    ) -> tuple[PushTarget, PushMessage] | None:
        def skip(reason: str) -> None:
            logger.info(
                "push.skipped",
                owner_kind=owner.kind.value,
                device_id=str(device_id),
                notice=notice,
                reason=reason,
            )

        with self._uow as uow:
            device = uow.push_subscriptions.get_for_owner(device_id, owner)
            if device is None or not device.is_active:
                skip("no_device")  # removed, expired, or taken over by another person
                return None
            if owner.kind is OwnerKind.PATIENT:
                kind = PatientNotificationKind(notice)
                account = uow.patient_accounts.get(owner.id)
                if account is None:  # pragma: no cover - the device is deleted with the account
                    skip("no_account")
                    return None
                if uow.patient_preferences.is_off(owner.id, kind, PatientChannel.PUSH):
                    skip("turned_off")
                    return None
                message = patient_message(kind, account.language, link)
            else:
                staff_kind = NotificationKind(notice)
                tenant = uow.tenant(clinic_id)
                membership = tenant.memberships.get_for_user(owner.id)
                if membership is None or membership.status is not MembershipStatus.ACTIVE:
                    skip("not_a_member")
                    return None
                if tenant.notification_preferences.disabled_among(
                    [owner.id], staff_kind, Channel.PUSH
                ):
                    skip("turned_off")
                    return None
                message = staff_message(staff_kind, link)
            target = self._target(device)
        if target is None:
            skip("unreadable")
            return None
        return target, message

    def _target(self, device: PushSubscription) -> PushTarget | None:
        try:
            endpoint = check_endpoint(self._cipher.decrypt(device.endpoint_encrypted))
            return PushTarget(
                endpoint=endpoint,
                p256dh=self._cipher.decrypt(device.p256dh_encrypted),
                auth=self._cipher.decrypt(device.auth_encrypted),
            )
        except (ValueError, InvalidValue):
            # Encrypted with a key no longer configured, or (never expected) not a push service.
            return None

    def _record(self, owner: PushOwner, device_id: UUID, *, gone: bool) -> None:
        now = self._clock.now()
        with self._uow as uow:
            device = uow.push_subscriptions.get_for_owner(device_id, owner)
            if device is None:
                return  # removed while the push was on its way
            if gone:
                device.disable(DisabledReason.EXPIRED, now)
            else:
                device.mark_sent(now)
            uow.push_subscriptions.update(device)
            uow.commit()
