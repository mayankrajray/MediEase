"""Reports attached to visits (M6d-P6; FR-VIS-04; spec visit-attachments; decisions B8, D7).

- **Attach** (``ATTACHMENTS_ADD``, every role: the front desk scans at the counter, D7): a PDF,
  JPEG or PNG of at most 10 MB, recognised by its first bytes, at most 20 per visit. The file is
  written to blob storage first and removed again if the row cannot be committed.
- **List** and **open** (``CLINICAL_VIEW``): opening is audited every time.
- **Delete** (``ATTACHMENTS_ADD``): by its uploader, within 24 hours; the row stays with the time
  and author, the file is removed.
- **Share** (``CLINICAL_WRITE``, the visit's doctor): shown in the patient's portal, or no more.
- **Portal**: a linked record's shared reports, listed and opened. Not audited, like every
  portal read (patient-portal decision 7A).

Logs and audit rows carry IDs, the type and the size only, never the file name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.portal.scope import PortalScope, ScopeEntry
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.application.visits.use_cases import ENTITY_TYPE, callers_doctor_id, load_visit
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.visits.attachment import (
    MAX_PER_VISIT,
    AttachmentLimitReached,
    AttachmentUploadFailed,
    VisitAttachment,
)
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

PORTAL_PER_CLINIC = 50


@dataclass(frozen=True, slots=True)
class AttachmentItem:
    """One report as staff see it; ``can_delete`` is for the caller (R8)."""

    attachment: VisitAttachment
    can_delete: bool


@dataclass(frozen=True, slots=True)
class AttachmentFile:
    data: bytes
    content_type: str
    filename: str


@dataclass(frozen=True, slots=True)
class PortalAttachment:
    """R11: a shared report of a linked record, with the clinic and the visit's day."""

    attachment: VisitAttachment
    clinic_id: UUID
    clinic_name: str
    visit_started_at: datetime


def _item(attachment: VisitAttachment, ctx: RequestContext, now: datetime) -> AttachmentItem:
    return AttachmentItem(attachment, attachment.can_delete(ctx.user_id, now))


def _load(tenant: TenantRepositories, visit_id: UUID, attachment_id: UUID) -> VisitAttachment:
    """A report of this visit that is not deleted; anything else is not found."""
    attachment = tenant.visit_attachments.get(attachment_id)
    if attachment is None or attachment.visit_id != visit_id or attachment.is_deleted:
        logger.info("tenancy.not_found", entity="attachment", entity_id=str(attachment_id))
        raise NotFound("attachment")
    return attachment


class _Attachments:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, storage: BlobStoragePort
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._storage = storage

    def _audit(
        self,
        uow: UnitOfWork,
        ctx: RequestContext,
        action: AuditAction,
        attachment: VisitAttachment,
        now: datetime,
        **extra: str,
    ) -> None:
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=action,
            actor=Actor.staff(ctx),
            now=now,
            clinic_id=ctx.clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=attachment.visit_id,
            metadata={"attachment_id": str(attachment.id), **extra},
        )


class AddAttachment(_Attachments):
    """R1-R4: attach a report to a visit (any status, the locked ones too: reports come later)."""

    def execute(
        self, ctx: RequestContext, *, visit_id: UUID, data: bytes | None, filename: str | None
    ) -> AttachmentItem:
        stored: str | None = None
        try:
            with self._uow as uow:
                tenant = uow.tenant(ctx.clinic_id)
                # The visit row lock makes the count and the insert one step (R3).
                visit = load_visit(tenant, ctx.clinic_id, visit_id, for_update=True)
                now = self._clock.now()
                attachment = VisitAttachment.upload(
                    id=self._ids.new_id(),
                    clinic_id=ctx.clinic_id,
                    visit_id=visit.id,
                    patient_id=visit.patient_id,
                    data=data,
                    filename=filename,
                    by=ctx.user_id,
                    now=now,
                )
                if tenant.visit_attachments.count_for_visit(visit.id) >= MAX_PER_VISIT:
                    raise AttachmentLimitReached()
                assert data is not None  # upload() refuses an empty file
                self._put(attachment, data)
                stored = attachment.storage_key
                tenant.visit_attachments.add(attachment)
                self._audit(
                    uow,
                    ctx,
                    AuditAction.VISIT_ATTACHMENT_ADDED,
                    attachment,
                    now,
                    content_type=attachment.content_type,
                    size_bytes=str(attachment.size_bytes),
                )
                uow.commit()
                stored = None
        finally:
            if stored is not None:
                # R4: the row was not committed, so the file must not stay either.
                self._remove(stored)

        logger.info(
            "visit.attachment_added",
            visit_id=str(visit_id),
            attachment_id=str(attachment.id),
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
        )
        return _item(attachment, ctx, now)

    def _put(self, attachment: VisitAttachment, data: bytes) -> None:
        try:
            self._storage.put(attachment.storage_key, data, content_type=attachment.content_type)
        except Exception:
            logger.warning("visit.attachment_upload_failed", attachment_id=str(attachment.id))
            raise AttachmentUploadFailed() from None

    def _remove(self, key: str) -> None:
        try:
            self._storage.delete(key)
        except Exception:
            logger.warning("visit.attachment_cleanup_failed", exc_info=True)


