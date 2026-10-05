"""ImportPatients against PostgreSQL (M2-P4; FR-PAT-08, FR-OPS-02, spec patients R8, R9).

The use case is driven directly, with a fixed clock (2 Oct 2026, 10:00 in Kolkata) and the
production ID generator, so dry run and commit can be compared on the same data.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.application.context import Actor, RequestContext, RequestInfo
from mediease_api.application.patients.errors import ImportInvalid
from mediease_api.application.patients.import_patients import (
    MAX_LISTED,
    MAX_ROWS,
    DuplicateKind,
    ImportPatients,
    ImportPatientsCommand,
    ImportReport,
    RowDuplicate,
    RowError,
)
from mediease_api.application.patients.register_patient import (
    RegisterPatient,
    RegisterPatientCommand,
)
from mediease_api.domain.audit.event import ActorType
from mediease_api.domain.clinics.onboarding import OnboardingStep
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.permissions import permissions_for
from mediease_api.domain.patients.patient import Language, Sex
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from tests.builders import a_clinic, a_patient, a_user, new_id
from tests.conftest import UowFactory
from tests.fakes import FakeClock, FakeIds

SessionFactory = sessionmaker[Session]
HEADER = "name,phone,sex,dob_or_age,guardian_name,language\n"


@pytest.fixture
def ops_actor(uow_factory: UowFactory) -> Actor:
    user = a_user(is_platform_ops=True)
    with uow_factory() as uow:
        uow.users.add(user)
        uow.commit()
    return Actor.for_user(user, RequestInfo(request_id="req-import-test"))


@pytest.fixture
def clinic_id(uow_factory: UowFactory) -> UUID:
    clinic = a_clinic(name="Import Clinic", patient_code_prefix="IM")
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.commit()
    return clinic.id


Run = Callable[..., ImportReport]


@pytest.fixture
def run(uow_factory: UowFactory, clinic_id: UUID, ops_actor: Actor) -> Run:
    def _run(csv: str | bytes, *, dry_run: bool = True, clinic: UUID | None = None) -> ImportReport:
        data = csv.encode() if isinstance(csv, str) else csv
        use_case = ImportPatients(uow=uow_factory(), clock=FakeClock(), ids=FakeIds())
        return use_case.execute(
            clinic_id=clinic or clinic_id,
            actor=ops_actor,
            cmd=ImportPatientsCommand(data=data, dry_run=dry_run),
        )

    return _run


def _count(uow_factory: UowFactory, clinic_id: UUID) -> int:
    with uow_factory() as uow:
        return uow.tenant(clinic_id).patients.count()


def _imported_audit(session_factory: SessionFactory) -> list[tuple[str, str, dict[str, str]]]:
    with session_factory() as session:
        rows = session.execute(
            text(
                "SELECT actor_type, request_id, metadata FROM audit_events "
                "WHERE action = 'patient.imported' ORDER BY occurred_at, id"
            )
        )
        return [(r.actor_type, r.request_id, dict(r.metadata)) for r in rows]


MIXED = (
    HEADER
    + "Asha Rao,90000 00101,F,1990-05-17,,en\n"  # row 2: fine
    + "Meera Rao,9000000101,F,6,Asha Rao,hi\n"  # row 3: same phone as row 2 (a family)
    + "No Phone,,M,40,,\n"  # row 4: invalid phone
    + ",,,,,\n"  # a blank line: not a row
    + "Small Child,9000000102,,4,,\n"  # row 6: a minor without a guardian
    + "Asha Rao,+919000000101,female,17/05/1990,,\n"  # row 7: row 2 again
    + "Deepa Nair,9000000103,,45,,\n"  # row 8: fine; blank sex is UNDISCLOSED (2A)
)


# --- dry run ------------------------------------------------------------------------------------


def test_fr_pat_08_a_dry_run_reports_everything_and_writes_nothing(
    run: Run, uow_factory: UowFactory, clinic_id: UUID, session_factory: SessionFactory
) -> None:
    report = run(MIXED)

    assert report.dry_run is True
    assert (report.rows, report.valid, report.invalid) == (6, 4, 2)
    assert (report.possible_duplicates, report.already_registered, report.imported) == (1, 1, 0)
    assert report.codes == ()
    assert report.errors == (
        RowError(4, "phone", "must not be empty"),
        RowError(6, "guardian_name", "is required for a patient under 18"),
    )
    assert report.duplicates == (
        RowDuplicate(3, DuplicateKind.EARLIER_ROW, same_as_row=2),
        RowDuplicate(7, DuplicateKind.ALREADY_REGISTERED, same_as_row=2),
    )
    assert _count(uow_factory, clinic_id) == 0
    assert _imported_audit(session_factory) == []


def test_r8_a_dry_run_compares_with_the_clinics_patients_and_names_no_one(
    run: Run, uow_factory: UowFactory, clinic_id: UUID
) -> None:
    staff = a_user()
    asha = a_patient(
        clinic_id, staff.id, full_name="Asha  RAO", phone=PhoneNumber.parse("9000000101")
    )
    arun = a_patient(
        clinic_id, staff.id, full_name="Arun Rao", phone=PhoneNumber.parse("9000000101")
    )
    with uow_factory() as uow:
        uow.users.add(staff)
        uow.tenant(clinic_id).patients.add(asha)
        uow.tenant(clinic_id).patients.add(arun)
        uow.commit()

    report = run(HEADER + "asha rao,9000000101,F,36,,\nMeera Rao,9000000101,F,6,Asha Rao,\n")

    assert report.duplicates == (
        RowDuplicate(2, DuplicateKind.ALREADY_REGISTERED, matches=2),
        RowDuplicate(3, DuplicateKind.EXISTING_PATIENT, matches=2),
    )
    assert (report.already_registered, report.possible_duplicates) == (1, 1)
    assert asha.code not in repr(report) and arun.code not in repr(report)
    assert "Asha" not in repr(report) and "9000000101" not in repr(report)


# --- commit -------------------------------------------------------------------------------------


def test_fr_pat_08_a_commit_imports_the_importable_rows_in_file_order(
    run: Run,
    uow_factory: UowFactory,
    clinic_id: UUID,
    session_factory: SessionFactory,
    ops_actor: Actor,
) -> None:
    report = run(MIXED, dry_run=False)

    assert report.dry_run is False
    assert report.imported == 3
    assert report.codes == ("IM-0001", "IM-0002", "IM-0003")
    with uow_factory() as uow:
        patients = uow.tenant(clinic_id).patients
        asha, meera, deepa = (patients.get_by_code(code) for code in report.codes)
        assert asha is not None and meera is not None and deepa is not None
        assert (asha.full_name, asha.sex, asha.language) == ("Asha Rao", Sex.FEMALE, Language.EN)
        assert (meera.age_years_at_registration, meera.guardian_name) == (6, "Asha Rao")
        assert meera.language is Language.HI
        assert deepa.sex is Sex.UNDISCLOSED  # decision 2A
        for patient in (asha, meera, deepa):
            # R8: consent false and "not asked"; the ops user registered them.
            assert not patient.whatsapp_consent and not patient.sms_consent
            assert patient.consent_recorded_at is None
            assert patient.created_by == ops_actor.user_id
        assert uow.clinics.get(clinic_id).next_patient_seq == 4  # type: ignore[union-attr]

    audit = _imported_audit(session_factory)
    assert [metadata["code"] for _, _, metadata in audit] == list(report.codes)
    assert {actor for actor, _, _ in audit} == {ActorType.OPS.value}
    assert {request_id for _, request_id, _ in audit} == {"req-import-test"}
    assert len({metadata["import_id"] for _, _, metadata in audit}) == 1
    assert all(set(metadata) == {"code", "import_id"} for _, _, metadata in audit)


def test_r8_importing_the_same_file_twice_imports_nothing_the_second_time(
    run: Run, uow_factory: UowFactory, clinic_id: UUID
) -> None:
    run(MIXED, dry_run=False)

    again = run(MIXED, dry_run=False)

    assert again.imported == 0
    assert again.already_registered == 4  # rows 2, 3, 7 and 8 all match someone now
    assert _count(uow_factory, clinic_id) == 3


def test_r8_a_commit_rechecks_against_patients_registered_after_the_dry_run(
    run: Run, uow_factory: UowFactory, clinic_id: UUID
) -> None:
    csv = HEADER + "Deepa Nair,9000000103,F,45,,\n"
    assert run(csv).already_registered == 0
    staff = a_user()
    with uow_factory() as uow:
        uow.users.add(staff)
        uow.tenant(clinic_id).patients.add(
            a_patient(
                clinic_id, staff.id, full_name="Deepa Nair", phone=PhoneNumber.parse("9000000103")
            )
        )
        uow.commit()

    committed = run(csv, dry_run=False)

    assert (committed.imported, committed.already_registered) == (0, 1)
    assert _count(uow_factory, clinic_id) == 1


def test_fr_ops_04_the_first_import_records_patients_imported_at_once(
    run: Run, uow_factory: UowFactory, clinic_id: UUID
) -> None:
    run(HEADER + "Deepa Nair,9000000103,F,45,,\n", dry_run=True)
    with uow_factory() as uow:
        assert uow.tenant(clinic_id).checklist.get() is None  # a dry run is not an import

    run(HEADER + "Deepa Nair,9000000103,F,45,,\n", dry_run=False)
    with uow_factory() as uow:
        first = uow.tenant(clinic_id).checklist.get()
    run(HEADER + "Bina Shah,9000000104,F,50,,\n", dry_run=False)
    with uow_factory() as uow:
        second = uow.tenant(clinic_id).checklist.get()

    step = OnboardingStep.PATIENTS_IMPORTED
    assert first is not None and step in first.steps
    assert second is not None and second.steps[step] == first.steps[step]


def test_a_commit_with_nothing_importable_changes_nothing(
    run: Run, uow_factory: UowFactory, clinic_id: UUID
) -> None:
    report = run(HEADER + "No Phone,,M,40,,\n", dry_run=False)

    assert (report.imported, report.invalid) == (0, 1)
    with uow_factory() as uow:
        assert uow.tenant(clinic_id).checklist.get() is None
        assert uow.clinics.get(clinic_id).next_patient_seq == 1  # type: ignore[union-attr]


def test_an_unknown_clinic_is_not_found(run: Run) -> None:
    with pytest.raises(NotFound):
        run(HEADER + "Deepa Nair,9000000103,F,45,,\n", clinic=uuid4())


# --- the file as a whole ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "problems"),
    [
        (b"", ["the file is empty"]),
        (HEADER.encode(), ["the file has no data rows"]),
        (HEADER.encode() + b",,,,,\n,,,,,\n", ["the file has no data rows"]),
        (
            b"name,phone\nAsha,9000000101\n",
            [
                "column sex is missing",
                "column dob_or_age is missing",
                "column guardian_name is missing",
                "column language is missing",
            ],
        ),
        (
            "name,phone,sex,dob_or_age,guardian_name,language\nAsha Ráo,9000000101,F,30,,\n".encode(
                "latin-1"
            ),
            ["the file is not UTF-8 text (save it as CSV UTF-8)"],
        ),
        (HEADER.encode() + b'"Asha,9000000101,F,30,,\n', ["the file is not valid CSV near row 2"]),
        (
            HEADER.encode() + b"Asha,9000000101,F,30,,\n" + b"x" * 200_000 + b"\n",
            ["the file is not valid CSV near row 3"],
        ),
    ],
)
def test_r8_a_file_that_cannot_be_read_imports_nothing(
    run: Run, uow_factory: UowFactory, clinic_id: UUID, data: bytes, problems: list[str]
) -> None:
    for dry_run in (True, False):
        with pytest.raises(ImportInvalid) as caught:
            run(data, dry_run=dry_run)
        assert list(caught.value.problems) == problems
    assert _count(uow_factory, clinic_id) == 0


def test_r8_an_excel_bom_and_windows_line_endings_are_fine(run: Run) -> None:
    data = ("\ufeff" + HEADER + "Asha Rao,9000000101,F,30,,\n").replace("\n", "\r\n")

    assert run(data.encode()).valid == 1


def test_r8_a_row_with_cells_beyond_the_header_is_refused_not_trimmed(run: Run) -> None:
    report = run(
        HEADER + "Asha Rao,9000000101,F,30,,en,diabetic\nDeepa Nair,9000000103,F,45,,en,\n"
    )

    assert report.errors == (RowError(2, "row", "has more cells than the header"),)
    assert report.valid == 1  # an empty trailing cell is harmless


def test_r8_rows_beyond_the_limit_reject_the_file(run: Run) -> None:
    rows = "".join(f"Person {n},9{n:09d},F,30,,\n" for n in range(MAX_ROWS + 1))

    with pytest.raises(ImportInvalid) as caught:
        run(HEADER + rows)

    assert caught.value.problems == (f"the file has more than {MAX_ROWS} data rows; split it",)


def test_the_report_lists_stop_at_the_cap_but_the_counts_do_not(run: Run) -> None:
    rows = "".join(f"Person {n},,F,30,,\n" for n in range(MAX_LISTED + 5))

    report = run(HEADER + rows)

    assert report.invalid == MAX_LISTED + 5
    assert len(report.errors) == MAX_LISTED and report.errors_truncated
    assert not report.duplicates_truncated


# --- concurrency and size -----------------------------------------------------------------------


def test_r9_an_import_and_a_registration_of_the_same_phone_serialise(
    uow_factory: UowFactory, clinic_id: UUID, ops_actor: Actor, session_factory: SessionFactory
) -> None:
    desk = a_user()
    with uow_factory() as uow:
        uow.users.add(desk)
        uow.commit()
    ctx = RequestContext(
        info=RequestInfo(),
        user_id=desk.id,
        session_id=new_id(),
        clinic_id=clinic_id,
        membership_id=new_id(),
        role=Role.FRONT_DESK,
        permissions=permissions_for(Role.FRONT_DESK, has_doctor_profile=False),
    )
    # Hold the clinic lock, start both, then let go: whichever runs second sees the first.
    holder = session_factory()
    holder.execute(text("SELECT 1 FROM clinics WHERE id = :id FOR UPDATE"), {"id": clinic_id})
    started = threading.Barrier(3, timeout=10)

    def import_() -> ImportReport:
        started.wait()
        return ImportPatients(uow=uow_factory(), clock=FakeClock(), ids=FakeIds()).execute(
            clinic_id=clinic_id,
            actor=ops_actor,
            cmd=ImportPatientsCommand(
                data=(HEADER + "Asha Rao,9000000101,F,30,,\n").encode(), dry_run=False
            ),
        )

    def register() -> str:
        started.wait()
        try:
            RegisterPatient(uow=uow_factory(), clock=FakeClock(), ids=FakeIds()).execute(
                ctx,
                RegisterPatientCommand(
                    full_name="Asha Rao", phone="9000000101", sex=Sex.FEMALE, age_years=30
                ),
            )
        except Exception as exc:
            return getattr(exc, "code", type(exc).__name__)
        return "created"

    with ThreadPoolExecutor(max_workers=2) as pool:
        imported, registered = pool.submit(import_), pool.submit(register)
        started.wait()
        time.sleep(0.3)  # both are now waiting on the clinic lock
        holder.rollback()
        holder.close()
        report, outcome = imported.result(), registered.result()

    # Never two Asha Raos: either the import ran first (registration refused as a duplicate)
    # or the registration did (the import skips her as already registered).
    if outcome == "created":
        assert (report.imported, report.already_registered) == (0, 1)
    else:
        assert outcome == "PAT_PHONE_EXISTS" and report.imported == 1
    assert _count(uow_factory, clinic_id) == 1


def test_fr_pat_08_five_thousand_rows_import_well_inside_the_request_timeout(
    run: Run, uow_factory: UowFactory, clinic_id: UUID
) -> None:
    rows = "".join(f"Person {n},9{n:09d},F,{n % 90 + 18},,\n" for n in range(MAX_ROWS))

    started = time.perf_counter()
    report = run(HEADER + rows, dry_run=False)
    elapsed = time.perf_counter() - started

    assert report.imported == MAX_ROWS
    assert report.codes[0] == "IM-0001" and report.codes[-1] == "IM-5000"
    assert _count(uow_factory, clinic_id) == MAX_ROWS
    # gunicorn's worker timeout is 30 s; leave most of it as headroom.
    assert elapsed < 15, f"5,000 rows took {elapsed:.1f} s"
