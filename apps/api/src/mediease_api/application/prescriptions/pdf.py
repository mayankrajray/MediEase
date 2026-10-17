"""Printing prescriptions: the PDF and what front desk may print (M4-P4).

FR-RX-04, 06; spec prescriptions R8, R16, R18, D6; ADR-0012; decisions 1A-3A.

**Render once (R18, AC8).** A version's PDF is rendered on its first download and stored under
``rx/{clinic_id}/{prescription_id}/v{version}.pdf``; its key is recorded on the row (once, which
the P2 trigger allows). The first download locks the row, so concurrent first downloads wait for
it and then find the key: one render, the same bytes for everyone. Waiting longer than
``wait_seconds`` is ``RX_PDF_BUSY``. A render or storage failure is ``RX_PDF_FAILED``; nothing is
recorded and the next download tries again.

**Who prints what (D6, 1A).** ``RX_PRINT`` (every role) prints the latest issued version; an older
(superseded) one needs ``CLINICAL_VIEW`` as well, otherwise ``RX_NOT_LATEST`` names the current
one. A draft is never printed (``RX_NOT_ISSUED``). ``ListPrintable`` gives front desk the
patient's current versions without any clinical content (2A).

**Audit (R16).** One ``prescription.pdf_downloaded`` per download: visit, version, the caller's
role and whether it rendered. Logs carry IDs and the failing stage, never content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.prescriptions.document import build_document, pdf_object_key
from mediease_api.domain.prescriptions.errors import NotIssued, NotLatest, PdfFailed
from mediease_api.domain.prescriptions.prescription import (
    Prescription,
    PrescriptionStatus,
    latest_issued,
)
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.pdf import PdfRendererPort
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
LOCK_WAIT_SECONDS = 10
PRINTABLE_LIMIT = 20


@dataclass(frozen=True, slots=True)
class PdfDownload:
    prescription_id: UUID
    version: int
    data: bytes
    rendered: bool

    @property
    def filename(self) -> str:
        return f"prescription-{self.prescription_id}-v{self.version}.pdf"


@dataclass(frozen=True, slots=True)
class Printable:
    """A patient's current version, without content (decision 2A)."""

    prescription_id: UUID
    visit_id: UUID
    version: int
    issued_at: datetime
    doctor_display_name: str


def _load(tenant: TenantRepositories, clinic_id: UUID, rx_id: UUID) -> Prescription:
    rx = tenant.prescriptions.get(rx_id)
    if rx is None:
        logger.info(
            "tenancy.not_found",
            entity="prescription",
            entity_id=str(rx_id),
            clinic_id=str(clinic_id),
        )
        raise NotFound("prescription")
    return rx


def _check_printable(tenant: TenantRepositories, ctx: RequestContext, rx: Prescription) -> None:
    if rx.status is PrescriptionStatus.DRAFT:
        raise NotIssued(rx.status.value)
    if rx.status is PrescriptionStatus.SUPERSEDED and not ctx.allows(Permission.CLINICAL_VIEW):
        latest = latest_issued(tenant.prescriptions.list_for_visit(rx.visit_id))
        assert latest is not None  # a superseded version has an issued successor
        raise NotLatest(latest.id)


class DownloadPrescriptionPdf:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        renderer: PdfRendererPort,
        storage: BlobStoragePort,
        wait_seconds: int = LOCK_WAIT_SECONDS,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._renderer = renderer
        self._storage = storage
        self._wait_seconds = wait_seconds

    def execute(self, ctx: RequestContext, *, rx_id: UUID) -> PdfDownload:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            rx = _load(tenant, ctx.clinic_id, rx_id)
            _check_printable(tenant, ctx, rx)
            data = self._stored(rx)
            rendered = False
            if data is None:
                locked = tenant.prescriptions.lock_for_render(
                    rx_id, wait_seconds=self._wait_seconds
                )
                assert locked is not None  # it was there a moment ago and issued rows stay
                rx = locked
                data = self._stored(rx)
                if data is None:
                    data = self._render(uow, tenant, ctx, rx)
                    rendered = True
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.PRESCRIPTION_PDF_DOWNLOADED,
                actor=Actor.staff(ctx),
                now=self._clock.now(),
                clinic_id=ctx.clinic_id,
                entity_type="prescription",
                entity_id=rx.id,
                metadata={
                    "visit_id": str(rx.visit_id),
                    "version": str(rx.version),
                    "role": ctx.role.value,
                    "rendered": str(rendered).lower(),
                },
            )
            uow.commit()
        return PdfDownload(rx.id, rx.version, data, rendered)

    def _stored(self, rx: Prescription) -> bytes | None:
        if rx.pdf_object_key is None:
            return None
        data = self._storage.get(rx.pdf_object_key)
        if data is None:  # recorded but missing: render again under the lock, same key
            logger.error("rx.pdf_missing", prescription_id=str(rx.id), version=rx.version)
        return data

    def _render(
        self, uow: UnitOfWork, tenant: TenantRepositories, ctx: RequestContext, rx: Prescription
    ) -> bytes:
        clinic = load_clinic(uow, ctx.clinic_id)
        patient = tenant.patients.get(rx.patient_id)
        assert patient is not None  # the foreign key keeps it
        document = build_document(
            rx, patient, paper_size=clinic.rx_paper_size, timezone=clinic.timezone
        )
        ids = {"prescription_id": str(rx.id), "version": rx.version}
        try:
            data = self._renderer.render(document)
        except Exception:
            logger.exception("rx.pdf_failed", stage="render", **ids)
            raise PdfFailed("render") from None
        key = pdf_object_key(rx.clinic_id, rx.id, rx.version)
        try:
            if not self._storage.put(key, data, content_type=PDF_CONTENT_TYPE):
                # Stored by an earlier attempt whose transaction did not commit: keep that file.
                kept = self._storage.get(key)
                assert kept is not None
                data = kept
        except Exception:
            logger.exception("rx.pdf_failed", stage="store", **ids)
            raise PdfFailed("store") from None
        if rx.pdf_object_key is None:
            rx.attach_pdf(key)
            tenant.prescriptions.update(rx)
        logger.info(
            "rx.pdf_rendered", paper_size=clinic.rx_paper_size.value, bytes=len(data), **ids
        )
        return data


class ListPrintable:
    """Decision 2A: what front desk may print for a patient, newest first, no content."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext, *, patient_id: UUID) -> list[Printable]:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            if tenant.patients.get(patient_id) is None:
                logger.info(
                    "tenancy.not_found",
                    entity="patient",
                    entity_id=str(patient_id),
                    clinic_id=str(ctx.clinic_id),
                )
                raise NotFound("patient")
            versions = tenant.prescriptions.list_issued_for_patient(
                patient_id, limit=PRINTABLE_LIMIT
            )
        printable = []
        for rx in versions:
            assert rx.issued_at is not None and rx.doctor_snapshot is not None
            printable.append(
                Printable(
                    prescription_id=rx.id,
                    visit_id=rx.visit_id,
                    version=rx.version,
                    issued_at=rx.issued_at,
                    doctor_display_name=rx.doctor_snapshot.display_name,
                )
            )
        return printable
