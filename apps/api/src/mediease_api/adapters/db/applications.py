"""Clinic applications (M6c-P1, ports/onboarding.py; ADR-0020).

A reviewed platform repository: applications are no clinic's data. ``registration_matches`` is
the one read across clinics, and it returns clinic IDs only; it matches existing doctors by the
normalised number alone, because ops-created doctors carry a council typed by hand (a false match
only flags the application for the reviewer, R17).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, select, tuple_
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.applications import (
    APPLICATION_REFERENCE_SEQUENCE,
    ClinicApplicationDoctorRow,
    ClinicApplicationRow,
)
from mediease_api.adapters.db.models.clinics import DoctorRow
from mediease_api.domain.onboarding.application import (
    ApplicationDoctor,
    ApplicationKind,
    ApplicationStatus,
    ClinicApplication,
    format_reference,
)
from mediease_api.domain.onboarding.certificate import Certificate
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.onboarding import ApplicationSummary, Removed


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def _doctor(row: ClinicApplicationDoctorRow) -> ApplicationDoctor:
    return ApplicationDoctor(
        position=row.position,
        name=row.name,
        qualification=row.qualification,
        council=row.registration_council,
        registration_number=row.registration_number,
        is_owner=row.is_owner,
        id=row.id,
        certificate=Certificate(
            key=row.certificate_key,
            content_type=row.certificate_content_type,
            size=row.certificate_size,
            sha256=row.certificate_sha256,
        ),
    )


def _application(
    row: ClinicApplicationRow, doctors: Sequence[ClinicApplicationDoctorRow]
) -> ClinicApplication:
    return ClinicApplication(
        id=row.id,
        reference=row.reference,
        kind=ApplicationKind(row.kind),
        status=ApplicationStatus(row.status),
        clinic_name=row.clinic_name,
        address_line=row.address_line,
        city=row.city,
        state=row.state,
        pincode=row.pincode,
        clinic_phone=PhoneNumber(row.clinic_phone_e164),
        specialties=tuple(row.specialties),
        owner_name=row.owner_name,
        owner_phone=PhoneNumber(row.owner_phone_e164),
        owner_email=EmailAddress(row.owner_email),
        owner_practises=row.owner_practises,
        doctors=tuple(_doctor(d) for d in sorted(doctors, key=lambda d: d.position)),
        submitted_at=row.submitted_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
        ip_hash=row.ip_hash,
        email_verified_at=_utc(row.email_verified_at),
        confirm_digest=row.confirm_digest,
        duplicate_of=tuple(row.duplicate_of or ()),
    )


class SqlAlchemyApplicationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def next_reference(self, year: int) -> str:
        number = self._session.execute(APPLICATION_REFERENCE_SEQUENCE.next_value()).scalar_one()
        return format_reference(year, int(number))

    def add(self, application: ClinicApplication) -> None:
        a = application
        self._session.add(
            ClinicApplicationRow(
                id=a.id,
                reference=a.reference,
                kind=a.kind.value,
                status=a.status.value,
                clinic_name=a.clinic_name,
                address_line=a.address_line,
                city=a.city,
                state=a.state,
                pincode=a.pincode,
                clinic_phone_e164=a.clinic_phone.e164,
                specialties=list(a.specialties),
                owner_name=a.owner_name,
                owner_phone_e164=a.owner_phone.e164,
                owner_email=a.owner_email.value,
                owner_practises=a.owner_practises,
                email_verified_at=a.email_verified_at,
                confirm_digest=a.confirm_digest,
                duplicate_of=list(a.duplicate_of),
                ip_hash=a.ip_hash,
                submitted_at=a.submitted_at,
                updated_at=a.updated_at,
            )
        )
        self._session.flush()
        for d in a.doctors:
            assert d.certificate is not None and d.id is not None  # R7; set at submission
            self._session.add(
                ClinicApplicationDoctorRow(
                    id=d.id,
                    application_id=a.id,
                    position=d.position,
                    name=d.name,
                    qualification=d.qualification,
                    registration_council=d.council,
                    registration_number=d.registration_number,
                    is_owner=d.is_owner,
                    certificate_key=d.certificate.key,
                    certificate_content_type=d.certificate.content_type,
                    certificate_size=d.certificate.size,
                    certificate_sha256=d.certificate.sha256,
                )
            )
        self._session.flush()

    def _load(self, row: ClinicApplicationRow | None) -> ClinicApplication | None:
        if row is None:
            return None
        doctors = self._session.scalars(
            select(ClinicApplicationDoctorRow).where(
                ClinicApplicationDoctorRow.application_id == row.id
            )
        ).all()
        return _application(row, doctors)

    def get(self, application_id: UUID, *, for_update: bool = False) -> ClinicApplication | None:
        statement = select(ClinicApplicationRow).where(ClinicApplicationRow.id == application_id)
        if for_update:
            statement = statement.with_for_update()
        return self._load(self._session.scalars(statement).one_or_none())

    def get_by_confirm_digest(self, digest: str) -> ClinicApplication | None:
        return self._load(
            self._session.scalars(
                select(ClinicApplicationRow)
                .where(
                    ClinicApplicationRow.confirm_digest == digest,
                    ClinicApplicationRow.email_verified_at.is_(None),
                )
                .with_for_update()
            ).one_or_none()
        )

    def update(self, application: ClinicApplication) -> None:
        row = self._session.get(ClinicApplicationRow, application.id)
        if row is None:
            raise LookupError("application not found")
        row.status = application.status.value
        row.email_verified_at = application.email_verified_at
        row.confirm_digest = application.confirm_digest
        row.duplicate_of = list(application.duplicate_of)
        row.updated_at = application.updated_at
        self._session.flush()

    def _remove(self, ids: list[UUID]) -> list[Removed]:
        if not ids:
            return []
        keys: dict[UUID, list[str]] = {i: [] for i in ids}
        for application_id, key in self._session.execute(
            select(
                ClinicApplicationDoctorRow.application_id,
                ClinicApplicationDoctorRow.certificate_key,
            ).where(ClinicApplicationDoctorRow.application_id.in_(ids))
        ):
            keys[application_id].append(key)
        self._session.execute(delete(ClinicApplicationRow).where(ClinicApplicationRow.id.in_(ids)))
        self._session.flush()
        return [Removed(i, tuple(sorted(k))) for i, k in keys.items()]

    def remove_unconfirmed_for_email(self, email: EmailAddress) -> list[Removed]:
        ids = list(
            self._session.scalars(
                select(ClinicApplicationRow.id)
                .where(
                    ClinicApplicationRow.owner_email == email.value,
                    ClinicApplicationRow.email_verified_at.is_(None),
                )
                .with_for_update()
            )
        )
        return self._remove(ids)

    def remove_unconfirmed_before(self, cutoff: datetime) -> list[Removed]:
        ids = list(
            self._session.scalars(
                select(ClinicApplicationRow.id)
                .where(
                    ClinicApplicationRow.email_verified_at.is_(None),
                    ClinicApplicationRow.submitted_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        return self._remove(ids)

    def _count_since(self, condition: ColumnElement[bool], since: datetime) -> int:
        statement = (
            select(func.count())
            .select_from(ClinicApplicationRow)
            .where(condition, ClinicApplicationRow.submitted_at >= since)
        )
        return int(self._session.execute(statement).scalar_one())

    def count_by_ip_since(self, ip_hash: str, since: datetime) -> int:
        return self._count_since(ClinicApplicationRow.ip_hash == ip_hash, since)

    def count_by_phone_since(self, phone: PhoneNumber, since: datetime) -> int:
        return self._count_since(ClinicApplicationRow.owner_phone_e164 == phone.e164, since)

    def count_by_email_since(self, email: EmailAddress, since: datetime) -> int:
        return self._count_since(ClinicApplicationRow.owner_email == email.value, since)

    def registration_matches(
        self, registrations: Sequence[tuple[str, str]], *, exclude_id: UUID | None = None
    ) -> list[str]:
        if not registrations:
            return []
        doctor = ClinicApplicationDoctorRow
        application = ClinicApplicationRow
        statement = (
            select(application.reference)
            .join(doctor, doctor.application_id == application.id)
            .where(
                tuple_(doctor.registration_council, doctor.registration_number).in_(
                    list(registrations)
                ),
                application.email_verified_at.is_not(None),
                application.status != ApplicationStatus.REJECTED.value,
            )
            .distinct()
        )
        if exclude_id is not None:
            statement = statement.where(application.id != exclude_id)
        references = sorted(self._session.scalars(statement))
        numbers = sorted({number for _, number in registrations})
        normalised = func.upper(func.regexp_replace(DoctorRow.registration_number, r"\s", "", "g"))
        clinics = sorted(
            str(c)
            for c in self._session.scalars(
                select(DoctorRow.clinic_id).where(normalised.in_(numbers)).distinct()
            )
        )
        return references + [f"clinic:{c}" for c in clinics]

    def list_confirmed(self) -> list[ApplicationSummary]:
        counts = (
            select(
                ClinicApplicationDoctorRow.application_id,
                func.count().label("doctors"),
            )
            .group_by(ClinicApplicationDoctorRow.application_id)
            .subquery()
        )
        rows = self._session.execute(
            select(ClinicApplicationRow, counts.c.doctors)
            .join(counts, counts.c.application_id == ClinicApplicationRow.id)
            .where(ClinicApplicationRow.email_verified_at.is_not(None))
            .order_by(ClinicApplicationRow.email_verified_at, ClinicApplicationRow.id)
        ).all()
        result: list[ApplicationSummary] = []
        for row, doctors in rows:
            assert row.email_verified_at is not None
            result.append(
                ApplicationSummary(
                    id=row.id,
                    reference=row.reference,
                    kind=ApplicationKind(row.kind),
                    clinic_name=row.clinic_name,
                    city=row.city,
                    doctors=int(doctors),
                    submitted_at=row.submitted_at.astimezone(UTC),
                    email_verified_at=row.email_verified_at.astimezone(UTC),
                    possible_duplicate=bool(row.duplicate_of),
                )
            )
        return result
