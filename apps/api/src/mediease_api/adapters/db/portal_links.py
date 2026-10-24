"""``patient_account_links`` and ``patient_portal_invites`` (M6b-P1, ``ports/portal.py``).

Both are tenant tables reached through ``TenantScopedRepository``. ``SqlAlchemyPortalLookup`` is
the reviewed cross-clinic exception: it returns an account's active links (IDs, method, dates)
and an invite digest's clinic, nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.portal_links import (
    DoseRecordRow,
    MedicineReminderPrefRow,
    PatientAccountLinkRow,
    PatientPortalInviteRow,
)
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.portal.doses import DoseRecord, DoseState
from mediease_api.domain.portal.link import (
    AlreadyLinked,
    LinkMethod,
    PatientAccountLink,
    PatientPortalInvite,
    RevokedBy,
)
from mediease_api.domain.portal.medicines import MedicineReminderPref
from mediease_api.domain.prescriptions.schedule import Slot
from mediease_api.ports.portal import DoseExport


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def _link(row: PatientAccountLinkRow) -> PatientAccountLink:
    return PatientAccountLink(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        account_id=row.account_id,
        method=LinkMethod(row.method),
        created_at=row.created_at.astimezone(UTC),
        created_by_user_id=row.created_by_user_id,
        revoked_at=_utc(row.revoked_at),
        revoked_by=RevokedBy(row.revoked_by) if row.revoked_by else None,
    )


def _invite(row: PatientPortalInviteRow) -> PatientPortalInvite:
    return PatientPortalInvite(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        token_hash=row.token_hash,
        expires_at=row.expires_at.astimezone(UTC),
        created_by=row.created_by,
        created_at=row.created_at.astimezone(UTC),
        used_at=_utc(row.used_at),
        used_by_account_id=row.used_by_account_id,
        superseded_at=_utc(row.superseded_at),
    )


class SqlAlchemyPortalLinkRepository(TenantScopedRepository[PatientAccountLinkRow]):
    model = PatientAccountLinkRow
    entity_name = "portal link"

    def add(self, link: PatientAccountLink) -> None:
        self._check_owned(link.clinic_id)
        row = PatientAccountLinkRow(
            id=link.id,
            clinic_id=self.clinic_id,
            patient_id=link.patient_id,
            account_id=link.account_id,
            method=link.method.value,
            created_at=link.created_at,
            created_by_user_id=link.created_by_user_id,
            revoked_at=link.revoked_at,
            revoked_by=link.revoked_by.value if link.revoked_by else None,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            # A concurrent link of the same record or account won (decision 1A's indexes).
            if "_active" in str(exc.orig):
                raise AlreadyLinked() from None
            raise

    def update(self, link: PatientAccountLink) -> None:
        self._check_owned(link.clinic_id)
        row = self._require_row(link.id)
        row.revoked_at = link.revoked_at
        row.revoked_by = link.revoked_by.value if link.revoked_by else None
        self._session.flush()

    def _one(
        self, query: Select[PatientAccountLinkRow], for_update: bool
    ) -> PatientAccountLink | None:
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _link(row) if row else None

    def get(self, link_id: UUID, *, for_update: bool = False) -> PatientAccountLink | None:
        return self._one(
            self._scoped_select().where(PatientAccountLinkRow.id == link_id), for_update
        )

    def active_for_patient(
        self, patient_id: UUID, *, for_update: bool = False
    ) -> PatientAccountLink | None:
        query = self._scoped_select().where(
            PatientAccountLinkRow.patient_id == patient_id,
            PatientAccountLinkRow.revoked_at.is_(None),
        )
        return self._one(query, for_update)

    def active_for_account(self, account_id: UUID) -> PatientAccountLink | None:
        query = self._scoped_select().where(
            PatientAccountLinkRow.account_id == account_id,
            PatientAccountLinkRow.revoked_at.is_(None),
        )
        return self._one(query, False)


class SqlAlchemyPortalInviteRepository(TenantScopedRepository[PatientPortalInviteRow]):
    model = PatientPortalInviteRow
    entity_name = "portal invite"

    def add(self, invite: PatientPortalInvite) -> None:
        self._check_owned(invite.clinic_id)
        self._session.add(
            PatientPortalInviteRow(
                id=invite.id,
                clinic_id=self.clinic_id,
                patient_id=invite.patient_id,
                token_hash=invite.token_hash,
                expires_at=invite.expires_at,
                used_at=invite.used_at,
                used_by_account_id=invite.used_by_account_id,
                superseded_at=invite.superseded_at,
                created_by=invite.created_by,
                created_at=invite.created_at,
            )
        )
        self._session.flush()

    def update(self, invite: PatientPortalInvite) -> None:
        self._check_owned(invite.clinic_id)
        row = self._require_row(invite.id)
        row.used_at = invite.used_at
        row.used_by_account_id = invite.used_by_account_id
        row.superseded_at = invite.superseded_at
        self._session.flush()

    def _one(
        self, query: Select[PatientPortalInviteRow], for_update: bool
    ) -> PatientPortalInvite | None:
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _invite(row) if row else None

    def get_by_digest(
        self, token_hash: str, *, for_update: bool = False
    ) -> PatientPortalInvite | None:
        return self._one(
            self._scoped_select().where(PatientPortalInviteRow.token_hash == token_hash),
            for_update,
        )

    def pending_for_patient(
        self, patient_id: UUID, *, for_update: bool = False
    ) -> PatientPortalInvite | None:
        query = self._scoped_select().where(
            PatientPortalInviteRow.patient_id == patient_id,
            PatientPortalInviteRow.used_at.is_(None),
            PatientPortalInviteRow.superseded_at.is_(None),
        )
        return self._one(query, for_update)


def _pref(row: MedicineReminderPrefRow) -> MedicineReminderPref:
    return MedicineReminderPref(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        account_id=row.account_id,
        prescription_id=row.prescription_id,
        item_id=row.item_id,
        slot=Slot(row.slot),
        enabled=row.enabled,
        remind_at=row.remind_at,
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
    )


class SqlAlchemyReminderPrefRepository(TenantScopedRepository[MedicineReminderPrefRow]):
    """M6b-P3 (R37-R40): one account's medicine-reminder choices in this clinic."""

    model = MedicineReminderPrefRow
    entity_name = "reminder preference"

    def for_account(
        self, account_id: UUID, prescription_ids: Sequence[UUID]
    ) -> Sequence[MedicineReminderPref]:
        if not prescription_ids:
            return []
        query = self._scoped_select().where(
            MedicineReminderPrefRow.account_id == account_id,
            MedicineReminderPrefRow.prescription_id.in_(sorted(prescription_ids)),
        )
        return [_pref(row) for row in self._session.scalars(query)]

    def get(
        self, account_id: UUID, prescription_id: UUID, item_id: UUID, slot: Slot
    ) -> MedicineReminderPref | None:
        query = self._scoped_select().where(
            MedicineReminderPrefRow.account_id == account_id,
            MedicineReminderPrefRow.prescription_id == prescription_id,
            MedicineReminderPrefRow.item_id == item_id,
            MedicineReminderPrefRow.slot == slot.value,
        )
        row = self._session.scalars(query).one_or_none()
        return _pref(row) if row else None

    def add(self, pref: MedicineReminderPref) -> None:
        self._check_owned(pref.clinic_id)
        self._session.add(
            MedicineReminderPrefRow(
                id=pref.id,
                clinic_id=self.clinic_id,
                patient_id=pref.patient_id,
                account_id=pref.account_id,
                prescription_id=pref.prescription_id,
                item_id=pref.item_id,
                slot=pref.slot.value,
                enabled=pref.enabled,
                remind_at=pref.remind_at,
                created_at=pref.created_at,
                updated_at=pref.updated_at,
            )
        )
        self._session.flush()

    def update(self, pref: MedicineReminderPref) -> None:
        self._check_owned(pref.clinic_id)
        row = self._require_row(pref.id)
        row.enabled = pref.enabled
        row.remind_at = pref.remind_at
        row.updated_at = pref.updated_at
        self._session.flush()

    def delete_for_link(self, account_id: UUID, patient_id: UUID) -> int:
        result = self._session.execute(
            delete(MedicineReminderPrefRow).where(
                MedicineReminderPrefRow.clinic_id == self.clinic_id,
                MedicineReminderPrefRow.account_id == account_id,
                MedicineReminderPrefRow.patient_id == patient_id,
            )
        )
        self._session.flush()
        return int(result.rowcount)  # type: ignore[attr-defined]


