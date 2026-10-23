"""Portal sessions and audit, shared by the portal use cases and Google sign-in (ADR-0015).

A portal session is a refresh-token family in ``patient_refresh_tokens`` plus an access token
with the ``mediease-portal`` audience (decision 2). The staff verifier refuses that audience and
this one refuses ``mediease``, so neither kind of token works on the other's routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from mediease_api.application.auth.views import SessionTokens
from mediease_api.application.context import RequestInfo
from mediease_api.application.portal.views import PatientAccountView, PatientSessionResult
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.portal.account import PatientAccount
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import AccessTokenIssuer, RefreshTokenSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

ENTITY_TYPE = "patient_account"


@dataclass(frozen=True, slots=True)
class PatientSessionIssuer:
    """Creates a portal refresh token in a family and the matching portal access token."""

    ids: IdPort
    secrets: RefreshTokenSecrets
    access_tokens: AccessTokenIssuer
    refresh_ttl: timedelta

    def issue(
        self, uow: UnitOfWork, *, account_id: UUID, family_id: UUID, now: datetime
    ) -> tuple[RefreshToken, SessionTokens]:
        value = self.secrets.generate()
        refresh = RefreshToken.issue(
            id=self.ids.new_id(),
            user_id=account_id,
            family_id=family_id,
            token_hash=self.secrets.digest(value),
            now=now,
            ttl=self.refresh_ttl,
        )
        uow.patient_refresh_tokens.add(refresh)
        access = self.access_tokens.issue(user_id=account_id, session_id=family_id, now=now)
        return refresh, SessionTokens(
            access_token=access.value,
            access_expires_at=access.expires_at,
            refresh_token=value,
            refresh_expires_at=refresh.expires_at,
        )

    def start(
        self, uow: UnitOfWork, account: PatientAccount, *, now: datetime
    ) -> tuple[UUID, PatientSessionResult]:
        """A new family for ``account``: its ID (the session) and the result to return."""
        family_id = self.ids.new_id()
        _, tokens = self.issue(uow, account_id=account.id, family_id=family_id, now=now)
        return family_id, PatientSessionResult(PatientAccountView.of(account), tokens)


def record_patient_event(
    uow: UnitOfWork,
    ids: IdPort,
    *,
    action: AuditAction,
    account_id: UUID,
    info: RequestInfo,
    now: datetime,
    **metadata: str,
) -> None:
    """One audit row by the account about itself. IDs and enums only, never an email."""
    uow.audit.record(
        AuditEvent.record(
            id=ids.new_id(),
            action=action,
            actor_type=ActorType.PATIENT,
            now=now,
            entity_type=ENTITY_TYPE,
            entity_id=account_id,
            request_id=info.request_id,
            ip_hash=info.ip_hash,
            metadata=metadata,
        )
    )
