"""A prescription upload and its lifecycle (M7b; FR-UPL-01..05; spec prescription-uploads §3).

An upload is a temporary pointer, never a record: it holds the file only while it is scanned and
read (``quarantine_key``), then only IDs and a state. Rules enforced here, and again by the
database CHECKs of migration 0042:

- ``VERIFIED`` exactly when the prescription, its clinic, the access, ``verified_at`` and
  ``expires_at`` are set;
- ``REJECTED`` exactly when ``rejection_code`` is set;
- a file key only in ``QUARANTINED``, ``SCANNING`` and ``EXTRACTING``;
- ``candidate_id`` only in ``NEEDS_CHALLENGE``.

Every move that ends the file's life clears ``quarantine_key``; the use case deletes the blob it
read before the move. The domain never reads a clock.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.errors import InvalidTransition
from mediease_api.domain.shared.files import FileProblem, sniff
from mediease_api.domain.shared.time import require_utc
from mediease_api.domain.uploads.errors import (
    NotAwaitingChallenge,
    NotVerified,
    SelectionRequired,
    UploadFileRejected,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_CHALLENGES = 5
MAX_IN_FLIGHT = 3
GRANT_TTL = timedelta(hours=24)
ABANDON_AFTER = timedelta(hours=1)
CHALLENGE_TTL = timedelta(hours=24)
ROW_RETENTION = timedelta(days=30)


class UploadSource(StrEnum):
    FILE = "FILE"
    CODE = "CODE"


class UploadState(StrEnum):
    QUARANTINED = "QUARANTINED"
    SCANNING = "SCANNING"
    EXTRACTING = "EXTRACTING"
    NEEDS_CHALLENGE = "NEEDS_CHALLENGE"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


# The file exists only while it is being checked (R17).
FILE_STATES = frozenset({UploadState.QUARANTINED, UploadState.SCANNING, UploadState.EXTRACTING})
TERMINAL = frozenset({UploadState.VERIFIED, UploadState.REJECTED})


class Access(StrEnum):
    OWN = "OWN"  # one of the account's linked records (R10)
    REPRESENTATIVE = "REPRESENTATIVE"  # passed the prescription's last-4 check (R11)


class Rejection(StrEnum):
    INFECTED = "UPL_INFECTED"
    SCAN_UNAVAILABLE = "UPL_SCAN_UNAVAILABLE"
    NO_IDENTIFIER = "UPL_NO_IDENTIFIER"
    AMBIGUOUS = "UPL_AMBIGUOUS"
    UNREADABLE = "UPL_UNREADABLE"
    LOCKED = "UPL_LOCKED"
    ABANDONED = "UPL_ABANDONED"
    EXPIRED = "UPL_EXPIRED"
    WITHDRAWN = "UPL_WITHDRAWN"
    FILE_MISSING = "UPL_FILE_MISSING"


class Choice(StrEnum):
    UPLOADED = "UPLOADED"
    LATEST = "LATEST"


def quarantine_key(account_id: UUID, upload_id: UUID) -> str:
    """R1: the quarantine prefix; nothing else is ever stored under it."""
    return f"uploads/{account_id}/{upload_id}"


@dataclass(slots=True)
class PrescriptionUpload:
    id: UUID
    account_id: UUID
    source: UploadSource
    state: UploadState
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    quarantine_key: str | None
    candidate_id: UUID | None
    clinic_id: UUID | None
    prescription_id: UUID | None
    access: Access | None
    selected_id: UUID | None
    rejection_code: Rejection | None
    failed_challenges: int
    created_at: datetime
    updated_at: datetime
    verified_at: datetime | None = None
    expires_at: datetime | None = None
    finished_at: datetime | None = None

    # --- Creating (R1, R9) ----------------------------------------------------------------------

    @classmethod
    def receive(
        cls, *, id: UUID, account_id: UUID, data: bytes | None, now: datetime
    ) -> PrescriptionUpload:
        """A file, recognised by its bytes and held in quarantine."""
        now = require_utc(now, "now")
        kind = sniff(data, max_bytes=MAX_UPLOAD_BYTES)
        if isinstance(kind, FileProblem):
            raise UploadFileRejected(kind.value)
        assert data is not None
        return cls(
            id=id,
            account_id=account_id,
            source=UploadSource.FILE,
            state=UploadState.QUARANTINED,
            content_type=kind,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            quarantine_key=quarantine_key(account_id, id),
            candidate_id=None,
            clinic_id=None,
            prescription_id=None,
            access=None,
            selected_id=None,
            rejection_code=None,
            failed_challenges=0,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def typed(cls, *, id: UUID, account_id: UUID, now: datetime) -> PrescriptionUpload:
        """R9: a typed code: no file, so it starts where a file's identifier has been read."""
        now = require_utc(now, "now")
        return cls(
            id=id,
            account_id=account_id,
            source=UploadSource.CODE,
            state=UploadState.EXTRACTING,
            content_type=None,
            size_bytes=None,
            sha256=None,
            quarantine_key=None,
            candidate_id=None,
            clinic_id=None,
            prescription_id=None,
            access=None,
            selected_id=None,
            rejection_code=None,
            failed_challenges=0,
            created_at=now,
            updated_at=now,
        )

    # --- Reading ---------------------------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    @property
    def attempts_left(self) -> int:
        return max(MAX_CHALLENGES - self.failed_challenges, 0)

    def usable_prescription(self, now: datetime) -> UUID:
        """R13, R16: the selected version, while the grant lasts."""
        if self.state is not UploadState.VERIFIED or self.expires_at is None:
            raise NotVerified()
        if require_utc(now, "now") >= self.expires_at:
            raise NotVerified()
        if self.selected_id is None:
            raise SelectionRequired()
        return self.selected_id

    # --- Moving ---------------------------------------------------------------------------------

    def _move(self, allowed: frozenset[UploadState], to: UploadState, now: datetime) -> None:
        if self.state not in allowed:
            raise InvalidTransition("upload", self.state.value, to.value)
        self.state = to
        self.updated_at = require_utc(now, "now")
        if to not in FILE_STATES:
            self.quarantine_key = None
        if to in TERMINAL:
            self.finished_at = self.updated_at

    def start_scan(self, now: datetime) -> None:
        self._move(
            frozenset({UploadState.QUARANTINED, UploadState.SCANNING}), UploadState.SCANNING, now
        )

    def scanned_clean(self, now: datetime) -> None:
        self._move(frozenset({UploadState.SCANNING}), UploadState.EXTRACTING, now)

    def verify(
        self,
        *,
        access: Access,
        clinic_id: UUID,
        prescription_id: UUID,
        current: bool,
        now: datetime,
    ) -> None:
        """R10, R11, R15: verified as this exact version; a superseded one waits for a choice."""
        allowed = (
            frozenset({UploadState.EXTRACTING})
            if access is Access.OWN
            else frozenset({UploadState.NEEDS_CHALLENGE})
        )
        self._move(allowed, UploadState.VERIFIED, now)
        self.access = access
        self.clinic_id = clinic_id
        self.prescription_id = prescription_id
        self.selected_id = prescription_id if current else None
        self.candidate_id = None
        self.verified_at = self.updated_at
        self.expires_at = self.updated_at + GRANT_TTL

    def needs_challenge(self, candidate_id: UUID, now: datetime) -> None:
        """R11: identified, but not one of the account's records."""
        self._move(frozenset({UploadState.EXTRACTING}), UploadState.NEEDS_CHALLENGE, now)
        self.candidate_id = candidate_id

    def challenge_failed(self, now: datetime) -> int:
        """R12: one more wrong answer; the fifth rejects the upload. Returns the attempts left."""
        if self.state is not UploadState.NEEDS_CHALLENGE:
            raise NotAwaitingChallenge()
        self.failed_challenges += 1
        self.updated_at = require_utc(now, "now")
        if self.failed_challenges >= MAX_CHALLENGES:
            self.reject(Rejection.LOCKED, now)
        return self.attempts_left

    def reject(self, code: Rejection, now: datetime) -> None:
        if self.is_terminal:
            raise InvalidTransition("upload", self.state.value, UploadState.REJECTED.value)
        self._move(frozenset(UploadState) - TERMINAL, UploadState.REJECTED, now)
        self.rejection_code = code
        self.candidate_id = None

    def withdraw(self, now: datetime) -> None:
        """R17: the user deletes it: the file goes and any grant ends."""
        if self.state is UploadState.REJECTED:
            return
        self.state = UploadState.REJECTED
        self.updated_at = self.finished_at = require_utc(now, "now")
        self.rejection_code = Rejection.WITHDRAWN
        self.quarantine_key = None
        self.candidate_id = None
        self.clinic_id = self.prescription_id = self.selected_id = None
        self.access = None
        self.verified_at = self.expires_at = None

    def choose(self, choice: Choice, *, latest_id: UUID, now: datetime) -> None:
        """R15: the uploaded (historical) version or the latest; it can be changed."""
        if self.state is not UploadState.VERIFIED or self.prescription_id is None:
            raise NotVerified()
        self.selected_id = self.prescription_id if choice is Choice.UPLOADED else latest_id
        self.updated_at = require_utc(now, "now")

    def stale(self, now: datetime) -> Rejection | None:
        """R18: why the sweep should end it now, if it should."""
        now = require_utc(now, "now")
        if self.state in FILE_STATES and now - self.created_at >= ABANDON_AFTER:
            return Rejection.ABANDONED
        if self.state is UploadState.NEEDS_CHALLENGE and now - self.updated_at >= CHALLENGE_TTL:
            return Rejection.EXPIRED
        return None

    def copy(self) -> PrescriptionUpload:
        return replace(self)
