"""SQLAlchemy implementations of the repository ports (ports/repositories.py).

Each repository maps rows ↔ domain entities explicitly, so the domain never
depends on SQLAlchemy and a schema detail never leaks into a use case. Writes
are flushed immediately: a constraint violation surfaces at the call that
caused it, inside the unit of work's transaction, rather than at commit.

Platform repositories (clinics, users) work on the session directly. Tenant
repositories extend ``TenantScopedRepository`` and are created only by the
unit of work, bound to one clinic.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models import ClinicMembershipRow, ClinicRow, DoctorRow, UserRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import ClinicMembership, MembershipStatus, Role
from mediease_api.domain.identity.user import User, UserStatus
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber


def _utc(value: datetime) -> datetime:
    # psycopg returns timestamptz in the session's TimeZone; the domain works in UTC.
    return value.astimezone(UTC)


# --- Clinics (platform) --------------------------------------------------------------------


def _clinic_from_row(row: ClinicRow) -> Clinic:
    return Clinic(
        id=row.id,
        name=row.name,
        slug=row.slug,
        timezone=row.timezone,
        status=ClinicStatus(row.status),
        phone=PhoneNumber(row.phone_e164) if row.phone_e164 else None,
        address_line=row.address_line,
        city=row.city,
        state=row.state,
        pincode=row.pincode,
        specialties=tuple(row.specialties),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _write_clinic(row: ClinicRow, clinic: Clinic) -> None:
    row.name = clinic.name
    row.slug = clinic.slug
    row.timezone = clinic.timezone
    row.status = clinic.status.value
    row.phone_e164 = clinic.phone.e164 if clinic.phone else None
    row.address_line = clinic.address_line
    row.city = clinic.city
    row.state = clinic.state
    row.pincode = clinic.pincode
    row.specialties = list(clinic.specialties)
    row.updated_at = clinic.updated_at


class SqlAlchemyClinicRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, clinic: Clinic) -> None:
        row = ClinicRow(id=clinic.id, created_at=clinic.created_at)
        _write_clinic(row, clinic)
        self._session.add(row)
        self._session.flush()

    def get(self, clinic_id: UUID) -> Clinic | None:
        row = self._session.get(ClinicRow, clinic_id)
        return _clinic_from_row(row) if row else None

    def get_by_slug(self, slug: str) -> Clinic | None:
        row = self._session.scalars(select(ClinicRow).where(ClinicRow.slug == slug)).one_or_none()
        return _clinic_from_row(row) if row else None

    def update(self, clinic: Clinic) -> None:
        row = self._session.get(ClinicRow, clinic.id)
        if row is None:
            raise NotFound("clinic")
        _write_clinic(row, clinic)
        self._session.flush()


# --- Users (platform) ----------------------------------------------------------------------


def _user_from_row(row: UserRow) -> User:
    return User(
        id=row.id,
        full_name=row.full_name,
        email=EmailAddress(row.email) if row.email else None,
        phone=PhoneNumber(row.phone_e164) if row.phone_e164 else None,
        is_platform_ops=row.is_platform_ops,
        status=UserStatus(row.status),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _write_user(row: UserRow, user: User) -> None:
    row.full_name = user.full_name
    row.email = user.email.value if user.email else None
    row.phone_e164 = user.phone.e164 if user.phone else None
    row.is_platform_ops = user.is_platform_ops
    row.status = user.status.value
    row.updated_at = user.updated_at


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> None:
        row = UserRow(id=user.id, created_at=user.created_at)
        _write_user(row, user)
        self._session.add(row)
        self._session.flush()

    def get(self, user_id: UUID) -> User | None:
        row = self._session.get(UserRow, user_id)
        return _user_from_row(row) if row else None

    def get_by_email(self, email: EmailAddress) -> User | None:
        return self._one(select(UserRow).where(UserRow.email == email.value))

    def get_by_phone(self, phone: PhoneNumber) -> User | None:
        return self._one(select(UserRow).where(UserRow.phone_e164 == phone.e164))

    def update(self, user: User) -> None:
        row = self._session.get(UserRow, user.id)
        if row is None:
            raise NotFound("user")
        _write_user(row, user)
        self._session.flush()

    def _one(self, query: Select[UserRow]) -> User | None:
        row = self._session.scalars(query).one_or_none()
        return _user_from_row(row) if row else None


# --- Doctors (tenant) ----------------------------------------------------------------------


def _doctor_from_row(row: DoctorRow) -> Doctor:
    return Doctor(
        id=row.id,
        clinic_id=row.clinic_id,
        user_id=row.user_id,
        display_name=row.display_name,
        qualification=row.qualification,
        registration_number=row.registration_number,
        registration_council=row.registration_council,
        specialty=row.specialty,
        is_active=row.is_active,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _write_doctor(row: DoctorRow, doctor: Doctor) -> None:
    row.user_id = doctor.user_id
    row.display_name = doctor.display_name
    row.qualification = doctor.qualification
    row.registration_number = doctor.registration_number
    row.registration_council = doctor.registration_council
    row.specialty = doctor.specialty
    row.is_active = doctor.is_active
    row.updated_at = doctor.updated_at


class SqlAlchemyDoctorRepository(TenantScopedRepository[DoctorRow]):
    model = DoctorRow
    entity_name = "doctor"

    def add(self, doctor: Doctor) -> None:
        self._check_owned(doctor.clinic_id)
        row = DoctorRow(id=doctor.id, clinic_id=self.clinic_id, created_at=doctor.created_at)
        _write_doctor(row, doctor)
        self._session.add(row)
        self._session.flush()

    def get(self, doctor_id: UUID) -> Doctor | None:
        row = self._get_row(doctor_id)
        return _doctor_from_row(row) if row else None

    def list(self) -> Sequence[Doctor]:
        query = self._scoped_select().order_by(DoctorRow.created_at, DoctorRow.id)
        return [_doctor_from_row(row) for row in self._session.scalars(query)]

    def update(self, doctor: Doctor) -> None:
        self._check_owned(doctor.clinic_id)
        row = self._require_row(doctor.id)
        _write_doctor(row, doctor)
        self._session.flush()


# --- Memberships (tenant) --------------------------------------------------------------------


def _membership_from_row(row: ClinicMembershipRow) -> ClinicMembership:
    return ClinicMembership(
        id=row.id,
        clinic_id=row.clinic_id,
        user_id=row.user_id,
        role=Role(row.role),
        status=MembershipStatus(row.status),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


class SqlAlchemyMembershipRepository(TenantScopedRepository[ClinicMembershipRow]):
    model = ClinicMembershipRow
    entity_name = "membership"

    def add(self, membership: ClinicMembership) -> None:
        self._check_owned(membership.clinic_id)
        row = ClinicMembershipRow(
            id=membership.id,
            clinic_id=self.clinic_id,
            user_id=membership.user_id,
            role=membership.role.value,
            status=membership.status.value,
            created_at=membership.created_at,
            updated_at=membership.updated_at,
        )
        self._session.add(row)
        self._session.flush()

    def get(self, membership_id: UUID) -> ClinicMembership | None:
        row = self._get_row(membership_id)
        return _membership_from_row(row) if row else None

    def get_for_user(self, user_id: UUID) -> ClinicMembership | None:
        query = self._scoped_select().where(ClinicMembershipRow.user_id == user_id)
        row = self._session.scalars(query).one_or_none()
        return _membership_from_row(row) if row else None

    def list(self) -> Sequence[ClinicMembership]:
        query = self._scoped_select().order_by(
            ClinicMembershipRow.created_at, ClinicMembershipRow.id
        )
        return [_membership_from_row(row) for row in self._session.scalars(query)]

    def count_active_owners(self) -> int:
        owners = self._scoped_select().where(
            ClinicMembershipRow.role == Role.OWNER.value,
            ClinicMembershipRow.status == MembershipStatus.ACTIVE.value,
        )
        return self._session.scalar(select(func.count()).select_from(owners.subquery())) or 0

    def update(self, membership: ClinicMembership) -> None:
        # clinic_id and user_id never change; only the role and the lifecycle do.
        self._check_owned(membership.clinic_id)
        row = self._require_row(membership.id)
        row.role = membership.role.value
        row.status = membership.status.value
        row.updated_at = membership.updated_at
        self._session.flush()
