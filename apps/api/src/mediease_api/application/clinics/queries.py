"""Read-only clinic queries, every one scoped to the request's clinic (NFR-08, spec R8).

Each query takes the ``RequestContext`` the access hook built and asks the
unit of work for repositories bound to ``ctx.clinic_id``. A doctor of another
clinic is not "forbidden" but *absent*: the scoped repository cannot express
the question, so the answer is ``REQ_NOT_FOUND`` and the resource's existence
stays hidden (AC3).

Writes (invite staff, change a role, add a doctor) arrive in M1-P5, after the
audit log, so every mutation is audited from the first one.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import structlog

from mediease_api.application.context import RequestContext
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class GetClinic:
    """The clinic the request is for; its ID comes from the context, never the client."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext) -> Clinic:
        with self._uow as uow:
            clinic = uow.clinics.get(ctx.clinic_id)
            if clinic is None:
                raise NotFound("clinic")
            return clinic


class ListDoctors:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext) -> Sequence[Doctor]:
        with self._uow as uow:
            return uow.tenant(ctx.clinic_id).doctors.list()


class GetDoctor:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext, doctor_id: UUID) -> Doctor:
        with self._uow as uow:
            doctor = uow.tenant(ctx.clinic_id).doctors.get(doctor_id)
            if doctor is None:
                # Also the cross-clinic case: logged for NFR-08 monitoring, never 403.
                logger.info(
                    "tenancy.not_found",
                    entity="doctor",
                    entity_id=str(doctor_id),
                    clinic_id=str(ctx.clinic_id),
                )
                raise NotFound("doctor")
            return doctor


class ListStaff:
    """The clinic's members with their roles (``STAFF_MANAGE``: owners only)."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext) -> Sequence[StaffMember]:
        with self._uow as uow:
            return uow.tenant(ctx.clinic_id).memberships.list_staff()
