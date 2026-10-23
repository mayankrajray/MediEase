"""What the portal use cases return. ``tokens`` are secrets: delivery puts them in cookies only."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from mediease_api.application.auth.views import SessionTokens
from mediease_api.domain.portal.account import PatientAccount, SignInMethod


@dataclass(frozen=True, slots=True)
class PatientAccountView:
    id: UUID
    full_name: str
    email: str
    sign_in_method: SignInMethod
    email_verified: bool

    @classmethod
    def of(cls, account: PatientAccount) -> PatientAccountView:
        return cls(
            id=account.id,
            full_name=account.full_name,
            email=account.email.value,
            sign_in_method=account.sign_in_method,
            email_verified=account.is_email_verified,
        )


@dataclass(frozen=True, slots=True)
class PatientSessionResult:
    account: PatientAccountView
    tokens: SessionTokens


@dataclass(frozen=True, slots=True)
class PatientPrincipal:
    """An authenticated portal caller: the account and the session (refresh family)."""

    account: PatientAccount
    session_id: UUID

    @property
    def account_id(self) -> UUID:
        return self.account.id
