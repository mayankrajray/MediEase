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

from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import Select, delete, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import aggregate_order_by, insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models import (
    AppointmentRow,
    AppointmentStatusHistoryRow,
    ClinicMembershipRow,
    ClinicRow,
    DoctorRow,
    DoctorScheduleRow,
    OnboardingChecklistRow,
    PatientLinkRow,
    PatientRow,
    PrescriptionItemRow,
    PrescriptionRow,
    PublicRateLimitRow,
    RefreshTokenRow,
    RxFavouriteRow,
    RxTemplateRow,
    ScheduleExceptionRow,
    SessionRow,
    UserRow,
    VisitAddendumRow,
    VisitRow,
)
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.appointments.appointment import Appointment, StatusChange
from mediease_api.domain.appointments.status import (
    AppointmentSource,
    AppointmentStatus,
    CancelReason,
)
from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus, PaperSize
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.clinics.verification import VerificationSource
from mediease_api.domain.identity.access import ClinicAccess, StaffMember
from mediease_api.domain.identity.membership import ClinicMembership, MembershipStatus, Role
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.identity.user import OpsRole, User, UserStatus
from mediease_api.domain.links.link import LinkPurpose, PatientLink
from mediease_api.domain.patients.patient import Language, Patient, Sex
from mediease_api.domain.prescriptions.errors import PdfBusy
from mediease_api.domain.prescriptions.library import Favourite, NameTaken, Template
from mediease_api.domain.prescriptions.prescription import (
    Advice,
    ClinicSnapshot,
    DoctorSnapshot,
    IssuedVersion,
    LinkDelivery,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    item_from_json,
    item_json,
)
from mediease_api.domain.prescriptions.schedule import DurationKind, Frequency
from mediease_api.domain.prescriptions.suggestions import HistoryName
from mediease_api.domain.prescriptions.vocabulary import (
    Preparation,
    PreparationCode,
    Storage,
    StorageCode,
    Timing,
)
from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock
from mediease_api.domain.scheduling.exceptions import ExceptionKind, ScheduleException
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session as BookableSession
from mediease_api.domain.scheduling.sessions import SessionStatus
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.visits.visit import Visit, VisitAddendum, VisitStatus
from mediease_api.domain.visits.vitals import Vitals
from mediease_api.ports.repositories import PatientMatch, RowLock, SeenPatient


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
        patient_code_prefix=row.patient_code_prefix,
        next_patient_seq=row.next_patient_seq,
        booking_mode=BookingMode(row.booking_mode),
        rx_paper_size=PaperSize(row.rx_paper_size),
        reminder_evening_before=row.reminder_evening_before,
        reminder_hours_before=row.reminder_hours_before,
        request_hold_minutes=row.request_hold_minutes,
        request_requires_age_sex=row.request_requires_age_sex,
        verified_at=_utc_or_none(row.verified_at),
        verified_by=row.verified_by,
        verification_source=(
            VerificationSource(row.verification_source) if row.verification_source else None
        ),
        application_id=row.application_id,
        listed=row.listed,
        listed_at=_utc_or_none(row.listed_at),
        search_indexing=row.search_indexing,
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
    row.patient_code_prefix = clinic.patient_code_prefix
    row.next_patient_seq = clinic.next_patient_seq
    row.booking_mode = clinic.booking_mode.value
    row.rx_paper_size = clinic.rx_paper_size.value
    row.reminder_evening_before = clinic.reminder_evening_before
    row.reminder_hours_before = clinic.reminder_hours_before
    row.request_hold_minutes = clinic.request_hold_minutes
    row.request_requires_age_sex = clinic.request_requires_age_sex
    row.verified_at = clinic.verified_at
    row.verified_by = clinic.verified_by
    row.verification_source = (
        clinic.verification_source.value if clinic.verification_source else None
    )
    row.application_id = clinic.application_id
    row.listed = clinic.listed
    row.listed_at = clinic.listed_at
    row.search_indexing = clinic.search_indexing
    row.updated_at = clinic.updated_at


class SqlAlchemyClinicRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, clinic: Clinic) -> None:
        row = ClinicRow(id=clinic.id, created_at=clinic.created_at)
        _write_clinic(row, clinic)
        self._session.add(row)
        self._session.flush()

    def get(self, clinic_id: UUID, *, for_update: bool = False) -> Clinic | None:
        if for_update:
            # populate_existing: a row already in the session is re-read under the lock, so
            # the counter seen here is the committed one, not a stale copy.
            query = select(ClinicRow).where(ClinicRow.id == clinic_id)
            row = self._session.scalars(
                query.with_for_update().execution_options(populate_existing=True)
            ).one_or_none()
        else:
            row = self._session.get(ClinicRow, clinic_id)
        return _clinic_from_row(row) if row else None

    def get_by_slug(self, slug: str) -> Clinic | None:
        row = self._session.scalars(select(ClinicRow).where(ClinicRow.slug == slug)).one_or_none()
        return _clinic_from_row(row) if row else None

    def list_listed(self, *, limit: int) -> Sequence[Clinic]:
        # M6c-P5: the candidates for the sitemap (the listing rule is applied by the caller).
        query = (
            select(ClinicRow)
            .where(
                ClinicRow.listed,
                ClinicRow.status == ClinicStatus.ACTIVE.value,
                ClinicRow.verified_at.is_not(None),
            )
            .order_by(ClinicRow.slug)
            .limit(limit)
        )
        return [_clinic_from_row(row) for row in self._session.scalars(query)]

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
        ops_roles=frozenset(OpsRole(r) for r in (row.ops_roles or ())),
    )


def _write_user(row: UserRow, user: User) -> None:
    row.full_name = user.full_name
    row.email = user.email.value if user.email else None
    row.phone_e164 = user.phone.e164 if user.phone else None
    row.is_platform_ops = user.is_platform_ops
    row.ops_roles = sorted(r.value for r in user.ops_roles)
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

    def get(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        if for_update:
            return self._one(select(UserRow).where(UserRow.id == user_id), for_update)
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

    def revoke_all_for_owner(self, owner_id: UUID, *, now: datetime) -> int:
        result = self._session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.user_id == owner_id, RefreshTokenRow.revoked_at.is_(None))
            .values(revoked_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]


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
                doctor_id=doctor_id,
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
        verified_at=_utc_or_none(row.verified_at),
        verified_by=row.verified_by,
        verification_source=(
            VerificationSource(row.verification_source) if row.verification_source else None
        ),
        visible=row.visible,
        languages=tuple(row.languages or ()),
        fee_paise=row.fee_paise,
    )