class ListAttachments(_Attachments):
    """R6: the visit's reports, oldest first (metadata only; the consultation read is audited)."""

    def execute(self, ctx: RequestContext, *, visit_id: UUID) -> list[AttachmentItem]:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            visit = load_visit(tenant, ctx.clinic_id, visit_id)
            attachments = tenant.visit_attachments.list_for_visit(visit.id)
        now = self._clock.now()
        return [_item(a, ctx, now) for a in attachments]


class OpenAttachment(_Attachments):
    """R7: the file itself, audited on every open."""

    def execute(
        self, ctx: RequestContext, *, visit_id: UUID, attachment_id: UUID
    ) -> AttachmentFile:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            visit = load_visit(tenant, ctx.clinic_id, visit_id)
            attachment = _load(tenant, visit.id, attachment_id)
            data = self._storage.get(attachment.storage_key)
            if data is None:
                logger.error("visit.attachment_missing", attachment_id=str(attachment.id))
                raise NotFound("attachment")
            self._audit(
                uow, ctx, AuditAction.VISIT_ATTACHMENT_OPENED, attachment, self._clock.now()
            )
            uow.commit()
        return AttachmentFile(data, attachment.content_type, attachment.filename)


class DeleteAttachment(_Attachments):
    """R8: by its uploader within 24 hours; the row stays, the file goes."""

    def execute(self, ctx: RequestContext, *, visit_id: UUID, attachment_id: UUID) -> None:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            visit = load_visit(tenant, ctx.clinic_id, visit_id, for_update=True)
            attachment = _load(tenant, visit.id, attachment_id)
            now = self._clock.now()
            deleted = attachment.delete(by=ctx.user_id, now=now)
            tenant.visit_attachments.update(deleted)
            self._audit(uow, ctx, AuditAction.VISIT_ATTACHMENT_DELETED, deleted, now)
            uow.commit()
        try:
            self._storage.delete(attachment.storage_key)
        except Exception:
            # The row says deleted, so the file is never served; ops can remove it later.
            logger.warning("visit.attachment_file_kept", attachment_id=str(attachment.id))
        logger.info("visit.attachment_deleted", attachment_id=str(attachment.id))


class ShareAttachment(_Attachments):
    """R10: the visit's doctor shows a report in the patient's portal, or stops showing it."""

    def execute(
        self, ctx: RequestContext, *, visit_id: UUID, attachment_id: UUID, shared: bool
    ) -> AttachmentItem:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            visit = load_visit(tenant, ctx.clinic_id, visit_id, for_update=True)
            visit.check_writer(callers_doctor_id(tenant, ctx))
            attachment = _load(tenant, visit.id, attachment_id)
            now = self._clock.now()
            changed = attachment.share(shared, by=ctx.user_id, now=now)
            if changed != attachment:
                tenant.visit_attachments.update(changed)
                action = (
                    AuditAction.VISIT_ATTACHMENT_SHARED
                    if shared
                    else AuditAction.VISIT_ATTACHMENT_UNSHARED
                )
                self._audit(uow, ctx, action, changed, now)
                uow.commit()
        return _item(changed, ctx, now)


class ListPortalAttachments:
    """R11: every linked record's shared reports, newest share first (50 per clinic)."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, principal: PatientPrincipal) -> list[PortalAttachment]:
        items: list[PortalAttachment] = []
        with self._uow as uow:
            for e in PortalScope.read(uow, principal.account_id):
                started: dict[UUID, datetime] = {}
                for a in e.tenant.visit_attachments.list_shared_for_patient(
                    e.patient_id, limit=PORTAL_PER_CLINIC
                ):
                    if a.visit_id not in started:
                        visit = e.tenant.visits.get(a.visit_id)
                        assert visit is not None  # the foreign key keeps it
                        started[a.visit_id] = visit.started_at
                    items.append(
                        PortalAttachment(a, e.clinic.id, e.clinic.name, started[a.visit_id])
                    )
        return sorted(
            items, key=lambda p: p.attachment.shared_at or p.visit_started_at, reverse=True
        )


def shared_in_scope(scope: PortalScope, attachment_id: UUID) -> tuple[ScopeEntry, VisitAttachment]:
    """R12: a shared report of a linked record; anything else is not found."""
    for entry in scope:
        attachment = entry.tenant.visit_attachments.get(attachment_id)
        if attachment is not None and attachment.patient_id == entry.patient_id:
            if attachment.is_shared and not attachment.is_deleted:
                return entry, attachment
            break
    logger.info("portal.not_found", entity="attachment", entity_id=str(attachment_id))
    raise NotFound("attachment")


class PortalAttachmentFile:
    """R12: the shared file in the patient's portal."""

    def __init__(self, *, uow: UnitOfWork, storage: BlobStoragePort) -> None:
        self._uow = uow
        self._storage = storage

    def execute(self, principal: PatientPrincipal, attachment_id: UUID) -> AttachmentFile:
        with self._uow as uow:
            _, attachment = shared_in_scope(
                PortalScope.read(uow, principal.account_id), attachment_id
            )
        data = self._storage.get(attachment.storage_key)
        if data is None:
            logger.error("visit.attachment_missing", attachment_id=str(attachment.id))
            raise NotFound("attachment")
        return AttachmentFile(data, attachment.content_type, attachment.filename)
