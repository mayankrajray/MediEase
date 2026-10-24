"""Prescription use cases (M4-P2; FR-RX-01..03, 06, 09; spec prescriptions R4-R6, R14, R16, R17).

Decisions 1A-6A: one chain per visit with at most one draft; version 1 is created, edited and
issued until the visit locks, an issued version is revised at any time (and its revision draft
edited and issued at any time); the draft is saved whole with its revision; the doctor and clinic
are copied at issue. Writes need ``CLINICAL_WRITE`` (route) and being the visit's doctor; reads
``CLINICAL_VIEW``.

Lock order: the visit (creating a draft), else the chain's rows oldest version first: issuing a
revision locks the version it supersedes, then the draft. Two issues or two revisions of one chain
therefore serialise, and the partial unique index on drafts is the backstop.

Audit (R16, R17): each write its own action; each read one row. Metadata holds IDs, versions,
counts and enum values, never a medicine, a dose or advice text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.links.use_cases import new_link
from mediease_api.application.notifications.service import publish
from mediease_api.application.reminders.scheduling import sync_prescription_reminder
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.application.visits.use_cases import callers_doctor_id, load_visit
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.notifications.events import PrescriptionIssued
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.errors import AlreadyExists, DraftExists, NotLatest
from mediease_api.domain.prescriptions.patient_view import PatientPage, build_preview
from mediease_api.domain.prescriptions.plan import course_start
from mediease_api.domain.prescriptions.prescription import (
    Advice,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    latest_issued,
)
from mediease_api.domain.prescriptions.schedule import DurationKind, Frequency
from mediease_api.domain.prescriptions.vocabulary import Preparation, Storage, Timing
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.domain.visits.errors import VisitLocked, VisitNotYours
from mediease_api.domain.visits.visit import Visit
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "prescription"


@dataclass(frozen=True, slots=True)
class PrescriptionView:
    """One version and the chain it belongs to (by version), for the reader."""

    prescription: Prescription
    chain: tuple[Prescription, ...] = ()
    # M6b-P3 (R24): the first day of the version this draft revises, shown as a hint.
    previous_start: date | None = None


def _previous_start(rx: Prescription, chain: Sequence[Prescription], tz: str) -> date | None:
    if rx.status is not PrescriptionStatus.DRAFT or rx.supersedes_id is None:
        return None
    older = next((p for p in chain if p.id == rx.supersedes_id), None)
    return course_start(older, tz) if older is not None and older.issued_at else None


@dataclass(frozen=True, slots=True)
class ItemInput:
    """One medicine line as sent; the domain checks it (``PrescriptionItem.create``)."""

    medicine_name: str
    form: str | None = None
    strength: str | None = None
    dose: str | None = None
    frequency: Frequency | None = None
    frequency_text: str | None = None
    timing: Timing | None = None
    duration_days: int | None = None
    duration_kind: DurationKind | None = None
    quantity: str | None = None
    preparation: tuple[Preparation, ...] = ()
    storage: tuple[Storage, ...] = ()
    warnings: str | None = None
    notes: str | None = None
    favourite_id: UUID | None = None  # M4-P3 provenance, counted at issue


def build_item(i: ItemInput, *, id: UUID, position: int, at: str | None = None) -> PrescriptionItem:
    "One validated line from what was sent (drafts, favourites and templates alike)."
    return PrescriptionItem.create(
        id=id,
        position=position,
        medicine_name=i.medicine_name,
        form=i.form,
        strength=i.strength,
        dose=i.dose,
        frequency=i.frequency,
        frequency_text=i.frequency_text,
        timing=i.timing,
        duration_days=i.duration_days,
        duration_kind=i.duration_kind,
        quantity=i.quantity,
        preparation=i.preparation,
        storage=i.storage,
        warnings=i.warnings,
        notes=i.notes,
        favourite_id=i.favourite_id,
        at=at,
    )


@dataclass(frozen=True, slots=True)
class DraftBody:
    seen_revision: int
    items: Sequence[ItemInput] = field(default_factory=tuple)
    advice: Advice = field(default_factory=Advice)
    follow_up_date: date | None = None
    template_id: UUID | None = None  # M4-P3 provenance, counted at issue
    starts_on: date | None = None  # M6b-P3: None = the issue day


def _load(
    tenant: TenantRepositories, clinic_id: UUID, rx_id: UUID, *, for_update: bool = False
) -> Prescription:
    rx = tenant.prescriptions.get(rx_id, for_update=for_update)
    if rx is None:
        logger.info(
            "tenancy.not_found",
            entity="prescription",
            entity_id=str(rx_id),
            clinic_id=str(clinic_id),
        )
        raise NotFound("prescription")
    return rx


def _check_writer(tenant: TenantRepositories, ctx: RequestContext, rx: Prescription) -> None:
    if callers_doctor_id(tenant, ctx) != rx.doctor_id:
        raise VisitNotYours()


def _check_window(visit: Visit, rx: Prescription, now: datetime) -> None:
    """Decision 2A: version 1 until the visit locks; revisions at any time."""
    if rx.version == 1 and visit.is_locked(now):
        assert visit.locked_at is not None
        raise VisitLocked(visit.locked_at)


def _record_uses(tenant: TenantRepositories, rx: Prescription, now: datetime) -> None:
    """M4-P3 decision 3A: each favourite and the template the issued body came from, once.

    Only the doctor's own count; an ID of a deleted or someone else's item is ignored.
    """
    for favourite_id in sorted({i.favourite_id for i in rx.items if i.favourite_id}):
        fav = tenant.rx_favourites.get(favourite_id, for_update=True)
        if fav is not None and fav.doctor_id == rx.doctor_id:
            fav.record_use(now)
            tenant.rx_favourites.update(fav)
    if rx.template_id is not None:
        template = tenant.rx_templates.get(rx.template_id, for_update=True)
        if template is not None and template.doctor_id == rx.doctor_id:
            template.record_use(now)
            tenant.rx_templates.update(template)


class _UseCase:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def _audit(
        self,
        uow: UnitOfWork,
        ctx: RequestContext,
        action: AuditAction,
        rx: Prescription,
        **metadata: str,
    ) -> None:
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=action,
            actor=Actor.staff(ctx),
            now=self._clock.now(),
            clinic_id=ctx.clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=rx.id,
            metadata={"visit_id": str(rx.visit_id), "version": str(rx.version), **metadata},
        )


class CreateDraft(_UseCase):
    """Decision 1A: version 1 of the visit's chain; a second one is ``RX_ALREADY_EXISTS``."""

    def execute(self, ctx: RequestContext, *, visit_id: UUID) -> PrescriptionView:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            visit = load_visit(tenant, ctx.clinic_id, visit_id, for_update=True)
            visit.check_writer(callers_doctor_id(tenant, ctx))
            now = self._clock.now()
            existing = tenant.prescriptions.list_for_visit(visit.id)
            if existing:
                raise AlreadyExists(existing[-1].id)
            rx = Prescription.first_draft(
                visit, id=self._ids.new_id(), created_by=ctx.user_id, now=now
            )
            _check_window(visit, rx, now)
            tenant.prescriptions.add(rx)
            self._audit(uow, ctx, AuditAction.PRESCRIPTION_CREATED, rx)
            uow.commit()
        logger.info("prescription.created", prescription_id=str(rx.id), visit_id=str(visit_id))
        return PrescriptionView(rx, (rx,))


