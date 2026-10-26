"""Reports attached to visits (M6d-P6; ports/repositories.py), tenant-scoped (ADR-0003)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC
from uuid import UUID

from sqlalchemy import func, select

from mediease_api.adapters.db.models.visits import VisitAttachmentRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.visits.attachment import VisitAttachment


def _attachment(row: VisitAttachmentRow) -> VisitAttachment:
    return VisitAttachment(
        id=row.id,
        clinic_id=row.clinic_id,
        visit_id=row.visit_id,
        patient_id=row.patient_id,
        storage_key=row.storage_key,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        filename=row.filename,
        uploaded_by=row.uploaded_by,
        uploaded_at=row.uploaded_at.astimezone(UTC),
        shared_at=row.shared_at.astimezone(UTC) if row.shared_at else None,
        shared_by=row.shared_by,
        deleted_at=row.deleted_at.astimezone(UTC) if row.deleted_at else None,
        deleted_by=row.deleted_by,
    )


class SqlAlchemyVisitAttachmentRepository(TenantScopedRepository[VisitAttachmentRow]):
    model = VisitAttachmentRow
    entity_name = "attachment"

    def add(self, attachment: VisitAttachment) -> None:
        self._check_owned(attachment.clinic_id)
        self._session.add(
            VisitAttachmentRow(
                id=attachment.id,
                clinic_id=self.clinic_id,
                visit_id=attachment.visit_id,
                patient_id=attachment.patient_id,
                storage_key=attachment.storage_key,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                filename=attachment.filename,
                uploaded_by=attachment.uploaded_by,
                uploaded_at=attachment.uploaded_at,
            )
        )
        self._session.flush()

    def update(self, attachment: VisitAttachment) -> None:
        self._check_owned(attachment.clinic_id)
        row = self._require_row(attachment.id)
        row.shared_at = attachment.shared_at
        row.shared_by = attachment.shared_by
        row.deleted_at = attachment.deleted_at
        row.deleted_by = attachment.deleted_by
        self._session.flush()

    def get(self, attachment_id: UUID) -> VisitAttachment | None:
        row = self._get_row(attachment_id)
        return _attachment(row) if row else None

    def list_for_visit(self, visit_id: UUID) -> Sequence[VisitAttachment]:
        query = (
            self._scoped_select()
            .where(VisitAttachmentRow.visit_id == visit_id, VisitAttachmentRow.deleted_at.is_(None))
            .order_by(VisitAttachmentRow.uploaded_at, VisitAttachmentRow.id)
        )
        return [_attachment(row) for row in self._session.scalars(query)]

    def count_for_visit(self, visit_id: UUID) -> int:
        query = (
            select(func.count())
            .select_from(VisitAttachmentRow)
            .where(
                VisitAttachmentRow.clinic_id == self.clinic_id,
                VisitAttachmentRow.visit_id == visit_id,
                VisitAttachmentRow.deleted_at.is_(None),
            )
        )
        return int(self._session.scalar(query) or 0)

    def list_shared_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[VisitAttachment]:
        query = (
            self._scoped_select()
            .where(
                VisitAttachmentRow.patient_id == patient_id,
                VisitAttachmentRow.shared_at.is_not(None),
                VisitAttachmentRow.deleted_at.is_(None),
            )
            .order_by(VisitAttachmentRow.shared_at.desc(), VisitAttachmentRow.id.desc())
            .limit(limit)
        )
        return [_attachment(row) for row in self._session.scalars(query)]
