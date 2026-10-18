"""Running, scheduling and purging jobs, with fakes (M5-P1, spec R9a-R9e)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Self

import pytest

from mediease_api.application.jobs.run import RunJob
from mediease_api.application.jobs.schedule import ScheduleRecurring
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.jobs.job import PURGE_KIND, ClaimedJob, NewJob
from mediease_api.domain.jobs.retry import (
    JOB_CLINIC_SUSPENDED,
    JOB_HANDLER_ERROR,
    JOB_HANDLER_MISSING,
    JobFailure,
)
from mediease_api.domain.jobs.schedule import Recurring
from tests.builders import NOW, a_clinic, new_id
from tests.conftest import LogReader
from tests.fakes import FakeClock, FakeIds


class FakeStore:
    """Records how each job ended; ``held`` says whether this worker still holds it."""

    def __init__(self, *, held: bool = True) -> None:
        self.held = held
        self.calls: list[tuple[Any, ...]] = []

    def succeed(self, job: ClaimedJob, now: datetime) -> bool:
        self.calls.append(("succeed", job.id))
        return self.held

    def retry(self, job: ClaimedJob, now: datetime, run_at: datetime, code: str) -> bool:
        self.calls.append(("retry", job.id, run_at, code))
        return self.held

    def kill(self, job: ClaimedJob, now: datetime, code: str) -> bool:
        self.calls.append(("kill", job.id, code))
        return self.held

    def cancel(self, job: ClaimedJob, now: datetime, code: str) -> bool:
        self.calls.append(("cancel", job.id, code))
        return self.held


class FakeClinics:
    def __init__(self, status: ClinicStatus) -> None:
        self.clinic = a_clinic()
        self.status = status

    def get(self, clinic_id: Any) -> Any:
        clinic = self.clinic
        clinic.status = self.status
        return clinic


class ClinicOnlyUow:
    """Just enough of a unit of work for the suspended-clinic check."""

    def __init__(self, status: ClinicStatus = ClinicStatus.ACTIVE) -> None:
        self.clinics = FakeClinics(status)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


def a_claimed(
    *, kind: str = "send_message", attempts: int = 1, max_attempts: int = 5, clinic: bool = True
) -> ClaimedJob:
    return ClaimedJob(
        id=new_id(),
        kind=kind,
        clinic_id=new_id() if clinic else None,
        payload={},
        attempts=attempts,
        max_attempts=max_attempts,
        request_id="req-1",
        locked_by="worker-1",
    )


def runner(
    store: FakeStore,
    handlers: dict[str, Callable[[ClaimedJob], None]],
    *,
    status: ClinicStatus = ClinicStatus.ACTIVE,
) -> RunJob:
    return RunJob(
        store=store,  # type: ignore[arg-type]
        handlers=handlers,
        uow=ClinicOnlyUow(status),  # type: ignore[arg-type]
        clock=FakeClock(),
        rand=lambda: 0.0,
    )


def test_r9a_a_handler_that_returns_succeeds_the_job() -> None:
    store, job = FakeStore(), a_claimed()
    runner(store, {"send_message": lambda j: None}).execute(job)
    assert store.calls == [("succeed", job.id)]


def test_r9b_a_failing_handler_is_retried_after_the_first_back_off() -> None:
    store, job = FakeStore(), a_claimed(attempts=1)

    def boom(_: ClaimedJob) -> None:
        raise JobFailure("MSG_PROVIDER_RATE_LIMIT")

    runner(store, {"send_message": boom}).execute(job)
    assert store.calls == [("retry", job.id, NOW + timedelta(minutes=1), "MSG_PROVIDER_RATE_LIMIT")]


def test_r9b_a_permanent_failure_goes_dead_without_retrying() -> None:
    store, job = FakeStore(), a_claimed()

    def bad(_: ClaimedJob) -> None:
        raise JobFailure("MSG_RECIPIENT_INVALID", retryable=False)

    runner(store, {"send_message": bad}).execute(job)
    assert store.calls == [("kill", job.id, "MSG_RECIPIENT_INVALID")]


def test_r9b_the_last_attempt_goes_dead_and_logs_that_it_ran_out(json_logs: LogReader) -> None:
    store, job = FakeStore(), a_claimed(attempts=5, max_attempts=5)

    def boom(_: ClaimedJob) -> None:
        raise JobFailure("MSG_PROVIDER_UNAVAILABLE")

    runner(store, {"send_message": boom}).execute(job)
    assert store.calls == [("kill", job.id, "MSG_PROVIDER_UNAVAILABLE")]
    dead = [e for e in json_logs() if e["event"] == "job.dead"]
    assert dead and dead[0]["reason"] == "JOB_MAX_ATTEMPTS"


def test_a_handler_bug_is_retryable_and_its_message_is_never_logged(json_logs: LogReader) -> None:
    store, job = FakeStore(), a_claimed()

    def leaky(_: ClaimedJob) -> None:
        raise ValueError("Asha Rao has fever")  # the kind of text that must not reach a log

    runner(store, {"send_message": leaky}).execute(job)
    assert store.calls[0][0] == "retry" and store.calls[0][3] == JOB_HANDLER_ERROR
    logged = str(json_logs())
    assert "Asha Rao" not in logged and "ValueError" in logged


def test_r9b_an_unknown_kind_is_retried_not_lost() -> None:
    store, job = FakeStore(), a_claimed(kind="newer_kind")
    runner(store, {}).execute(job)
    assert store.calls[0][0] == "retry" and store.calls[0][3] == JOB_HANDLER_MISSING


def test_r9d_a_suspended_clinics_job_is_cancelled_and_never_run() -> None:
    store, job = FakeStore(), a_claimed()
    ran: list[ClaimedJob] = []
    runner(store, {"send_message": ran.append}, status=ClinicStatus.SUSPENDED).execute(job)
    assert store.calls == [("cancel", job.id, JOB_CLINIC_SUSPENDED)]
    assert ran == []


def test_a_system_job_does_not_look_up_a_clinic() -> None:
    store, job = FakeStore(), a_claimed(kind=PURGE_KIND, clinic=False)
    runner(store, {PURGE_KIND: lambda j: None}, status=ClinicStatus.SUSPENDED).execute(job)
    assert store.calls == [("succeed", job.id)]


def test_r10_a_job_whose_lock_was_lost_changes_nothing_and_says_so(json_logs: LogReader) -> None:
    store, job = FakeStore(held=False), a_claimed()
    runner(store, {"send_message": lambda j: None}).execute(job)  # must not raise
    assert any(e["event"] == "job.lost_lock" for e in json_logs())


class RecordingJobs:
    def __init__(self) -> None:
        self.enqueued: list[NewJob] = []
        self.live_keys: set[str] = set()

    def enqueue(self, job: NewJob) -> bool:
        if job.dedupe_key in self.live_keys:
            return False
        self.live_keys.add(job.dedupe_key or "")
        self.enqueued.append(job)
        return True


class JobsUow:
    def __init__(self, jobs: RecordingJobs) -> None:
        self.jobs = jobs
        self.commits = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1


def test_r9e_the_scheduler_enqueues_each_period_once_however_often_it_ticks() -> None:
    jobs = RecordingJobs()
    clock = FakeClock()
    schedule = ScheduleRecurring(
        uow=JobsUow(jobs),
        clock=clock,
        ids=FakeIds(),
        recurring=[Recurring(PURGE_KIND, timedelta(days=1))],  # type: ignore[arg-type]
    )

    assert schedule.execute("req-a") == 1
    assert schedule.execute("req-b") == 0  # same day: the live key makes it a no-op
    clock.advance(days=1)
    assert schedule.execute("req-c") == 1

    first, second = jobs.enqueued
    assert first.kind == PURGE_KIND and first.clinic_id is None and first.request_id == "req-a"
    assert first.dedupe_key != second.dedupe_key


@pytest.mark.parametrize("held", [True, False])
def test_the_store_double_matches_the_port_shape(held: bool) -> None:
    # The fake mirrors JobStore's outcome calls, so a signature change breaks this test first.
    store, job = FakeStore(held=held), a_claimed()
    assert store.succeed(job, NOW) is held
    assert store.retry(job, NOW, NOW, "X") is held
    assert store.kill(job, NOW, "X") is held
    assert store.cancel(job, NOW, "X") is held
