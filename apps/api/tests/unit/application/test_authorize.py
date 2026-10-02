"""Per-request authentication, clinic resolution and permissions (FR-AUTH-03; R6, R7, R10, AC4).

Uses the same in-memory harness as the sign-in tests: a real access token is
issued by signing in, then handed to ``AuthenticateRequest`` the way the
access hook does on every request.
"""

from __future__ import annotations

import pytest

from mediease_api.application.auth.authenticate import resolve_clinic
from mediease_api.application.auth.errors import (
    AccountDisabled,
    ClinicRequired,
    ClinicSuspended,
    PermissionDenied,
    SessionExpired,
)
from mediease_api.application.context import RequestContext
from mediease_api.application.identity.me import me_view
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.permissions import Permission
from tests.conftest import LogReader
from tests.unit.application.harness import Auth

# --- Authentication (who) --------------------------------------------------------------------


def test_fr_auth_03_valid_access_token_yields_the_principal(auth: Auth) -> None:
    user = auth.add_user(clinics=2, role=Role.FRONT_DESK)
    principal = auth.authenticate.execute(auth.signed_in(user))

    assert principal.user_id == user.id
    assert not principal.is_platform_ops
    assert [a.clinic_name for a in principal.access] == ["Sample Clinic 0", "Sample Clinic 1"]
    assert principal.access[0].role is Role.FRONT_DESK


@pytest.mark.parametrize("token", [None, "", "access-999", "garbage"])
def test_missing_or_unknown_access_token_is_session_expired(auth: Auth, token: str | None) -> None:
    auth.add_user()
    with pytest.raises(SessionExpired) as excinfo:
        auth.authenticate.execute(token)
    assert excinfo.value.code == "AUTH_SESSION_EXPIRED"


def test_expired_access_token_is_session_expired(auth: Auth) -> None:
    user = auth.add_user()
    token = auth.signed_in(user)
    auth.clock.advance(minutes=16)
    with pytest.raises(SessionExpired):
        auth.authenticate.execute(token)


def test_r7_signing_out_ends_access_before_the_token_expires(auth: Auth) -> None:
    user = auth.add_user()
    result = auth.session_of(user)
    auth.sign_out.execute(result.tokens.refresh_token)

    with pytest.raises(SessionExpired):
        auth.authenticate.execute(result.tokens.access_token)


def test_r7_disabled_user_is_rejected_on_the_next_request(auth: Auth) -> None:
    user = auth.add_user()
    token = auth.signed_in(user)
    auth.stored(user).disable(now=auth.clock.now())

    with pytest.raises(AccountDisabled) as excinfo:
        auth.authenticate.execute(token)
    assert excinfo.value.code == "AUTH_ACCOUNT_DISABLED"


def test_ac4_fr_org_04_deactivated_membership_is_rejected_on_the_next_request(
    auth: Auth, json_logs: LogReader
) -> None:
    user = auth.add_user(role=Role.FRONT_DESK)
    token = auth.signed_in(user)
    auth.access_of(user).clear()  # the owner deactivated them a moment ago
    json_logs()

    with pytest.raises(AccountDisabled):
        auth.authenticate.execute(token)
    rejected = [e for e in json_logs() if e["event"] == "auth.rejected"]
    assert [e["reason"] for e in rejected] == ["account_disabled"]
    assert rejected[0]["user_id"] == str(user.id)


def test_r10_platform_ops_without_a_membership_is_authenticated(auth: Auth) -> None:
    user = auth.add_user(clinics=0, is_platform_ops=True)
    principal = auth.authenticate.execute(auth.signed_in(user))
    assert principal.is_platform_ops and principal.access == ()


# --- Clinic resolution (where, R6) -----------------------------------------------------------


def test_r6_single_membership_needs_no_header(auth: Auth) -> None:
    user = auth.add_user()
    principal = auth.authenticate.execute(auth.signed_in(user))
    assert resolve_clinic(principal, None).clinic_id == auth.clinic_ids(user)[0]


