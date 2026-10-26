"""Receipts: the printed bill, its patient link and the portal's bills (M6d-P4; FR-BIL-04;
spec billing R43-R54; B7, D6).

The PDF is rendered **once per state** of the bill (``receipt_state``) and stored under that
state's key, like a prescription (ADR-0012). Rendering takes the bill row lock, so two first
downloads make one file. Staff need ``BILLING_MANAGE`` (a doctor their own bills, R21); a
download is audited. The patient reaches it through a receipt link with the last-4 check (the
prescription link's rules, R48-R51) or in the patient portal for a linked record (R52, not
audited, like every portal read).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.billing.bills import BillView, bill_view, load_bill
from mediease_api.application.context import Actor, RequestContext, RequestInfo
from mediease_api.application.links.use_cases import (
    LinkInfo,
    LinkTokens,
    _patient_audit,
    _Public,
)
from mediease_api.application.portal.scope import PortalScope, ScopeEntry
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.billing.bill import Bill, BillKind, BillStatus
from mediease_api.domain.billing.receipt import (
    ReceiptNotReady,
    build_receipt,
    receipt_object_key,
    receipt_state,
)
from mediease_api.domain.links.errors import LinkInvalid
from mediease_api.domain.links.link import LinkPurpose, PatientLink
from mediease_api.domain.links.token import LinkClaims
from mediease_api.domain.prescriptions.errors import PdfFailed
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.pdf import PdfRendererPort
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
BILLS_PER_CLINIC = 50
LINK_ENTITY = "patient_link"


@dataclass(frozen=True, slots=True)
class ReceiptFile:
    bill_id: UUID
    number: str
    state: int
    data: bytes
    rendered: bool

    @property
    def filename(self) -> str:
        return f"bill-{self.number.replace('/', '-')}.pdf"


class ReceiptFiles:
    """R45, R46: the receipt of a bill's current state, rendered once, in the caller's
    transaction (which must commit)."""

    def __init__(self, *, renderer: PdfRendererPort, storage: BlobStoragePort) -> None:
        self._renderer = renderer
        self._storage = storage

    def file_for(self, uow: UnitOfWork, tenant: TenantRepositories, bill: Bill) -> ReceiptFile:
        if bill.status is BillStatus.DRAFT or bill.number is None:
            raise ReceiptNotReady()
        view = bill_view(uow, tenant, bill)
        key = self._key(view)
        data = self._storage.get(key)
        if data is not None:
            return ReceiptFile(bill.id, bill.number, self._state(view), data, False)
        # Two first downloads make one file: the second waits here, then finds it stored.
        locked = tenant.bills.get(bill.id, for_update=True)
        assert locked is not None
        view = bill_view(uow, tenant, locked)
        key = self._key(view)
        data = self._storage.get(key)
        if data is not None:
            return ReceiptFile(bill.id, bill.number, self._state(view), data, False)
        return ReceiptFile(
            bill.id, bill.number, self._state(view), self._render(uow, view, key), True
        )

    @staticmethod
    def _state(view: BillView) -> int:
        return receipt_state(view.credit_notes, view.payments)

    def _key(self, view: BillView) -> str:
        return receipt_object_key(view.bill.clinic_id, view.bill.id, self._state(view))

    def _render(self, uow: UnitOfWork, view: BillView, key: str) -> bytes:
        clinic = load_clinic(uow, view.bill.clinic_id)
        document = build_receipt(
            view.bill,
            credit_notes=view.credit_notes,
            payments=view.payments,
            patient=view.patient,
            doctor=view.doctor,
            clinic=clinic,
        )
        ids = {"bill_id": str(view.bill.id)}
        try:
            data = self._renderer.render_receipt(document)
        except Exception:
            logger.exception("receipt.pdf_failed", stage="render", **ids)
            raise PdfFailed("render") from None
        try:
            if not self._storage.put(key, data, content_type=PDF_CONTENT_TYPE):
                kept = self._storage.get(key)
                assert kept is not None
                data = kept
        except Exception:
            logger.exception("receipt.pdf_failed", stage="store", **ids)
            raise PdfFailed("store") from None
        logger.info("receipt.pdf_rendered", bytes=len(data), **ids)
        return data


class DownloadReceipt:
    """R46: the staff download, audited (``bill.receipt_downloaded``)."""

    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, files: ReceiptFiles
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._files = files

    def execute(self, ctx: RequestContext, bill_id: UUID) -> ReceiptFile:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id)
            receipt = self._files.file_for(uow, tenant, bill)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.BILL_RECEIPT_DOWNLOADED,
                actor=Actor.staff(ctx),
                now=self._clock.now(),
                clinic_id=ctx.clinic_id,
                entity_type="bill",
                entity_id=bill.id,
                metadata={"state": str(receipt.state), "rendered": str(receipt.rendered).lower()},
            )
            uow.commit()
        return receipt


class _StaffLinks:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, tokens: LinkTokens, ttl_days: int
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._tokens = tokens
        self._ttl_days = ttl_days

    def _audit(
        self, uow: UnitOfWork, ctx: RequestContext, action: AuditAction, link: PatientLink
    ) -> None:
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=action,
            actor=Actor.staff(ctx),
            now=self._clock.now(),
            clinic_id=ctx.clinic_id,
            entity_type=LINK_ENTITY,
            entity_id=link.id,
            metadata={"bill_id": str(link.resource_id)},
        )


class GetReceiptLink(_StaffLinks):
    """R48: the bill's receipt link for the QR code at the desk, made on first ask."""

    def execute(self, ctx: RequestContext, bill_id: UUID) -> LinkInfo:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id)
            if bill.status is BillStatus.DRAFT:
                raise ReceiptNotReady()
            link = tenant.patient_links.active_for_bill(bill.id)
            if link is None:
                tenant.bills.get(bill.id, for_update=True)  # one link for two first asks
                link = tenant.patient_links.active_for_bill(bill.id)
            if link is None:
                link = PatientLink.create_receipt(
                    id=self._ids.new_id(),
                    clinic_id=ctx.clinic_id,
                    patient_id=bill.patient_id,
                    bill_id=bill.id,
                    key_id=self._tokens.current_key_id,
                    ttl_days=self._ttl_days,
                    created_by=ctx.user_id,
                    now=self._clock.now(),
                )
                tenant.patient_links.add(link)
                self._audit(uow, ctx, AuditAction.RECEIPT_LINK_CREATED, link)
                uow.commit()
                logger.info("receipt_link.created", link_id=str(link.id))
        return LinkInfo(link, self._tokens.link_token(link))


