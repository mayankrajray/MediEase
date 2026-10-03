"""Patients against a real PostgreSQL (M2-P1): round trips, constraints, code lock, lookup speed.

The 10,000-patient test is spec patients AC4 (FR-PAT-04): it loads one clinic with
10,000 patients, times the three lookups through the repository, and asks PostgreSQL
to plan each of the repository's own statements *without* the option of a sequential
scan, so a query that no index can serve fails loudly instead of merely being fast
enough on this machine.
"""

from __future__ import annotations

import random
import statistics
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, insert, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.db.models import PatientRow
from mediease_api.adapters.db.repositories import SqlAlchemyPatientRepository
from mediease_api.domain.patients.patient import Language, Sex
from mediease_api.domain.shared.phone import PhoneNumber
from tests.builders import LATER, NOW, a_clinic, a_patient, a_user, new_id
from tests.conftest import UowFactory

SessionFactory = sessionmaker[Session]


@pytest.fixture
def staff_user_id(uow_factory: UowFactory) -> UUID:
    user = a_user()
    with uow_factory() as uow:
        uow.users.add(user)
        uow.commit()
    return user.id


@pytest.fixture
def clinic_id(uow_factory: UowFactory) -> UUID:
    clinic = a_clinic(name="Perf Clinic", patient_code_prefix="PF")
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.commit()
    return clinic.id


# --- Round trip --------------------------------------------------------------------------------