def test_r6_header_chooses_between_several_clinics(auth: Auth) -> None:
    user = auth.add_user(clinics=2)
    principal = auth.authenticate.execute(auth.signed_in(user))
    wanted = auth.clinic_ids(user)[1]
    assert resolve_clinic(principal, str(wanted)).clinic_id == wanted


@pytest.mark.parametrize(
    ("clinics", "header"),
    [
        (2, None),  # several memberships, no choice made
        (1, "not-a-uuid"),  # malformed header
        (1, "00000000-0000-0000-0000-000000000001"),  # a clinic this user has no membership in
    ],
    ids=["ambiguous", "malformed", "foreign"],
)
def test_r6_ambiguous_or_foreign_clinic_is_clinic_required(
    auth: Auth, clinics: int, header: str | None
) -> None:
    user = auth.add_user(clinics=clinics)
    principal = auth.authenticate.execute(auth.signed_in(user))
    with pytest.raises(ClinicRequired) as excinfo:
        resolve_clinic(principal, header)
    # Identical answer whether or not that clinic exists.
    assert excinfo.value.code == "PERM_CLINIC_REQUIRED"
    assert excinfo.value.details == {}


def test_suspended_clinic_is_refused_with_its_own_code(auth: Auth) -> None:
    user = auth.add_user(clinic_status=ClinicStatus.SUSPENDED)
    principal = auth.authenticate.execute(auth.signed_in(user))
    with pytest.raises(ClinicSuspended) as excinfo:
        resolve_clinic(principal, None)
    assert excinfo.value.code == "CLN_SUSPENDED"


def test_r10_platform_ops_cannot_use_a_clinic_route(auth: Auth, json_logs: LogReader) -> None:
    user = auth.add_user(is_platform_ops=True)  # even with a membership
    principal = auth.authenticate.execute(auth.signed_in(user))
    json_logs()

    with pytest.raises(PermissionDenied) as excinfo:
        resolve_clinic(principal, None)
    assert excinfo.value.code == "PERM_DENIED"
    assert any(e["event"] == "perm.denied" for e in json_logs())


# --- Permissions (what) ----------------------------------------------------------------------


def _context(auth: Auth, role: Role, **kwargs: object) -> RequestContext:
    user = auth.add_user(role=role, **kwargs)
    principal = auth.authenticate.execute(auth.signed_in(user))
    return RequestContext.of(principal, resolve_clinic(principal, None), request_id="req-1")


def test_fr_auth_03_context_carries_the_members_permissions(auth: Auth) -> None:
    ctx = _context(auth, Role.OWNER)
    assert ctx.role is Role.OWNER
    assert ctx.allows(Permission.STAFF_MANAGE)
    ctx.require(Permission.STAFF_MANAGE)  # does not raise


def test_fr_auth_03_require_refuses_a_permission_the_role_lacks(auth: Auth) -> None:
    ctx = _context(auth, Role.FRONT_DESK)
    with pytest.raises(PermissionDenied) as excinfo:
        ctx.require(Permission.STAFF_MANAGE)
    assert excinfo.value.details == {"permission": "STAFF_MANAGE", "role": "FRONT_DESK"}


def test_spec_8_owner_with_a_doctor_profile_may_write_clinical_records(auth: Auth) -> None:
    ctx = _context(auth, Role.OWNER, has_doctor_profile=True)
    ctx.require(Permission.CLINICAL_WRITE)


# --- /me -------------------------------------------------------------------------------------


def test_fr_auth_03_me_view_lists_each_membership_with_role_and_permissions(auth: Auth) -> None:
    user = auth.add_user(clinics=2, role=Role.DOCTOR)
    principal = auth.authenticate.execute(auth.signed_in(user))

    view = me_view(principal)
    assert view.user.id == user.id
    assert [m.clinic_name for m in view.memberships] == ["Sample Clinic 0", "Sample Clinic 1"]
    first = view.memberships[0]
    assert first.role is Role.DOCTOR
    assert first.clinic_status is ClinicStatus.ACTIVE
    assert Permission.CLINICAL_WRITE in first.permissions
    assert Permission.STAFF_MANAGE not in first.permissions
    assert list(first.permissions) == sorted(first.permissions)
