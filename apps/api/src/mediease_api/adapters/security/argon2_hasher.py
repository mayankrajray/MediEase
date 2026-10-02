"""Argon2id password hashing (FR-AUTH-01) with argon2-cffi.

Production parameters are argon2-cffi's defaults, the RFC 9106 "low memory"
profile: 3 passes over 64 MiB with 4 lanes, a 16-byte random salt and a 32-byte
tag — roughly 50 ms per hash on a server core. Tests pass cheaper parameters.
"""

from __future__ import annotations

from argon2 import PasswordHasher as _Argon2
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class Argon2PasswordHasher:
    def __init__(
        self,
        *,
        time_cost: int | None = None,
        memory_cost_kib: int | None = None,
        parallelism: int | None = None,
    ) -> None:
        defaults = _Argon2()
        self._hasher = _Argon2(
            time_cost=time_cost or defaults.time_cost,
            memory_cost=memory_cost_kib or defaults.memory_cost,
            parallelism=parallelism or defaults.parallelism,
            type=Type.ID,
        )

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True