def test_fr_pat_01_a_patient_round_trips_through_the_repository(
    uow_factory: UowFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    patient = a_patient(
        clinic_id,
        staff_user_id,
        full_name="Asha Rao",
        date_of_birth=None,
        age_years=6,
        guardian_name="Meera Rao",
        sex=Sex.FEMALE,
        language=Language.HI,
    )
    with uow_factory() as uow:
        uow.tenant(clinic_id).patients.add(patient)
        uow.commit()

    with uow_factory() as uow:
        patients = uow.tenant(clinic_id).patients
        assert patients.get(patient.id) == patient
        assert patients.get_by_code(patient.code) == patient
        assert patients.get(uuid4()) is None
        assert patients.count() == 1


def test_r7_fr_pat_05_edits_and_consent_are_saved(
    uow_factory: UowFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    patient = a_patient(clinic_id, staff_user_id)
    with uow_factory() as uow:
        uow.tenant(clinic_id).patients.add(patient)
        uow.commit()

    with uow_factory() as uow:
        patients = uow.tenant(clinic_id).patients
        stored = patients.get(patient.id)
        assert stored is not None
        stored.update_details(today=date(2026, 10, 3), now=LATER, full_name="Changed Name")
        stored.record_consent(whatsapp=True, sms=False, by=staff_user_id, now=LATER)
        stored.opt_out(now=LATER)
        patients.update(stored)
        uow.commit()

    with uow_factory() as uow:
        again = uow.tenant(clinic_id).patients.get(patient.id)
        assert again is not None
        assert again.full_name == "Changed Name"
        assert again.whatsapp_consent and not again.sms_consent
        assert (again.consent_recorded_at, again.consent_recorded_by) == (LATER, staff_user_id)
        assert again.opted_out_at == LATER
        assert not again.may_receive_whatsapp
        assert again.code == patient.code


# --- Lookups ------------------------------------------------------------------------------------


def test_r5_lookups_find_by_phone_code_and_name_prefix(
    uow_factory: UowFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    shared = PhoneNumber.parse("9000000001")
    asha = a_patient(clinic_id, staff_user_id, full_name="Asha Rao", phone=shared)
    arun = a_patient(clinic_id, staff_user_id, full_name="Arun Rao", phone=shared)
    bina = a_patient(clinic_id, staff_user_id, full_name="BINA Shah")
    with uow_factory() as uow:
        for patient in (asha, arun, bina):
            uow.tenant(clinic_id).patients.add(patient)
        uow.commit()

    with uow_factory() as uow:
        patients = uow.tenant(clinic_id).patients
        # A family shares a phone: both come back, oldest first.
        assert [p.id for p in patients.find_by_phone(shared, limit=10)] == [asha.id, arun.id]
        assert [p.id for p in patients.find_by_phone(shared, limit=1)] == [asha.id]
        assert patients.find_by_phone(PhoneNumber.parse("9000000099"), limit=10) == []
        # Names are matched case-insensitively from the start, ordered by name.
        assert [p.id for p in patients.search_by_name_prefix("a", limit=20)] == [arun.id, asha.id]
        assert [p.id for p in patients.search_by_name_prefix("bin", limit=20)] == [bina.id]
        assert patients.search_by_name_prefix("rao", limit=20) == []  # a prefix, not a substring
        assert len(patients.search_by_name_prefix("a", limit=1)) == 1


def test_a_name_prefix_is_literal_not_a_pattern(
    uow_factory: UowFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    underscore = a_patient(clinic_id, staff_user_id, full_name="A_b Underscore")
    other = a_patient(clinic_id, staff_user_id, full_name="Axb Other")
    percent = a_patient(clinic_id, staff_user_id, full_name="50% Discount")
    plain = a_patient(clinic_id, staff_user_id, full_name="500 Plain")
    with uow_factory() as uow:
        for patient in (underscore, other, percent, plain):
            uow.tenant(clinic_id).patients.add(patient)
        uow.commit()

    with uow_factory() as uow:
        patients = uow.tenant(clinic_id).patients
        assert [p.id for p in patients.search_by_name_prefix("a_", limit=20)] == [underscore.id]
        assert [p.id for p in patients.search_by_name_prefix("50%", limit=20)] == [percent.id]
        assert patients.search_by_name_prefix("\\", limit=20) == []


# --- Constraints the database enforces ---------------------------------------------------------


def test_i3_a_code_is_unique_within_a_clinic(
    uow_factory: UowFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    first = a_patient(clinic_id, staff_user_id, code="PF-0001")
    second = a_patient(clinic_id, staff_user_id, code="PF-0001")
    with uow_factory() as uow:
        uow.tenant(clinic_id).patients.add(first)
        with pytest.raises(IntegrityError) as refused:
            uow.tenant(clinic_id).patients.add(second)
        assert "uq_patients_clinic_id_code" in str(refused.value)


def test_i3_two_clinics_may_use_the_same_code(
    uow_factory: UowFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    other = a_clinic()
    with uow_factory() as uow:
        uow.clinics.add(other)
        uow.tenant(clinic_id).patients.add(a_patient(clinic_id, staff_user_id, code="PF-0001"))
        uow.tenant(other.id).patients.add(a_patient(other.id, staff_user_id, code="PF-0001"))
        uow.commit()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"date_of_birth": None, "age_years_at_registration": None}, "ck_patients_age_known"),
        (
            {"date_of_birth": date(1990, 1, 1), "age_years_at_registration": 30},
            "ck_patients_age_known",
        ),
        (
            {"date_of_birth": None, "age_years_at_registration": 121},
            "ck_patients_age_years_at_registration_range",
        ),
        ({"sex": "ROBOT"}, "ck_patients_sex"),
        ({"language": "fr"}, "ck_patients_language"),
        ({"whatsapp_consent": True}, "ck_patients_consent_recorded"),
    ],
)
def test_the_database_refuses_rows_that_break_the_invariants(
    session_factory: SessionFactory,
    uow_factory: UowFactory,
    clinic_id: UUID,
    staff_user_id: UUID,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    row: dict[str, Any] = {
        "id": new_id(),
        "clinic_id": clinic_id,
        "code": "PF-0001",
        "full_name": "Asha Rao",
        "phone_e164": "+919000000001",
        "sex": "FEMALE",
        "date_of_birth": date(1990, 1, 1),
        "age_years_at_registration": None,
        "registered_on": date(2026, 10, 2),
        "language": "en",
        "whatsapp_consent": False,
        "sms_consent": False,
        "created_by": staff_user_id,
        "created_at": NOW,
        "updated_at": NOW,
        **overrides,
    }
    with session_factory() as session, pytest.raises(IntegrityError) as refused:
        session.execute(insert(PatientRow), [row])
        session.commit()
    assert constraint in str(refused.value)


# --- The clinic's code counter under a lock (R4, R9, AC3) --------------------------------------


def test_r4_a_rolled_back_allocation_leaves_no_gap(
    uow_factory: UowFactory, clinic_id: UUID
) -> None:
    with uow_factory() as uow, pytest.raises(RuntimeError, match="boom"):
        clinic = uow.clinics.get(clinic_id, for_update=True)
        assert clinic is not None
        assert clinic.allocate_patient_code(now=NOW) == "PF-0001"
        uow.clinics.update(clinic)
        raise RuntimeError("boom")  # the registration failed after taking a number

    with uow_factory() as uow:
        clinic = uow.clinics.get(clinic_id, for_update=True)
        assert clinic is not None
        assert clinic.allocate_patient_code(now=NOW) == "PF-0001"
        uow.clinics.update(clinic)
        uow.commit()


def test_ac3_concurrent_registrations_get_unique_gap_free_codes(
    uow_factory: UowFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    """Forty registrations on eight threads: each locks the clinic, takes a number, inserts."""
    registrations = 40

    def register(_: int) -> str:
        with uow_factory() as uow:
            clinic = uow.clinics.get(clinic_id, for_update=True)
            assert clinic is not None
            code = clinic.allocate_patient_code(now=NOW)
            uow.clinics.update(clinic)
            uow.tenant(clinic_id).patients.add(a_patient(clinic_id, staff_user_id, code=code))
            uow.commit()
            return code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(register, range(registrations)))

    assert sorted(codes) == [f"PF-{n:04d}" for n in range(1, registrations + 1)]
    with uow_factory() as uow:
        assert uow.tenant(clinic_id).patients.count() == registrations
        clinic = uow.clinics.get(clinic_id)
        assert clinic is not None and clinic.next_patient_seq == registrations + 1


# --- AC4: 10,000 patients, p95 < 500 ms --------------------------------------------------------

_FIRST = [
    "Aarav", "Aditi", "Akash", "Ananya", "Arjun", "Asha", "Bhavna", "Chetan", "Deepa", "Divya",
    "Farhan", "Gauri", "Harish", "Isha", "Jatin", "Kavya", "Lakshmi", "Manoj", "Neha", "Omkar",
]  # fmt: skip
_LAST = [
    "Agarwal", "Bose", "Chopra", "Desai", "Engineer", "Fernandes", "Gupta", "Hegde", "Iyer",
    "Joshi", "Kulkarni", "Lal", "Menon", "Nair", "Oberoi", "Patel", "Qureshi", "Rao", "Sharma",
    "Trivedi",
]  # fmt: skip
PATIENTS_IN_CLINIC = 10_000


def _bulk_insert(
    session_factory: SessionFactory, clinic_id: UUID, user_id: UUID, prefix: str, count: int
) -> None:
    rng = random.Random(7)
    rows: list[dict[str, Any]] = []
    for n in range(1, count + 1):
        # Every 25th patient shares the previous patient's phone (a family).
        phone_number = 9_000_000_000 + (n - 1 if n % 25 else n - 2)
        rows.append(
            {
                "id": new_id(),
                "clinic_id": clinic_id,
                "code": f"{prefix}-{n:04d}",
                "full_name": f"{rng.choice(_FIRST)} {rng.choice(_LAST)}",
                "phone_e164": f"+91{phone_number}",
                "sex": "UNDISCLOSED",
                "date_of_birth": date(1950 + n % 50, 1 + n % 12, 1 + n % 28),
                "age_years_at_registration": None,
                "registered_on": date(2026, 10, 2),
                "language": "en",
                "whatsapp_consent": False,
                "sms_consent": False,
                "created_by": user_id,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )
    with session_factory() as session:
        session.execute(insert(PatientRow), rows)
        session.commit()
        # Fresh bulk-loaded tables have no statistics yet; autovacuum does this in production.
        session.execute(text("ANALYZE patients"))
        session.commit()


@contextmanager
def _captured_statements(session: Session) -> Iterator[list[tuple[str, Any]]]:
    seen: list[tuple[str, Any]] = []

    def record(_conn: Connection, _cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
        if "FROM patients" in statement:
            seen.append((statement, parameters))

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _p95_ms(samples: list[float]) -> float:
    return statistics.quantiles(samples, n=100, method="inclusive")[94] * 1000


def test_ac4_lookup_over_ten_thousand_patients_is_well_under_500_ms(
    uow_factory: UowFactory, session_factory: SessionFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    other = a_clinic(name="Neighbour Clinic", patient_code_prefix="NB")
    with uow_factory() as uow:
        uow.clinics.add(other)
        uow.commit()
    _bulk_insert(session_factory, clinic_id, staff_user_id, "PF", PATIENTS_IN_CLINIC)
    _bulk_insert(session_factory, other.id, staff_user_id, "NB", 500)  # scoping under load

    rng = random.Random(11)
    timings: dict[str, list[float]] = {"phone": [], "code": [], "name": []}
    with uow_factory() as uow:
        patients = uow.tenant(clinic_id).patients
        assert patients.count() == PATIENTS_IN_CLINIC
        for _ in range(100):
            n = rng.randint(1, PATIENTS_IN_CLINIC)
            phone = PhoneNumber(f"+91{9_000_000_000 + n - 1}")
            prefix = f"{rng.choice(_FIRST)[:3]}".lower()
            for key, call in (
                ("phone", lambda phone=phone: patients.find_by_phone(phone, limit=10)),
                ("code", lambda n=n: patients.get_by_code(f"PF-{n:04d}")),
                ("name", lambda prefix=prefix: patients.search_by_name_prefix(prefix, limit=20)),
            ):
                started = time.perf_counter()
                call()
                timings[key].append(time.perf_counter() - started)

        # Correctness at volume: the right patients, only this clinic's, capped at 20.
        found = patients.search_by_name_prefix("aar", limit=20)
        assert len(found) == 20 and all(p.full_name.lower().startswith("aar") for p in found)
        assert all(p.clinic_id == clinic_id and p.code.startswith("PF-") for p in found)
        family = patients.find_by_phone(PhoneNumber("+919000000023"), limit=10)
        assert [p.code for p in family] == ["PF-0024", "PF-0025"]  # n=25 shares n=24's phone

    report = {key: round(_p95_ms(samples), 2) for key, samples in timings.items()}
    print(f"lookup p95 over {PATIENTS_IN_CLINIC} patients, ms: {report}")  # pytest -s shows it
    for key, p95 in report.items():
        assert p95 < 500, f"{key}: p95 {p95} ms"


def test_ac4_each_lookup_can_be_served_by_an_index(
    uow_factory: UowFactory, session_factory: SessionFactory, clinic_id: UUID, staff_user_id: UUID
) -> None:
    """Plan the repository's own SQL with sequential scans disabled: an index must exist for it."""
    _bulk_insert(session_factory, clinic_id, staff_user_id, "PF", PATIENTS_IN_CLINIC)
    phone = PhoneNumber("+919000000100")
    lookups: dict[str, Callable[[Any], object]] = {
        "phone": lambda repo: repo.find_by_phone(phone, limit=10),
        "code": lambda repo: repo.get_by_code("PF-0100"),
        "name prefix": lambda repo: repo.search_by_name_prefix("aar", limit=20),
    }

    with session_factory() as session:
        repo = SqlAlchemyPatientRepository(session, clinic_id)
        for label, lookup in lookups.items():
            with _captured_statements(session) as seen:
                lookup(repo)
            assert seen, label
            statement, parameters = seen[-1]
            session.execute(text("SET LOCAL enable_seqscan = off"))
            plan = "\n".join(
                row[0]
                for row in session.connection().exec_driver_sql(f"EXPLAIN {statement}", parameters)
            )
            assert "Seq Scan" not in plan, f"{label}: {plan}"
            assert "Index" in plan or "Bitmap" in plan, f"{label}: {plan}"
        session.rollback()
