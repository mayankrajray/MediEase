"""Patient account links and portal invites (M6b-P1; patient portal spec R1-R9, NFR-18)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.portal.doses import DoseRecord
from mediease_api.domain.portal.link import PatientAccountLink, PatientPortalInvite
from mediease_api.domain.portal.medicines import MedicineReminderPref
from mediease_api.domain.prescriptions.schedule import Slot


class PortalLinkRepository(Protocol):
    """``patient_account_links`` of one clinic (tenant-scoped, ADR-0003)."""

    def add(self, link: PatientAccountLink) -> None:
        """Insert; a concurrent link of the same record or account is ``PRT_ALREADY_LINKED``."""
        ...

    def update(self, link: PatientAccountLink) -> None:
        """Save the revocation."""
        ...

    def get(self, link_id: UUID, *, for_update: bool = False) -> PatientAccountLink | None: ...

    def active_for_patient(
        self, patient_id: UUID, *, for_update: bool = False
    ) -> PatientAccountLink | None: ...

    def active_for_account(self, account_id: UUID) -> PatientAccountLink | None:
        """The account's active link in this clinic, if any (decision 1A: at most one)."""
        ...


class PortalInviteRepository(Protocol):
    """``patient_portal_invites`` of one clinic (tenant-scoped)."""

    def add(self, invite: PatientPortalInvite) -> None: ...
    def update(self, invite: PatientPortalInvite) -> None: ...

    def get_by_digest(
        self, token_hash: str, *, for_update: bool = False
    ) -> PatientPortalInvite | None: ...

    def pending_for_patient(
        self, patient_id: UUID, *, for_update: bool = False
    ) -> PatientPortalInvite | None:
        """The record's invite that is neither used nor superseded (it may have expired)."""
        ...


class ReminderPrefRepository(Protocol):
    """``medicine_reminder_prefs`` of one clinic (tenant-scoped; M6b-P3, R37-R40)."""

    def for_account(
        self, account_id: UUID, prescription_ids: Sequence[UUID]
    ) -> Sequence[MedicineReminderPref]:
        """The account's preferences for these versions."""
        ...

    def get(
        self, account_id: UUID, prescription_id: UUID, item_id: UUID, slot: Slot
    ) -> MedicineReminderPref | None: ...

    def add(self, pref: MedicineReminderPref) -> None: ...
    def update(self, pref: MedicineReminderPref) -> None: ...

    def list_enabled(self, *, limit: int) -> Sequence[MedicineReminderPref]:
        """M6b-P6 (R65): this clinic's reminder choices that are turned on, for the medicine
        sweep."""
        ...

    def delete_for_link(self, account_id: UUID, patient_id: UUID) -> int:
        """R40: an unlinked record keeps no preferences. Returns how many were removed."""
        ...


class DoseRecordRepository(Protocol):
    """``dose_records`` of one clinic (tenant-scoped; M6b-P3b, R45-R52). Patient routes only."""

    def for_account(
        self, account_id: UUID, prescription_ids: Sequence[UUID]
    ) -> Sequence[DoseRecord]:
        """The account's records for these versions, any date."""
        ...

    def get(
        self, account_id: UUID, prescription_id: UUID, item_id: UUID, on_date: date, slot: Slot
    ) -> DoseRecord | None: ...

    def add(self, record: DoseRecord) -> None: ...
    def update(self, record: DoseRecord) -> None: ...
    def delete(self, record: DoseRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class DoseExport:
    """One record as the patient's export carries it (R54): IDs, day, slot, state and time."""

    clinic_id: UUID
    patient_id: UUID
    prescription_id: UUID
    item_id: UUID
    on_date: date
    slot: str
    state: str
    marked_at: datetime


class DoseLifecycle(Protocol):
    """R54, reviewed cross-clinic exception: an account's records in every clinic, for support.

    Run only on the patient's own request (RUNBOOK), until FR-PRT-10's screens exist.
    """

    def export_for_account(self, account_id: UUID) -> Sequence[DoseExport]: ...

    def delete_for_account(self, account_id: UUID) -> int: ...


class PortalLookup(Protocol):
    """The portal's two cross-clinic reads (reviewed tenancy exception, M6b-P1 decision 6A).

    A portal caller names no clinic, so the scope starts here: the account's active links (IDs,
    method and dates only), and which clinic an invite digest belongs to. Everything else is read
    through that clinic's tenant repositories.
    """

    def active_links(self, account_id: UUID) -> Sequence[PatientAccountLink]:
        """Oldest first."""
        ...

    def invite_clinic(self, token_hash: str) -> UUID | None: ...
