"""Fernet encryption of stored phone numbers (M5-P2 decision 1A; docs/SECURITY_AND_COMPLIANCE.md).

Keys come from ``MESSAGING_PHONE_KEYS`` (comma-separated Fernet keys): the first encrypts, every
key decrypts, so a key is rotated by putting a new one first and dropping the old one once no
stored row still needs it. Fernet is AES-128-CBC with HMAC-SHA256 and a timestamp; ciphertexts of
the same number differ, so the column cannot be searched or compared (inbound STOP in P5 matches
on a keyed hash instead).
"""

from __future__ import annotations

from collections.abc import Sequence

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from mediease_api.domain.shared.phone import PhoneNumber


class PhoneDecryptionFailed(ValueError):
    """No configured key opens the value (wrong key, or a corrupted row)."""


class FernetPhoneCipher:
    def __init__(self, keys: Sequence[bytes]) -> None:
        if not keys:
            raise ValueError("at least one phone encryption key is required")
        self._fernet = MultiFernet([Fernet(key) for key in keys])

    def encrypt(self, phone: PhoneNumber) -> str:
        return self._fernet.encrypt(phone.e164.encode("ascii")).decode("ascii")

    def decrypt(self, token: str) -> PhoneNumber:
        try:
            return PhoneNumber(self._fernet.decrypt(token.encode("ascii")).decode("ascii"))
        except (InvalidToken, UnicodeError):
            raise PhoneDecryptionFailed("the stored phone number cannot be decrypted") from None