def _write_doctor(row: DoctorRow, doctor: Doctor) -> None:
    row.user_id = doctor.user_id
    row.display_name = doctor.display_name
    row.qualification = doctor.qualification
    row.registration_number = doctor.registration_number
    row.registration_council = doctor.registration_council
    row.specialty = doctor.specialty
    row.is_active = doctor.is_active
    row.verified_at = doctor.verified_at
    row.verified_by = doctor.verified_by
    row.verification_source = (
        doctor.verification_source.value if doctor.verification_source else None
    )
    row.visible = doctor.visible
    row.languages = list(doctor.languages)
    row.fee_paise = doctor.fee_paise
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

    def get(self, doctor_id: UUID, *, lock: RowLock | None = None) -> Doctor | None:
        if lock is None:
            row = self._get_row(doctor_id)
        else:
            query = self._scoped_select().where(DoctorRow.id == doctor_id)
            row = self._session.scalars(
                query.with_for_update(read=lock is RowLock.SHARE).execution_options(
                    populate_existing=True
                )
            ).one_or_none()
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
        # Scoped like every other query here; the joins only add the member's name and sign-in
        # identifiers (platform `users`) and whether an active doctor profile at *this* clinic
        # is linked to them (M6a-P5).
        query = (
            self._scoped_select()
            .add_columns(UserRow.full_name, UserRow.email, UserRow.phone_e164, DoctorRow.id)
            .join(UserRow, UserRow.id == ClinicMembershipRow.user_id)
            .outerjoin(
                DoctorRow,
                (DoctorRow.clinic_id == ClinicMembershipRow.clinic_id)
                & (DoctorRow.user_id == ClinicMembershipRow.user_id)
                & DoctorRow.is_active,
            )
            .order_by(UserRow.full_name, ClinicMembershipRow.id)
        )
        return [
            StaffMember(
                membership_id=row.id,
                user_id=row.user_id,
                full_name=full_name,
                role=Role(row.role),
                status=MembershipStatus(row.status),
                email=email,
                phone_e164=phone,
                invite_expires_at=(
                    _utc_or_none(row.invite_expires_at)
                    if row.status == MembershipStatus.INVITED.value
                    else None
                ),
                has_doctor_profile=doctor_id is not None,
            )
            for row, full_name, email, phone, doctor_id in self._session.execute(query)
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


# --- Patients (tenant) ---------------------------------------------------------------------


def _patient_from_row(row: PatientRow) -> Patient:
    return Patient(
        id=row.id,
        clinic_id=row.clinic_id,
        code=row.code,
        full_name=row.full_name,
        phone=PhoneNumber(row.phone_e164),
        sex=Sex(row.sex),
        date_of_birth=row.date_of_birth,
        age_years_at_registration=row.age_years_at_registration,
        registered_on=row.registered_on,
        guardian_name=row.guardian_name,
        language=Language(row.language),
        whatsapp_consent=row.whatsapp_consent,
        sms_consent=row.sms_consent,
        consent_recorded_at=_utc_or_none(row.consent_recorded_at),
        consent_recorded_by=row.consent_recorded_by,
        opted_out_at=_utc_or_none(row.opted_out_at),
        created_by=row.created_by,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _write_patient(row: PatientRow, patient: Patient) -> None:
    # The code is fixed at creation (I3), so it is set by ``add`` and never here.
    row.full_name = patient.full_name
    row.phone_e164 = patient.phone.e164
    row.sex = patient.sex.value
    row.date_of_birth = patient.date_of_birth
    row.age_years_at_registration = patient.age_years_at_registration
    row.registered_on = patient.registered_on
    row.guardian_name = patient.guardian_name
    row.language = patient.language.value
    row.whatsapp_consent = patient.whatsapp_consent
    row.sms_consent = patient.sms_consent
    row.consent_recorded_at = patient.consent_recorded_at
    row.consent_recorded_by = patient.consent_recorded_by
    row.opted_out_at = patient.opted_out_at
    row.updated_at = patient.updated_at


def _like_prefix(prefix: str) -> str:
    """``prefix`` as a LIKE pattern that matches it literally, then anything."""
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%"


class SqlAlchemyPatientRepository(TenantScopedRepository[PatientRow]):
    model = PatientRow
    entity_name = "patient"

    def add(self, patient: Patient) -> None:
        self.add_many([patient])

    def add_many(self, patients: Sequence[Patient]) -> None:
        rows = []
        for patient in patients:
            self._check_owned(patient.clinic_id)
            row = PatientRow(
                id=patient.id,
                clinic_id=self.clinic_id,
                code=patient.code,
                created_by=patient.created_by,
                created_at=patient.created_at,
            )
            _write_patient(row, patient)
            rows.append(row)
        # One flush: SQLAlchemy sends the rows as batched multi-row INSERTs.
        self._session.add_all(rows)
        self._session.flush()

    def get(self, patient_id: UUID, *, for_update: bool = False) -> Patient | None:
        if not for_update:
            row = self._get_row(patient_id)
        else:
            query = self._scoped_select().where(PatientRow.id == patient_id)
            # populate_existing: a row already in the session is re-read under the lock.
            row = self._session.scalars(
                query.with_for_update().execution_options(populate_existing=True)
            ).one_or_none()
        return _patient_from_row(row) if row else None

    def update(self, patient: Patient) -> None:
        self._check_owned(patient.clinic_id)
        row = self._require_row(patient.id)
        _write_patient(row, patient)
        self._session.flush()

    def get_by_code(self, code: str) -> Patient | None:
        query = self._scoped_select().where(PatientRow.code == code)
        row = self._session.scalars(query).one_or_none()
        return _patient_from_row(row) if row else None

    def find_by_phone(self, phone: PhoneNumber, *, limit: int) -> Sequence[Patient]:
        query = (
            self._scoped_select()
            .where(PatientRow.phone_e164 == phone.e164)
            .order_by(PatientRow.created_at, PatientRow.id)
            .limit(limit)
        )
        return [_patient_from_row(row) for row in self._session.scalars(query)]

    def find_by_phones(self, phones: Collection[PhoneNumber]) -> Sequence[Patient]:
        numbers = sorted({phone.e164 for phone in phones})
        if not numbers:
            return []
        query = (
            self._scoped_select()
            .where(PatientRow.phone_e164.in_(numbers))
            .order_by(PatientRow.created_at, PatientRow.id)
        )
        return [_patient_from_row(row) for row in self._session.scalars(query)]

    def get_many(self, patient_ids: Collection[UUID]) -> Sequence[Patient]:
        ids = sorted(set(patient_ids))
        if not ids:
            return []
        query = self._scoped_select().where(PatientRow.id.in_(ids))
        return [_patient_from_row(row) for row in self._session.scalars(query)]

    def search_by_name_prefix(self, prefix: str, *, limit: int) -> Sequence[Patient]:
        query = (
            self._scoped_select()
            .where(func.lower(PatientRow.full_name).like(_like_prefix(prefix.lower()), escape="\\"))
            .order_by(func.lower(PatientRow.full_name), PatientRow.code)
            .limit(limit)
        )
        return [_patient_from_row(row) for row in self._session.scalars(query)]

    def count(self) -> int:
        query = (
            select(func.count())
            .select_from(PatientRow)
            .where(PatientRow.clinic_id == self._clinic_id)
        )
        return int(self._session.scalar(query) or 0)


# --- Schedules, exceptions and sessions (tenant, M3-P1) ---------------------------------------


def _shape(start: time | None, end: time | None, slot: int | None, cap: int | None) -> BlockShape:
    assert start is not None and end is not None  # the CHECK constraints guarantee it for blocks
    return BlockShape(start_time=start, end_time=end, slot_minutes=slot, capacity=cap)


def _block_from_row(row: DoctorScheduleRow) -> WeeklyBlock:
    return WeeklyBlock(
        id=row.id,
        clinic_id=row.clinic_id,
        doctor_id=row.doctor_id,
        weekday=row.weekday,
        shape=_shape(row.start_time, row.end_time, row.slot_minutes, row.capacity),
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _write_block(row: DoctorScheduleRow, block: WeeklyBlock) -> None:
    row.doctor_id = block.doctor_id
    row.weekday = block.weekday
    row.start_time = block.shape.start_time
    row.end_time = block.shape.end_time
    row.slot_minutes = block.shape.slot_minutes
    row.capacity = block.shape.capacity
    row.valid_from = block.valid_from
    row.valid_to = block.valid_to
    row.updated_at = block.updated_at


class SqlAlchemyScheduleRepository(TenantScopedRepository[DoctorScheduleRow]):
    model = DoctorScheduleRow
    entity_name = "schedule block"

    def add(self, block: WeeklyBlock) -> None:
        self._check_owned(block.clinic_id)
        row = DoctorScheduleRow(id=block.id, clinic_id=self.clinic_id, created_at=block.created_at)
        _write_block(row, block)
        self._session.add(row)
        self._session.flush()

    def update(self, block: WeeklyBlock) -> None:
        self._check_owned(block.clinic_id)
        row = self._require_row(block.id)
        _write_block(row, block)
        self._session.flush()

    def delete(self, block_id: UUID) -> None:
        self._delete_row(block_id)

    def list_for_doctor(self, doctor_id: UUID, *, valid_since: date) -> Sequence[WeeklyBlock]:
        query = self._current(valid_since).where(DoctorScheduleRow.doctor_id == doctor_id)
        return [_block_from_row(row) for row in self._session.scalars(query)]

    def list_current(self, *, valid_since: date) -> Sequence[WeeklyBlock]:
        return [_block_from_row(row) for row in self._session.scalars(self._current(valid_since))]

    def _current(self, valid_since: date) -> Select[DoctorScheduleRow]:
        return (
            self._scoped_select()
            .where(
                or_(DoctorScheduleRow.valid_to.is_(None), DoctorScheduleRow.valid_to >= valid_since)
            )
            .order_by(
                DoctorScheduleRow.doctor_id,
                DoctorScheduleRow.weekday,
                DoctorScheduleRow.start_time,
                DoctorScheduleRow.valid_from,
            )
        )


def _exception_from_row(row: ScheduleExceptionRow) -> ScheduleException:
    kind = ExceptionKind(row.kind)
    return ScheduleException(
        id=row.id,
        clinic_id=row.clinic_id,
        doctor_id=row.doctor_id,
        on_date=row.on_date,
        kind=kind,
        shape=(
            _shape(row.start_time, row.end_time, row.slot_minutes, row.capacity)
            if kind is ExceptionKind.EXTRA
            else None
        ),
        note=row.note,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


class SqlAlchemyScheduleExceptionRepository(TenantScopedRepository[ScheduleExceptionRow]):
    model = ScheduleExceptionRow
    entity_name = "schedule exception"

    def add(self, exception: ScheduleException) -> None:
        self._check_owned(exception.clinic_id)
        shape = exception.shape
        self._session.add(
            ScheduleExceptionRow(
                id=exception.id,
                clinic_id=self.clinic_id,
                doctor_id=exception.doctor_id,
                on_date=exception.on_date,
                kind=exception.kind.value,
                start_time=shape.start_time if shape else None,
                end_time=shape.end_time if shape else None,
                slot_minutes=shape.slot_minutes if shape else None,
                capacity=shape.capacity if shape else None,
                note=exception.note,
                created_at=exception.created_at,
                updated_at=exception.updated_at,
            )
        )
        self._session.flush()

    def get(self, exception_id: UUID) -> ScheduleException | None:
        row = self._get_row(exception_id)
        return _exception_from_row(row) if row else None

    def delete(self, exception_id: UUID) -> None:
        self._delete_row(exception_id)

    def list_for_doctor(
        self, doctor_id: UUID, *, first: date, last: date
    ) -> Sequence[ScheduleException]:
        query = (
            self._scoped_select()
            .where(
                ScheduleExceptionRow.doctor_id == doctor_id,
                ScheduleExceptionRow.on_date.between(first, last),
            )
            .order_by(ScheduleExceptionRow.on_date, ScheduleExceptionRow.start_time)
        )
        return [_exception_from_row(row) for row in self._session.scalars(query)]

    def list_from(self, first: date) -> Sequence[ScheduleException]:
        query = (
            self._scoped_select()
            .where(ScheduleExceptionRow.on_date >= first)
            .order_by(ScheduleExceptionRow.on_date, ScheduleExceptionRow.doctor_id)
        )
        return [_exception_from_row(row) for row in self._session.scalars(query)]


def _session_from_row(row: SessionRow) -> BookableSession:
    return BookableSession(
        id=row.id,
        clinic_id=row.clinic_id,
        doctor_id=row.doctor_id,
        on_date=row.on_date,
        starts_at=_utc(row.starts_at),
        ends_at=_utc(row.ends_at),
        mode=BookingMode(row.mode),
        slot_minutes=row.slot_minutes,
        capacity=row.capacity,
        booked_count=row.booked_count,
        next_token=row.next_token,
        status=SessionStatus(row.status),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


class SqlAlchemySessionRepository(TenantScopedRepository[SessionRow]):
    model = SessionRow
    entity_name = "session"

    def add_missing(self, sessions: Sequence[BookableSession]) -> int:
        if not sessions:
            return 0
        for session in sessions:
            self._check_owned(session.clinic_id)
        values = [
            {
                "id": s.id,
                "clinic_id": self.clinic_id,
                "doctor_id": s.doctor_id,
                "on_date": s.on_date,
                "starts_at": s.starts_at,
                "ends_at": s.ends_at,
                "mode": s.mode.value,
                "slot_minutes": s.slot_minutes,
                "capacity": s.capacity,
                "booked_count": s.booked_count,
                "next_token": s.next_token,
                "status": s.status.value,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in sessions
        ]
        # Idempotent (R1): two screens generating one date leave one set of sessions. RETURNING
        # counts what was really inserted (rowcount is not reliable for a multi-row INSERT).
        query = (
            insert(SessionRow)
            .values(values)
            .on_conflict_do_nothing(index_elements=["doctor_id", "starts_at"])
            .returning(SessionRow.id)
        )
        return len(self._session.execute(query).all())

    def get(self, session_id: UUID, *, lock: RowLock | None = None) -> BookableSession | None:
        if lock is None:
            row = self._get_row(session_id)
        else:
            query = self._scoped_select().where(SessionRow.id == session_id)
            row = self._session.scalars(
                query.with_for_update(read=lock is RowLock.SHARE).execution_options(
                    populate_existing=True
                )
            ).one_or_none()
        return _session_from_row(row) if row else None

    def get_many(self, session_ids: Collection[UUID]) -> Sequence[BookableSession]:
        ids = sorted(set(session_ids))
        if not ids:
            return []
        query = self._scoped_select().where(SessionRow.id.in_(ids))
        return [_session_from_row(row) for row in self._session.scalars(query)]

    def update(self, session: BookableSession) -> None:
        self._check_owned(session.clinic_id)
        row = self._require_row(session.id)
        # The key (doctor, start, date) never changes; a revived session takes a new shape.
        row.ends_at = session.ends_at
        row.mode = session.mode.value
        row.slot_minutes = session.slot_minutes
        row.capacity = session.capacity
        row.booked_count = session.booked_count
        row.next_token = session.next_token
        row.status = session.status.value
        row.updated_at = session.updated_at
        self._session.flush()

    def list_for_date(
        self, on_date: date, *, doctor_id: UUID | None = None, include_retired: bool = False
    ) -> Sequence[BookableSession]:
        query = self._scoped_select().where(SessionRow.on_date == on_date)
        if not include_retired:
            query = query.where(SessionRow.status != SessionStatus.CANCELLED.value)
        if doctor_id is not None:
            query = query.where(SessionRow.doctor_id == doctor_id)
        query = query.order_by(SessionRow.starts_at, SessionRow.doctor_id)
        return [_session_from_row(row) for row in self._session.scalars(query)]

    def list_for_doctor(
        self, doctor_id: UUID, *, first: date, last: date | None = None
    ) -> Sequence[BookableSession]:
        query = self._scoped_select().where(
            SessionRow.doctor_id == doctor_id, SessionRow.on_date >= first
        )
        if last is not None:
            query = query.where(SessionRow.on_date <= last)
        query = query.order_by(SessionRow.starts_at)
        return [_session_from_row(row) for row in self._session.scalars(query)]

    def delete(self, session_id: UUID) -> None:
        self._delete_row(session_id)


# --- Appointments (tenant, M3-P2) ------------------------------------------------------------


def _appointment_from_row(row: AppointmentRow) -> Appointment:
    return Appointment(
        id=row.id,
        clinic_id=row.clinic_id,
        session_id=row.session_id,
        doctor_id=row.doctor_id,
        patient_id=row.patient_id,
        slot_start=_utc_or_none(row.slot_start),
        token_number=row.token_number,
        status=AppointmentStatus(row.status),
        source=AppointmentSource(row.source),
        reason=row.reason,
        cancel_reason=CancelReason(row.cancel_reason) if row.cancel_reason else None,
        cancel_note=row.cancel_note,
        cancelled_at=_utc_or_none(row.cancelled_at),
        rescheduled_from_id=row.rescheduled_from_id,
        arrived_at=_utc_or_none(row.arrived_at),
        started_at=_utc_or_none(row.started_at),
        completed_at=_utc_or_none(row.completed_at),
        created_by=row.created_by,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _write_appointment(row: AppointmentRow, appointment: Appointment) -> None:
    # The session, doctor, patient, place, source and creator are fixed at booking.
    row.status = appointment.status.value
    row.reason = appointment.reason
    row.cancel_reason = appointment.cancel_reason.value if appointment.cancel_reason else None
    row.cancel_note = appointment.cancel_note
    row.cancelled_at = appointment.cancelled_at
    row.arrived_at = appointment.arrived_at
    row.started_at = appointment.started_at
    row.completed_at = appointment.completed_at
    row.updated_at = appointment.updated_at


class SqlAlchemyAppointmentRepository(TenantScopedRepository[AppointmentRow]):
    model = AppointmentRow
    entity_name = "appointment"

    def add(self, appointment: Appointment) -> None:
        self._check_owned(appointment.clinic_id)
        row = AppointmentRow(
            id=appointment.id,
            clinic_id=self.clinic_id,
            session_id=appointment.session_id,
            doctor_id=appointment.doctor_id,
            patient_id=appointment.patient_id,
            slot_start=appointment.slot_start,
            token_number=appointment.token_number,
            source=appointment.source.value,
            rescheduled_from_id=appointment.rescheduled_from_id,
            created_by=appointment.created_by,
            created_at=appointment.created_at,
        )
        _write_appointment(row, appointment)
        self._session.add(row)
        self._session.flush()

    def update(self, appointment: Appointment) -> None:
        self._check_owned(appointment.clinic_id)
        row = self._require_row(appointment.id)
        _write_appointment(row, appointment)
        self._session.flush()

    def get(self, appointment_id: UUID, *, for_update: bool = False) -> Appointment | None:
        if not for_update:
            row = self._get_row(appointment_id)
        else:
            query = self._scoped_select().where(AppointmentRow.id == appointment_id)
            row = self._session.scalars(
                query.with_for_update().execution_options(populate_existing=True)
            ).one_or_none()
        return _appointment_from_row(row) if row else None

    def list_active_for_sessions(self, session_ids: Collection[UUID]) -> Sequence[Appointment]:
        return self._in_sessions(session_ids, active_only=True)

    def list_for_sessions(self, session_ids: Collection[UUID]) -> Sequence[Appointment]:
        return self._in_sessions(session_ids, active_only=False)

    def _in_sessions(
        self, session_ids: Collection[UUID], *, active_only: bool
    ) -> list[Appointment]:
        ids = sorted(set(session_ids))
        if not ids:
            return []
        query = self._scoped_select().where(AppointmentRow.session_id.in_(ids))
        if active_only:
            query = query.where(AppointmentRow.status != AppointmentStatus.CANCELLED.value)
        query = query.order_by(
            AppointmentRow.session_id,
            AppointmentRow.slot_start,
            AppointmentRow.token_number,
        )
        return [_appointment_from_row(row) for row in self._session.scalars(query)]

    def exists_for_session(self, session_id: UUID) -> bool:
        query = select(
            exists().where(
                AppointmentRow.clinic_id == self._clinic_id,
                AppointmentRow.session_id == session_id,
            )
        )
        return bool(self._session.scalar(query))

    def list_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[Appointment]:
        query = (
            self._scoped_select()
            .where(AppointmentRow.patient_id == patient_id)
            .order_by(AppointmentRow.created_at.desc(), AppointmentRow.id.desc())
            .limit(limit)
        )
        return [_appointment_from_row(row) for row in self._session.scalars(query)]

    def list_booked_ended_before(self, cutoff: datetime, *, limit: int) -> Sequence[UUID]:
        query = (
            select(AppointmentRow.id)
            .join(SessionRow, SessionRow.id == AppointmentRow.session_id)
            .where(
                AppointmentRow.clinic_id == self.clinic_id,
                SessionRow.clinic_id == self.clinic_id,
                AppointmentRow.status == AppointmentStatus.BOOKED.value,
                SessionRow.ends_at <= cutoff,
            )
            .order_by(SessionRow.ends_at, AppointmentRow.id)
            .limit(limit)
        )
        return list(self._session.scalars(query))

    def count_no_shows(self, patient_ids: Collection[UUID], since: datetime) -> dict[UUID, int]:
        ids = sorted(set(patient_ids))
        if not ids:
            return {}
        query = (
            select(AppointmentRow.patient_id, func.count())
            .join(SessionRow, SessionRow.id == AppointmentRow.session_id)
            .where(
                AppointmentRow.clinic_id == self.clinic_id,
                SessionRow.clinic_id == self.clinic_id,
                AppointmentRow.patient_id.in_(ids),
                AppointmentRow.status == AppointmentStatus.NO_SHOW.value,
                SessionRow.starts_at >= since,
            )
            .group_by(AppointmentRow.patient_id)
        )
        return {row[0]: int(row[1]) for row in self._session.execute(query)}

    def _to_move(self, from_date: date, doctor_id: UUID | None) -> Select[AppointmentRow]:
        query = (
            select(AppointmentRow)
            .join(SessionRow, SessionRow.id == AppointmentRow.session_id)
            .where(
                AppointmentRow.clinic_id == self.clinic_id,
                SessionRow.clinic_id == self.clinic_id,
                AppointmentRow.status.in_(
                    [AppointmentStatus.BOOKED.value, AppointmentStatus.ARRIVED.value]
                ),
                SessionRow.status == SessionStatus.CLOSED.value,
                SessionRow.on_date >= from_date,
            )
        )
        if doctor_id is not None:
            query = query.where(AppointmentRow.doctor_id == doctor_id)
        return query

    def list_to_move(
        self, *, from_date: date, doctor_id: UUID | None = None, limit: int
    ) -> Sequence[tuple[Appointment, BookableSession]]:
        query = (
            self._to_move(from_date, doctor_id)
            .add_columns(SessionRow)
            .order_by(
                SessionRow.starts_at,
                AppointmentRow.slot_start,
                AppointmentRow.token_number,
                AppointmentRow.id,
            )
            .limit(limit)
        )
        return [
            (_appointment_from_row(appointment), _session_from_row(session))
            for appointment, session in self._session.execute(query)
        ]

    def count_to_move(self, *, from_date: date, doctor_id: UUID | None = None) -> int:
        query = select(func.count()).select_from(self._to_move(from_date, doctor_id).subquery())
        return int(self._session.scalar(query) or 0)


class SqlAlchemyAppointmentHistoryRepository(TenantScopedRepository[AppointmentStatusHistoryRow]):
    model = AppointmentStatusHistoryRow
    entity_name = "appointment history"

    def add(self, change: StatusChange) -> None:
        self._check_owned(change.clinic_id)
        self._session.add(
            AppointmentStatusHistoryRow(
                id=change.id,
                clinic_id=self.clinic_id,
                appointment_id=change.appointment_id,
                from_status=change.from_status.value if change.from_status else None,
                to_status=change.to_status.value,
                changed_by=change.changed_by,
                changed_at=change.changed_at,
                request_id=change.request_id,
            )
        )
        self._session.flush()

    def list_for_appointment(self, appointment_id: UUID) -> Sequence[StatusChange]:
        query = (
            self._scoped_select()
            .where(AppointmentStatusHistoryRow.appointment_id == appointment_id)
            .order_by(AppointmentStatusHistoryRow.changed_at, AppointmentStatusHistoryRow.id)
        )
        return [
            StatusChange(
                id=row.id,
                clinic_id=row.clinic_id,
                appointment_id=row.appointment_id,
                from_status=AppointmentStatus(row.from_status) if row.from_status else None,
                to_status=AppointmentStatus(row.to_status),
                changed_by=row.changed_by,
                changed_at=_utc(row.changed_at),
                request_id=row.request_id,
            )
            for row in self._session.scalars(query)
        ]


def _visit_from_row(row: VisitRow) -> Visit:
    return Visit(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        doctor_id=row.doctor_id,
        appointment_id=row.appointment_id,
        status=VisitStatus(row.status),
        chief_complaint=row.chief_complaint,
        findings=row.findings,
        diagnosis=row.diagnosis,
        notes=row.notes,
        vitals=Vitals.parse(row.vitals or {}),
        revision=row.revision,
        started_at=_utc(row.started_at),
        completed_at=_utc_or_none(row.completed_at),
        locked_at=_utc_or_none(row.locked_at),
        created_by=row.created_by,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _write_visit(row: VisitRow, visit: Visit) -> None:
    # The patient, doctor, appointment, start and creator are fixed when the visit starts.
    row.status = visit.status.value
    row.chief_complaint = visit.chief_complaint
    row.findings = visit.findings
    row.diagnosis = visit.diagnosis
    row.notes = visit.notes
    row.vitals = visit.vitals.as_json()
    row.revision = visit.revision
    row.completed_at = visit.completed_at
    row.locked_at = visit.locked_at
    row.updated_at = visit.updated_at


class SqlAlchemyVisitRepository(TenantScopedRepository[VisitRow]):
    model = VisitRow
    entity_name = "visit"

    def add(self, visit: Visit) -> None:
        self._check_owned(visit.clinic_id)
        row = VisitRow(
            id=visit.id,
            clinic_id=self.clinic_id,
            patient_id=visit.patient_id,
            doctor_id=visit.doctor_id,
            appointment_id=visit.appointment_id,
            started_at=visit.started_at,
            created_by=visit.created_by,
            created_at=visit.created_at,
        )
        _write_visit(row, visit)
        self._session.add(row)
        self._session.flush()

    def update(self, visit: Visit) -> None:
        self._check_owned(visit.clinic_id)
        row = self._require_row(visit.id)
        _write_visit(row, visit)
        self._session.flush()

    def get(self, visit_id: UUID, *, for_update: bool = False) -> Visit | None:
        query = self._scoped_select().where(VisitRow.id == visit_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _visit_from_row(row) if row else None

    def get_for_appointment(self, appointment_id: UUID) -> Visit | None:
        query = self._scoped_select().where(VisitRow.appointment_id == appointment_id)
        row = self._session.scalars(query).one_or_none()
        return _visit_from_row(row) if row else None

    def ids_for_appointments(self, appointment_ids: Collection[UUID]) -> dict[UUID, UUID]:
        ids = sorted(set(appointment_ids))
        if not ids:
            return {}
        query = select(VisitRow.appointment_id, VisitRow.id).where(
            VisitRow.clinic_id == self.clinic_id, VisitRow.appointment_id.in_(ids)
        )
        return {row[0]: row[1] for row in self._session.execute(query)}

    def list_for_patient(
        self, patient_id: UUID, *, limit: int, before: tuple[datetime, UUID] | None = None
    ) -> Sequence[Visit]:
        query = self._scoped_select().where(VisitRow.patient_id == patient_id)
        if before is not None:
            started, visit_id = before
            query = query.where(
                or_(
                    VisitRow.started_at < started,
                    (VisitRow.started_at == started) & (VisitRow.id < visit_id),
                )
            )
        query = query.order_by(VisitRow.started_at.desc(), VisitRow.id.desc()).limit(limit)
        return [_visit_from_row(row) for row in self._session.scalars(query)]

    def patients_seen_by(
        self, doctor_id: UUID, *, match: PatientMatch | None, limit: int, offset: int
    ) -> Sequence[SeenPatient]:
        # Both tables scoped to this clinic; ix_visits_clinic_id_doctor_id_started_at (0022)
        # serves the aggregate.
        seen = (
            select(
                VisitRow.patient_id.label("patient_id"),
                func.max(VisitRow.started_at).label("last_visit_at"),
                func.count().label("visits"),
            )
            .where(VisitRow.clinic_id == self.clinic_id, VisitRow.doctor_id == doctor_id)
            .group_by(VisitRow.patient_id)
            .subquery()
        )
        query = (
            select(PatientRow, seen.c.last_visit_at, seen.c.visits)
            .join(seen, seen.c.patient_id == PatientRow.id)
            .where(PatientRow.clinic_id == self.clinic_id)
        )
        if match is not None and match.phone_e164 is not None:
            query = query.where(PatientRow.phone_e164 == match.phone_e164)
        elif match is not None and match.code is not None:
            query = query.where(PatientRow.code == match.code)
        elif match is not None and match.name_prefix is not None:
            pattern = _like_prefix(match.name_prefix.lower())
            query = query.where(func.lower(PatientRow.full_name).like(pattern, escape="\\"))
        query = (
            query.order_by(seen.c.last_visit_at.desc(), PatientRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [
            SeenPatient(patient=_patient_from_row(row), last_visit_at=_utc(last), visits=count)
            for row, last, count in self._session.execute(query)
        ]


class SqlAlchemyVisitAddendumRepository(TenantScopedRepository[VisitAddendumRow]):
    model = VisitAddendumRow
    entity_name = "visit addendum"

    def add(self, addendum: VisitAddendum) -> None:
        self._check_owned(addendum.clinic_id)
        self._session.add(
            VisitAddendumRow(
                id=addendum.id,
                clinic_id=self.clinic_id,
                visit_id=addendum.visit_id,
                author_user_id=addendum.author_user_id,
                body=addendum.body,
                created_at=addendum.created_at,
            )
        )
        self._session.flush()

    def list_for_visit(self, visit_id: UUID) -> Sequence[VisitAddendum]:
        query = (
            self._scoped_select()
            .where(VisitAddendumRow.visit_id == visit_id)
            .order_by(VisitAddendumRow.created_at, VisitAddendumRow.id)
        )
        return [
            VisitAddendum(
                id=row.id,
                clinic_id=row.clinic_id,
                visit_id=row.visit_id,
                author_user_id=row.author_user_id,
                body=row.body,
                created_at=_utc(row.created_at),
            )
            for row in self._session.scalars(query)
        ]


def _item_from_row(row: PrescriptionItemRow) -> PrescriptionItem:
    return PrescriptionItem(
        id=row.id,
        position=row.position,
        medicine_name=row.medicine_name,
        form=row.form,
        strength=row.strength,
        dose=row.dose,
        frequency=Frequency(row.frequency) if row.frequency else None,
        frequency_text=row.frequency_text,
        timing=Timing(row.timing) if row.timing else None,
        duration_days=row.duration_days,
        duration_kind=(
            DurationKind(row.duration_kind)
            if row.duration_kind
            else (DurationKind.DAYS if row.duration_days is not None else None)
        ),
        quantity=row.quantity,
        preparation=tuple(
            Preparation(PreparationCode(p["code"]), p.get("text")) for p in row.preparation
        ),
        storage=tuple(Storage(StorageCode(s["code"]), s.get("days")) for s in row.storage),
        warnings=row.warnings,
        notes=row.notes,
        favourite_id=row.favourite_id,
    )


def _item_row(
    clinic_id: UUID, prescription_id: UUID, item: PrescriptionItem
) -> PrescriptionItemRow:
    return PrescriptionItemRow(
        id=item.id,
        clinic_id=clinic_id,
        prescription_id=prescription_id,
        position=item.position,
        medicine_name=item.medicine_name,
        form=item.form,
        strength=item.strength,
        dose=item.dose,
        frequency=item.frequency.value if item.frequency else None,
        frequency_text=item.frequency_text,
        timing=item.timing.value if item.timing else None,
        duration_days=item.duration_days,
        duration_kind=item.duration_kind.value if item.duration_kind else None,
        quantity=item.quantity,
        preparation=[p.as_json() for p in item.preparation],
        storage=[s.as_json() for s in item.storage],
        warnings=item.warnings,
        notes=item.notes,
        favourite_id=item.favourite_id,
    )


def _prescription_from_row(row: PrescriptionRow, items: Sequence[PrescriptionItem]) -> Prescription:
    advice = row.advice or {}
    doctor = row.doctor_snapshot
    clinic = row.clinic_snapshot
    return Prescription(
        id=row.id,
        clinic_id=row.clinic_id,
        visit_id=row.visit_id,
        patient_id=row.patient_id,
        doctor_id=row.doctor_id,
        version=row.version,
        supersedes_id=row.supersedes_id,
        status=PrescriptionStatus(row.status),
        revision=row.revision,
        items=tuple(items),
        advice=Advice(
            diet=tuple(advice.get("diet", ())),
            activity=tuple(advice.get("activity", ())),
            return_if=tuple(advice.get("return_if", ())),
            notes=advice.get("notes"),
        ),
        follow_up_date=row.follow_up_date,
        language=Language(row.language) if row.language else None,
        issued_at=_utc_or_none(row.issued_at),
        doctor_snapshot=(
            DoctorSnapshot(
                doctor_id=UUID(doctor["doctor_id"]),
                display_name=doctor["display_name"],
                qualification=doctor["qualification"],
                registration_number=doctor["registration_number"],
                registration_council=doctor["registration_council"],
                specialty=doctor.get("specialty"),
            )
            if doctor
            else None
        ),
        clinic_snapshot=ClinicSnapshot(**clinic) if clinic else None,
        pdf_object_key=row.pdf_object_key,
        link_delivery=LinkDelivery(row.link_delivery) if row.link_delivery else None,
        link_delivery_requested_at=_utc_or_none(row.link_delivery_requested_at),
        created_by=row.created_by,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        template_id=row.template_id,
        layout_version=row.layout_version,
        starts_on=row.starts_on,
    )


def _write_prescription(row: PrescriptionRow, rx: Prescription) -> None:
    # The visit, patient, doctor, version, predecessor and creator are fixed at creation.
    row.status = rx.status.value
    row.revision = rx.revision
    row.advice = rx.advice.as_json()
    row.follow_up_date = rx.follow_up_date
    row.language = rx.language.value if rx.language else None
    row.issued_at = rx.issued_at
    row.doctor_snapshot = rx.doctor_snapshot.as_json() if rx.doctor_snapshot else None
    row.clinic_snapshot = rx.clinic_snapshot.as_json() if rx.clinic_snapshot else None
    row.pdf_object_key = rx.pdf_object_key
    row.link_delivery = rx.link_delivery.value if rx.link_delivery else None
    row.link_delivery_requested_at = rx.link_delivery_requested_at
    row.template_id = rx.template_id
    row.layout_version = rx.layout_version
    row.starts_on = rx.starts_on
    row.updated_at = rx.updated_at


class SqlAlchemyPrescriptionItemRepository(TenantScopedRepository[PrescriptionItemRow]):
    """The items of this clinic's prescriptions; used through the prescription repository."""

    model = PrescriptionItemRow
    entity_name = "prescription item"

    def for_prescriptions(self, ids: Collection[UUID]) -> dict[UUID, list[PrescriptionItem]]:
        found: dict[UUID, list[PrescriptionItem]] = {i: [] for i in ids}
        if not found:
            return found
        query = (
            self._scoped_select()
            .where(PrescriptionItemRow.prescription_id.in_(sorted(found)))
            .order_by(PrescriptionItemRow.prescription_id, PrescriptionItemRow.position)
        )
        for row in self._session.scalars(query):
            found[row.prescription_id].append(_item_from_row(row))
        return found

    def insert(self, rx: Prescription) -> None:
        self._session.add_all([_item_row(self.clinic_id, rx.id, item) for item in rx.items])
        self._session.flush()

    def delete_for(self, prescription_id: UUID) -> None:
        self._session.execute(
            delete(PrescriptionItemRow).where(
                PrescriptionItemRow.clinic_id == self.clinic_id,
                PrescriptionItemRow.prescription_id == prescription_id,
            )
        )
        self._session.flush()


class SqlAlchemyPrescriptionRepository(TenantScopedRepository[PrescriptionRow]):
    model = PrescriptionRow
    entity_name = "prescription"

    def __init__(self, session: Session, clinic_id: UUID) -> None:
        super().__init__(session, clinic_id)
        self._items = SqlAlchemyPrescriptionItemRepository(session, clinic_id)

    def add(self, prescription: Prescription) -> None:
        self._check_owned(prescription.clinic_id)
        row = PrescriptionRow(
            id=prescription.id,
            clinic_id=self.clinic_id,
            visit_id=prescription.visit_id,
            patient_id=prescription.patient_id,
            doctor_id=prescription.doctor_id,
            version=prescription.version,
            supersedes_id=prescription.supersedes_id,
            created_by=prescription.created_by,
            created_at=prescription.created_at,
        )
        _write_prescription(row, prescription)
        self._session.add(row)
        self._session.flush()
        self._items.insert(prescription)

    def update(self, prescription: Prescription) -> None:
        self._check_owned(prescription.clinic_id)
        row = self._require_row(prescription.id)
        _write_prescription(row, prescription)
        self._session.flush()

    def replace_items(self, prescription: Prescription) -> None:
        self._check_owned(prescription.clinic_id)
        self._require_row(prescription.id)
        self._items.delete_for(prescription.id)
        self._items.insert(prescription)

    def get(self, prescription_id: UUID, *, for_update: bool = False) -> Prescription | None:
        query = self._scoped_select().where(PrescriptionRow.id == prescription_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        if row is None:
            return None
        return _prescription_from_row(row, self._items.for_prescriptions([row.id])[row.id])

    def list_for_visit(self, visit_id: UUID) -> Sequence[Prescription]:
        return self.list_for_visits([visit_id])

    def list_for_visits(self, visit_ids: Collection[UUID]) -> Sequence[Prescription]:
        ids = sorted(set(visit_ids))
        if not ids:
            return []
        query = (
            self._scoped_select()
            .where(PrescriptionRow.visit_id.in_(ids))
            .order_by(PrescriptionRow.visit_id, PrescriptionRow.version)
        )
        rows = list(self._session.scalars(query))
        items = self._items.for_prescriptions([r.id for r in rows])
        return [_prescription_from_row(r, items[r.id]) for r in rows]

    def issued_for_visits(self, visit_ids: Collection[UUID]) -> dict[UUID, IssuedVersion]:
        ids = sorted(set(visit_ids))
        if not ids:
            return {}
        query = select(
            PrescriptionRow.id,
            PrescriptionRow.visit_id,
            PrescriptionRow.version,
            PrescriptionRow.issued_at,
        ).where(
            PrescriptionRow.clinic_id == self.clinic_id,
            PrescriptionRow.visit_id.in_(ids),
            PrescriptionRow.status == PrescriptionStatus.ISSUED.value,
        )
        found: dict[UUID, IssuedVersion] = {}
        for rx_id, visit_id, version, issued_at in self._session.execute(query):
            assert issued_at is not None  # an issued version has its time (CHECK)
            found[visit_id] = IssuedVersion(rx_id, visit_id, version, _utc(issued_at))
        return found

    def delete(self, prescription_id: UUID) -> None:
        self._require_row(prescription_id)
        self._items.delete_for(prescription_id)
        self._delete_row(prescription_id)

    def lock_for_render(self, prescription_id: UUID, *, wait_seconds: int) -> Prescription | None:
        # SET LOCAL lasts until the transaction ends; an int, so no injection is possible.
        self._session.execute(text(f"SET LOCAL lock_timeout = '{int(wait_seconds)}s'"))
        try:
            return self.get(prescription_id, for_update=True)
        except OperationalError as exc:
            if getattr(exc.orig, "sqlstate", None) == "55P03":  # lock_not_available
                raise PdfBusy() from None
            raise

    def list_issued_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[Prescription]:
        query = (
            self._scoped_select()
            .where(
                PrescriptionRow.patient_id == patient_id,
                PrescriptionRow.status == PrescriptionStatus.ISSUED.value,
            )
            .order_by(PrescriptionRow.issued_at.desc(), PrescriptionRow.id.desc())
            .limit(limit)
        )
        rows = list(self._session.scalars(query))
        items = self._items.for_prescriptions([r.id for r in rows])
        return [_prescription_from_row(r, items[r.id]) for r in rows]

    def medicine_history(self, prefix: str, *, limit: int) -> Sequence[HistoryName]:
        key = func.lower(func.regexp_replace(PrescriptionItemRow.medicine_name, r"\s+", " ", "g"))
        pattern = _like_prefix(prefix.lower())
        visits = func.count(PrescriptionRow.visit_id.distinct())
        last = func.max(PrescriptionRow.issued_at)
        spelling = func.array_agg(
            aggregate_order_by(PrescriptionItemRow.medicine_name, PrescriptionRow.issued_at.desc())
        )[1]
        query = (
            select(spelling, visits, last)
            .select_from(PrescriptionItemRow)
            .join(PrescriptionRow, PrescriptionRow.id == PrescriptionItemRow.prescription_id)
            .where(
                PrescriptionItemRow.clinic_id == self.clinic_id,
                PrescriptionRow.clinic_id == self.clinic_id,
                PrescriptionRow.status.in_(
                    [PrescriptionStatus.ISSUED.value, PrescriptionStatus.SUPERSEDED.value]
                ),
                # Served by ix_prescription_items_clinic_id_medicine_name (text_pattern_ops).
                func.lower(PrescriptionItemRow.medicine_name).like(pattern, escape="\\"),
            )
            .group_by(key)
            .order_by(visits.desc(), last.desc())
            .limit(limit)
        )
        return [
            HistoryName(name=row[0], visits=int(row[1]), last_issued_at=_utc(row[2]))
            for row in self._session.execute(query)
        ]


def _add_library_row(session: Session, row: RxFavouriteRow | RxTemplateRow) -> None:
    """Insert or flush, turning the per-doctor name index into ``NameTaken``."""
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        if "_doctor_id_name" in str(exc.orig):
            raise NameTaken() from None
        raise


def _favourite_from_row(row: RxFavouriteRow) -> Favourite:
    return Favourite(
        id=row.id,
        clinic_id=row.clinic_id,
        doctor_id=row.doctor_id,
        name=row.name,
        item=item_from_json(row.item, id=row.id, position=1),
        revision=row.revision,
        use_count=row.use_count,
        last_used_at=_utc_or_none(row.last_used_at),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _template_from_row(row: RxTemplateRow) -> Template:
    advice = row.advice or {}
    return Template(
        id=row.id,
        clinic_id=row.clinic_id,
        doctor_id=row.doctor_id,
        name=row.name,
        items=tuple(
            item_from_json(item, id=row.id, position=i) for i, item in enumerate(row.items, start=1)
        ),
        advice=Advice(
            diet=tuple(advice.get("diet", ())),
            activity=tuple(advice.get("activity", ())),
            return_if=tuple(advice.get("return_if", ())),
            notes=advice.get("notes"),
        ),
        follow_up_days=row.follow_up_days,
        revision=row.revision,
        use_count=row.use_count,
        last_used_at=_utc_or_none(row.last_used_at),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


class SqlAlchemyRxFavouriteRepository(TenantScopedRepository[RxFavouriteRow]):
    model = RxFavouriteRow
    entity_name = "favourite"

    def _write(self, row: RxFavouriteRow, fav: Favourite) -> None:
        row.name = fav.name
        row.item = item_json(fav.item)
        row.revision = fav.revision
        row.use_count = fav.use_count
        row.last_used_at = fav.last_used_at
        row.updated_at = fav.updated_at

    def add(self, favourite: Favourite) -> None:
        self._check_owned(favourite.clinic_id)
        row = RxFavouriteRow(
            id=favourite.id,
            clinic_id=self.clinic_id,
            doctor_id=favourite.doctor_id,
            created_at=favourite.created_at,
        )
        self._write(row, favourite)
        _add_library_row(self._session, row)

    def update(self, favourite: Favourite) -> None:
        self._check_owned(favourite.clinic_id)
        row = self._require_row(favourite.id)
        self._write(row, favourite)
        _add_library_row(self._session, row)

    def delete(self, favourite_id: UUID) -> None:
        self._delete_row(favourite_id)

    def get(self, favourite_id: UUID, *, for_update: bool = False) -> Favourite | None:
        query = self._scoped_select().where(RxFavouriteRow.id == favourite_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _favourite_from_row(row) if row else None

    def list_for_doctor(self, doctor_id: UUID) -> Sequence[Favourite]:
        query = (
            self._scoped_select()
            .where(RxFavouriteRow.doctor_id == doctor_id)
            .order_by(RxFavouriteRow.use_count.desc(), func.lower(RxFavouriteRow.name))
        )
        return [_favourite_from_row(row) for row in self._session.scalars(query)]

    def count_for_doctor(self, doctor_id: UUID) -> int:
        query = select(func.count()).where(
            RxFavouriteRow.clinic_id == self.clinic_id, RxFavouriteRow.doctor_id == doctor_id
        )
        return int(self._session.scalar(query) or 0)


class SqlAlchemyRxTemplateRepository(TenantScopedRepository[RxTemplateRow]):
    model = RxTemplateRow
    entity_name = "template"

    def _write(self, row: RxTemplateRow, template: Template) -> None:
        row.name = template.name
        row.items = [item_json(i) for i in template.items]
        row.advice = template.advice.as_json()
        row.follow_up_days = template.follow_up_days
        row.revision = template.revision
        row.use_count = template.use_count
        row.last_used_at = template.last_used_at
        row.updated_at = template.updated_at

    def add(self, template: Template) -> None:
        self._check_owned(template.clinic_id)
        row = RxTemplateRow(
            id=template.id,
            clinic_id=self.clinic_id,
            doctor_id=template.doctor_id,
            created_at=template.created_at,
        )
        self._write(row, template)
        _add_library_row(self._session, row)

    def update(self, template: Template) -> None:
        self._check_owned(template.clinic_id)
        row = self._require_row(template.id)
        self._write(row, template)
        _add_library_row(self._session, row)

    def delete(self, template_id: UUID) -> None:
        self._delete_row(template_id)

    def get(self, template_id: UUID, *, for_update: bool = False) -> Template | None:
        query = self._scoped_select().where(RxTemplateRow.id == template_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _template_from_row(row) if row else None

    def list_for_doctor(self, doctor_id: UUID) -> Sequence[Template]:
        query = (
            self._scoped_select()
            .where(RxTemplateRow.doctor_id == doctor_id)
            .order_by(RxTemplateRow.use_count.desc(), func.lower(RxTemplateRow.name))
        )
        return [_template_from_row(row) for row in self._session.scalars(query)]

    def count_for_doctor(self, doctor_id: UUID) -> int:
        query = select(func.count()).where(
            RxTemplateRow.clinic_id == self.clinic_id, RxTemplateRow.doctor_id == doctor_id
        )
        return int(self._session.scalar(query) or 0)


# --- Patient links and public rate limits (M4-P5) ------------------------------------------------


def _link_from_row(row: PatientLinkRow) -> PatientLink:
    return PatientLink(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        prescription_id=row.prescription_id,
        purpose=LinkPurpose(row.purpose),
        key_id=row.key_id,
        expires_at=_utc(row.expires_at),
        revoked_at=_utc_or_none(row.revoked_at),
        failed_challenges=row.failed_challenges,
        locked_at=_utc_or_none(row.locked_at),
        open_count=row.open_count,
        last_opened_at=_utc_or_none(row.last_opened_at),
        created_by=row.created_by,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _write_link(row: PatientLinkRow, link: PatientLink) -> None:
    row.revoked_at = link.revoked_at
    row.failed_challenges = link.failed_challenges
    row.locked_at = link.locked_at
    row.open_count = link.open_count
    row.last_opened_at = link.last_opened_at
    row.updated_at = link.updated_at


class SqlAlchemyPatientLinkRepository(TenantScopedRepository[PatientLinkRow]):
    model = PatientLinkRow
    entity_name = "patient link"

    def add(self, link: PatientLink) -> None:
        self._check_owned(link.clinic_id)
        row = PatientLinkRow(
            id=link.id,
            clinic_id=self.clinic_id,
            patient_id=link.patient_id,
            prescription_id=link.prescription_id,
            purpose=link.purpose.value,
            key_id=link.key_id,
            expires_at=link.expires_at,
            created_by=link.created_by,
            created_at=link.created_at,
        )
        _write_link(row, link)
        self._session.add(row)
        self._session.flush()

    def update(self, link: PatientLink) -> None:
        self._check_owned(link.clinic_id)
        _write_link(self._require_row(link.id), link)
        self._session.flush()

    def _one(self, query: Select[PatientLinkRow], for_update: bool) -> PatientLink | None:
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _link_from_row(row) if row else None

    def get(self, link_id: UUID, *, for_update: bool = False) -> PatientLink | None:
        return self._one(self._scoped_select().where(PatientLinkRow.id == link_id), for_update)

    def active_for_prescription(
        self, prescription_id: UUID, *, for_update: bool = False
    ) -> PatientLink | None:
        query = self._scoped_select().where(
            PatientLinkRow.prescription_id == prescription_id,
            PatientLinkRow.revoked_at.is_(None),
        )
        return self._one(query, for_update)


class SqlAlchemyRateLimitRepository:
    """Counts per bucket and minute in ``public_rate_limits`` (decision 4A); not tenant data."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def hit(self, bucket: str, *, window_start: datetime) -> int:
        values = insert(PublicRateLimitRow).values(bucket=bucket, window_start=window_start, hits=1)
        returning = values.on_conflict_do_update(
            index_elements=[PublicRateLimitRow.bucket, PublicRateLimitRow.window_start],
            set_={"hits": PublicRateLimitRow.hits + 1},
        ).returning(PublicRateLimitRow.hits)
        hits = int(self._session.execute(returning).scalar_one())
        self._session.execute(
            delete(PublicRateLimitRow).where(
                PublicRateLimitRow.window_start < window_start - timedelta(hours=1)
            )
        )
        return hits
