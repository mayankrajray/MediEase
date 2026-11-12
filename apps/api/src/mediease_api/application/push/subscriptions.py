"""A person's devices for web push (M7e-E2, ADR-0025; spec web-push R10-R19).

The same use cases serve a patient account (``@patient``) and a staff user (``@authenticated``);
the owner comes from the session, never from the request. A device is added or refreshed by its
endpoint: the same browser subscribing again updates its keys; another person subscribing the
same browser takes the device over (a shared phone delivers to whoever turned push on last).
Adding and removing are audited with the device's ID and label only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.context import RequestInfo
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.push.errors import PushRateLimited, TooManyDevices
from mediease_api.domain.push.subscription import (
    MAX_DEVICES,
    SUBSCRIBES_PER_HOUR,
    OwnerKind,
    PushOwner,
    PushSubscription,
    check_endpoint,
    check_keys,
    device_label,
    endpoint_digest,
)
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.push import TextCipherPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "push_subscription"


@dataclass(frozen=True, slots=True)
class DeviceView:
    id: UUID
    label: str
    created_at: datetime
    last_success_at: datetime | None
    active: bool


def _view(s: PushSubscription) -> DeviceView:
    return DeviceView(s.id, s.label, s.created_at, s.last_success_at, s.is_active)


def _audit(
    uow: UnitOfWork,
    ids: IdPort,
    *,
    action: AuditAction,
    owner: PushOwner,
    device: PushSubscription,
    info: RequestInfo,
    now: datetime,
) -> None:
    patient = owner.kind is OwnerKind.PATIENT
    uow.audit.record(
        AuditEvent.record(
            id=ids.new_id(),
            action=action,
            actor_type=ActorType.PATIENT if patient else ActorType.STAFF,
            actor_user_id=None if patient else owner.id,
            now=now,
            entity_type=ENTITY_TYPE,
            entity_id=device.id,
            request_id=info.request_id,
            ip_hash=info.ip_hash,
            metadata={"label": device.label, **({"account_id": str(owner.id)} if patient else {})},
        )
    )


@dataclass(frozen=True, slots=True)
class SubscribeResult:
    device: DeviceView
    created: bool


class SubscribeDevice:
    """R11-R15: add this browser, or refresh it; at most ``MAX_DEVICES`` active ones per owner."""

    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, cipher: TextCipherPort
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._cipher = cipher

    def _limit(self, owner: PushOwner, now: datetime) -> None:
        window = now.replace(minute=0, second=0, microsecond=0)
        with self._uow as uow:
            hits = uow.rate_limits.hit(
                f"push-sub:{owner.kind.value}:{owner.id}", window_start=window
            )
            uow.commit()
        if hits > SUBSCRIBES_PER_HOUR:
            logger.info("push.rate_limited", owner_kind=owner.kind.value)
            raise PushRateLimited(int((window + timedelta(hours=1) - now).total_seconds()))

    def execute(
        self,
        owner: PushOwner,
        *,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: str | None,
        info: RequestInfo,
    ) -> SubscribeResult:
        check_endpoint(endpoint)
        check_keys(p256dh, auth)
        now = self._clock.now()
        self._limit(owner, now)
        digest = endpoint_digest(endpoint)
        label = device_label(user_agent)
        p256dh_encrypted = self._cipher.encrypt(p256dh)
        auth_encrypted = self._cipher.encrypt(auth)
        with self._uow as uow:
            repo = uow.push_subscriptions
            existing = repo.by_digest(digest, for_update=True)
            if existing is not None and existing.owner == owner:
                existing.refresh(
                    p256dh_encrypted=p256dh_encrypted,
                    auth_encrypted=auth_encrypted,
                    label=label,
                    now=now,
                )
                repo.update(existing)
                uow.commit()
                logger.info(
                    "push.device_refreshed", owner_kind=owner.kind.value, device_id=str(existing.id)
                )
                return SubscribeResult(_view(existing), created=False)
            if repo.count_active(owner) >= MAX_DEVICES:
                raise TooManyDevices()
            if existing is not None:
                # R14: another person's device, now this person's; the previous owner is not told.
                repo.delete(existing.id)
            device = PushSubscription.create(
                id=self._ids.new_id(),
                owner=owner,
                digest=digest,
                endpoint_encrypted=self._cipher.encrypt(endpoint),
                p256dh_encrypted=p256dh_encrypted,
                auth_encrypted=auth_encrypted,
                label=label,
                now=now,
            )
            repo.add(device)
            _audit(
                uow,
                self._ids,
                action=AuditAction.PUSH_DEVICE_ADDED,
                owner=owner,
                device=device,
                info=info,
                now=now,
            )
            uow.commit()
        logger.info(
            "push.device_added",
            owner_kind=owner.kind.value,
            device_id=str(device.id),
            moved=existing is not None,
        )
        return SubscribeResult(_view(device), created=True)


class ListDevices:
    """R16: the owner's devices, newest first."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, owner: PushOwner) -> Sequence[DeviceView]:
        with self._uow as uow:
            return [_view(s) for s in uow.push_subscriptions.list_for_owner(owner)]


class RemoveDevice:
    """R17: the owner turns push off for one of their devices; another's is not found."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, owner: PushOwner, device_id: UUID, info: RequestInfo) -> None:
        now = self._clock.now()
        with self._uow as uow:
            device = uow.push_subscriptions.get_for_owner(device_id, owner)
            if device is None:
                raise NotFound("device")
            uow.push_subscriptions.delete(device.id)
            _audit(
                uow,
                self._ids,
                action=AuditAction.PUSH_DEVICE_REMOVED,
                owner=owner,
                device=device,
                info=info,
                now=now,
            )
            uow.commit()
        logger.info("push.device_removed", owner_kind=owner.kind.value, device_id=str(device_id))


@dataclass(frozen=True, slots=True)
class PushConfig:
    enabled: bool
    public_key: str | None


class GetPushConfig:
    """R10: whether push is offered here, and the key a browser subscribes with."""

    def __init__(self, *, public_key: str) -> None:
        self._public_key = public_key

    def execute(self) -> PushConfig:
        return PushConfig(enabled=bool(self._public_key), public_key=self._public_key or None)
