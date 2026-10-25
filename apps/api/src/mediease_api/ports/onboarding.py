"""Clinic applications (M6c-P1; spec clinic-onboarding; ADR-0020).

Platform data, outside any tenant: a reviewed repository used only by the public application
routes, the application jobs and the ops routes. The one cross-clinic read is
``registration_matches``, which returns clinic IDs only (R17).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.onboarding.application import (
    ApplicationKind,
    ApplicationStatus,
    ClinicApplication,
    DoctorCheck,
)
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.phone import PhoneNumber


@dataclass(frozen=True, slots=True)
class ApplicationSummary:
    """R18: what ops sees in P1; no phone, email, registration number or certificate."""

    id: UUID
    reference: str
    kind: ApplicationKind
    clinic_name: str
    city: str
    doctors: int
    submitted_at: datetime
    email_verified_at: datetime
    possible_duplicate: bool
    # M6c-P2: the queue shows every state.
    status: ApplicationStatus = ApplicationStatus.PENDING
    taken_at: datetime | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Removed:
    """An application that was deleted, and the certificate keys it held."""

    id: UUID
    certificate_keys: tuple[str, ...]


class ApplicationRepository(Protocol):
    def next_reference(self, year: int) -> str:
        """The next ``MA-<year>-NNNN`` (a database sequence; numbers are never reused)."""
        ...

    def add(self, application: ClinicApplication) -> None: ...

    def get(
        self, application_id: UUID, *, for_update: bool = False
    ) -> ClinicApplication | None: ...

    def get_by_confirm_digest(self, digest: str) -> ClinicApplication | None:
        """The unconfirmed application whose link has this digest (locked for update)."""
        ...

    def update(self, application: ClinicApplication) -> None: ...

    def remove_unconfirmed_for_email(self, email: EmailAddress) -> list[Removed]:
        """R13: delete the earlier unconfirmed applications of this owner email."""
        ...

    def remove_unconfirmed_before(self, cutoff: datetime) -> list[Removed]:
        """R14: delete applications submitted before ``cutoff`` and never confirmed."""
        ...

    def count_by_ip_since(self, ip_hash: str, since: datetime) -> int: ...

    def count_by_phone_since(self, phone: PhoneNumber, since: datetime) -> int: ...

    def count_by_email_since(self, email: EmailAddress, since: datetime) -> int: ...

    def registration_matches(
        self, registrations: Sequence[tuple[str, str]], *, exclude_id: UUID | None = None
    ) -> list[str]:
        """R17: references of confirmed, not rejected applications, and ``clinic:<id>`` of
        clinics with a doctor, holding any of these (council, number) pairs."""
        ...

    def list_confirmed(
        self, statuses: frozenset[ApplicationStatus] | None = None
    ) -> list[ApplicationSummary]:
        """R18, R25: confirmed applications, oldest first, optionally of these states."""
        ...

    def checks(self, application_id: UUID) -> dict[UUID, DoctorCheck]:
        """R29: the latest check per application doctor."""
        ...

    def put_check(self, application_id: UUID, check: DoctorCheck) -> None:
        """R29: record a check, replacing the doctor's earlier one."""
        ...

    def remove_rejected_before(self, cutoff: datetime) -> list[Removed]:
        """R35: delete applications rejected before ``cutoff``."""
        ...
