"""``PortalScope``: what one patient account may read (M6b-P1 decision 6A; NFR-18, spec R9).

Read once per request, inside the caller's unit of work: the account's **active** links, each a
(clinic, patient record) pair, for clinics that are not suspended (spec §8). Every portal read
goes through ``uow.tenant(clinic)`` and filters by that pair's patient, so nothing outside the
scope can be named: an ID that is not in it is ``REQ_NOT_FOUND``, never a 403.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.portal.link import PatientAccountLink
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ScopeEntry:
    link: PatientAccountLink
    clinic: Clinic
    patient: Patient
    tenant: TenantRepositories

    @property
    def patient_id(self) -> UUID:
        return self.patient.id


class PortalScope:
    """The linked records of one account, valid for the unit of work it was read in."""

    def __init__(self, entries: list[ScopeEntry]) -> None:
        self._entries = entries

    @classmethod
    def read(cls, uow: UnitOfWork, account_id: UUID) -> PortalScope:
        entries = []
        for link in uow.portal_lookup.active_links(account_id):
            clinic = uow.clinics.get(link.clinic_id)
            if clinic is None or clinic.status is ClinicStatus.SUSPENDED:
                continue
            tenant = uow.tenant(link.clinic_id)
            patient = tenant.patients.get(link.patient_id)
            assert patient is not None  # the foreign key keeps it
            entries.append(ScopeEntry(link, clinic, patient, tenant))
        return cls(entries)

    def __iter__(self) -> Iterator[ScopeEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def link(self, link_id: UUID) -> ScopeEntry:
        """The entry of one of the account's active links, else ``REQ_NOT_FOUND``."""
        for entry in self._entries:
            if entry.link.id == link_id:
                return entry
        raise _not_found("portal link", link_id)


def _not_found(entity: str, entity_id: UUID) -> NotFound:
    logger.info("portal.not_found", entity=entity, entity_id=str(entity_id))
    return NotFound(entity)
