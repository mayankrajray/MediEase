"""``scripts/watch.sh``, the production watch (M9-P2; RUNBOOK §41), run for real against fakes.

``docker``, ``systemctl``, ``df`` and ``openssl`` are replaced on PATH by small scripts that answer
from files in a temporary folder, so each check and the decision of what to email (new, still
failing once a day, resolved; warnings held outside 08:00-22:00 IST) is exercised without a server.
The "email" is what the script pipes to ``docker compose run ... ops_alert``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "watch.sh"
IST = ZoneInfo("Asia/Kolkata")
SERVICES = "db\nmigrate\napi\nworker\nupload-worker\nclamav\nweb\ncaddy\n"
HEALTHY = (
    "db running healthy\nmigrate exited \napi running healthy\nworker running healthy\n"
    "upload-worker running healthy\nclamav running healthy\nweb running healthy\n"
    "caddy running healthy\n"
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

FAKE_DOCKER = r"""#!/usr/bin/env bash
d="$FAKE_DIR"; shift
case "$1" in
  config) [ -f "$d/compose_down" ] && exit 1; cat "$d/services" ;;
  ps) cat "$d/ps" ;;
  logs) cat "$d/logs" 2>/dev/null; true ;;
  exec) cat "$d/jobs" ;;
  run) { printf 'SUBJECT: %s\n' "${@: -1}"; cat; printf '\n===\n'; } >>"$d/alerts"
       exit "$(cat "$d/alert_exit" 2>/dev/null || echo 0)" ;;
esac
"""
FAKE_SYSTEMCTL = r"""#!/usr/bin/env bash
d="$FAKE_DIR"
case "$1" in
  cat) [ -f "$d/backup_result" ] ;;
  show) case "$4" in Result) cat "$d/backup_result" ;; *) cat "$d/backup_ended" ;; esac ;;
