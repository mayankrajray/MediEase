"""SQLAlchemy repositories for patient accounts, portal sessions and Google identities (M6a-P3).

Platform repositories (ADR-0003): none of these rows is tenant data. The portal refresh-token
repository has the same shape as the staff one (``RefreshTokenRepository``) over its own table,
with the owning account's ID in the domain's ``user_id``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models import (
    EmailTokenRow,
    ExternalIdentityRow,
    PatientAccountRow,
    PatientRefreshTokenRow,
)
from mediease_api.domain.identity.email_token import EmailToken, EmailTokenPurpose
from mediease_api.domain.identity.external import ExternalIdentity, IdentityProvider
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.account import (
    AccountStatus,
    EmailTaken,
    PatientAccount,
    SignInMethod,
)
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import NotFound

_PASSWORD_EMAIL_INDEX = "uq_patient_accounts_password_email"


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _utc_or_none(value: datetime | None) -> datetime | None:
    return _utc(value) if value is not None else None


# --- Patient accounts ------------------------------------------------------------------------


def _account_from_row(row: PatientAccountRow) -> PatientAccount:
    return PatientAccount(
        id=row.id,
        full_name=row.full_name,
        email=EmailAddress(row.email),
        sign_in_method=SignInMethod(row.sign_in_method),
        status=AccountStatus(row.status),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        email_verified_at=_utc_or_none(row.email_verified_at),
        password_hash=row.password_hash,
        failed_sign_in_count=row.failed_login_count,
        locked_until=_utc_or_none(row.locked_until),
        last_signed_in_at=_utc_or_none(row.last_login_at),
        language=Language(row.language),
    )


def _write_account(row: PatientAccountRow, account: PatientAccount) -> None:
    row.full_name = account.full_name
    row.email = account.email.value
    row.email_verified_at = account.email_verified_at
    row.sign_in_method = account.sign_in_method.value
    row.status = account.status.value
    row.password_hash = account.password_hash
    row.failed_login_count = account.failed_sign_in_count
    row.locked_until = account.locked_until
    row.last_login_at = account.last_signed_in_at
    row.language = account.language.value
    row.updated_at = account.updated_at


class SqlAlchemyPatientAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, account: PatientAccount) -> None:
        row = PatientAccountRow(id=account.id, created_at=account.created_at)
        _write_account(row, account)
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            if _PASSWORD_EMAIL_INDEX in str(exc.orig):
                raise EmailTaken() from None
            raise

    def get(self, account_id: UUID, *, for_update: bool = False) -> PatientAccount | None:
        return self._one(
            select(PatientAccountRow).where(PatientAccountRow.id == account_id), for_update
        )

    def get_password_account(
        self, email: EmailAddress, *, for_update: bool = False
    ) -> PatientAccount | None:
        query = select(PatientAccountRow).where(
            PatientAccountRow.email == email.value,
            PatientAccountRow.sign_in_method == SignInMethod.PASSWORD.value,
        )
        return self._one(query, for_update)

    def find_google_account(self, email: EmailAddress) -> PatientAccount | None:
        query = (
            select(PatientAccountRow)
            .where(
                PatientAccountRow.email == email.value,
                PatientAccountRow.sign_in_method == SignInMethod.GOOGLE.value,
            )
            .order_by(PatientAccountRow.created_at)
            .limit(1)
        )
        row = self._session.scalars(query).first()
        return _account_from_row(row) if row else None

    def update(self, account: PatientAccount) -> None:
        row = self._session.get(PatientAccountRow, account.id)
        if row is None:
            raise NotFound("patient account")
        _write_account(row, account)
        self._session.flush()

    def _one(self, query: Select[PatientAccountRow], for_update: bool) -> PatientAccount | None:
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _account_from_row(row) if row else None


# --- Portal refresh tokens -------------------------------------------------------------------


def _token_from_row(row: PatientRefreshTokenRow) -> RefreshToken:
    return RefreshToken(
        id=row.id,
        user_id=row.account_id,
        family_id=row.family_id,
        token_hash=row.token_hash,
        expires_at=_utc(row.expires_at),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        revoked_at=_utc_or_none(row.revoked_at),
        replaced_by_id=row.replaced_by_id,
    )


class SqlAlchemyPatientRefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: RefreshToken) -> None:
        self._session.add(
            PatientRefreshTokenRow(
                id=token.id,
                account_id=token.user_id,
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
        query = select(PatientRefreshTokenRow).where(
            PatientRefreshTokenRow.token_hash == token_hash
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _token_from_row(row) if row else None

    def update(self, token: RefreshToken) -> None:
        row = self._session.get(PatientRefreshTokenRow, token.id)
        if row is None:
            raise NotFound("refresh token")
        row.revoked_at = token.revoked_at
        row.replaced_by_id = token.replaced_by_id
        row.updated_at = token.updated_at
        self._session.flush()

    def revoke_family(self, family_id: UUID, *, now: datetime) -> int:
        result = self._session.execute(
            update(PatientRefreshTokenRow)
            .where(
                PatientRefreshTokenRow.family_id == family_id,
                PatientRefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def is_family_live(self, family_id: UUID, *, now: datetime) -> bool:
        query = select(
            exists().where(
                PatientRefreshTokenRow.family_id == family_id,
                PatientRefreshTokenRow.revoked_at.is_(None),
                PatientRefreshTokenRow.expires_at > now,
            )
        )
        return bool(self._session.scalar(query))

    def revoke_all_for_owner(self, owner_id: UUID, *, now: datetime) -> int:
        result = self._session.execute(
            update(PatientRefreshTokenRow)
            .where(
                PatientRefreshTokenRow.account_id == owner_id,
                PatientRefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]


# --- Email tokens (M6a-P4) -------------------------------------------------------------------


def _email_token_from_row(row: EmailTokenRow) -> EmailToken:
    return EmailToken(
        id=row.id,
        purpose=EmailTokenPurpose(row.purpose),
        user_id=row.user_id,
        patient_account_id=row.patient_account_id,
        email=EmailAddress(row.email),
        token_hash=row.token_hash,
        expires_at=_utc(row.expires_at),
        created_at=_utc(row.created_at),
        used_at=_utc_or_none(row.used_at),
        superseded_at=_utc_or_none(row.superseded_at),
    )


class SqlAlchemyEmailTokenRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: EmailToken) -> None:
        self._session.add(
            EmailTokenRow(
                id=token.id,
                purpose=token.purpose.value,
                user_id=token.user_id,
                patient_account_id=token.patient_account_id,
                email=token.email.value,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                created_at=token.created_at,
                used_at=token.used_at,
                superseded_at=token.superseded_at,
            )
        )
        self._session.flush()

    def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> EmailToken | None:
        query = select(EmailTokenRow).where(EmailTokenRow.token_hash == token_hash)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _email_token_from_row(row) if row else None

    def update(self, token: EmailToken) -> None:
        row = self._session.get(EmailTokenRow, token.id)
        if row is None:
            raise NotFound("email token")
        row.used_at = token.used_at
        row.superseded_at = token.superseded_at
        self._session.flush()

    def supersede_active(
        self, *, purpose: EmailTokenPurpose, owner_id: UUID, staff: bool, now: datetime
    ) -> int:
        owner = EmailTokenRow.user_id if staff else EmailTokenRow.patient_account_id
        result = self._session.execute(
            update(EmailTokenRow)
            .where(
                owner == owner_id,
                EmailTokenRow.purpose == purpose.value,
                EmailTokenRow.used_at.is_(None),
                EmailTokenRow.superseded_at.is_(None),
                EmailTokenRow.expires_at > now,
            )
            .values(superseded_at=now)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]


# --- External identities ---------------------------------------------------------------------


def _identity_from_row(row: ExternalIdentityRow) -> ExternalIdentity:
    return ExternalIdentity(
        id=row.id,
        provider=IdentityProvider(row.provider),
        subject=row.subject,
        user_id=row.user_id,
        patient_account_id=row.patient_account_id,
        created_at=_utc(row.created_at),
        last_used_at=_utc(row.last_used_at),
    )


class SqlAlchemyExternalIdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, identity: ExternalIdentity) -> None:
        self._session.add(
            ExternalIdentityRow(
                id=identity.id,
                provider=identity.provider.value,
                subject=identity.subject,
                user_id=identity.user_id,
                patient_account_id=identity.patient_account_id,
                created_at=identity.created_at,
                last_used_at=identity.last_used_at,
            )
        )
        self._session.flush()

    def get_for_staff(
        self, provider: IdentityProvider, subject: str, *, for_update: bool = False
    ) -> ExternalIdentity | None:
        return self._one(provider, subject, ExternalIdentityRow.user_id.is_not(None), for_update)

    def get_for_patient(
        self, provider: IdentityProvider, subject: str, *, for_update: bool = False
    ) -> ExternalIdentity | None:
        return self._one(
            provider, subject, ExternalIdentityRow.patient_account_id.is_not(None), for_update
        )

    def update(self, identity: ExternalIdentity) -> None:
        row = self._session.get(ExternalIdentityRow, identity.id)
        if row is None:
            raise NotFound("external identity")
        row.last_used_at = identity.last_used_at
        self._session.flush()

    def _one(
        self, provider: IdentityProvider, subject: str, owner: object, for_update: bool
    ) -> ExternalIdentity | None:
        query = select(ExternalIdentityRow).where(
            ExternalIdentityRow.provider == provider.value,
            ExternalIdentityRow.subject == subject,
            owner,  # type: ignore[arg-type]
        )
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _identity_from_row(row) if row else None
