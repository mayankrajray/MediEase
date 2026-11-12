"""Encryption at rest for short secrets: push endpoints and keys (M7e-E2, ADR-0025).

The same Fernet keys and rotation as the phone cipher (``MESSAGING_PHONE_KEYS``): the first key
encrypts, every key decrypts, so rotating means putting a new key first. Ciphertext cannot be
searched; a device is found by its endpoint's digest instead.
"""

from __future__ import annotations

from collections.abc import Sequence

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class TextDecryptionFailed(ValueError):
    """The value was not encrypted with any of the configured keys."""


class FernetTextCipher:
    def __init__(self, keys: Sequence[bytes]) -> None:
        if not keys:
            raise ValueError("at least one key is required")
        self._fernet = MultiFernet([Fernet(key) for key in keys])

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise TextDecryptionFailed("push value could not be decrypted") from exc