esac
"""
FAKE_DF = r"""#!/usr/bin/env bash
echo "Filesystem 1024-blocks Used Available Capacity Mounted on"
echo "/dev/root 40000000 1 1 $(cat "$FAKE_DIR/disk")% /"
"""
FAKE_OPENSSL = r"""#!/usr/bin/env bash
[ "$1" = x509 ] && { cat >/dev/null; cat "$FAKE_DIR/cert" 2>/dev/null; }
true
"""


def _at(day: int, hour: int) -> int:
    return int(datetime(2026, 11, day, hour, 0, tzinfo=IST).timestamp())


MORNING = _at(27, 10)
NIGHT = _at(27, 23)


@dataclass
class Watch:
    root: Path

    @property
    def fake(self) -> Path:
        return self.root / "fake"

    def put(self, name: str, text: str) -> None:
        (self.fake / name).write_text(text)

    def drop(self, name: str) -> None:
        (self.fake / name).unlink(missing_ok=True)

    def run(self, now: int, **env: str) -> subprocess.CompletedProcess[str]:
        self.drop("alerts")
        full = {
            "PATH": f"{self.root / 'bin'}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.root),
            "FAKE_DIR": str(self.fake),
            "WATCH_ENV_FILE": str(self.root / "no.env"),  # never the developer's .env
            "WATCH_STATE_DIR": str(self.root / "state"),
            "WATCH_NOW": str(now),
            **env,
        }
        return subprocess.run(
            ["bash", str(SCRIPT)], env=full, capture_output=True, text=True, check=False, timeout=60
        )

    @property
    def emails(self) -> list[str]:
        path = self.fake / "alerts"
        return (
            [e.strip() for e in path.read_text().split("===") if e.strip()] if path.exists() else []
        )


@pytest.fixture
def watch(tmp_path: Path) -> Watch:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "docker": FAKE_DOCKER,
        "systemctl": FAKE_SYSTEMCTL,
        "df": FAKE_DF,
        "openssl": FAKE_OPENSSL,
    }.items():
        path = bin_dir / name
        path.write_text(body)
        path.chmod(0o755)
    w = Watch(tmp_path)
    w.fake.mkdir()
    w.put("services", SERVICES)
    w.put("ps", HEALTHY)
    w.put("jobs", "0 0 0\n")
    w.put("disk", "40")
    w.put("backup_result", "success\n")
    w.put("backup_ended", f"@{MORNING - 3600}\n")
    return w


def test_m9_p2_a_healthy_stack_is_all_clear_and_emails_nothing(watch: Watch) -> None:
    result = watch.run(MORNING)
    assert result.returncode == 0, result.stderr
    assert "watch: all clear" in result.stdout
    assert watch.emails == []


def test_m9_p2_the_site_down_is_sent_at_night_once_then_its_recovery(watch: Watch) -> None:
    watch.put("ps", HEALTHY.replace("api running healthy", "api exited "))
    first = watch.run(NIGHT)
    assert first.returncode == 0, first.stderr
    [email] = watch.emails
    assert email.startswith("SUBJECT: 1 new")
    assert "[critical] api is not running (exited)" in email

    assert watch.run(NIGHT + 300).returncode == 0
    assert watch.emails == []  # no repeat every 5 minutes

    watch.put("ps", HEALTHY)
    assert watch.run(NIGHT + 600).returncode == 0
    [resolved] = watch.emails
    assert resolved.startswith("SUBJECT: 1 resolved") and "api is not running" in resolved


def test_m9_p2_warnings_wait_for_clinic_hours(watch: Watch) -> None:
    watch.put("jobs", "3 0 0\n")
    night = watch.run(NIGHT)
    assert night.returncode == 0
    assert watch.emails == []
    assert "[warning] 3 dead jobs in the last 24 hours" in night.stdout
    assert "held until 08:00 IST" in night.stdout

    morning = _at(28, 8) + 120
    assert watch.run(morning).returncode == 0
    [email] = watch.emails
    assert "New problems:" in email and "3 dead jobs" in email


def test_m9_p2_a_lasting_problem_is_repeated_once_a_day(watch: Watch) -> None:
    watch.put("ps", HEALTHY.replace("web running healthy", "web running unhealthy"))
    watch.run(MORNING)
    assert len(watch.emails) == 1
    watch.run(MORNING + 12 * 3600)
    assert watch.emails == []
    watch.run(MORNING + 24 * 3600 + 60)
    [again] = watch.emails
    assert again.startswith("SUBJECT: 1 still failing")
    assert "web is running but unhealthy (since 27 Nov 10:00 IST)" in again


def test_m9_p2_an_email_that_fails_is_tried_again(watch: Watch) -> None:
    watch.put("ps", HEALTHY.replace("db running healthy", "db exited "))
    watch.put("alert_exit", "1")
    failed = watch.run(MORNING)
    assert failed.returncode == 1 and "next run tries again" in failed.stderr
    watch.put("alert_exit", "0")
    watch.run(MORNING + 300)
    [email] = watch.emails
    assert "SUBJECT: 1 new" in email and "db is not running" in email


def test_m9_p2_without_an_alert_address_the_problem_waits_for_one(watch: Watch) -> None:
    watch.put("ps", HEALTHY.replace("caddy running healthy", "caddy exited "))
    watch.put("alert_exit", "3")
    unset = watch.run(MORNING)
    assert unset.returncode == 0 and "OPS_ALERT_EMAIL is not set" in unset.stdout
    watch.put("alert_exit", "0")
    watch.run(MORNING + 300)
    assert "SUBJECT: 1 new" in watch.emails[0]


def test_m9_p2_each_check_names_what_is_wrong_with_counts_only(watch: Watch) -> None:
    watch.drop("services")
    watch.put("services", SERVICES)
    watch.put("ps", HEALTHY.replace("clamav running healthy\n", ""))
    error = '{"event": "app.unexpected_error", "code": "SYS_UNEXPECTED", "level": "error"}\n'
    watch.put("logs", error * 6 + '{"event": "http.access", "status": 200}\n')
    watch.put("jobs", "0 2 900\n")
    watch.put("disk", "91")
    watch.put("backup_result", "exit-code\n")
    watch.put(
        "cert",
        "notAfter="
        + (datetime(2026, 11, 27, tzinfo=IST) + timedelta(days=5)).strftime("%b %d %H:%M:%S %Y GMT")
        + "\n",
    )

    result = watch.run(MORNING, WATCH_HOST="mediease.example.test")
    assert result.returncode == 0, result.stderr
    [email] = watch.emails
    assert email.startswith("SUBJECT: 7 new")
    for expected in (
        "[warning] clamav is not running (missing)",
        "[warning] 6 server errors in the API in the last 5 minutes (threshold 5)",
        "[warning] 2 running jobs stuck for over 5 minutes",
        "[warning] the oldest due job has waited 15 minutes (threshold 10)",
        "[warning] the disk is 91% full (threshold 85%)",
        "[warning] the last backup failed (exit-code)",
        "[warning] the certificate of mediease.example.test ends in 4 days",
    ):
        assert expected in email


def test_m9_p2_no_backup_for_a_day_is_a_problem_and_thresholds_are_settings(watch: Watch) -> None:
    watch.put("backup_ended", f"@{MORNING - 27 * 3600}\n")
    watch.put("disk", "91")
    result = watch.run(MORNING, WATCH_DISK_PERCENT="95")
    [email] = watch.emails
    assert "no backup has finished in the last 26 hours" in email
    assert "disk" not in email, result.stdout


def test_m9_p2_docker_not_answering_is_critical(watch: Watch) -> None:
    watch.put("compose_down", "")
    watch.run(NIGHT)
    [email] = watch.emails
    assert "[critical] docker compose does not answer" in email


def test_m9_p2_the_dry_run_shows_the_email_and_keeps_no_state(watch: Watch) -> None:
    watch.put("ps", HEALTHY.replace("api running healthy", "api exited "))
    dry = watch.run(MORNING, WATCH_DRY_RUN="1")
    assert dry.returncode == 0
    assert 'would email "1 new"' in dry.stdout and watch.emails == []
    assert not (watch.root / "state" / "state.tsv").exists()
    watch.run(MORNING + 60)
    assert len(watch.emails) == 1  # the real run still treats it as new
