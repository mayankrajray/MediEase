"""Prescription uploads and the reviewed prescription lookup (M7b, ``ports/uploads.py``).

``SqlAlchemyPrescriptionUploadRepository`` is account-owned platform data, never a clinic's: the
portal's methods filter by the account, the worker's by the upload ID it was given.
``SqlAlchemyPrescriptionLookup`` is a reviewed cross-clinic exception (ADR-0003, ADR-0023): it
returns a prescription's clinic ID and nothing else, for the last-4 check only.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.prescriptions import PrescriptionRow
from mediease_api.adapters.db.models.uploads import PrescriptionUploadRow
from mediease_api.domain.uploads.upload import (
    FILE_STATES,
    TERMINAL,
    Access,
    PrescriptionUpload,
    Rejection,
    UploadSource,
    UploadState,
)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def _upload(row: PrescriptionUploadRow) -> PrescriptionUpload:
    return PrescriptionUpload(
        id=row.id,
        account_id=row.account_id,
        source=UploadSource(row.source),
        state=UploadState(row.state),
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        quarantine_key=row.quarantine_key,
        candidate_id=row.candidate_id,
        clinic_id=row.clinic_id,
        prescription_id=row.prescription_id,
        access=Access(row.access) if row.access else None,
        selected_id=row.selected_id,
        rejection_code=Rejection(row.rejection_code) if row.rejection_code else None,
        failed_challenges=row.failed_challenges,
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
        verified_at=_utc(row.verified_at),
        expires_at=_utc(row.expires_at),
        finished_at=_utc(row.finished_at),
    )


def _copy(upload: PrescriptionUpload, row: PrescriptionUploadRow) -> None:
    row.state = upload.state.value
    row.quarantine_key = upload.quarantine_key
    row.candidate_id = upload.candidate_id
    row.clinic_id = upload.clinic_id
    row.prescription_id = upload.prescription_id
    row.access = upload.access.value if upload.access else None
    row.selected_id = upload.selected_id
    row.rejection_code = upload.rejection_code.value if upload.rejection_code else None
    row.failed_challenges = upload.failed_challenges
    row.updated_at = upload.updated_at
    row.verified_at = upload.verified_at
    row.expires_at = upload.expires_at
    row.finished_at = upload.finished_at


class SqlAlchemyPrescriptionUploadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, upload: PrescriptionUpload) -> None:
        row = PrescriptionUploadRow(
            id=upload.id,
            account_id=upload.account_id,
            source=upload.source.value,
            content_type=upload.content_type,
            size_bytes=upload.size_bytes,
            sha256=upload.sha256,
            created_at=upload.created_at,
        )
        _copy(upload, row)
        self._session.add(row)
        self._session.flush()

    def update(self, upload: PrescriptionUpload) -> None:
        row = self._session.scalars(
            select(PrescriptionUploadRow).where(PrescriptionUploadRow.id == upload.id)
        ).one()
        _copy(upload, row)
        self._session.flush()

    def _one(
        self, query: Select[PrescriptionUploadRow], for_update: bool
    ) -> PrescriptionUpload | None:
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _upload(row) if row else None

    def get(self, upload_id: UUID, *, for_update: bool = False) -> PrescriptionUpload | None:
        return self._one(
            select(PrescriptionUploadRow).where(PrescriptionUploadRow.id == upload_id), for_update
        )

    def get_for_account(
        self, upload_id: UUID, account_id: UUID, *, for_update: bool = False
    ) -> PrescriptionUpload | None:
        query = select(PrescriptionUploadRow).where(
            PrescriptionUploadRow.id == upload_id, PrescriptionUploadRow.account_id == account_id
        )
        return self._one(query, for_update)

    def count_in_flight(self, account_id: UUID) -> int:
        query = select(func.count()).where(
            PrescriptionUploadRow.account_id == account_id,
            PrescriptionUploadRow.state.in_([s.value for s in FILE_STATES]),
        )
        return int(self._session.scalar(query) or 0)

    def unfinished_before(self, before: datetime, *, limit: int) -> Sequence[PrescriptionUpload]:
        query = (
            select(PrescriptionUploadRow)
            .where(
                PrescriptionUploadRow.state.not_in([s.value for s in TERMINAL]),
                PrescriptionUploadRow.updated_at < before,
            )
            .order_by(PrescriptionUploadRow.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [_upload(row) for row in self._session.scalars(query)]

    def delete_created_before(self, before: datetime) -> Sequence[str]:
        result = self._session.execute(
            delete(PrescriptionUploadRow)
            .where(PrescriptionUploadRow.created_at < before)
            .returning(PrescriptionUploadRow.quarantine_key)
        )
        keys = [key for (key,) in result if key]
        self._session.flush()
        return keys


class SqlAlchemyPrescriptionLookup:
    """Reviewed cross-clinic read (prescription-uploads R11): a prescription's clinic, by ID."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def clinic_of(self, prescription_id: UUID) -> UUID | None:
        query = select(PrescriptionRow.clinic_id).where(
            PrescriptionRow.id == prescription_id, PrescriptionRow.status != "DRAFT"
        )
        return self._session.scalars(query).one_or_none()
