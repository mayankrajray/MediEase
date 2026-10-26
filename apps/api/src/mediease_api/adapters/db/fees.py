"""The fee schedule's repository (M6d-P1; ports/billing.py), tenant-scoped (ADR-0003)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.billing import ClinicServiceRow, DoctorServicePriceRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.billing.fees import (
    ClinicService,
    DoctorPrice,
    ServiceKind,
    ServiceNameTaken,
)

_NAME_INDEX = "uq_clinic_services_clinic_id_name"


def _service(row: ClinicServiceRow) -> ClinicService:
    return ClinicService(
        id=row.id,
        clinic_id=row.clinic_id,
        name=row.name,
        kind=ServiceKind(row.kind),
        default_price_paise=row.default_price_paise,
        active=row.active,
        position=row.position,
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
    )


def _write(row: ClinicServiceRow, service: ClinicService) -> None:
    row.name = service.name
    row.kind = service.kind.value
    row.default_price_paise = service.default_price_paise
    row.active = service.active
    row.position = service.position
    row.updated_at = service.updated_at


class SqlAlchemyDoctorPriceRepository(TenantScopedRepository[DoctorServicePriceRow]):
    """`doctor_service_prices` of one clinic; reached through `SqlAlchemyFeeRepository`."""

    model = DoctorServicePriceRow
    entity_name = "doctor price"

    def list(self) -> Sequence[DoctorPrice]:
        query = self._scoped_select().order_by(
            DoctorServicePriceRow.service_id, DoctorServicePriceRow.doctor_id
        )
        return [
            DoctorPrice(row.service_id, row.doctor_id, row.price_paise)
            for row in self._session.scalars(query)
        ]


class SqlAlchemyFeeRepository(TenantScopedRepository[ClinicServiceRow]):
    model = ClinicServiceRow
    entity_name = "service"

    def __init__(self, session: Session, clinic_id: UUID) -> None:
        super().__init__(session, clinic_id)
        self._prices = SqlAlchemyDoctorPriceRepository(session, clinic_id)

    def list_services(self) -> Sequence[ClinicService]:
        query = self._scoped_select().order_by(
            ClinicServiceRow.position, func.lower(ClinicServiceRow.name), ClinicServiceRow.id
        )
        return [_service(row) for row in self._session.scalars(query)]

    def get_service(self, service_id: UUID, *, for_update: bool = False) -> ClinicService | None:
        query = self._scoped_select().where(ClinicServiceRow.id == service_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _service(row) if row else None

    def add_service(self, service: ClinicService) -> None:
        self._check_owned(service.clinic_id)
        row = ClinicServiceRow(
            id=service.id, clinic_id=self.clinic_id, created_at=service.created_at
        )
        _write(row, service)
        self._session.add(row)
        self._flush()

    def update_service(self, service: ClinicService) -> None:
        self._check_owned(service.clinic_id)
        _write(self._require_row(service.id), service)
        self._flush()

    def _flush(self) -> None:
        # R3: the partial unique index decides between two writers with the same name.
        try:
            with self._session.begin_nested():
                self._session.flush()
        except IntegrityError as error:
            if _NAME_INDEX in str(error.orig):
                raise ServiceNameTaken() from None
            raise

    def list_prices(self) -> Sequence[DoctorPrice]:
        return self._prices.list()

    def set_price(
        self, service_id: UUID, doctor_id: UUID, price_paise: int | None, *, id: UUID, now: datetime
    ) -> None:
        # Both are this clinic's: the caller loaded them through this clinic's repositories,
        # and the rows carry this clinic's ID.
        if price_paise is None:
            self._session.execute(
                delete(DoctorServicePriceRow).where(
                    DoctorServicePriceRow.clinic_id == self.clinic_id,
                    DoctorServicePriceRow.service_id == service_id,
                    DoctorServicePriceRow.doctor_id == doctor_id,
                )
            )
            return
        self._session.execute(
            insert(DoctorServicePriceRow)
            .values(
                id=id,
                clinic_id=self.clinic_id,
                service_id=service_id,
                doctor_id=doctor_id,
                price_paise=price_paise,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["service_id", "doctor_id"],
                set_={"price_paise": price_paise, "updated_at": now},
                where=DoctorServicePriceRow.clinic_id == self.clinic_id,
            )
        )
