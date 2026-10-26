"""Repository ports: how the application loads and saves domain entities.

Two kinds (ADR-0003, ARCHITECTURE.md §6):

- **Platform repositories** (``ClinicRepository``, ``UserRepository``) hold rows
  that are not owned by one clinic: the clinics themselves, and users, who may
  work at several clinics. They never return clinical content.
- **Tenant repositories** (``DoctorRepository``, ``MembershipRepository``) are
  bound to one clinic when the unit of work creates them. No method takes a
  clinic ID, so a query for another clinic cannot be expressed: another
  clinic's row is simply not found (spec R8 → ``REQ_NOT_FOUND``).

``add`` stores a new entity; ``update`` saves a changed one and raises
``NotFound`` if it is not (or no longer) visible to the repository. Changes are
durable only after ``UnitOfWork.commit``.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from mediease_api.domain.appointments.appointment import Appointment, StatusChange
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.onboarding import OnboardingChecklist
from mediease_api.domain.identity.access import ClinicAccess, StaffMember
from mediease_api.domain.identity.email_token import EmailToken, EmailTokenPurpose
from mediease_api.domain.identity.external import ExternalIdentity, IdentityProvider
from mediease_api.domain.identity.membership import ClinicMembership
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.identity.user import User
from mediease_api.domain.links.link import PatientLink
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.portal.account import PatientAccount
from mediease_api.domain.prescriptions.library import Favourite, Template
from mediease_api.domain.prescriptions.prescription import IssuedVersion, Prescription
from mediease_api.domain.prescriptions.suggestions import HistoryName
from mediease_api.domain.scheduling.blocks import WeeklyBlock
from mediease_api.domain.scheduling.exceptions import ScheduleException
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.visits.attachment import VisitAttachment
from mediease_api.domain.visits.visit import Visit, VisitAddendum


@dataclass(frozen=True, slots=True)
class PatientMatch:
    """How *My Patients* narrows its list: exactly one of the three, as the lookup box parses."""

    phone_e164: str | None = None
    code: str | None = None
    name_prefix: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class SeenPatient:
    """A patient one doctor has seen (M6a-P6): no clinical content, just when and how often."""

    patient: Patient
    last_visit_at: datetime
    visits: int

    def __repr__(self) -> str:
        return f"SeenPatient(code={self.patient.code!r}, visits={self.visits})"


class RowLock(StrEnum):
    """How a read locks its row until the unit of work ends (spec appointments R20)."""

    UPDATE = "UPDATE"  # exclusive: a change that others must wait for
    SHARE = "SHARE"  # shared: readers run together, but never alongside an UPDATE lock


# --- Platform repositories ---------------------------------------------------------------


class ClinicRepository(Protocol):
    def add(self, clinic: Clinic) -> None: ...
    def get(self, clinic_id: UUID, *, for_update: bool = False) -> Clinic | None:
        """``for_update`` locks the clinic row until the unit of work ends.

        Registering a patient takes this lock first, which serialises the duplicate-phone
        check and the code counter per clinic (spec patients R9).
        """
        ...

    def get_by_slug(self, slug: str) -> Clinic | None: ...
    def list_listed(self, *, limit: int) -> Sequence[Clinic]:
        """M6c-P5: listed, ``ACTIVE`` and verified clinics, by slug (the sitemap's candidates)."""
        ...

    def update(self, clinic: Clinic) -> None: ...
    def list_onboarding(self) -> Sequence[tuple[Clinic, OnboardingChecklist | None]]:
        """Every clinic with its checklist, newest first — the ops console list (FR-OPS-01).

        A deliberate cross-clinic read for platform staff (ADR-0003): clinics
        are not tenant-owned, and no clinical content is involved.
        """
        ...


class UserRepository(Protocol):
    def add(self, user: User) -> None: ...
    def get(self, user_id: UUID, *, for_update: bool = False) -> User | None: ...
    def get_by_email(self, email: EmailAddress, *, for_update: bool = False) -> User | None:
        """``for_update`` locks the row until the unit of work ends (sign-in counting)."""
        ...

    def get_by_phone(self, phone: PhoneNumber, *, for_update: bool = False) -> User | None: ...
    def update(self, user: User) -> None: ...


class RefreshTokenRepository(Protocol):
    """Refresh tokens are owned by users, not clinics (platform repository)."""

    def add(self, token: RefreshToken) -> None: ...
    def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> RefreshToken | None: ...
    def update(self, token: RefreshToken) -> None: ...
    def revoke_family(self, family_id: UUID, *, now: datetime) -> int:
        """Revoke every not-yet-revoked token in the family; returns how many."""
        ...

    def is_family_live(self, family_id: UUID, *, now: datetime) -> bool:
        """True while the session has an unrevoked, unexpired token (checked per request)."""
        ...

    def revoke_all_for_owner(self, owner_id: UUID, *, now: datetime) -> int:
        """End every session of one user or account (a password reset, M6a-P4); returns how many."""
        ...


class EmailTokenRepository(Protocol):
    """Verification and reset tokens (M6a-P4, ADR-0016); found by digest, not by clinic."""

    def add(self, token: EmailToken) -> None: ...
    def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> EmailToken | None: ...
    def update(self, token: EmailToken) -> None: ...
    def supersede_active(
        self, *, purpose: EmailTokenPurpose, owner_id: UUID, staff: bool, now: datetime
    ) -> int:
        """Retire the owner's unused, unexpired tokens of ``purpose``; returns how many."""
        ...


class PatientAccountRepository(Protocol):
    """Patient portal accounts (M6a-P3, ADR-0015). Platform data, never tenant data."""

    def add(self, account: PatientAccount) -> None:
        """Raises ``EmailTaken`` when a password account already uses the email."""
        ...

    def get(self, account_id: UUID, *, for_update: bool = False) -> PatientAccount | None: ...
    def get_password_account(
        self, email: EmailAddress, *, for_update: bool = False
    ) -> PatientAccount | None:
        """The ``PASSWORD`` account with this email (unique among them), if any."""
        ...

    def find_google_account(self, email: EmailAddress) -> PatientAccount | None:
        """A ``GOOGLE`` account with this email, if any (a reset asked for it gets a notice)."""
        ...

    def update(self, account: PatientAccount) -> None: ...


class ExternalIdentityRepository(Protocol):
    """Google identities linked to a staff user or a patient account (M6a-P3, decision 4)."""

    def add(self, identity: ExternalIdentity) -> None: ...
    def get_for_staff(
        self, provider: IdentityProvider, subject: str, *, for_update: bool = False
    ) -> ExternalIdentity | None: ...
    def get_for_patient(
        self, provider: IdentityProvider, subject: str, *, for_update: bool = False
    ) -> ExternalIdentity | None: ...
    def update(self, identity: ExternalIdentity) -> None: ...


class ClinicAccessRepository(Protocol):
    """Which clinics a user may work in — a deliberate cross-clinic read (ADR-0003).

    Platform repository keyed by user: it returns IDs, clinic names and roles
    only, never tenant content.
    """

    def list_active_for_user(self, user_id: UUID) -> Sequence[ClinicAccess]:
        """The user's ``ACTIVE`` memberships with their clinic, ordered by clinic name."""
        ...


class StaffInviteRepository(Protocol):
    """Finds the membership a pending invitation belongs to (M1-P5).

    Keyed by the digest of a 256-bit secret, like ``RefreshTokenRepository``:
    the invitee has no session and no clinic context yet, so this read cannot
    be clinic-scoped (ADR-0003 "platform repositories"). Writes go through the
    tenant-scoped ``MembershipRepository``.
    """

    def get_by_invite_digest(self, token_hash: str) -> ClinicMembership | None: ...


# --- Tenant repositories (bound to one clinic) ---------------------------------------------


class DoctorRepository(Protocol):
    def add(self, doctor: Doctor) -> None: ...
    def get(self, doctor_id: UUID, *, lock: RowLock | None = None) -> Doctor | None:
        """``lock`` serialises schedule changes and session generation per doctor (R20)."""
        ...

    def get_for_user(self, user_id: UUID) -> Doctor | None:
        """This clinic's doctor profile for ``user_id``, if the account is linked to one.

        At most one exists: a partial unique index enforces one profile per user
        per clinic (spec §8 "owner who is also a doctor").
        """
        ...

    def list(self) -> Sequence[Doctor]:
        """All of this clinic's doctors, oldest first."""
        ...

    def update(self, doctor: Doctor) -> None: ...


class MembershipRepository(Protocol):
    def add(self, membership: ClinicMembership) -> None: ...
    def get(self, membership_id: UUID) -> ClinicMembership | None: ...
    def get_for_user(self, user_id: UUID) -> ClinicMembership | None:
        """This clinic's membership for ``user_id`` (at most one, invariant I2)."""
        ...

    def list(self) -> Sequence[ClinicMembership]:
        """All of this clinic's memberships, oldest first."""
        ...

    def count_active_owners(self) -> int:
        """Active ``OWNER`` memberships, for I1 and R9."""
        ...

    def list_staff(self) -> Sequence[StaffMember]:
        """Every membership of this clinic with the member's name, ordered by name."""
        ...

    def update(self, membership: ClinicMembership) -> None: ...


class ChecklistRepository(Protocol):
    """This clinic's onboarding checklist (FR-OPS-04, spec R12). One row per clinic."""

    def add(self, checklist: OnboardingChecklist) -> None: ...
    def get(self) -> OnboardingChecklist | None: ...
    def update(self, checklist: OnboardingChecklist) -> None: ...


class PatientRepository(Protocol):
    """This clinic's patients (M2). Every query is scoped to the clinic by construction.

    Names and phone numbers are personal data: callers must not log them, and the
    audit trail records field names only (spec patients D5).
    """

    def add(self, patient: Patient) -> None: ...
    def add_many(self, patients: Sequence[Patient]) -> None:
        """Insert several in one round trip (the ops import, M2-P4)."""
        ...

    def get(self, patient_id: UUID, *, for_update: bool = False) -> Patient | None:
        """``for_update`` locks the row: consent, opt-out and opt-in must not interleave (M2-P3)."""
        ...

    def update(self, patient: Patient) -> None: ...
    def get_by_code(self, code: str) -> Patient | None:
        """Exact, canonical code (``ME-0142``); codes are unique within the clinic."""
        ...

    def find_by_phone(self, phone: PhoneNumber, *, limit: int) -> Sequence[Patient]:
        """Patients on this exact number (family members may share one), oldest first."""
        ...

    def find_by_phones(self, phones: Collection[PhoneNumber]) -> Sequence[Patient]:
        """Every patient on any of these numbers, oldest first: one query for an import (M2-P4)."""
        ...

    def get_many(self, patient_ids: Collection[UUID]) -> Sequence[Patient]:
        """These patients of this clinic, in no particular order; others are skipped."""
        ...

    def search_by_name_prefix(self, prefix: str, *, limit: int) -> Sequence[Patient]:
        """Case-insensitive name prefix, ordered by name then code (spec R5)."""
        ...

    def count(self) -> int: ...


class ScheduleRepository(Protocol):
    """This clinic's weekly blocks (M3-P1)."""

    def add(self, block: WeeklyBlock) -> None: ...
    def update(self, block: WeeklyBlock) -> None: ...
    def delete(self, block_id: UUID) -> None: ...
    def list_for_doctor(self, doctor_id: UUID, *, valid_since: date) -> Sequence[WeeklyBlock]:
        """Blocks still in force on or after ``valid_since``, by weekday and start time."""
        ...

    def list_current(self, *, valid_since: date) -> Sequence[WeeklyBlock]:
        """Every doctor's blocks in force on or after ``valid_since`` (booking-mode check, R19)."""
        ...


class ScheduleExceptionRepository(Protocol):
    """This clinic's leave and extra sessions (M3-P1)."""

    def add(self, exception: ScheduleException) -> None: ...
    def get(self, exception_id: UUID) -> ScheduleException | None: ...
    def delete(self, exception_id: UUID) -> None: ...
    def list_for_doctor(
        self, doctor_id: UUID, *, first: date, last: date
    ) -> Sequence[ScheduleException]:
        """Exceptions dated ``first`` to ``last`` inclusive, by date."""
        ...

    def list_from(self, first: date) -> Sequence[ScheduleException]:
        """Every doctor's exceptions from ``first`` on (booking-mode check, R19)."""
        ...


class SessionRepository(Protocol):
    """This clinic's generated sessions (M3-P1)."""

    def add_missing(self, sessions: Sequence[Session]) -> int:
        """Insert the ones not there yet (``ON CONFLICT DO NOTHING``, R1); returns how many."""
        ...

    def get(self, session_id: UUID, *, lock: RowLock | None = None) -> Session | None:
        """One session; ``UPDATE`` while booking or cancelling in it (R5)."""
        ...

    def get_many(self, session_ids: Collection[UUID]) -> Sequence[Session]:
        """These sessions (any status), in no particular order; unknown IDs are skipped."""
        ...

    def update(self, session: Session) -> None:
        """Save ``booked_count``, ``next_token``, status and shape (booking, reconcile)."""
        ...

    def list_for_date(
        self, on_date: date, *, doctor_id: UUID | None = None, include_retired: bool = False
    ) -> Sequence[Session]:
        """The date's sessions, by start time then doctor; retired (``CANCELLED``) ones only
        when asked, for generation to revive."""
        ...

    def list_for_doctor(
        self, doctor_id: UUID, *, first: date, last: date | None = None
    ) -> Sequence[Session]:
        """A doctor's sessions dated ``first`` to ``last`` (open-ended when None), by start."""
        ...

    def delete(self, session_id: UUID) -> None: ...


class AppointmentRepository(Protocol):
    """This clinic's appointments (M3-P2)."""

    def add(self, appointment: Appointment) -> None: ...

    def update(self, appointment: Appointment) -> None: ...

    def get(self, appointment_id: UUID, *, for_update: bool = False) -> Appointment | None: ...

    def list_active_for_sessions(self, session_ids: Collection[UUID]) -> Sequence[Appointment]:
        """Active (not cancelled) appointments in these sessions, by slot or token."""
        ...

    def list_for_sessions(self, session_ids: Collection[UUID]) -> Sequence[Appointment]:
        """Every appointment in these sessions, cancelled ones too, by slot or token."""
        ...

    def exists_for_session(self, session_id: UUID) -> bool:
        """Any appointment, cancelled or not, points at the session (so it cannot be deleted)."""
        ...

    def list_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[Appointment]:
        """The patient's appointments, newest first."""
        ...

    def list_booked_ended_before(self, cutoff: datetime, *, limit: int) -> Sequence[UUID]:
        """Appointments still ``BOOKED`` whose session ended by ``cutoff`` (M5-P4, R10)."""
        ...

    def count_no_shows(self, patient_ids: Collection[UUID], since: datetime) -> dict[UUID, int]:
        """M6b-P5 (FR-BKG-07, R47): ``NO_SHOW`` appointments per record whose session started on
        or after ``since``; records without any are left out."""
        ...

    def list_to_move(
        self, *, from_date: date, doctor_id: UUID | None = None, limit: int
    ) -> Sequence[tuple[Appointment, Session]]:
        """M6a-P8 (FR-APT-09): ``BOOKED`` or ``ARRIVED`` bookings in ``CLOSED`` sessions on or
        after ``from_date``, earliest first, each with its session."""
        ...

    def count_to_move(self, *, from_date: date, doctor_id: UUID | None = None) -> int: ...


class AppointmentHistoryRepository(Protocol):
    """Append-only status history (FR-APT-05)."""

    def add(self, change: StatusChange) -> None: ...

    def list_for_appointment(self, appointment_id: UUID) -> Sequence[StatusChange]:
        """Oldest first."""
        ...


class VisitRepository(Protocol):
    """This clinic's visits (M4-P1). Clinical content: never logged by callers."""

    def add(self, visit: Visit) -> None: ...

    def update(self, visit: Visit) -> None: ...

    def get(self, visit_id: UUID, *, for_update: bool = False) -> Visit | None: ...

    def get_for_appointment(self, appointment_id: UUID) -> Visit | None: ...

    def ids_for_appointments(self, appointment_ids: Collection[UUID]) -> dict[UUID, UUID]:
        """M4-P6: appointment ID -> its visit's ID, for those that have one. No content."""
        ...

    def list_for_patient(
        self, patient_id: UUID, *, limit: int, before: tuple[datetime, UUID] | None = None
    ) -> Sequence[Visit]:
        """Newest first by ``(started_at, id)``; ``before`` continues after that position."""
        ...

    def patients_seen_by(
        self, doctor_id: UUID, *, match: PatientMatch | None, limit: int, offset: int
    ) -> Sequence[SeenPatient]:
        """M6a-P6 *My Patients*: patients with a visit by this doctor, latest visit first."""
        ...


class VisitAddendumRepository(Protocol):
    """Append-only addenda (R3); there is no update or delete."""

    def add(self, addendum: VisitAddendum) -> None: ...

    def list_for_visit(self, visit_id: UUID) -> Sequence[VisitAddendum]:
        """Oldest first."""
        ...


class VisitAttachmentRepository(Protocol):
    """M6d-P6: reports on visits. A delete or share is a column change; rows are never removed."""

    def add(self, attachment: VisitAttachment) -> None: ...

    def update(self, attachment: VisitAttachment) -> None:
        """Save the share and delete columns."""
        ...

    def get(self, attachment_id: UUID) -> VisitAttachment | None:
        """Deleted ones too (the caller decides)."""
        ...

    def list_for_visit(self, visit_id: UUID) -> Sequence[VisitAttachment]:
        """Not deleted, oldest first."""
        ...

    def count_for_visit(self, visit_id: UUID) -> int:
        """Not deleted."""
        ...

    def list_shared_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[VisitAttachment]:
        """Shared and not deleted, newest share first."""
        ...


class PrescriptionRepository(Protocol):
    """This clinic's prescription versions with their items (M4-P2). Clinical: never logged."""

    def add(self, prescription: Prescription) -> None:
        """Insert the version and its items."""
        ...

    def update(self, prescription: Prescription) -> None:
        """Save the version's own columns (items untouched)."""
        ...

    def replace_items(self, prescription: Prescription) -> None:
        """A draft's items become exactly ``prescription.items``."""
        ...

    def get(self, prescription_id: UUID, *, for_update: bool = False) -> Prescription | None: ...

    def list_for_visit(self, visit_id: UUID) -> Sequence[Prescription]:
        """The visit's chain, by version."""
        ...

    def list_for_visits(self, visit_ids: Collection[UUID]) -> Sequence[Prescription]:
        """Every version of these visits, by visit then version."""
        ...

    def issued_for_visits(self, visit_ids: Collection[UUID]) -> dict[UUID, IssuedVersion]:
        """M4-P6: each visit's current issued version, IDs and time only (no items read)."""
        ...

    def delete(self, prescription_id: UUID) -> None:
        """Remove a draft and its items (the database refuses anything else)."""
        ...

    def lock_for_render(self, prescription_id: UUID, *, wait_seconds: int) -> Prescription | None:
        """M4-P4, R18: the version locked for update, waiting at most `wait_seconds` for another
        transaction's lock; longer raises `PdfBusy`. The wait limit then holds for the rest of
        the transaction."""
        ...

    def list_issued_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[Prescription]:
        """M4-P4 decision 2A: the patient's current versions (`ISSUED`; a superseded one never
        is), newest issue first."""
        ...

    def medicine_history(self, prefix: str, *, limit: int) -> Sequence[HistoryName]:
        """M4-P3, R7: medicine names on this clinic's issued (or superseded) prescriptions that
        start with ``prefix`` ignoring case, grouped ignoring case and spaces, with the distinct
        visits they were prescribed in and when last; most visits first. Never drafts."""
        ...


class PatientLinkRepository(Protocol):
    """This clinic's patient links (M4-P5). The token's `jti` is the row's ID."""

    def add(self, link: PatientLink) -> None: ...
    def update(self, link: PatientLink) -> None: ...
    def get(self, link_id: UUID, *, for_update: bool = False) -> PatientLink | None: ...

    def active_for_prescription(
        self, prescription_id: UUID, *, for_update: bool = False
    ) -> PatientLink | None:
        """The chain's link that is not revoked (version 1's ID), if any."""
        ...

    def active_for_bill(self, bill_id: UUID, *, for_update: bool = False) -> PatientLink | None:
        """M6d-P4: the bill's receipt link that is not revoked, if any."""
        ...


class RateLimitRepository(Protocol):
    """Fixed one-minute windows shared by every API worker (M4-P5 decision 4A)."""

    def hit(self, bucket: str, *, window_start: datetime) -> int:
        """Count one request in `bucket` for the window; return the window's count so far.
        Windows older than an hour are removed as a side effect."""
        ...


class FavouriteRepository(Protocol):
    """This clinic's favourites (M4-P3). A name the doctor already uses raises ``NameTaken``."""

    def add(self, favourite: Favourite) -> None: ...

    def update(self, favourite: Favourite) -> None: ...

    def delete(self, favourite_id: UUID) -> None: ...

    def get(self, favourite_id: UUID, *, for_update: bool = False) -> Favourite | None: ...

    def list_for_doctor(self, doctor_id: UUID) -> Sequence[Favourite]:
        """By use, then name."""
        ...

    def count_for_doctor(self, doctor_id: UUID) -> int: ...


class TemplateRepository(Protocol):
    """This clinic's templates (M4-P3), as ``FavouriteRepository``."""

    def add(self, template: Template) -> None: ...

    def update(self, template: Template) -> None: ...

    def delete(self, template_id: UUID) -> None: ...

    def get(self, template_id: UUID, *, for_update: bool = False) -> Template | None: ...

    def list_for_doctor(self, doctor_id: UUID) -> Sequence[Template]: ...

    def count_for_doctor(self, doctor_id: UUID) -> int: ...
