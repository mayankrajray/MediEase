"""Favourites, templates and medicine suggestions (M4-P3; FR-RX-05, FR-RX-10; spec R7).

Decisions 1A-5A: each doctor has their own favourites and templates (``CLINICAL_WRITE`` and a
doctor profile; another doctor's are not found); suggestions come from the caller's favourites and
the clinic's issued prescriptions only; use is counted at issue (``use_cases.IssuePrescription``);
changes are audited with IDs only and reads not at all (no patient record is read, and the
builder asks on every keystroke). No name, medicine or instruction reaches a log or audit row.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.prescriptions.use_cases import ItemInput, build_item
from mediease_api.application.visits.use_cases import callers_doctor_id
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.prescriptions.library import (
    MAX_FAVOURITES,
    MAX_TEMPLATES,
    Favourite,
    LibraryFull,
    Template,
)
from mediease_api.domain.prescriptions.prescription import Advice
from mediease_api.domain.prescriptions.suggestions import LIMIT, Suggestion, clean_query, rank
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FavouriteInput:
    name: str
    item: ItemInput
    seen_revision: int | None = None


@dataclass(frozen=True, slots=True)
class TemplateInput:
    name: str
    items: Sequence[ItemInput]
    advice: Advice
    follow_up_days: int | None
    seen_revision: int | None = None


class _Library:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def _audit(
        self, uow: UnitOfWork, ctx: RequestContext, action: AuditAction, kind: str, id: UUID
    ) -> None:
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=action,
            actor=Actor.staff(ctx),
            now=self._clock.now(),
            clinic_id=ctx.clinic_id,
            entity_type=kind,
            entity_id=id,
        )


def _own_favourite(
    tenant: TenantRepositories, doctor_id: UUID, favourite_id: UUID, *, for_update: bool = False
) -> Favourite:
    fav = tenant.rx_favourites.get(favourite_id, for_update=for_update)
    if fav is None or fav.doctor_id != doctor_id:
        raise NotFound("favourite")
    return fav


def _own_template(
    tenant: TenantRepositories, doctor_id: UUID, template_id: UUID, *, for_update: bool = False
) -> Template:
    template = tenant.rx_templates.get(template_id, for_update=for_update)
    if template is None or template.doctor_id != doctor_id:
        raise NotFound("template")
    return template


class ListFavourites(_Library):
    def execute(self, ctx: RequestContext) -> Sequence[Favourite]:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            return tenant.rx_favourites.list_for_doctor(callers_doctor_id(tenant, ctx))


class SaveFavourite(_Library):
    """Create (no ``favourite_id``) or replace one of the caller's favourites."""

    def execute(
        self, ctx: RequestContext, body: FavouriteInput, *, favourite_id: UUID | None = None
    ) -> Favourite:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            doctor_id = callers_doctor_id(tenant, ctx)
            now = self._clock.now()
            item = build_item(body.item, id=self._ids.new_id(), position=1, at="item")
            if favourite_id is None:
                if tenant.rx_favourites.count_for_doctor(doctor_id) >= MAX_FAVOURITES:
                    raise LibraryFull(MAX_FAVOURITES)
                fav = Favourite.create(
                    id=self._ids.new_id(),
                    clinic_id=ctx.clinic_id,
                    doctor_id=doctor_id,
                    name=body.name,
                    item=item,
                    now=now,
                )
                tenant.rx_favourites.add(fav)
                action = AuditAction.RX_FAVOURITE_CREATED
            else:
                fav = _own_favourite(tenant, doctor_id, favourite_id, for_update=True)
                fav.replace(
                    name=body.name, item=item, seen_revision=body.seen_revision or 0, now=now
                )
                tenant.rx_favourites.update(fav)
                action = AuditAction.RX_FAVOURITE_UPDATED
            self._audit(uow, ctx, action, "rx_favourite", fav.id)
            uow.commit()
        logger.info(action.value, favourite_id=str(fav.id))
        return fav


class DeleteFavourite(_Library):
    def execute(self, ctx: RequestContext, *, favourite_id: UUID) -> None:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            fav = _own_favourite(tenant, callers_doctor_id(tenant, ctx), favourite_id)
            tenant.rx_favourites.delete(fav.id)
            self._audit(uow, ctx, AuditAction.RX_FAVOURITE_DELETED, "rx_favourite", fav.id)
            uow.commit()
        logger.info("rx_favourite.deleted", favourite_id=str(favourite_id))


class ListTemplates(_Library):
    def execute(self, ctx: RequestContext) -> Sequence[Template]:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            return tenant.rx_templates.list_for_doctor(callers_doctor_id(tenant, ctx))


class GetTemplate(_Library):
    def execute(self, ctx: RequestContext, *, template_id: UUID) -> Template:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            return _own_template(tenant, callers_doctor_id(tenant, ctx), template_id)


class SaveTemplate(_Library):
    """Create (no ``template_id``) or replace one of the caller's templates."""

    def execute(
        self, ctx: RequestContext, body: TemplateInput, *, template_id: UUID | None = None
    ) -> Template:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            doctor_id = callers_doctor_id(tenant, ctx)
            now = self._clock.now()
            items = [
                build_item(i, id=self._ids.new_id(), position=n)
                for n, i in enumerate(body.items, start=1)
            ]
            if template_id is None:
                if tenant.rx_templates.count_for_doctor(doctor_id) >= MAX_TEMPLATES:
                    raise LibraryFull(MAX_TEMPLATES)
                template = Template.create(
                    id=self._ids.new_id(),
                    clinic_id=ctx.clinic_id,
                    doctor_id=doctor_id,
                    name=body.name,
                    items=items,
                    advice=body.advice,
                    follow_up_days=body.follow_up_days,
                    now=now,
                )
                tenant.rx_templates.add(template)
                action = AuditAction.RX_TEMPLATE_CREATED
            else:
                template = _own_template(tenant, doctor_id, template_id, for_update=True)
                template.replace(
                    name=body.name,
                    items=items,
                    advice=body.advice,
                    follow_up_days=body.follow_up_days,
                    seen_revision=body.seen_revision or 0,
                    now=now,
                )
                tenant.rx_templates.update(template)
                action = AuditAction.RX_TEMPLATE_UPDATED
            self._audit(uow, ctx, action, "rx_template", template.id)
            uow.commit()
        logger.info(action.value, template_id=str(template.id))
        return template


class DeleteTemplate(_Library):
    def execute(self, ctx: RequestContext, *, template_id: UUID) -> None:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            template = _own_template(tenant, callers_doctor_id(tenant, ctx), template_id)
            tenant.rx_templates.delete(template.id)
            self._audit(uow, ctx, AuditAction.RX_TEMPLATE_DELETED, "rx_template", template.id)
            uow.commit()
        logger.info("rx_template.deleted", template_id=str(template_id))


class SuggestMedicines(_Library):
    """R7, AC5: the caller's favourites, then names the clinic has issued; never anything else."""

    def execute(self, ctx: RequestContext, *, query: str) -> Sequence[Suggestion]:
        prefix = clean_query(query)
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            favourites = tenant.rx_favourites.list_for_doctor(callers_doctor_id(tenant, ctx))
            history = tenant.prescriptions.medicine_history(prefix, limit=LIMIT * 2)
        return rank(prefix, favourites, history)
