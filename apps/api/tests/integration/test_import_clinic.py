"""The clinic import (M9-P1 C2; spec clinic-import) against a real migrated database.

The bundled demo clinic is invented data; the broken copies are made in a temporary folder.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text

from mediease_api.adapters.security.argon2_hasher import Argon2PasswordHasher
from mediease_api.config.settings import AppEnv, load_settings
from mediease_api.delivery.cli import import_clinic
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.time import local_date
from tests.conftest import TEST_IP_SALT, TEST_SIGNING_KEY, SetEnv, UowFactory

SLUG = "kesar-bagh-family-clinic"
PASSWORD = "import-test-password-1"


@pytest.fixture
def import_env(set_env: SetEnv, migrated_database_url: str) -> dict[str, str]:
    env = {
        "APP_ENV": "local",
        "DATABASE_URL": migrated_database_url,
        "JWT_SIGNING_KEY": TEST_SIGNING_KEY,
        "AUDIT_IP_SALT": TEST_IP_SALT,
    }
    set_env(env)
    return env


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _count(db: Engine, sql: str) -> int:
    with db.connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


def _demo_copy(tmp_path: Path) -> Path:
    folder = tmp_path / "clinic"
    shutil.copytree(Path(str(import_clinic.demo_source())), folder)
    return folder


def test_m9_p1_the_demo_clinic_imports_with_its_history_logins_and_reminders(
    import_env: dict[str, str],
    uow_factory: UowFactory,
    db: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert import_clinic.main(["--demo", "--dry-run"]) == 0
    assert "dry run, nothing written" in capsys.readouterr().out
    assert _count(db, "SELECT count(*) FROM clinics") == 0

    assert import_clinic.main(["--demo"]) == 0
    out = capsys.readouterr().out
    assert f"clinic '{SLUG}' imported" in out

    with uow_factory() as uow:
        clinic = uow.clinics.get_by_slug(SLUG)
        assert clinic is not None and clinic.status is ClinicStatus.ACTIVE
        assert clinic.is_verified and clinic.listed
        staff = uow.tenant(clinic.id)
        assert sorted(m.role for m in staff.memberships.list()) == sorted(
            [Role.OWNER, Role.DOCTOR, Role.DOCTOR, Role.FRONT_DESK]
        )
        assert len(staff.doctors.list()) == 2
        assert staff.patients.count() == 20
        today = local_date(datetime.now(UTC), clinic.timezone)
        pending = staff.reminders.pending_follow_ups(
            today=today, timezone=clinic.timezone, limit=50, offset=0
        )
        # V01, V02, V08 and V12 are overdue; V05's patient came back (V20), so it is not.
        assert len(pending) == 4

        # Each login works with the password printed once.
        desk = uow.users.get_by_email(EmailAddress.parse("mentor.desk@demo-clinic.example"))
        assert desk is not None and desk.password_hash is not None
        line = next(x for x in out.splitlines() if "mentor.desk@demo-clinic.example" in x)
        assert Argon2PasswordHasher().verify(desk.password_hash, line.split()[-1])
        account = uow.patient_accounts.get_password_account(
            EmailAddress.parse("mentor.patient@demo-clinic.example")
        )
        assert account is not None and account.email_verified_at is not None

    sql = {
        "SELECT count(*) FROM visits WHERE status = 'COMPLETED'": 26,
        "SELECT count(*) FROM appointments WHERE status = 'COMPLETED'": 26,
        "SELECT count(*) FROM appointments WHERE status = 'BOOKED'": 10,
        "SELECT count(*) FROM prescriptions WHERE status = 'ISSUED'": 24,
        "SELECT count(*) FROM bills WHERE status = 'ISSUED'": 26,
        "SELECT count(*) FROM payments": 23,
        "SELECT count(*) FROM patient_account_links": 1,
        # V18, V22 and V24 have follow-ups ahead: one reminder each, with its send job.
        "SELECT count(*) FROM reminders WHERE kind = 'FOLLOW_UP'": 3,
        # Nothing about the past is sent now: no prescription link or confirmation jobs.
        "SELECT count(*) FROM jobs WHERE kind IN ('send_rx_link', 'send_booking_confirmation')": 0,
    }
    for query, expected in sql.items():
        assert _count(db, query) == expected, query
    # The bill numbers run in visit order without gaps.
    assert _count(db, "SELECT max(seq) FROM bills") == 26


def test_m9_p1_an_existing_slug_or_login_is_refused_and_nothing_changes(
    import_env: dict[str, str],
    uow_factory: UowFactory,
    db: Engine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert import_clinic.main(["--demo", "--password", PASSWORD]) == 0
    capsys.readouterr()
    visits = _count(db, "SELECT count(*) FROM visits")

    assert import_clinic.main(["--demo", "--password", PASSWORD]) == 1
    err = capsys.readouterr().err
    assert "clinic.csv line 2, column slug: a clinic with this slug already exists" in err
    assert "nothing written" in err
    assert _count(db, "SELECT count(*) FROM visits") == visits


def test_m9_p1_a_problem_names_the_file_line_and_column_and_writes_nothing(
    import_env: dict[str, str],
    uow_factory: UowFactory,
    db: Engine,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder = _demo_copy(tmp_path)
    visits = folder / "visits.csv"
    body = visits.read_text(encoding="utf-8")
    visits.write_text(body.replace("V03,P06,doctor.two@", "V03,P06,nobody@", 1), encoding="utf-8")
    assert import_clinic.main(["--dir", str(folder)]) == 1
    err = capsys.readouterr().err
    assert "visits.csv line 4, column doctor_email: is not a doctor in staff.csv" in err
    assert "nobody@" not in err  # the value itself is never echoed
    assert _count(db, "SELECT count(*) FROM clinics") == 0

    # A visit outside every session of its day is refused while writing, also located.
    visits.write_text(body.replace("today-12,11:15", "today-12,15:30", 1), encoding="utf-8")
    assert import_clinic.main(["--dir", str(folder)]) == 1
    err = capsys.readouterr().err
    assert "visits.csv line 4: no session of Dr. Kavya Iyer covers 15:30" in err
    assert _count(db, "SELECT count(*) FROM clinics") == 0


def test_m9_p1_an_unknown_column_and_a_bad_value_are_named(
    import_env: dict[str, str],
    uow_factory: UowFactory,
    db: Engine,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder = _demo_copy(tmp_path)
    patients = folder / "patients.csv"
    body = patients.read_text(encoding="utf-8")
    patients.write_text(body.replace("guardian_name", "guardian", 1), encoding="utf-8")
    assert import_clinic.main(["--dir", str(folder)]) == 1
    assert "patients.csv: unknown column 'guardian'" in capsys.readouterr().err

    patients.write_text(body.replace("1992-04-18", "18/04/1992", 1), encoding="utf-8")
    assert import_clinic.main(["--dir", str(folder)]) == 1
    assert (
        "patients.csv line 2, column date_of_birth: write a date as 1990-05-17"
        in capsys.readouterr().err
    )


def test_m9_p1_production_asks_for_the_slug_before_writing(
    import_env: dict[str, str],
    uow_factory: UowFactory,
    db: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The test database's URL is a local placeholder, which production settings refuse; only
    # the environment's name matters here.
    local = load_settings()
    monkeypatch.setattr(
        import_clinic,
        "load_settings",
        lambda: local.model_copy(update={"APP_ENV": AppEnv.PRODUCTION}),
    )
    asked: list[str] = []

    def wrong(prompt: str) -> str:
        asked.append(prompt)
        return "something-else"

    assert import_clinic.main(["--demo", "--password", PASSWORD], ask=wrong) == 2
    assert asked and "production" in asked[0]
    assert "not confirmed" in capsys.readouterr().err
    assert _count(db, "SELECT count(*) FROM clinics") == 0

    assert import_clinic.main(["--demo", "--password", PASSWORD, "--confirm", SLUG]) == 0
    assert _count(db, "SELECT count(*) FROM clinics") == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("today", 0), ("today-3", -3), ("Today + 2", 2), ("2026-11-10", None)],
)
def test_m9_p1_dates_may_be_relative_to_the_import_day(raw: str, expected: int | None) -> None:
    today = datetime(2026, 11, 14, tzinfo=UTC).date()
    day = import_clinic.parse_day(raw, today)
    if expected is None:
        assert day.isoformat() == "2026-11-10"
    else:
        assert (day - today).days == expected
    with pytest.raises(ValueError, match="today-3"):
        import_clinic.parse_day("yesterday", today)


def test_m9_p1_an_unreadable_file_is_a_named_problem_not_a_crash(tmp_path: Path) -> None:
    folder = _demo_copy(tmp_path)
    (folder / "clinic.csv").chmod(0)
    try:
        with pytest.raises(import_clinic.ImportProblem, match=r"clinic\.csv: cannot be read"):
            import_clinic.read_rows(folder, import_clinic.FILES["clinic.csv"])
    finally:
        (folder / "clinic.csv").chmod(0o644)