class ResetReceiptLink(_StaffLinks):
    """R51: staff unlock a receipt link after five wrong answers."""

    def execute(self, ctx: RequestContext, bill_id: UUID) -> LinkInfo:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id)
            link = tenant.patient_links.active_for_bill(bill.id, for_update=True)
            if link is None:
                raise NotFound("patient link")
            link.reset(self._clock.now())
            tenant.patient_links.update(link)
            self._audit(uow, ctx, AuditAction.PATIENT_LINK_RESET, link)
            uow.commit()
        return LinkInfo(link, self._tokens.link_token(link))


@dataclass(frozen=True, slots=True)
class ReceiptSummary:
    """R49: what the receipt page shows after the challenge; no clinical content."""

    clinic_name: str
    number: str
    bill_date: date
    total_paise: int
    credited_paise: int
    paid_paise: int
    refunded_paise: int
    balance_paise: int
    cancelled: bool


class _ReceiptByLink(_Public):
    def _receipt_claims(self, token: str, info: RequestInfo) -> LinkClaims:
        # Rate limits commit in their own unit of work, so this runs before the caller's.
        claims = self._claims(token, info)
        if claims.purpose is not LinkPurpose.RECEIPT:
            raise LinkInvalid()
        return claims

    def _receipt(
        self, uow: UnitOfWork, claims: LinkClaims, token: str, view: str | None
    ) -> tuple[TenantRepositories, Bill]:
        tenant = uow.tenant(claims.cid)
        link = self._load(tenant, token, claims, for_update=False)
        link.check_unlocked()
        self._tokens.check_view(view, link, self._clock.now())
        bill = tenant.bills.get(link.resource_id)
        if bill is None or bill.kind is not BillKind.BILL:  # pragma: no cover - a foreign key
            raise LinkInvalid()
        return tenant, bill


