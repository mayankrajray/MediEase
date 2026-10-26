"""Suspending and reactivating a clinic (M6c-P4; FR-ONB-05; spec R56-R58).

``SuspendClinic`` (``OPS_ADMIN``): ``ACTIVE`` -> ``SUSPENDED`` with a reason. In the same
transaction every open booking request of the clinic is declined by the system with
``CLINIC_UNAVAILABLE`` and its patient is told in the portal (the notice is written here, because
the worker cancels a suspended clinic's jobs, so the email is not sent). The clinic leaves every
public surface at once: the public page, requests, the directory and the live token links all
need ``ACTIVE``. Staff are refused on their next request (``CLN_SUSPENDED``).

``ReactivateClinic``: ``SUSPENDED`` -> ``ACTIVE`` (needs an active owner, I1). The listing the
owner chose is kept, so a reactivated clinic is discoverable again if nothing else changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor
from mediease_api.application.notifications.service import publish
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus, SuspendReason
from mediease_api.domain.notifications.events import BookingRequestAnswered
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# R57: a clinic has at most a few dozen open requests; read them all.
_OPEN_LIMIT = 10_000
NOTE_MAX = 500


@dataclass(frozen=True, slots=True)
class Suspension:
    clinic: Clinic
    withdrawn: int


class SuspendClinic:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, actor: Actor, clinic_id: UUID, reason: SuspendReason, note: str | None
    ) -> Suspension:
        if reason is SuspendReason.OTHER and not (note and note.strip()):
            raise InvalidValue("note", "is required for OTHER")
        with self._uow as uow:
            now = self._clock.now()
            clinic = uow.clinics.get(clinic_id, for_update=True)
            if clinic is None:
                raise NotFound("clinic")
            clinic.suspend(now=now)
            uow.clinics.update(clinic)
            tenant = uow.tenant(clinic_id)
            withdrawn = 0
            for open_request in tenant.booking_requests.list_open(now, limit=_OPEN_LIMIT):
                request = tenant.booking_requests.get(open_request.id, for_update=True)
                if request is None or not request.withdraw(now):
                    continue
                tenant.booking_requests.update(request)
                publish(
                    uow,
                    BookingRequestAnswered(request.id),
                    clinic_id=clinic_id,
                    ids=self._ids,
                    now=now,
                    request_id=actor.info.request_id,
                    actor_user_id=actor.user_id,
                )
                withdrawn += 1
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.CLINIC_SUSPENDED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                # The reason code and a count; the ops note stays out of the audit (it is free
                # text) and is only logged as present or not.
                metadata={"reason": reason.value, "requests_withdrawn": str(withdrawn)},
            )
            uow.commit()
        logger.info(
            "clinic.suspended",
            clinic_id=str(clinic_id),
            reason=reason.value,
            requests_withdrawn=withdrawn,
            note=bool(note),
        )
        return Suspension(clinic, withdrawn)


class ReactivateClinic:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, actor: Actor, clinic_id: UUID) -> Clinic:
        with self._uow as uow:
            now = self._clock.now()
            clinic = uow.clinics.get(clinic_id, for_update=True)
            if clinic is None:
                raise NotFound("clinic")
            if clinic.status is not ClinicStatus.SUSPENDED:
                raise InvalidValue("status", "only a suspended clinic can be reactivated")
            owners = uow.tenant(clinic_id).memberships.count_active_owners()
            clinic.activate(active_owner_count=owners, now=now)
            uow.clinics.update(clinic)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.CLINIC_REACTIVATED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
            )
            uow.commit()
        logger.info("clinic.reactivated", clinic_id=str(clinic_id))
        return clinic
