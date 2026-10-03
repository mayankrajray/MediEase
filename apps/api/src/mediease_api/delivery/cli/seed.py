"""``make seed`` — synthetic demo data for trying the app locally (AGENTS.md §4).

Creates two active clinics and a platform ops user, all sharing one demo
password:

- ``sample-clinic``: an owner, a doctor (with a doctor profile) and a front desk;
  It also gets six synthetic patients, once (while it has none): a family of three sharing one
  phone, a child registered with a guardian, an adult known only by age, and a Hindi-speaking
  patient, so the patient screens can be tried by hand;
- `sample-clinic-two`: its own owner, plus the *same* doctor user as a second
  membership, so one person belongs to two clinics and the web app's clinic
  switcher can be tried (spec: "Same phone used by a doctor in two clinics").

Every name, email and ``+9190000000xx`` number is invented (CLAUDE.md "No real
patient data outside production").

Safe by construction:

- refuses to run unless ``APP_ENV=local``;
- idempotent per clinic: a clinic whose slug exists is left untouched, so a
  database seeded before the second clinic existed gains only the new one.

Run: ``make seed`` (or ``python -m mediease_api.delivery.cli.seed``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from mediease_api.bootstrap import SeedDependencies, build_seed_dependencies
from mediease_api.config.settings import AppEnv, load_settings
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import ClinicMembership, Role
from mediease_api.domain.identity.user import User
from mediease_api.domain.patients.patient import Language, Patient, Sex
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.unit_of_work import UnitOfWork

DEMO_SLUG = "sample-clinic"
SECOND_SLUG = "sample-clinic-two"
# Synthetic credentials for a local, synthetic database only.
DEFAULT_DEMO_PASSWORD = "MediEase-demo-2026"


@dataclass(frozen=True)
class _Person:
    email: str
    phone: str
    name: str
    role: Role | None = None  # None = platform ops


@dataclass(frozen=True)
class _ClinicSpec:
    slug: str
    name: str
    phone: str
    doctor_registration: str
    members: tuple[_Person, ...]


_DOCTOR = _Person("doctor@sample-clinic.example", "+919000000002", "Dr. Sample Doctor", Role.DOCTOR)
_OPS = _Person("ops@mediease.example", "+919000000009", "Sample Ops")

_CLINICS: tuple[_ClinicSpec, ...] = (
    _ClinicSpec(
        DEMO_SLUG,
        "Sample Clinic",
        "+919000000000",
        "SAMPLE-0001",
        (
            _Person("owner@sample-clinic.example", "+919000000001", "Sample Owner", Role.OWNER),
            _DOCTOR,
            _Person(
                "desk@sample-clinic.example",
                "+919000000003",
                "Sample Front Desk",
                Role.FRONT_DESK,
            ),
        ),
    ),
    _ClinicSpec(
        SECOND_SLUG,
        "Sample Clinic Two",
        "+919000000010",
        "SAMPLE-0002",
        (
            _Person(
                "owner@sample-clinic-two.example",
                "+919000000011",
                "Second Clinic Owner",
                Role.OWNER,
            ),
            _DOCTOR,
        ),
    ),
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--password", default=DEFAULT_DEMO_PASSWORD, help="demo password")
    args = parser.parse_args(argv)

    settings = load_settings()
    if settings.APP_ENV is not AppEnv.LOCAL:
        print(f"seed: refused — APP_ENV is {settings.APP_ENV.value}, not local", file=sys.stderr)
        return 2

    deps = build_seed_dependencies(settings)
    password_hash = deps.hasher.hash(args.password)
    created: list[_ClinicSpec] = []
    patients_added = 0
    with deps.uow as uow:
        users: dict[str, User] = {}
        _ensure_user(deps, uow, users, _OPS, password_hash)
        for spec in _CLINICS:
            if uow.clinics.get_by_slug(spec.slug) is not None:
                print(f"seed: '{spec.slug}' already exists; nothing to do")
                continue
            _create_clinic(deps, uow, users, spec, password_hash)
            created.append(spec)
        patients_added = _seed_patients(deps, uow, users)
        uow.commit()

    for spec in created:
        emails = ", ".join(person.email for person in spec.members)
        print(f"seed: created '{spec.slug}' with users: {emails}")
    if patients_added:
        print(f"seed: added {patients_added} synthetic patients to '{DEMO_SLUG}'")
    if created:
        print(f"seed: ops user: {_OPS.email}")
        print("seed: sign in with any of them and the demo password (see docs/RUNBOOK.md §1)")
    return 0


def _ensure_user(
    deps: SeedDependencies,
    uow: UnitOfWork,
    users: dict[str, User],
    person: _Person,
    password_hash: str,
) -> User:
    """The user with this email: already seeded, created earlier in this run, or new."""
    if person.email in users:
        return users[person.email]
    user = uow.users.get_by_email(EmailAddress.parse(person.email))
    if user is None:
        user = User.create(
            id=deps.ids.new_id(),
            full_name=person.name,
            email=EmailAddress.parse(person.email),
            phone=PhoneNumber.parse(person.phone),
            is_platform_ops=person.role is None,
            password_hash=password_hash,
            now=deps.clock.now(),
        )
        uow.users.add(user)
    users[person.email] = user
    return user


def _create_clinic(
    deps: SeedDependencies,
    uow: UnitOfWork,
    users: dict[str, User],
    spec: _ClinicSpec,
    password_hash: str,
) -> None:
    now = deps.clock.now()
    clinic = Clinic.create(
        id=deps.ids.new_id(),
        name=spec.name,
        slug=spec.slug,
        now=now,
        phone=PhoneNumber.parse(spec.phone),
        city="Sample City",
        pincode="560001",
        specialties=("General Medicine",),
    )
    uow.clinics.add(clinic)
    staff = uow.tenant(clinic.id)

    for person in spec.members:
        assert person.role is not None  # ops users belong to no clinic
        user = _ensure_user(deps, uow, users, person, password_hash)
        membership = ClinicMembership.invite(
            id=deps.ids.new_id(), clinic_id=clinic.id, user_id=user.id, role=person.role, now=now
        )
        membership.activate(now=now)
        staff.memberships.add(membership)
        if person.role is Role.DOCTOR:
            staff.doctors.add(
                Doctor.create(
                    id=deps.ids.new_id(),
                    clinic_id=clinic.id,
                    user_id=user.id,
                    display_name=person.name,
                    qualification="MBBS",
                    registration_number=spec.doctor_registration,
                    registration_council="Sample State Medical Council",
                    now=now,
                )
            )

    clinic.activate(active_owner_count=staff.memberships.count_active_owners(), now=now)
    uow.clinics.update(clinic)


@dataclass(frozen=True)
class _PatientSpec:
    full_name: str
    phone: str
    sex: Sex
    born: date | None = None
    years_old: int | None = None  # the age in years when the birth date is unknown
    child_of_years: int | None = None  # a child this many years old (born relative to today)
    guardian: str | None = None
    language: Language = Language.EN


_PATIENTS: tuple[_PatientSpec, ...] = (
    _PatientSpec("Asha Rao", "+919000000101", Sex.FEMALE, born=date(1990, 5, 17)),
    _PatientSpec("Arun Rao", "+919000000101", Sex.MALE, born=date(1988, 2, 11)),
    _PatientSpec("Meera Rao", "+919000000101", Sex.FEMALE, child_of_years=6, guardian="Asha Rao"),
    _PatientSpec("Bina Shah", "+919000000102", Sex.FEMALE, years_old=47),
    _PatientSpec(
        "Chetan Verma", "+919000000103", Sex.MALE, born=date(1975, 9, 3), language=Language.HI
    ),
    _PatientSpec("Deepa Nair", "+919000000104", Sex.FEMALE, born=date(2001, 12, 25)),
)


def _seed_patients(deps: SeedDependencies, uow: UnitOfWork, users: dict[str, User]) -> int:
    """Synthetic patients for the demo clinic, once: only while it has none."""
    clinic = uow.clinics.get_by_slug(DEMO_SLUG)
    owner = users.get(_CLINICS[0].members[0].email) or uow.users.get_by_email(
        EmailAddress.parse(_CLINICS[0].members[0].email)
    )
    if clinic is None or owner is None:
        return 0
    patients = uow.tenant(clinic.id).patients
    if patients.count() > 0:
        return 0

    clinic = uow.clinics.get(clinic.id, for_update=True) or clinic  # the counter, under its lock
    now = deps.clock.now()
    today = local_date(now, clinic.timezone)
    for spec in _PATIENTS:
        born = spec.born
        if spec.child_of_years is not None:
            born = today - timedelta(days=spec.child_of_years * 365 + 60)
        patients.add(
            Patient.create(
                id=deps.ids.new_id(),
                clinic_id=clinic.id,
                code=clinic.allocate_patient_code(now=now),
                full_name=spec.full_name,
                phone=PhoneNumber.parse(spec.phone),
                sex=spec.sex,
                registered_on=today,
                created_by=owner.id,
                now=now,
                date_of_birth=born,
                age_years=spec.years_old,
                guardian_name=spec.guardian,
                language=spec.language,
            )
        )
    uow.clinics.update(clinic)
    return len(_PATIENTS)


if __name__ == "__main__":
    raise SystemExit(main())
