"""*My Patients*: the patients the caller has seen as a doctor (M6a-P6; FR-UX-02, FR-UX-06).

A patient is "mine" once the caller's own doctor profile in this clinic has a visit with them
(decision 5A); one only booked is not mine yet. Most recent visit first, 50 a page, narrowed by
the lookup box's rules (phone, then code, then name prefix). The answer is who and when, never
what: no complaint, finding, diagnosis or medicine. Like the lookup, it is not audited; opening
a visit is.

For a doctor and for a practising owner alike, whatever workspace they are in: the route needs
``CLINICAL_VIEW``, and a caller with no doctor profile here gets ``CLN_NO_DOCTOR_PROFILE``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.clinics.errors import NoDoctorProfile
from mediease_api.application.context import RequestContext
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.patients.lookup import QueryKind, classify_query
from mediease_api.domain.patients.patient import Sex
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.repositories import PatientMatch
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

MY_PATIENTS_MAX_LIMIT = 100


@dataclass(frozen=True, slots=True, repr=False)
class MyPatientView:
    id: UUID
    code: str
    full_name: str = field(repr=False)
    sex: Sex
    age_years: int
    age_is_estimated: bool
    last_visit_at: datetime
    visits: int

    def __repr__(self) -> str:
        return f"MyPatientView(code={self.code!r})"


class ListMyPatients:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, ctx: RequestContext, *, q: str | None, limit: int, offset: int
    ) -> Sequence[MyPatientView]:
        if not 1 <= limit <= MY_PATIENTS_MAX_LIMIT:
            raise InvalidValue("limit", f"must be 1-{MY_PATIENTS_MAX_LIMIT}")
        if offset < 0:
            raise InvalidValue("offset", "must not be negative")
        nobody, match = _match(q)
        with self._uow as uow:
            clinic = uow.clinics.get(ctx.clinic_id)
            if clinic is None:  # pragma: no cover - the request context names an existing clinic
                raise NotFound("clinic")
            tenant = uow.tenant(ctx.clinic_id)
            profile = tenant.doctors.get_for_user(ctx.user_id)
            if profile is None or (ctx.role is Role.OWNER and not profile.is_active):
                raise NoDoctorProfile()
            if nobody:
                return []
            seen = tenant.visits.patients_seen_by(
                profile.id, match=match, limit=limit, offset=offset
            )
            today = local_date(self._clock.now(), clinic.timezone)
        logger.info("patient.my_patients", results=len(seen), filtered=match is not None)
        return [
            MyPatientView(
                id=s.patient.id,
                code=s.patient.code,
                full_name=s.patient.full_name,
                sex=s.patient.sex,
                age_years=s.patient.age_years(today),
                age_is_estimated=s.patient.date_of_birth is None,
                last_visit_at=s.last_visit_at,
                visits=s.visits,
            )
            for s in seen
        ]


def _match(q: str | None) -> tuple[bool, PatientMatch | None]:
    """(matches nobody, the filter). Phone-shaped text that is not a number matches nobody."""
    if q is None or q.strip() == "":
        return False, None
    parsed = classify_query(q)
    if parsed is None or parsed.value is None:
        return True, None
    if parsed.kind is QueryKind.PHONE:
        return False, PatientMatch(phone_e164=parsed.value)
    if parsed.kind is QueryKind.CODE:
        return False, PatientMatch(code=parsed.value)
    return False, PatientMatch(name_prefix=parsed.value)