def _dose(row: DoseRecordRow) -> DoseRecord:
    return DoseRecord(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        account_id=row.account_id,
        prescription_id=row.prescription_id,
        item_id=row.item_id,
        on_date=row.on_date,
        slot=Slot(row.slot),
        state=DoseState(row.state),
        marked_at=row.marked_at.astimezone(UTC),
        keep_until=row.keep_until,
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
    )


class SqlAlchemyDoseRecordRepository(TenantScopedRepository[DoseRecordRow]):
    """M6b-P3b (R45-R52): one account's dose marks in this clinic. Patient routes only."""

    model = DoseRecordRow
    entity_name = "dose record"

    def for_account(
        self, account_id: UUID, prescription_ids: Sequence[UUID]
    ) -> Sequence[DoseRecord]:
        if not prescription_ids:
            return []
        query = (
            self._scoped_select()
            .where(
                DoseRecordRow.account_id == account_id,
                DoseRecordRow.prescription_id.in_(sorted(prescription_ids)),
            )
            .order_by(DoseRecordRow.on_date, DoseRecordRow.slot)
        )
        return [_dose(row) for row in self._session.scalars(query)]

    def get(
        self, account_id: UUID, prescription_id: UUID, item_id: UUID, on_date: date, slot: Slot
    ) -> DoseRecord | None:
        query = self._scoped_select().where(
            DoseRecordRow.account_id == account_id,
            DoseRecordRow.prescription_id == prescription_id,
            DoseRecordRow.item_id == item_id,
            DoseRecordRow.on_date == on_date,
            DoseRecordRow.slot == slot.value,
        )
        row = self._session.scalars(query.with_for_update()).one_or_none()
        return _dose(row) if row else None

    def add(self, record: DoseRecord) -> None:
        self._check_owned(record.clinic_id)
        self._session.add(
            DoseRecordRow(
                id=record.id,
                clinic_id=self.clinic_id,
                patient_id=record.patient_id,
                account_id=record.account_id,
                prescription_id=record.prescription_id,
                item_id=record.item_id,
                on_date=record.on_date,
                slot=record.slot.value,
                state=record.state.value,
                marked_at=record.marked_at,
                keep_until=record.keep_until,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )
        self._session.flush()

    def update(self, record: DoseRecord) -> None:
        self._check_owned(record.clinic_id)
        row = self._require_row(record.id)
        row.state = record.state.value
        row.marked_at = record.marked_at
        row.updated_at = record.updated_at
        self._session.flush()

    def delete(self, record: DoseRecord) -> None:
        self._check_owned(record.clinic_id)
        self._session.execute(
            delete(DoseRecordRow).where(
                DoseRecordRow.clinic_id == self.clinic_id, DoseRecordRow.id == record.id
            )
        )
        self._session.flush()


class SqlAlchemyDoseLifecycle:
    """R54, a reviewed cross-clinic exception: one account's records, for its own export or
    deletion on request. Selects by account alone; nothing else reads dose records across clinics.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def export_for_account(self, account_id: UUID) -> Sequence[DoseExport]:
        query = (
            select(DoseRecordRow)
            .where(DoseRecordRow.account_id == account_id)
            .order_by(DoseRecordRow.on_date, DoseRecordRow.slot, DoseRecordRow.id)
        )
        return [
            DoseExport(
                clinic_id=row.clinic_id,
                patient_id=row.patient_id,
                prescription_id=row.prescription_id,
                item_id=row.item_id,
                on_date=row.on_date,
                slot=row.slot,
                state=row.state,
                marked_at=row.marked_at.astimezone(UTC),
            )
            for row in self._session.scalars(query)
        ]

    def delete_for_account(self, account_id: UUID) -> int:
        result = self._session.execute(
            delete(DoseRecordRow).where(DoseRecordRow.account_id == account_id)
        )
        self._session.flush()
        return int(result.rowcount)  # type: ignore[attr-defined]


class SqlAlchemyPortalLookup:
    """The portal's reviewed cross-clinic reads (M6b-P1 decision 6A): IDs, method and dates only.

    ``ix_patient_account_links_account_id_active`` serves ``active_links``; the token digest is
    unique across clinics.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def active_links(self, account_id: UUID) -> Sequence[PatientAccountLink]:
        query = (
            select(PatientAccountLinkRow)
            .where(
                PatientAccountLinkRow.account_id == account_id,
                PatientAccountLinkRow.revoked_at.is_(None),
            )
            .order_by(PatientAccountLinkRow.created_at, PatientAccountLinkRow.id)
        )
        return [_link(row) for row in self._session.scalars(query)]

    def invite_clinic(self, token_hash: str) -> UUID | None:
        query = select(PatientPortalInviteRow.clinic_id).where(
            PatientPortalInviteRow.token_hash == token_hash
        )
        return self._session.scalars(query).one_or_none()
