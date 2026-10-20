"""Ops reads: which clinics exist and how far each one got (FR-OPS-01, FR-OPS-04), and what
their messages cost each month (M5-P5, spec R18).

Deliberate cross-clinic reads for platform staff (ADR-0003): clinics are not
tenant-owned, and nothing here touches clinical content. The checklist beside
each clinic is what makes goal G4 measurable — "clinic created 14:02, owner
accepted 14:31" rather than somebody's recollection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.onboarding import OnboardingChecklist
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.messaging import ChannelCost
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


def paise(millipaise: int) -> int:
    """Whole paise, rounded half up: money is reported in paise (decision 5A)."""
    return (millipaise + 500) // 1000


@dataclass(frozen=True, slots=True)
class ClinicMessagingCost:
    clinic_id: UUID
    clinic_name: str
    channels: Sequence[ChannelCost]

    @property
    def messages(self) -> int:
        return sum(c.messages for c in self.channels)

    @property
    def unpriced(self) -> int:
        return sum(c.unpriced for c in self.channels)

    @property
    def cost_millipaise(self) -> int:
        return sum(c.cost_millipaise for c in self.channels)


class MessagingCosts:
    """Each clinic's messages and their cost in one month (M5-P5; spec R18; decision 7A).

    Counts and sums only, no message, patient or number. A clinic with no message that month is
    left out; a message whose cost is not yet known is counted as unpriced, never guessed.
    """

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, month: date) -> Sequence[ClinicMessagingCost]:
        with self._uow as uow:
            rows = uow.message_costs.monthly(month.replace(day=1))
        clinics: dict[UUID, ClinicMessagingCost] = {}
        for row in rows:
            entry = clinics.get(row.clinic_id)
            channels = (*entry.channels, row) if entry is not None else (row,)
            clinics[row.clinic_id] = ClinicMessagingCost(row.clinic_id, row.clinic_name, channels)
        return list(clinics.values())