class ReplaceDraft(_UseCase):
    """Decision 3A: the whole draft, from the revision it was loaded at (``RX_STALE``)."""

    def execute(self, ctx: RequestContext, *, rx_id: UUID, body: DraftBody) -> PrescriptionView:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            rx = _load(tenant, ctx.clinic_id, rx_id, for_update=True)
            _check_writer(tenant, ctx, rx)
            rx.check_draft()
            now = self._clock.now()
            _check_window(load_visit(tenant, ctx.clinic_id, rx.visit_id), rx, now)
            items = [
                build_item(i, id=self._ids.new_id(), position=position)
                for position, i in enumerate(body.items, start=1)
            ]
            rx.replace_body(
                items=items,
                advice=body.advice,
                follow_up_date=body.follow_up_date,
                seen_revision=body.seen_revision,
                today=local_date(now, clinic.timezone),
                now=now,
                template_id=body.template_id,
                starts_on=body.starts_on,
            )
            tenant.prescriptions.update(rx)
            tenant.prescriptions.replace_items(rx)
            chain = tenant.prescriptions.list_for_visit(rx.visit_id)
            self._audit(
                uow,
                ctx,
                AuditAction.PRESCRIPTION_UPDATED,
                rx,
                revision=str(rx.revision),
                items=str(len(rx.items)),
            )
            uow.commit()
        logger.info("prescription.updated", prescription_id=str(rx_id), items=len(rx.items))
        return PrescriptionView(rx, (), _previous_start(rx, chain, clinic.timezone))


