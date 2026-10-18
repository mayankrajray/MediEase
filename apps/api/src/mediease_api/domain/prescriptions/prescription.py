"""A prescription version: draft, issued or superseded (spec prescriptions R4-R6, R14, R20).

One visit has one chain of versions (M4-P2 decision 1A): version 1, then revisions, each its own
row pointing at the version it replaces. A draft is edited whole with the revision it was loaded
at (3A, ``RX_STALE``). Issuing freezes it: the content, the doctor and clinic as printed (5A),
the patient's language for the PDF (R20) and the pending-delivery marker (R14). From then on the
content never changes, here and in the database (R6, AC1); only ``status`` to ``SUPERSEDED``, the
PDF key once (P4) and the delivery marker move.

Every text the doctor writes is kept exactly as written (trimmed) and never interpreted: no drug
data, no dose logic (FR-RX-10). The domain never reads a clock: ``now`` and the clinic's ``today``
are passed in.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.errors import (
    DoctorIncomplete,
    Empty,
    NotDraft,
    NotIssued,
    Stale,
)
from mediease_api.domain.prescriptions.vocabulary import (
    Frequency,
    Preparation,
    PreparationCode,
    Storage,
    StorageCode,
    Timing,
)
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from mediease_api.domain.shared.text import optional_text, required_text
from mediease_api.domain.shared.time import require_utc
from mediease_api.domain.visits.visit import Visit

MAX_ITEMS = 40
MAX_PREPARATIONS = 5
MAX_STORAGE = 4
MAX_ADVICE_ENTRIES = 10
ADVICE_ENTRY_MAX = 300
ADVICE_NOTES_MAX = 2000
FOLLOW_UP_MAX_DAYS = 365
DURATION_MAX_DAYS = 365
NAME_MAX = 200
SHORT_MAX = 100  # form, strength, dose, quantity, custom frequency
WARNINGS_MAX = 500
ITEM_NOTES_MAX = 1000
# The printed layout new issues get (M4-P5). Raise it with a new template in adapters/pdf, keeping
# the old one, so a prescription issued before a layout change still prints as it was issued.
CURRENT_LAYOUT = 1


class PrescriptionStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    SUPERSEDED = "SUPERSEDED"


class LinkDelivery(StrEnum):
    """R14, R15. M4 writes the first three; M5's sender writes SENT and EXPIRED."""

    PENDING = "PENDING"
    NOT_CONSENTED = "NOT_CONSENTED"
    SUPERSEDED = "SUPERSEDED"
    SENT = "SENT"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class PrescriptionItem:
    """One medicine line. Free text as written; frequency and timing from the vocabulary."""

    id: UUID
    position: int
    medicine_name: str
    form: str | None = None
    strength: str | None = None
    dose: str | None = None
    frequency: Frequency | None = None
    frequency_text: str | None = None
    timing: Timing | None = None
    duration_days: int | None = None
    quantity: str | None = None
    preparation: tuple[Preparation, ...] = ()
    storage: tuple[Storage, ...] = ()
    warnings: str | None = None
    notes: str | None = None
    # M4-P3: the doctor's favourite this line came from (counted at issue, decision 3A).
    favourite_id: UUID | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        position: int,
        medicine_name: str,
        form: str | None = None,
        strength: str | None = None,
        dose: str | None = None,
        frequency: Frequency | None = None,
        frequency_text: str | None = None,
        timing: Timing | None = None,
        duration_days: int | None = None,
        quantity: str | None = None,
        preparation: Sequence[Preparation] = (),
        storage: Sequence[Storage] = (),
        warnings: str | None = None,
        notes: str | None = None,
        favourite_id: UUID | None = None,
        at: str | None = None,
    ) -> PrescriptionItem:
        at = at or f"items.{position - 1}"
        custom = optional_text(frequency_text, f"{at}.frequency_text", max_length=SHORT_MAX)
        if (frequency is Frequency.CUSTOM) != (custom is not None):
            raise InvalidValue(f"{at}.frequency_text", "is required for CUSTOM and only then")
        if duration_days is not None and not 1 <= duration_days <= DURATION_MAX_DAYS:
            raise InvalidValue(f"{at}.duration_days", f"must be 1-{DURATION_MAX_DAYS}")
        if len(preparation) > MAX_PREPARATIONS:
            raise InvalidValue(f"{at}.preparation", f"must have at most {MAX_PREPARATIONS}")
        if len(storage) > MAX_STORAGE:
            raise InvalidValue(f"{at}.storage", f"must have at most {MAX_STORAGE}")
        if len({p.code for p in preparation}) != len(preparation):
            raise InvalidValue(f"{at}.preparation", "must not repeat a phrase")
        if len({s.code for s in storage}) != len(storage):
            raise InvalidValue(f"{at}.storage", "must not repeat a phrase")
        return cls(
            id=id,
            position=position,
            medicine_name=required_text(medicine_name, f"{at}.medicine_name", max_length=NAME_MAX),
            form=optional_text(form, f"{at}.form", max_length=SHORT_MAX),
            strength=optional_text(strength, f"{at}.strength", max_length=SHORT_MAX),
            dose=optional_text(dose, f"{at}.dose", max_length=SHORT_MAX),
            frequency=frequency,
            frequency_text=custom,
            timing=timing,
            duration_days=duration_days,
            quantity=optional_text(quantity, f"{at}.quantity", max_length=SHORT_MAX),
            preparation=tuple(preparation),
            storage=tuple(storage),
            warnings=optional_text(warnings, f"{at}.warnings", max_length=WARNINGS_MAX),
            notes=optional_text(notes, f"{at}.notes", max_length=ITEM_NOTES_MAX),
            favourite_id=favourite_id,
        )


