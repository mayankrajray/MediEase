"""Patient account links and portal invites (M6b-P1; patient portal spec R1-R9, NFR-18)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from mediease_api.domain.portal.link import PatientAccountLink, PatientPortalInvite


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