class DiscardDraft(_UseCase):
    """A draft that was never issued is removed; anything else is ``RX_NOT_DRAFT``."""

    def execute(self, ctx: RequestContext, *, rx_id: UUID) -> None:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            rx = _load(tenant, ctx.clinic_id, rx_id, for_update=True)
            _check_writer(tenant, ctx, rx)
            rx.check_draft()
            tenant.prescriptions.delete(rx.id)
            self._audit(uow, ctx, AuditAction.PRESCRIPTION_DISCARDED, rx)
            uow.commit()
        logger.info("prescription.discarded", prescription_id=str(rx_id))


class IssuePrescription(_UseCase):
    """R4, R5, R14, R20: freeze the draft; a revision supersedes the version before it.

    Issuing version 1 also creates the chain's patient link (M4-P5 decision 1A); revisions
    reuse it, so a link already shown or sent always opens the latest version.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        link_key_id: str,
        link_ttl_days: int,
    ) -> None:
        super().__init__(uow=uow, clock=clock, ids=ids)
        self._link_key_id = link_key_id
        self._link_ttl_days = link_ttl_days

    def execute(self, ctx: RequestContext, *, rx_id: UUID, seen_revision: int) -> PrescriptionView:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            seen = _load(tenant, ctx.clinic_id, rx_id)
            older = (
                _load(tenant, ctx.clinic_id, seen.supersedes_id, for_update=True)
                if seen.supersedes_id
                else None
            )
            rx = _load(tenant, ctx.clinic_id, rx_id, for_update=True)
            _check_writer(tenant, ctx, rx)
            rx.check_draft()
            now = self._clock.now()
            _check_window(load_visit(tenant, ctx.clinic_id, rx.visit_id), rx, now)
            doctor = tenant.doctors.get(rx.doctor_id)
            patient = tenant.patients.get(rx.patient_id)
            assert doctor is not None and patient is not None  # foreign keys keep them
            rx.issue(
                doctor=doctor,
                clinic=clinic,
                language=patient.language,
                may_message=patient.may_receive_whatsapp or patient.may_receive_sms,
                seen_revision=seen_revision,
                today=local_date(now, clinic.timezone),
                now=now,
            )
            tenant.prescriptions.update(rx)
            if older is not None:
                older.supersede(now)
                tenant.prescriptions.update(older)
            _record_uses(tenant, rx, now)
            assert rx.language is not None and rx.link_delivery is not None
            metadata = {
                "items": str(len(rx.items)),
                "language": rx.language.value,
                "link_delivery": rx.link_delivery.value,
            }
            if rx.version == 1 and tenant.patient_links.active_for_prescription(rx.id) is None:
                link = new_link(
                    tenant,
                    rx,
                    ids=self._ids,
                    key_id=self._link_key_id,
                    ttl_days=self._link_ttl_days,
                    created_by=ctx.user_id,
                    now=now,
                )
                metadata["link_id"] = str(link.id)
            if older is not None:
                metadata["supersedes_id"] = str(older.id)
            self._audit(uow, ctx, AuditAction.PRESCRIPTION_ISSUED, rx, **metadata)
            # M5-P2 (R14, R15): the worker sends a pending link; the job commits with the issue.
            # From M6a-P7 through the notification service (ADR-0017), the same job and key.
            publish(
                uow,
                PrescriptionIssued(rx.id),
                clinic_id=ctx.clinic_id,
                ids=self._ids,
                now=now,
                request_id=ctx.request_id,
                actor_user_id=ctx.user_id,
            )
            chain = tuple(tenant.prescriptions.list_for_visit(rx.visit_id))
            # M5-P4 (R1, R2): the chain's follow-up reminder follows this version's date.
            sync_prescription_reminder(
                uow,
                tenant,
                ids=self._ids,
                rx=rx,
                chain_id=next(v.id for v in chain if v.version == 1),
                timezone=clinic.timezone,
                user_id=ctx.user_id,
                request_id=ctx.request_id,
                now=now,
            )
            uow.commit()
        logger.info(
            "prescription.issued",
            prescription_id=str(rx_id),
            version=rx.version,
            link_delivery=rx.link_delivery.value,
        )
        return PrescriptionView(rx, chain)


class RevisePrescription(_UseCase):
    """R6, FR-RX-09: a new draft from the latest issued version, at any time (decision 2A)."""

    def execute(self, ctx: RequestContext, *, rx_id: UUID) -> PrescriptionView:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            issued = _load(tenant, ctx.clinic_id, rx_id, for_update=True)
            _check_writer(tenant, ctx, issued)
            chain = tenant.prescriptions.list_for_visit(issued.visit_id)
            draft = next((p for p in chain if p.status is PrescriptionStatus.DRAFT), None)
            if draft is not None:
                raise DraftExists(draft.id)
            latest = latest_issued(chain)
            assert latest is not None  # a chain without a draft has an issued version
            if latest.id != issued.id:
                raise NotLatest(latest.id)
            now = self._clock.now()
            rx = Prescription.revision_of(
                issued,
                id=self._ids.new_id(),
                new_item_id=self._ids.new_id,
                created_by=ctx.user_id,
                now=now,
            )
            tenant.prescriptions.add(rx)
            self._audit(uow, ctx, AuditAction.PRESCRIPTION_REVISED, rx, from_id=str(issued.id))
            uow.commit()
        logger.info("prescription.revised", prescription_id=str(rx.id), version=rx.version)
        return PrescriptionView(rx, (*chain, rx), _previous_start(rx, chain, clinic.timezone))


class GetPrescription(_UseCase):
    """One version with its chain; one ``prescription.viewed`` row (R16)."""

    def execute(self, ctx: RequestContext, *, rx_id: UUID) -> PrescriptionView:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            rx = _load(tenant, ctx.clinic_id, rx_id)
            chain = tuple(tenant.prescriptions.list_for_visit(rx.visit_id))
            self._audit(uow, ctx, AuditAction.PRESCRIPTION_VIEWED, rx)
            uow.commit()
        return PrescriptionView(rx, chain, _previous_start(rx, chain, clinic.timezone))


class PreviewPrescription(_UseCase):
    """M4-P6 decision 3A: a draft as the patient's page would show it if issued now.

    The same builder as the patient page, with the doctor and clinic as they are today (what
    issuing copies) and the patient's language unless one is asked for. Read only and part of
    the consultation the doctor already opened (one ``visit.viewed``), so it writes no audit row.
    """

    def execute(
        self, ctx: RequestContext, *, rx_id: UUID, language: Language | None = None
    ) -> PatientPage:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            rx = _load(tenant, ctx.clinic_id, rx_id)
            doctor = tenant.doctors.get(rx.doctor_id)
            patient = tenant.patients.get(rx.patient_id)
            assert doctor is not None and patient is not None  # foreign keys keep them
        return build_preview(
            rx,
            doctor=doctor,
            clinic=clinic,
            language=language or patient.language,
            today=local_date(self._clock.now(), clinic.timezone),
        )