class ViewReceipt(_ReceiptByLink):
    """``GET /public/links/{token}/receipt``: the bill's summary, after the challenge."""

    def execute(self, token: str, view: str | None, info: RequestInfo) -> ReceiptSummary:
        claims = self._receipt_claims(token, info)
        with self._uow as uow:
            _, bill = self._receipt(uow, claims, token, view)
            clinic = load_clinic(uow, bill.clinic_id)
        assert bill.number is not None and bill.bill_date is not None
        return ReceiptSummary(
            clinic.name,
            bill.number,
            bill.bill_date,
            bill.total_paise,
            bill.credited_paise,
            bill.paid_paise,
            bill.refunded_paise,
            bill.balance_paise,
            bill.status is BillStatus.CANCELLED,
        )


class ReceiptPdfByLink(_ReceiptByLink):
    """``GET /public/links/{token}/receipt.pdf``: the same file the clinic prints (R46, R50)."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        tokens: LinkTokens,
        files: ReceiptFiles,
    ) -> None:
        super().__init__(uow=uow, clock=clock, ids=ids, tokens=tokens)
        self._files = files

    def execute(self, token: str, view: str | None, info: RequestInfo) -> ReceiptFile:
        claims = self._receipt_claims(token, info)
        with self._uow as uow:
            tenant, bill = self._receipt(uow, claims, token, view)
            receipt = self._files.file_for(uow, tenant, bill)
            link = tenant.patient_links.active_for_bill(bill.id)
            if link is not None:
                _patient_audit(
                    uow,
                    self._ids,
                    info,
                    AuditAction.RECEIPT_LINK_DOWNLOADED,
                    link,
                    self._clock.now(),
                    bill_id=str(bill.id),
                    state=str(receipt.state),
                )
            uow.commit()
        return receipt


@dataclass(frozen=True, slots=True)
class PortalBill:
    """R52: an issued bill of a linked record; amounts and the number only."""

    id: UUID
    clinic_id: UUID
    clinic_name: str
    number: str
    bill_date: date
    total_paise: int
    balance_paise: int
    cancelled: bool
    issued_at: datetime


class ListPortalBills:
    """R52: every linked record's issued bills, newest first (50 per clinic)."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, principal: PatientPrincipal) -> list[PortalBill]:
        from mediease_api.ports.billing import BillQuery

        items: list[PortalBill] = []
        with self._uow as uow:
            for e in PortalScope.read(uow, principal.account_id):
                for b in e.tenant.bills.list(
                    BillQuery(patient_id=e.patient_id, limit=BILLS_PER_CLINIC * 2)
                ):
                    if b.status is BillStatus.DRAFT:
                        continue
                    assert b.number and b.bill_date and b.issued_at
                    items.append(
                        PortalBill(
                            b.id,
                            e.clinic.id,
                            e.clinic.name,
                            b.number,
                            b.bill_date,
                            b.total_paise,
                            b.balance_paise,
                            b.status is BillStatus.CANCELLED,
                            b.issued_at,
                        )
                    )
        return sorted(items, key=lambda b: b.issued_at, reverse=True)


def bill_in_scope(scope: PortalScope, bill_id: UUID) -> tuple[ScopeEntry, Bill]:
    """R52: an issued bill of a linked record; anything else (a draft too) is not found."""
    for entry in scope:
        bill = entry.tenant.bills.get(bill_id)
        if bill is not None and bill.patient_id == entry.patient_id:
            if bill.kind is BillKind.BILL and bill.status is not BillStatus.DRAFT:
                return entry, bill
            break
    logger.info("portal.not_found", entity="bill", entity_id=str(bill_id))
    raise NotFound("bill")


class PortalReceiptPdf:
    """R52: the receipt in the patient portal; the same file the clinic prints."""

    def __init__(self, *, uow: UnitOfWork, files: ReceiptFiles) -> None:
        self._uow = uow
        self._files = files

    def execute(self, principal: PatientPrincipal, bill_id: UUID) -> ReceiptFile:
        with self._uow as uow:
            entry, bill = bill_in_scope(PortalScope.read(uow, principal.account_id), bill_id)
            receipt = self._files.file_for(uow, entry.tenant, bill)
            uow.commit()
        return receipt
