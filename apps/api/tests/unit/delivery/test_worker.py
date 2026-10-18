"""The worker loop and its heartbeat, with everything injected (M5-P1, spec R9, R11a)."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from mediease_api.delivery.worker import heartbeat
from mediease_api.delivery.worker.loop import MAINTENANCE_EVERY, LockRenewer, Worker
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.ports.jobs import ReapResult
from tests.builders import new_id
from tests.conftest import LogReader
from tests.fakes import FakeClock


def a_claimed(n: int = 1) -> ClaimedJob:
    return ClaimedJob(
        id=new_id(),
        kind="send_message",
        clinic_id=new_id(),
        payload={},
        attempts=n,
        max_attempts=5,
        request_id="req-1",
        locked_by="w1",
    )


class FakeStore:
    def __init__(self, jobs: Sequence[ClaimedJob] = ()) -> None:
        self.to_claim = list(jobs)
        self.claims: list[tuple[str, int]] = []
        self.released: list[ClaimedJob] = []
        self.reaps = 0
        self.fail_with: Exception | None = None
        self.heartbeats: list[ClaimedJob] = []
        self.hold = True

    def claim(self, worker: str, now: datetime, limit: int) -> Sequence[ClaimedJob]:
        if self.fail_with is not None:
            raise self.fail_with
        self.claims.append((worker, limit))
        taken, self.to_claim = self.to_claim[:limit], self.to_claim[limit:]
        return taken

    def release(self, job: ClaimedJob, now: datetime) -> bool:
        self.released.append(job)
        return True

    def reap(self, now: datetime, stale_after: timedelta, failure: Any, rand: Any) -> ReapResult:
        self.reaps += 1
        return ReapResult(requeued=0, dead=0)

    def heartbeat(self, job: ClaimedJob, now: datetime) -> bool:
        self.heartbeats.append(job)
        return self.hold


class FakeRunJob:
    def __init__(self, on_run: Callable[[ClaimedJob], None] | None = None) -> None:
        self.ran: list[ClaimedJob] = []
        self._on_run = on_run

    def execute(self, job: ClaimedJob) -> None:
        self.ran.append(job)
        if self._on_run is not None:
            self._on_run(job)


class FakeSchedule:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def execute(self, request_id: str) -> int:
        self.requests.append(request_id)
        return 0


class Rig:
    def __init__(self, jobs: Sequence[ClaimedJob] = (), *, batch: int = 10) -> None:
        self.store = FakeStore(jobs)
        self.run_job = FakeRunJob()
        self.schedule = FakeSchedule()
        self.clock = FakeClock()
        self.beats = 0
        self.sleeps: list[float] = []
        self.stop = False
        self.worker = Worker(
            worker_id="w1",
            store=self.store,  # type: ignore[arg-type]
            run_job=self.run_job,  # type: ignore[arg-type]
            schedule=self.schedule,  # type: ignore[arg-type]
            clock=self.clock,
            rand=lambda: 0.0,
            request_id=lambda: "tick-req",
            beat=self._beat,
            sleep=self.sleeps.append,
            stopping=lambda: self.stop,
            batch_size=batch,
            poll_seconds=2.0,
            renewer=lambda job: _nothing(),
        )

    def _beat(self) -> None:
        self.beats += 1


@contextmanager
def _nothing() -> Iterator[None]:
    yield


def test_r9_a_poll_claims_a_batch_and_runs_each_job_in_turn() -> None:
    jobs = [a_claimed(), a_claimed(), a_claimed()]
    rig = Rig(jobs, batch=10)

    assert rig.worker.iterate() == 3

    assert rig.store.claims == [("w1", 10)]
    assert rig.run_job.ran == jobs
    assert rig.sleeps == []  # busy: straight on to the next poll


def test_r9_an_idle_poll_sleeps_the_poll_interval() -> None:
    rig = Rig()
    assert rig.worker.iterate() == 0
    assert rig.sleeps == [2.0]


def test_r11a_the_heartbeat_is_rewritten_after_a_poll_that_reached_the_database() -> None:
    rig = Rig()
    rig.worker.iterate()
    rig.worker.iterate()
    assert rig.beats == 2


def test_r11a_a_dead_database_connection_leaves_the_heartbeat_alone(json_logs: LogReader) -> None:
    rig = Rig()
    rig.worker.iterate()
    assert rig.beats == 1

    rig.store.fail_with = ConnectionError("password=hunter2 host=db")
    rig.worker.iterate()
    rig.worker.iterate()

    assert rig.beats == 1  # no new beat while the database is unreachable
    failed = [e for e in json_logs() if e["event"] == "worker.poll_failed"]
    assert [e["consecutive"] for e in failed] == [1, 2]
    assert "hunter2" not in str(failed)  # the error's type is logged, never its message
    assert failed[0]["error_type"] == "ConnectionError"


def test_r11a_failed_polls_back_off_and_a_good_one_resets_the_count() -> None:
    rig = Rig()
    rig.store.fail_with = ConnectionError()
    for _ in range(8):
        rig.worker.iterate()
    assert rig.sleeps[:3] == [4.0, 8.0, 16.0]
    assert max(rig.sleeps) == 30.0  # capped

    rig.store.fail_with = None
    rig.worker.iterate()
    rig.store.fail_with = ConnectionError()
    rig.sleeps.clear()
    rig.worker.iterate()
    assert rig.sleeps == [4.0]  # counting again from one


def test_r9e_r10_maintenance_runs_on_the_first_poll_then_at_most_once_a_minute() -> None:
    rig = Rig()
    rig.worker.iterate()
    assert (len(rig.schedule.requests), rig.store.reaps) == (1, 1)
    assert rig.schedule.requests == ["tick-req"]  # R11: the tick's own request ID

    rig.clock.advance(seconds=59)
    rig.worker.iterate()
    assert (len(rig.schedule.requests), rig.store.reaps) == (1, 1)

    rig.clock.advance(seconds=2)
    rig.worker.iterate()
    assert (len(rig.schedule.requests), rig.store.reaps) == (2, 2)
    assert timedelta(minutes=1) == MAINTENANCE_EVERY


def test_a_stop_request_runs_the_job_in_hand_and_hands_back_the_rest() -> None:
    first, second, third = a_claimed(), a_claimed(), a_claimed()
    rig = Rig([first, second, third])
    rig.run_job = FakeRunJob(on_run=lambda job: setattr(rig, "stop", True))
    rig.worker._run_job = rig.run_job  # type: ignore[assignment]

    assert rig.worker.iterate() == 1

    assert rig.run_job.ran == [first]
    assert rig.store.released == [second, third]  # claimed but never started: given back


def test_run_stops_when_told_to_and_logs_it(json_logs: LogReader) -> None:
    rig = Rig()
    polls = iter([False, False, True])
    rig.worker._stopping = lambda: next(polls)  # type: ignore[method-assign]

    rig.worker.run()

    events = [e["event"] for e in json_logs()]
    assert events[0] == "worker.started" and events[-1] == "worker.stopped"
    assert rig.beats == 2


def test_r11_a_running_job_is_logged_with_its_ids(json_logs: LogReader) -> None:
    job = a_claimed()
    rig = Rig([job])
    seen: list[dict[str, Any]] = []

    def capture(_: ClaimedJob) -> None:
        import structlog

        seen.append(dict(structlog.contextvars.get_contextvars()))

    rig.worker._run_job = FakeRunJob(on_run=capture)  # type: ignore[assignment]
    rig.worker.iterate()

    assert seen[0]["job_id"] == str(job.id)
    assert seen[0]["request_id"] == "req-1" and seen[0]["worker_id"] == "w1"
    claimed = [e for e in json_logs() if e["event"] == "job.claimed"]
    assert claimed and claimed[0]["job_kind"] == "send_message"


def test_r9_the_lock_is_renewed_while_a_handler_runs_and_stops_afterwards() -> None:
    store, job = FakeStore(), a_claimed()
    renewer = LockRenewer(store, FakeClock(), every=0.01)  # type: ignore[arg-type]

    with renewer.hold(job):
        deadline = time.monotonic() + 2
        while not store.heartbeats and time.monotonic() < deadline:
            time.sleep(0.005)
    seen = len(store.heartbeats)
    time.sleep(0.05)

    assert seen >= 1
    assert len(store.heartbeats) == seen  # no renewals after the handler finished
    assert all(t.name != f"lock-renewer-{job.id}" for t in threading.enumerate())


def test_r10_a_renewer_that_lost_the_lock_stops_trying(json_logs: LogReader) -> None:
    store, job = FakeStore(), a_claimed()
    store.hold = False
    renewer = LockRenewer(store, FakeClock(), every=0.01)  # type: ignore[arg-type]

    with renewer.hold(job):
        time.sleep(0.15)

    assert len(store.heartbeats) == 1
    assert any(e["event"] == "job.lost_lock" for e in json_logs())


def test_r11a_the_health_check_is_healthy_only_while_the_file_is_fresh(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    assert not heartbeat.is_healthy(path)  # no beat yet

    heartbeat.beat(path)
    assert heartbeat.is_healthy(path)
    now = path.stat().st_mtime
    assert heartbeat.is_healthy(path, now=now + 89)
    assert not heartbeat.is_healthy(path, now=now + 91)

    os.utime(path, (now - 300, now - 300))
    assert not heartbeat.is_healthy(path)  # a stale file fails the check


@pytest.mark.parametrize("healthy,expected", [(True, 0), (False, 1)])
def test_r11a_the_health_command_exits_with_the_verdict(
    monkeypatch: pytest.MonkeyPatch, healthy: bool, expected: int
) -> None:
    monkeypatch.setattr(heartbeat, "is_healthy", lambda: healthy)
    assert heartbeat.main() == expected
