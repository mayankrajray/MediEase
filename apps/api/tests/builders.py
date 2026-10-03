"""Builders for domain objects with synthetic data (docs/TESTING.md "builders, not fixtures").

Names, slugs and ``+9190000000xx`` numbers are invented. IDs are UUIDv7s from
the production generator, so creation order is ID order.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import ClinicMembership, Role
from mediease_api.domain.identity.user import User
from mediease_api.domain.patients.patient import Patient, Sex
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.phone import PhoneNumber

NOW = datetime(2026, 10, 2, 4, 30, tzinfo=UTC)
LATER = datetime(2026, 10, 2, 5, 0, tzinfo=UTC)

_ids = Uuid7Generator()


def new_id() -> UUID:
    return _ids.new_id()


_counter = iter(range(10, 10_000))


def _n() -> int:
    return next(_counter)


def a_clinic(*, slug: str | None = None, **overrides: object) -> Clinic:
    n = _n()
    fields: dict[str, object] = {
        "id": new_id(),
        "name": f"Sample Clinic {n}",
        "slug": slug or f"sample-clinic-{n}",
        "now": NOW,
        "phone": PhoneNumber.parse(f"90000{n:05d}"),
        "city": "Sample City",
        "pincode": "560001",
        "specialties": ("General Medicine",),
    }
    fields.update(overrides)
    return Clinic.create(**fields)  # type: ignore[arg-type]


def a_user(**overrides: object) -> User:
    n = _n()
    fields: dict[str, object] = {
        "id": new_id(),
        "full_name": f"Sample User {n}",
        "now": NOW,
        "email": EmailAddress.parse(f"user{n}@example.test"),
        "phone": PhoneNumber.parse(f"+9190000{n:05d}"),
    }
    fields.update(overrides)
    return User.create(**fields)  # type: ignore[arg-type]


def a_doctor(clinic_id: UUID, **overrides: object) -> Doctor:
    n = _n()
    fields: dict[str, object] = {
        "id": new_id(),
        "clinic_id": clinic_id,
        "display_name": f"Dr. Sample {n}",
        "qualification": "MBBS",
        "registration_number": f"REG-{n:05d}",
        "registration_council": "Sample State Medical Council",
        "now": NOW,
    }
    fields.update(overrides)
    return Doctor.create(**fields)  # type: ignore[arg-type]


def a_membership(
    clinic_id: UUID, user_id: UUID, role: Role = Role.FRONT_DESK, *, active: bool = True
) -> ClinicMembership:
    membership = ClinicMembership.invite(
        id=new_id(), clinic_id=clinic_id, user_id=user_id, role=role, now=NOW
    )
    if active:
        membership.activate(now=NOW)
    return membership


def a_patient(clinic_id: UUID, created_by: UUID, **overrides: object) -> Patient:
    """An adult patient (born 1990) registered on 2 Oct 2026, with a unique synthetic code."""
    n = _n()
    fields: dict[str, object] = {
        "id": new_id(),
        "clinic_id": clinic_id,
        "code": f"TS-{n:04d}",
        "full_name": f"Sample Patient {n}",
        "phone": PhoneNumber.parse(f"91000{n:05d}"),
        "sex": Sex.UNDISCLOSED,
        "registered_on": date(2026, 10, 2),
        "created_by": created_by,
        "now": NOW,
        "date_of_birth": date(1990, 5, 17),
    }
    fields.update(overrides)
    return Patient.create(**fields)  # type: ignore[arg-type]
