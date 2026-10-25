"""Reviewing clinic applications (M6c-P2; FR-ONB-03, 05; spec clinic-onboarding R24-R40).

Only ops users with ``OPS_REVIEWER`` reach these (the ``@reviewer`` policy). A reviewer sees the
whole application (the owner's contact, each doctor's registration and certificate), so opening
it and each certificate is audited. Every transition records the reviewer and the time, under the
application's row lock, in the same transaction as its audit row (FR-AUD-01).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor
from mediease_api.application.onboarding.submit import ENTITY, enqueue_application_email
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.onboarding.application import (
    ApplicationStatus,
    CheckResult,
    ClinicApplication,
    DoctorCheck,
    NotUnderReview,
    RejectReason,
)
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.onboarding import ApplicationSummary
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# R25: what the queue's tabs ask for.
QUEUES: dict[str, frozenset[ApplicationStatus]] = {
    "waiting": frozenset({ApplicationStatus.PENDING}),
    "review": frozenset({ApplicationStatus.UNDER_REVIEW}),
    "decided": frozenset({ApplicationStatus.APPROVED, ApplicationStatus.REJECTED}),
}


class EmailKindReview:
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ApplicationDetail:
    application: ClinicApplication
    checks: dict[UUID, DoctorCheck]

    @property
    def all_verified(self) -> bool:
        return all(
            d.id in self.checks and self.checks[d.id].result is CheckResult.VERIFIED
            for d in self.application.doctors
        )


@dataclass(frozen=True, slots=True)
class CheckCommand:
    register_checked: bool
    certificate_matches: bool
    result: CheckResult
    note: str | None = None


def load_application(
    uow: UnitOfWork, application_id: UUID, *, lock: bool = False
) -> ClinicApplication:
    found = uow.applications.get(application_id, for_update=lock)
    if found is None or not found.is_confirmed:
        logger.info("application.not_found", application_id=str(application_id))
        raise NotFound("application")
    return found


def _audit(
    uow: UnitOfWork,
    ids: IdPort,
    action: AuditAction,
    actor: Actor,
    application: ClinicApplication,
    now: datetime,
    **metadata: str,
) -> None:
    record_event(
        uow,
        event_id=ids.new_id(),
        action=action,
        actor=actor,
        now=now,
        entity_type=ENTITY,
        entity_id=application.id,
        metadata={"application_id": str(application.id), **metadata},
    )


class ListReviewQueue:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, queue: str | None = None) -> list[ApplicationSummary]:
        statuses = QUEUES.get(queue) if queue else None
        with self._uow as uow:
            return list(uow.applications.list_confirmed(statuses))


class GetApplication:
    """R26: the whole application for a reviewer; audited (``application.viewed``)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, actor: Actor, application_id: UUID) -> ApplicationDetail:
        with self._uow as uow:
            application = load_application(uow, application_id)
            detail = ApplicationDetail(application, uow.applications.checks(application.id))
            _audit(
                uow,
                self._ids,
                AuditAction.APPLICATION_VIEWED,
                actor,
                application,
                self._clock.now(),
            )
            uow.commit()
        return detail


class GetCertificate:
    """R26: one doctor's certificate, streamed by the API only; audited per download."""

    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, storage: BlobStoragePort
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._storage = storage

    def execute(self, actor: Actor, application_id: UUID, doctor_id: UUID) -> tuple[bytes, str]:
        with self._uow as uow:
            application = load_application(uow, application_id)
            doctor = application.doctor(doctor_id)
            assert doctor.certificate is not None
            data = self._storage.get(doctor.certificate.key)
            if data is None:
                logger.error("application.certificate_missing", application_id=str(application.id))
                raise NotFound("certificate")
            _audit(
                uow,
                self._ids,
                AuditAction.APPLICATION_CERTIFICATE_VIEWED,
                actor,
                application,
                self._clock.now(),
                doctor_id=str(doctor_id),
            )
            uow.commit()
        return data, doctor.certificate.content_type


class TakeApplication:
    """R27: ``PENDING`` -> ``UNDER_REVIEW``; a second reviewer is ``ONB_ALREADY_TAKEN``."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, actor: Actor, application_id: UUID) -> ApplicationDetail:
        with self._uow as uow:
            now = self._clock.now()
            taken = load_application(uow, application_id, lock=True).start_review(
                reviewer_id=actor.user_id, now=now
            )
            uow.applications.update(taken)
            _audit(uow, self._ids, AuditAction.APPLICATION_TAKEN, actor, taken, now)
            detail = ApplicationDetail(taken, uow.applications.checks(taken.id))
            uow.commit()
        logger.info("application.taken", application_id=str(application_id))
        return detail


class CheckDoctor:
    """R29, R30: record a doctor's check while the application is under review."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, actor: Actor, application_id: UUID, doctor_id: UUID, cmd: CheckCommand
    ) -> ApplicationDetail:
        with self._uow as uow:
            now = self._clock.now()
            application = load_application(uow, application_id, lock=True)
            if application.status is not ApplicationStatus.UNDER_REVIEW:
                raise NotUnderReview()
            application.doctor(doctor_id)
            check = DoctorCheck.record(
                doctor_id=doctor_id,
                checked_by=actor.user_id,
                now=now,
                register_checked=cmd.register_checked,
                certificate_matches=cmd.certificate_matches,
                result=cmd.result,
                note=cmd.note,
            )
            uow.applications.put_check(application.id, check)
            _audit(
                uow,
                self._ids,
                AuditAction.APPLICATION_DOCTOR_CHECKED,
                actor,
                application,
                now,
                doctor_id=str(doctor_id),
                result=check.result.value,
            )
            detail = ApplicationDetail(application, uow.applications.checks(application.id))
            uow.commit()
        return detail


class RejectApplication:
    """R33, R34: ``UNDER_REVIEW`` -> ``REJECTED`` with a reason; the applicant is emailed."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, actor: Actor, application_id: UUID, reason: RejectReason, message: str | None
    ) -> ApplicationDetail:
        with self._uow as uow:
            now = self._clock.now()
            rejected = load_application(uow, application_id, lock=True).reject(
                reviewer_id=actor.user_id, reason=reason, message=message, now=now
            )
            uow.applications.update(rejected)
            _audit(
                uow,
                self._ids,
                AuditAction.APPLICATION_REJECTED,
                actor,
                rejected,
                now,
                reason=reason.value,
            )
            enqueue_application_email(
                uow,
                ids=self._ids,
                application=rejected,
                email=EmailKindReview.REJECTED,
                now=now,
                request_id=actor.info.request_id,
            )
            detail = ApplicationDetail(rejected, uow.applications.checks(rejected.id))
            uow.commit()
        logger.info("application.rejected", application_id=str(application_id), reason=reason.value)
        return detail
