"""``make seed`` — synthetic demo data for trying the app locally (AGENTS.md §4).

Creates one active clinic with an owner, a doctor (with a doctor profile), a
front-desk user and a platform ops user, all sharing one demo password. Every
name, email and ``+9190000000xx`` number is invented (CLAUDE.md "No real
patient data outside production").

Safe by construction:

- refuses to run unless ``APP_ENV=local``;
- idempotent: if the demo clinic's slug exists, nothing is written.

Run: ``make seed`` (or ``python -m mediease_api.delivery.cli.seed``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from mediease_api.bootstrap import build_seed_dependencies
from mediease_api.config.settings import AppEnv, load_settings
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import ClinicMembership, Role
from mediease_api.domain.identity.user import User
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.phone import PhoneNumber

DEMO_SLUG = "sample-clinic"
# Synthetic credentials for a local, synthetic database only.
DEFAULT_DEMO_PASSWORD = "MediEase-demo-2026"

# (email, phone, full name, role); role None = platform ops.
_PEOPLE: tuple[tuple[str, str, str, Role | None], ...] = (
    ("owner@sample-clinic.example", "+919000000001", "Sample Owner", Role.OWNER),
    ("doctor@sample-clinic.example", "+919000000002", "Dr. Sample Doctor", Role.DOCTOR),
    ("desk@sample-clinic.example", "+919000000003", "Sample Front Desk", Role.FRONT_DESK),
    ("ops@mediease.example", "+919000000009", "Sample Ops", None),
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
    with deps.uow as uow:
        if uow.clinics.get_by_slug(DEMO_SLUG) is not None:
            print(f"seed: '{DEMO_SLUG}' already exists; nothing to do")
            return 0

        now = deps.clock.now()
        password_hash = deps.hasher.hash(args.password)
        clinic = Clinic.create(
            id=deps.ids.new_id(),
            name="Sample Clinic",
            slug=DEMO_SLUG,
            now=now,
            phone=PhoneNumber.parse("+919000000000"),
            city="Sample City",
            pincode="560001",
            specialties=("General Medicine",),
        )
        uow.clinics.add(clinic)
        staff = uow.tenant(clinic.id)

        for email, phone, name, role in _PEOPLE:
            user = User.create(
                id=deps.ids.new_id(),
                full_name=name,
                email=EmailAddress.parse(email),
                phone=PhoneNumber.parse(phone),
                is_platform_ops=role is None,
                password_hash=password_hash,
                now=now,
            )
            uow.users.add(user)
            if role is None:
                continue
            membership = ClinicMembership.invite(
                id=deps.ids.new_id(), clinic_id=clinic.id, user_id=user.id, role=role, now=now
            )
            membership.activate(now=now)
            staff.memberships.add(membership)
            if role is Role.DOCTOR:
                staff.doctors.add(
                    Doctor.create(
                        id=deps.ids.new_id(),
                        clinic_id=clinic.id,
                        user_id=user.id,
                        display_name=name,
                        qualification="MBBS",
                        registration_number="SAMPLE-0001",
                        registration_council="Sample State Medical Council",
                        now=now,
                    )
                )

        clinic.activate(active_owner_count=staff.memberships.count_active_owners(), now=now)
        uow.clinics.update(clinic)
        uow.commit()

    print(f"seed: created '{DEMO_SLUG}' with users: " + ", ".join(p[0] for p in _PEOPLE))
    print("seed: sign in with any of them and the demo password (see docs/RUNBOOK.md §1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
