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

from sqlalchemy import Select, exists, func, select, update
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models import (
    ClinicMembershipRow,
    ClinicRow,
    DoctorRow,
    OnboardingChecklistRow,
    RefreshTokenRow,
    UserRow,
)
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.access import ClinicAccess, StaffMember
from mediease_api.domain.identity.membership import ClinicMembership, MembershipStatus, Role
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.identity.user import User, UserStatus
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber


def _utc(value: datetime) -> datetime:
    # psycopg returns timestamptz in the session's TimeZone; the domain works in UTC.
    return value.astimezone(UTC)


def _utc_or_none(value: datetime | None) -> datetime | None:
    return _utc(value) if value is not None else None


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

    def list_onboarding(self) -> Sequence[tuple[Clinic, OnboardingChecklist | None]]:
        query = (
            select(ClinicRow, OnboardingChecklistRow)
            .outerjoin(OnboardingChecklistRow, OnboardingChecklistRow.clinic_id == ClinicRow.id)
            .order_by(ClinicRow.created_at.desc(), ClinicRow.id)
        )
        return [
            (_clinic_from_row(clinic), _checklist_from_row(checklist) if checklist else None)
            for clinic, checklist in self._session.execute(query)
        ]


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
        password_hash=row.password_hash,
        failed_sign_in_count=row.failed_login_count,
        locked_until=_utc_or_none(row.locked_until),
        last_signed_in_at=_utc_or_none(row.last_login_at),
    )


def _write_user(row: UserRow, user: User) -> None:
    row.full_name = user.full_name
    row.email = user.email.value if user.email else None
    row.phone_e164 = user.phone.e164 if user.phone else None
    row.is_platform_ops = user.is_platform_ops
    row.status = user.status.value
    row.password_hash = user.password_hash
    row.failed_login_count = user.failed_sign_in_count
    row.locked_until = user.locked_until
    row.last_login_at = user.last_signed_in_at
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

    def get_by_email(self, email: EmailAddress, *, for_update: bool = False) -> User | None:
        return self._one(select(UserRow).where(UserRow.email == email.value), for_update)

    def get_by_phone(self, phone: PhoneNumber, *, for_update: bool = False) -> User | None:
        return self._one(select(UserRow).where(UserRow.phone_e164 == phone.e164), for_update)

    def update(self, user: User) -> None:
        row = self._session.get(UserRow, user.id)
        if row is None:
            raise NotFound("user")
        _write_user(row, user)
        self._session.flush()

    def _one(self, query: Select[UserRow], for_update: bool) -> User | None:
        if for_update:
            # populate_existing: a row already in the session is re-read under the lock.
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _user_from_row(row) if row else None


# --- Refresh tokens (platform, owned by users) -------------------------------------------------


def _refresh_token_from_row(row: RefreshTokenRow) -> RefreshToken:
    return RefreshToken(
        id=row.id,
        user_id=row.user_id,
        family_id=row.family_id,
        token_hash=row.token_hash,
        expires_at=_utc(row.expires_at),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        revoked_at=_utc_or_none(row.revoked_at),
        replaced_by_id=row.replaced_by_id,
    )


class SqlAlchemyRefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: RefreshToken) -> None:
        self._session.add(
            RefreshTokenRow(
                id=token.id,
                user_id=token.user_id,
                family_id=token.family_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                revoked_at=token.revoked_at,
                replaced_by_id=token.replaced_by_id,
                created_at=token.created_at,
                updated_at=token.updated_at,
            )
        )
        self._session.flush()

    def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> RefreshToken | None:
        query = select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _refresh_token_from_row(row) if row else None

    def update(self, token: RefreshToken) -> None:
        # Only the lifecycle changes; identity, family and hash are fixed at issue.
        row = self._session.get(RefreshTokenRow, token.id)
        if row is None:
            raise NotFound("refresh token")
        row.revoked_at = token.revoked_at
        row.replaced_by_id = token.replaced_by_id
        row.updated_at = token.updated_at
        self._session.flush()

    def revoke_family(self, family_id: UUID, *, now: datetime) -> int:
        result = self._session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.family_id == family_id, RefreshTokenRow.revoked_at.is_(None))
            .values(revoked_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def is_family_live(self, family_id: UUID, *, now: datetime) -> bool:
        query = select(
            exists().where(
                RefreshTokenRow.family_id == family_id,
                RefreshTokenRow.revoked_at.is_(None),
                RefreshTokenRow.expires_at > now,
            )
        )
        return bool(self._session.scalar(query))


# --- Clinic access (platform, cross-clinic by user) ---------------------------------------------


class SqlAlchemyClinicAccessRepository:
    """Reads ``clinic_memberships`` by user across clinics, joined to the clinic's name.

    The one sanctioned cross-clinic read of memberships (ADR-0003 "platform
    repositories"): keyed by the signed-in user, returning IDs, names and enums.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active_for_user(self, user_id: UUID) -> Sequence[ClinicAccess]:
        query = (
            select(ClinicMembershipRow, ClinicRow, DoctorRow.id)
            .join(ClinicRow, ClinicRow.id == ClinicMembershipRow.clinic_id)
            # The user's doctor profile at the same clinic, if any (owner who is a doctor).
            .outerjoin(
                DoctorRow,
                (DoctorRow.clinic_id == ClinicMembershipRow.clinic_id)
                & (DoctorRow.user_id == ClinicMembershipRow.user_id)
                & DoctorRow.is_active,
            )
            .where(
                ClinicMembershipRow.user_id == user_id,
                ClinicMembershipRow.status == MembershipStatus.ACTIVE.value,
            )
            .order_by(ClinicRow.name, ClinicRow.id)
        )
        return [
            ClinicAccess(
                membership_id=membership.id,
                clinic_id=clinic.id,
                clinic_name=clinic.name,
                clinic_status=ClinicStatus(clinic.status),
                role=Role(membership.role),
                has_doctor_profile=doctor_id is not None,
            )
            for membership, clinic, doctor_id in self._session.execute(query)
        ]


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

    def get_for_user(self, user_id: UUID) -> Doctor | None:
        query = self._scoped_select().where(DoctorRow.user_id == user_id)
        row = self._session.scalars(query).one_or_none()
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
        invite_token_hash=row.invite_token_hash,
        invite_expires_at=_utc_or_none(row.invite_expires_at),
        invite_accepted_at=_utc_or_none(row.invite_accepted_at),
    )


def _write_membership(row: ClinicMembershipRow, membership: ClinicMembership) -> None:
    # clinic_id and user_id never change; only the role, the lifecycle and the
    # invitation do.
    row.role = membership.role.value
    row.status = membership.status.value
    row.invite_token_hash = membership.invite_token_hash
    row.invite_expires_at = membership.invite_expires_at
    row.invite_accepted_at = membership.invite_accepted_at
    row.updated_at = membership.updated_at


class SqlAlchemyStaffInviteRepository:
    """Finds a membership by its invitation digest (platform read, M1-P5).

    The invitee has no clinic context yet, so this cannot be clinic-scoped; the
    key is a 256-bit secret's digest, exactly like refresh tokens (ADR-0003).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_invite_digest(self, token_hash: str) -> ClinicMembership | None:
        query = select(ClinicMembershipRow).where(
            ClinicMembershipRow.invite_token_hash == token_hash
        )
        row = self._session.scalars(query).one_or_none()
        return _membership_from_row(row) if row else None


class SqlAlchemyMembershipRepository(TenantScopedRepository[ClinicMembershipRow]):
    model = ClinicMembershipRow
    entity_name = "membership"

    def add(self, membership: ClinicMembership) -> None:
        self._check_owned(membership.clinic_id)
        row = ClinicMembershipRow(
            id=membership.id,
            clinic_id=self.clinic_id,
            user_id=membership.user_id,
            created_at=membership.created_at,
        )
        _write_membership(row, membership)
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

    def list_staff(self) -> Sequence[StaffMember]:
        # Scoped like every other query here; the join only adds the member's
        # name, which lives on the platform `users` table.
        query = (
            self._scoped_select()
            .add_columns(UserRow.full_name)
            .join(UserRow, UserRow.id == ClinicMembershipRow.user_id)
            .order_by(UserRow.full_name, ClinicMembershipRow.id)
        )
        return [
            StaffMember(
                membership_id=row.id,
                user_id=row.user_id,
                full_name=full_name,
                role=Role(row.role),
                status=MembershipStatus(row.status),
            )
            for row, full_name in self._session.execute(query)
        ]

    def update(self, membership: ClinicMembership) -> None:
        self._check_owned(membership.clinic_id)
        row = self._require_row(membership.id)
        _write_membership(row, membership)
        self._session.flush()


# --- Onboarding checklist (tenant) ------------------------------------------------------------


def _checklist_from_row(row: OnboardingChecklistRow) -> OnboardingChecklist:
    steps = {}
    for step in OnboardingStep:
        # The step's value is the column name, so the mapping cannot drift.
        recorded = getattr(row, step.value)
        if recorded is not None:
            steps[step] = _utc(recorded)
    return OnboardingChecklist(
        id=row.id,
        clinic_id=row.clinic_id,
        started_at=_utc(row.started_at),
        steps=steps,
    )


def _write_checklist(row: OnboardingChecklistRow, checklist: OnboardingChecklist) -> None:
    for step in OnboardingStep:
        setattr(row, step.value, checklist.at(step))


class SqlAlchemyChecklistRepository(TenantScopedRepository[OnboardingChecklistRow]):
    model = OnboardingChecklistRow
    entity_name = "onboarding checklist"

    def add(self, checklist: OnboardingChecklist) -> None:
        self._check_owned(checklist.clinic_id)
        row = OnboardingChecklistRow(
            id=checklist.id, clinic_id=self.clinic_id, started_at=checklist.started_at
        )
        _write_checklist(row, checklist)
        self._session.add(row)
        self._session.flush()

    def get(self) -> OnboardingChecklist | None:
        row = self._session.scalars(self._scoped_select()).one_or_none()
        return _checklist_from_row(row) if row else None

    def update(self, checklist: OnboardingChecklist) -> None:
        self._check_owned(checklist.clinic_id)
        row = self._require_row(checklist.id)
        _write_checklist(row, checklist)
        self._session.flush()
