"""The password policy (FR-AUTH-01, M1-P5).

One rule, in the domain, applied wherever a password is *chosen* — today when
an invited member accepts their invitation, later when ops resets one. Sign-in
does not call it: an existing password must keep working even if the policy
tightens, and the hash is upgraded instead (M1-P2).

Length only. Composition rules (a digit, a symbol, mixed case) push people
towards `Clinic@123` and are no longer recommended (NIST SP 800-63B); 12
characters of anything is a better floor for a clinic's front desk.
"""

from __future__ import annotations

from mediease_api.domain.shared.errors import InvalidValue

MIN_PASSWORD_LENGTH = 12
# The sign-in boundary already caps the length; the same cap applies here, so a
# hostile value cannot make hashing arbitrarily expensive.
MAX_PASSWORD_LENGTH = 1024


def validate_password(password: str, *, field: str = "password") -> str:
    """The password as given, or ``InvalidValue``. Never echoed back in the error."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidValue(field, f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidValue(field, f"must be at most {MAX_PASSWORD_LENGTH} characters")
    if not password.strip():
        raise InvalidValue(field, "must not be only spaces")
    return password
