"""Single-use email tokens (M6a-P4, ADR-0016 decision 5)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from mediease_api.domain.identity.email_token import (
    EmailToken,
    EmailTokenPurpose,
    EmailTokenState,
    TokenExpired,
    TokenInvalid,
)
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, new_id

EMAIL = EmailAddress.parse("asha@example.test")
RESET = EmailTokenPurpose.RESET_PASSWORD


def _token(purpose: EmailTokenPurpose = RESET) -> EmailToken:
    return EmailToken.issue(
        id=new_id(), purpose=purpose, email=EMAIL, token_hash="digest", now=NOW, user_id=new_id()
    )


def test_fr_auth_05_a_reset_link_lasts_30_minutes_and_a_verification_24_hours() -> None:
    assert _token().expires_at == NOW + timedelta(minutes=30)
    assert _token(EmailTokenPurpose.VERIFY_EMAIL).expires_at == NOW + timedelta(hours=24)
    assert "digest" not in repr(_token())


def test_adr_0016_a_token_is_used_once() -> None:
    token = _token()
    token.check_usable(purpose=RESET, email=EMAIL, now=NOW)
    token.use(now=NOW)
    assert token.state(NOW) is EmailTokenState.USED
    with pytest.raises(TokenInvalid):
        token.check_usable(purpose=RESET, email=EMAIL, now=NOW)
    with pytest.raises(TokenInvalid):
        token.use(now=NOW)


def test_adr_0016_expired_superseded_another_purpose_or_another_address_are_refused() -> None:
    token = _token()
    with pytest.raises(TokenExpired):
        token.check_usable(purpose=RESET, email=EMAIL, now=NOW + timedelta(minutes=30))
    with pytest.raises(TokenInvalid):
        token.check_usable(purpose=EmailTokenPurpose.VERIFY_EMAIL, email=EMAIL, now=NOW)
    with pytest.raises(TokenInvalid):
        token.check_usable(purpose=RESET, email=EmailAddress.parse("moved@example.test"), now=NOW)
    token.superseded_at = NOW
    assert token.state(NOW) is EmailTokenState.SUPERSEDED
    with pytest.raises(TokenInvalid):
        token.check_usable(purpose=RESET, email=EMAIL, now=NOW)


def test_a_token_belongs_to_exactly_one_kind_of_account() -> None:
    with pytest.raises(InvalidValue):
        EmailToken.issue(id=new_id(), purpose=RESET, email=EMAIL, token_hash="d", now=NOW)
    with pytest.raises(InvalidValue):
        EmailToken.issue(
            id=new_id(),
            purpose=RESET,
            email=EMAIL,
            token_hash="d",
            now=NOW,
            user_id=new_id(),
            patient_account_id=new_id(),
        )
