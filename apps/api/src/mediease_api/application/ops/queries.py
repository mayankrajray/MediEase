"""Ops reads: which clinics exist and how far each one got (FR-OPS-01, FR-OPS-04).

Deliberate cross-clinic reads for platform staff (ADR-0003): clinics are not
tenant-owned, and nothing here touches clinical content. The checklist beside
each clinic is what makes goal G4 measurable — "clinic created 14:02, owner
accepted 14:31" rather than somebody's recollection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.onboarding import OnboardingChecklist
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class ClinicOnboarding:
    clinic: Clinic
    checklist: OnboardingChecklist | None


@dataclass(frozen=True, slots=True)
class ClinicDetail:
    clinic: Clinic
    checklist: OnboardingChecklist | None
    staff: Sequence[StaffMember]
    doctor_count: int


class ListClinics:
    """Every clinic with its onboarding state, newest first."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self) -> Sequence[ClinicOnboarding]:
        with self._uow as uow:
            return [
                ClinicOnboarding(clinic=clinic, checklist=checklist)
                for clinic, checklist in uow.clinics.list_onboarding()
            ]


class GetClinicOnboarding:
    """One clinic with its checklist, staff and doctor count — the ops detail view."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, clinic_id: UUID) -> ClinicDetail:
        with self._uow as uow:
            clinic = uow.clinics.get(clinic_id)
            if clinic is None:
                raise NotFound("clinic")
            tenant = uow.tenant(clinic_id)
            return ClinicDetail(
                clinic=clinic,
                checklist=tenant.checklist.get(),
                staff=tenant.memberships.list_staff(),
                doctor_count=len(tenant.doctors.list()),
            )
