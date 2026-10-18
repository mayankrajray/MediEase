"""Jobs: creation rules, back-off, the dead state and recurring keys (M5-P1, spec R9-R11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mediease_api.domain.jobs.job import PURGE_KIND, SYSTEM_KINDS, NewJob
from mediease_api.domain.jobs.retry import (
    BACKOFF,
    JOB_HANDLER_ERROR,
    JobFailure,
    Outcome,
    decide,
    delay_after,
)
from mediease_api.domain.jobs.schedule import (
    RECURRING,
    Recurring,
    RetentionCutoffs,
    dedupe_key,
    period_start,
)
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, new_id


def a_job(**overrides: object) -> NewJob:
    fields: dict[str, object] = {
        "id": new_id(),
        "kind": "send_message",
        "now": NOW,
        "clinic_id": new_id(),
    }
    fields.update(overrides)
    return NewJob.create(**fields)  # type: ignore[arg-type]


def test_r9d_a_clinic_job_needs_its_clinic_and_a_system_job_has_none() -> None:
    assert a_job().clinic_id is not None
    with pytest.raises(InvalidValue):
        a_job(clinic_id=None)  # an ordinary kind with no clinic
    with pytest.raises(InvalidValue):
        a_job(kind=PURGE_KIND, clinic_id=new_id())  # a system kind with one
    assert a_job(kind=PURGE_KIND, clinic_id=None).clinic_id is None


def test_r9d_the_purge_is_a_system_kind() -> None:
    assert PURGE_KIND in SYSTEM_KINDS
    assert {r.kind for r in RECURRING} <= SYSTEM_KINDS  # nothing recurring belongs to a clinic


@pytest.mark.parametrize("kind", ["", "ab", "Send", "send-message", "1send", "x" * 65])
def test_kind_must_be_a_lowercase_identifier(kind: str) -> None:
    with pytest.raises(InvalidValue):
        a_job(kind=kind)


@pytest.mark.parametrize("attempts", [0, 21, -1])
def test_max_attempts_is_between_1_and_20(attempts: int) -> None:
    with pytest.raises(InvalidValue):
        a_job(max_attempts=attempts)


def test_r11_a_payload_is_flat_ids_and_flags_and_read_only() -> None:
    job = a_job(payload={"reminder_id": str(new_id()), "attempt_group": 1, "urgent": False})
    with pytest.raises(TypeError):
        job.payload["x"] = "y"  # type: ignore[index]
    with pytest.raises(InvalidValue):
        a_job(payload={"nested": {"a": 1}})  # type: ignore[dict-item]
    with pytest.raises(InvalidValue):
        a_job(payload={"text": "x" * 201})


def test_a_job_is_due_now_unless_told_otherwise() -> None:
    later = NOW + timedelta(hours=2)
    assert a_job().run_at == NOW
    assert a_job(run_at=later).run_at == later
    with pytest.raises(InvalidValue):
        a_job(run_at=datetime(2026, 10, 2, 4, 30))  # naive


def test_r9b_the_back_off_is_1_5_15_then_60_minutes() -> None:
    assert (
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=15),
        timedelta(minutes=60),
    ) == BACKOFF
    assert [delay_after(n, 0.0) for n in (1, 2, 3, 4, 5, 9)] == [
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=15),
        timedelta(minutes=60),
        timedelta(minutes=60),
        timedelta(minutes=60),
    ]


def test_r9b_jitter_adds_at_most_ten_percent() -> None:
    assert delay_after(2, 0.5) == timedelta(minutes=5) * 1.05
    assert delay_after(2, 0.999999) < timedelta(minutes=5) * 1.1
    assert delay_after(2, 7.0) == timedelta(minutes=5) * 1.1  # out of range is clamped


def test_r9b_a_retryable_failure_with_attempts_left_is_retried_later() -> None:
    decision = decide(
        attempts=2, max_attempts=5, failure=JobFailure(JOB_HANDLER_ERROR), now=NOW, rand=0.0
    )
    assert decision.outcome is Outcome.RETRY
    assert decision.run_at == NOW + timedelta(minutes=5)
    assert decision.code == JOB_HANDLER_ERROR and not decision.exhausted


def test_r9b_the_last_attempt_ends_dead_and_says_it_ran_out() -> None:
    decision = decide(
        attempts=5, max_attempts=5, failure=JobFailure(JOB_HANDLER_ERROR), now=NOW, rand=0.0
    )
    assert decision.outcome is Outcome.DEAD and decision.exhausted
    assert decision.code == JOB_HANDLER_ERROR  # the cause stays visible


def test_r9b_a_permanent_failure_is_dead_at_once() -> None:
    failure = JobFailure("MSG_RECIPIENT_INVALID", retryable=False)
    decision = decide(attempts=1, max_attempts=5, failure=failure, now=NOW, rand=0.0)
    assert decision.outcome is Outcome.DEAD and not decision.exhausted
    assert decision.code == "MSG_RECIPIENT_INVALID"


def test_a_job_failure_can_be_raised_and_carries_its_code() -> None:
    with pytest.raises(JobFailure) as raised:
        raise JobFailure("MSG_TEMPLATE_PARAMS", retryable=False)
    assert raised.value.code == "MSG_TEMPLATE_PARAMS" and not raised.value.retryable
    assert str(raised.value) == "MSG_TEMPLATE_PARAMS"


def test_r9e_every_tick_in_a_day_makes_the_same_key_and_the_next_day_a_new_one() -> None:
    daily = Recurring(PURGE_KIND, timedelta(days=1))
    morning = datetime(2026, 10, 18, 0, 0, 1, tzinfo=UTC)
    evening = datetime(2026, 10, 18, 23, 59, 59, tzinfo=UTC)
    midnight = datetime(2026, 10, 19, 0, 0, 0, tzinfo=UTC)
    assert dedupe_key(daily, morning) == dedupe_key(daily, evening)
    assert dedupe_key(daily, evening) != dedupe_key(daily, midnight)
    assert dedupe_key(daily, morning) == f"{PURGE_KIND}:20261018T000000Z"


def test_period_start_counts_from_the_epoch_in_utc() -> None:
    hourly = timedelta(hours=1)
    assert period_start(datetime(2026, 10, 18, 5, 59, tzinfo=UTC), hourly) == datetime(
        2026, 10, 18, 5, 0, tzinfo=UTC
    )


def test_retention_cutoffs_keep_thirty_days_and_dead_jobs_ninety() -> None:
    cutoffs = RetentionCutoffs.at(NOW)
    assert cutoffs.refresh_tokens == NOW - timedelta(days=30)
    assert cutoffs.patient_links == NOW - timedelta(days=30)
    assert cutoffs.finished_jobs == NOW - timedelta(days=30)
    assert cutoffs.dead_jobs == NOW - timedelta(days=90)