def _entries(values: Sequence[str], field: str) -> tuple[str, ...]:
    if len(values) > MAX_ADVICE_ENTRIES:
        raise InvalidValue(field, f"must have at most {MAX_ADVICE_ENTRIES} entries")
    cleaned = []
    for i, value in enumerate(values):
        text = optional_text(value, f"{field}.{i}", max_length=ADVICE_ENTRY_MAX)
        if text is not None:
            cleaned.append(text)
    return tuple(cleaned)


@dataclass(frozen=True, slots=True)
class Advice:
    """FR-RX-03: diet, activity, "come back immediately if…" and notes, all as written."""

    diet: tuple[str, ...] = ()
    activity: tuple[str, ...] = ()
    return_if: tuple[str, ...] = ()
    notes: str | None = None

    @classmethod
    def create(
        cls,
        *,
        diet: Sequence[str] = (),
        activity: Sequence[str] = (),
        return_if: Sequence[str] = (),
        notes: str | None = None,
    ) -> Advice:
        return cls(
            diet=_entries(diet, "advice.diet"),
            activity=_entries(activity, "advice.activity"),
            return_if=_entries(return_if, "advice.return_if"),
            notes=optional_text(notes, "advice.notes", max_length=ADVICE_NOTES_MAX),
        )

    @property
    def is_empty(self) -> bool:
        return not (self.diet or self.activity or self.return_if or self.notes)

    def as_json(self) -> dict[str, object]:
        return {
            "diet": list(self.diet),
            "activity": list(self.activity),
            "return_if": list(self.return_if),
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class DoctorSnapshot:
    """The doctor as printed on this version (R8), copied at issue."""

    doctor_id: UUID
    display_name: str
    qualification: str
    registration_number: str
    registration_council: str
    specialty: str | None

    REQUIRED = ("display_name", "qualification", "registration_number", "registration_council")

    @classmethod
    def of(cls, doctor: Doctor) -> DoctorSnapshot:
        missing = [f for f in cls.REQUIRED if not str(getattr(doctor, f) or "").strip()]
        if missing:
            raise DoctorIncomplete(missing)
        return cls(
            doctor_id=doctor.id,
            display_name=doctor.display_name.strip(),
            qualification=doctor.qualification.strip(),
            registration_number=doctor.registration_number.strip(),
            registration_council=doctor.registration_council.strip(),
            specialty=doctor.specialty,
        )

    def as_json(self) -> dict[str, str | None]:
        return {
            "doctor_id": str(self.doctor_id),
            "display_name": self.display_name,
            "qualification": self.qualification,
            "registration_number": self.registration_number,
            "registration_council": self.registration_council,
            "specialty": self.specialty,
        }


@dataclass(frozen=True, slots=True)
class ClinicSnapshot:
    """The letterhead as printed on this version (decision 5A), copied at issue."""

    name: str
    address_line: str | None
    city: str | None
    state: str | None
    pincode: str | None
    phone_e164: str | None

    @classmethod
    def of(cls, clinic: Clinic) -> ClinicSnapshot:
        return cls(
            name=clinic.name,
            address_line=clinic.address_line,
            city=clinic.city,
            state=clinic.state,
            pincode=clinic.pincode,
            phone_e164=clinic.phone.e164 if clinic.phone else None,
        )

    def as_json(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "address_line": self.address_line,
            "city": self.city,
            "state": self.state,
            "pincode": self.pincode,
            "phone_e164": self.phone_e164,
        }


@dataclass(slots=True)
class Prescription:
    id: UUID
    clinic_id: UUID
    visit_id: UUID
    patient_id: UUID
    doctor_id: UUID
    version: int
    supersedes_id: UUID | None
    status: PrescriptionStatus
    revision: int
    items: tuple[PrescriptionItem, ...]
    advice: Advice
    follow_up_date: date | None
    language: Language | None
    issued_at: datetime | None
    doctor_snapshot: DoctorSnapshot | None
    clinic_snapshot: ClinicSnapshot | None
    pdf_object_key: str | None
    link_delivery: LinkDelivery | None
    link_delivery_requested_at: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    # M4-P3: the doctor's template the body came from (counted at issue, decision 3A).
    template_id: UUID | None = None
    # M4-P5: the printed layout fixed at issue (`CURRENT_LAYOUT` then); drafts carry the current.
    layout_version: int = CURRENT_LAYOUT

    # --- Creating -----------------------------------------------------------------------------

    @classmethod
    def first_draft(
        cls, visit: Visit, *, id: UUID, created_by: UUID, now: datetime
    ) -> Prescription:
        """Version 1 of the visit's chain, empty."""
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=visit.clinic_id,
            visit_id=visit.id,
            patient_id=visit.patient_id,
            doctor_id=visit.doctor_id,
            version=1,
            supersedes_id=None,
            status=PrescriptionStatus.DRAFT,
            revision=1,
            items=(),
            advice=Advice(),
            follow_up_date=None,
            language=None,
            issued_at=None,
            doctor_snapshot=None,
            clinic_snapshot=None,
            pdf_object_key=None,
            link_delivery=None,
            link_delivery_requested_at=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def revision_of(
        cls,
        issued: Prescription,
        *,
        id: UUID,
        new_item_id: Callable[[], UUID],
        created_by: UUID,
        now: datetime,
    ) -> Prescription:
        """R6: version n+1 as a draft with the issued version's content (new item rows)."""
        now = require_utc(now, "now")
        if issued.status is not PrescriptionStatus.ISSUED:
            raise NotDraft(issued.status.value)  # only an issued version is revised
        return cls(
            id=id,
            clinic_id=issued.clinic_id,
            visit_id=issued.visit_id,
            patient_id=issued.patient_id,
            doctor_id=issued.doctor_id,
            version=issued.version + 1,
            supersedes_id=issued.id,
            status=PrescriptionStatus.DRAFT,
            revision=1,
            items=tuple(replace(item, id=new_item_id()) for item in issued.items),
            advice=issued.advice,
            template_id=issued.template_id,
            follow_up_date=issued.follow_up_date,
            language=None,
            issued_at=None,
            doctor_snapshot=None,
            clinic_snapshot=None,
            pdf_object_key=None,
            link_delivery=None,
            link_delivery_requested_at=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    # --- Drafting ----------------------------------------------------------------------------

    @property
    def is_draft(self) -> bool:
        return self.status is PrescriptionStatus.DRAFT

    def check_draft(self) -> None:
        if not self.is_draft:
            raise NotDraft(self.status.value)

    def _check_revision(self, seen_revision: int) -> None:
        if seen_revision != self.revision:
            raise Stale(self.revision)

    def replace_body(
        self,
        *,
        items: Sequence[PrescriptionItem],
        advice: Advice,
        follow_up_date: date | None,
        seen_revision: int,
        today: date,
        now: datetime,
        template_id: UUID | None = None,
    ) -> None:
        """Decision 3A: the whole draft at once, from the revision it was loaded at."""
        now = require_utc(now, "now")
        self.check_draft()
        self._check_revision(seen_revision)
        if len(items) > MAX_ITEMS:
            raise InvalidValue("items", f"must have at most {MAX_ITEMS}")
        if [i.position for i in items] != list(range(1, len(items) + 1)):
            raise InvalidValue("items", "positions must run 1, 2, 3 …")
        _check_follow_up(follow_up_date, today)
        self.items = tuple(items)
        self.advice = advice
        self.follow_up_date = follow_up_date
        self.template_id = template_id
        self.revision += 1
        self.updated_at = now

    # --- Issuing -----------------------------------------------------------------------------

    def issue(
        self,
        *,
        doctor: Doctor,
        clinic: Clinic,
        language: Language,
        may_message: bool,
        seen_revision: int,
        today: date,
        now: datetime,
    ) -> None:
        """R4, R5, R14, R20: freeze the draft with what will be printed and sent."""
        now = require_utc(now, "now")
        self.check_draft()
        self._check_revision(seen_revision)
        if not self.items and self.advice.is_empty:
            raise Empty()
        assert doctor.id == self.doctor_id, "the visit's own doctor"
        snapshot = DoctorSnapshot.of(doctor)
        _check_follow_up(self.follow_up_date, today)
        self.status = PrescriptionStatus.ISSUED
        self.issued_at = now
        self.layout_version = CURRENT_LAYOUT
        self.language = language
        self.doctor_snapshot = snapshot
        self.clinic_snapshot = ClinicSnapshot.of(clinic)
        if may_message:
            self.link_delivery = LinkDelivery.PENDING
            self.link_delivery_requested_at = now
        else:
            self.link_delivery = LinkDelivery.NOT_CONSENTED
        self.revision += 1
        self.updated_at = now

    def attach_pdf(self, key: str) -> None:
        """R18: the version's PDF was stored under `key`; set once (the database agrees)."""
        if self.status is PrescriptionStatus.DRAFT:
            raise NotIssued(self.status.value)
        assert self.pdf_object_key is None, "a version's PDF is stored once"
        self.pdf_object_key = key

    def supersede(self, now: datetime) -> None:
        """R6, R14: a newer version was issued; a pending link for this one is never sent."""
        now = require_utc(now, "now")
        if self.status is not PrescriptionStatus.ISSUED:
            raise NotDraft(self.status.value)
        self.status = PrescriptionStatus.SUPERSEDED
        if self.link_delivery is LinkDelivery.PENDING:
            self.link_delivery = LinkDelivery.SUPERSEDED
        self.updated_at = now

    def link_sent(self, now: datetime) -> None:
        """R15 (M5-P2): the pending link was accepted by the provider."""
        self._settle_link(LinkDelivery.SENT, now)

    def link_expired(self, now: datetime) -> None:
        """R15: too old, or consent no longer holds; the link is never sent."""
        self._settle_link(LinkDelivery.EXPIRED, now)

    def _settle_link(self, to: LinkDelivery, now: datetime) -> None:
        now = require_utc(now, "now")
        if self.link_delivery is not LinkDelivery.PENDING:
            raise InvalidTransition(
                "link delivery", self.link_delivery.value if self.link_delivery else "NONE", to
            )
        self.link_delivery = to
        self.updated_at = now


def _check_follow_up(follow_up: date | None, today: date) -> None:
    if follow_up is None:
        return
    if follow_up <= today:
        raise InvalidValue("follow_up_date", "must be after today")
    if follow_up > today + timedelta(days=FOLLOW_UP_MAX_DAYS):
        raise InvalidValue("follow_up_date", f"must be within {FOLLOW_UP_MAX_DAYS} days")


def item_json(item: PrescriptionItem) -> dict[str, object]:
    """A line's body without its identity, as favourites and templates store it (M4-P3)."""
    return {
        "medicine_name": item.medicine_name,
        "form": item.form,
        "strength": item.strength,
        "dose": item.dose,
        "frequency": item.frequency.value if item.frequency else None,
        "frequency_text": item.frequency_text,
        "timing": item.timing.value if item.timing else None,
        "duration_days": item.duration_days,
        "quantity": item.quantity,
        "preparation": [p.as_json() for p in item.preparation],
        "storage": [s.as_json() for s in item.storage],
        "warnings": item.warnings,
        "notes": item.notes,
    }


def item_from_json(data: dict[str, Any], *, id: UUID, position: int) -> PrescriptionItem:
    """The inverse of ``item_json`` for stored bodies (already validated when saved)."""
    return PrescriptionItem(
        id=id,
        position=position,
        medicine_name=data["medicine_name"],
        form=data.get("form"),
        strength=data.get("strength"),
        dose=data.get("dose"),
        frequency=Frequency(data["frequency"]) if data.get("frequency") else None,
        frequency_text=data.get("frequency_text"),
        timing=Timing(data["timing"]) if data.get("timing") else None,
        duration_days=data.get("duration_days"),
        quantity=data.get("quantity"),
        preparation=tuple(
            Preparation(PreparationCode(p["code"]), p.get("text"))
            for p in data.get("preparation", [])
        ),
        storage=tuple(
            Storage(StorageCode(s["code"]), s.get("days")) for s in data.get("storage", [])
        ),
        warnings=data.get("warnings"),
        notes=data.get("notes"),
    )


def latest_issued(chain: Sequence[Prescription]) -> Prescription | None:
    issued = [p for p in chain if p.status is PrescriptionStatus.ISSUED]
    return max(issued, key=lambda p: p.version) if issued else None


@dataclass(frozen=True, slots=True)
class IssuedVersion:
    """A visit's current issued version without any content (the queue row, M4-P6 4A)."""

    id: UUID
    visit_id: UUID
    version: int
    issued_at: datetime
