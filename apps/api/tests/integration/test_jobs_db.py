"""The job queue on real PostgreSQL (M5-P1; spec R9-R11, R9a-R9e; AC3, AC8-AC10; ADR-0005)."""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.db.jobs import SqlAlchemyJobStore
from mediease_api.application.jobs.purge import PurgeExpired
from mediease_api.application.jobs.run import RunJob
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.jobs.job import PURGE_KIND, SYSTEM_KINDS, ClaimedJob, NewJob
from mediease_api.domain.jobs.retry import (
    JOB_CLINIC_SUSPENDED,
    JOB_LOCK_EXPIRED,
    STALE_AFTER,
    JobFailure,
)
from tests.builders import NOW, a_clinic, a_user, new_id
from tests.conftest import UowFactory
from tests.fakes import FakeClock, FakeIds
from tests.integration.db.test_patient_links import _chain, _link

NEVER = lambda: 0.0  # noqa: E731 - no jitter, so times are exact
REAP = (STALE_AFTER, JobFailure(JOB_LOCK_EXPIRED), NEVER)


@pytest.fixture
def store(session_factory: sessionmaker[Session]) -> SqlAlchemyJobStore:
    return SqlAlchemyJobStore(session_factory)


def a_stored_clinic(uow_factory: UowFactory) -> UUID:
    clinic = a_clinic()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.commit()
    return clinic.id


def enqueue(uow_factory: UowFactory, clinic_id: UUID | None, **fields: Any) -> NewJob:
    kind = fields.pop("kind", PURGE_KIND if clinic_id is None else "send_message")
    job = NewJob.create(id=new_id(), kind=kind, now=NOW, clinic_id=clinic_id, **fields)
    with uow_factory() as uow:
        assert uow.jobs.enqueue(job)
        uow.commit()
    return job


def row(session_factory: sessionmaker[Session], job_id: UUID) -> Any:
    with session_factory() as session:
        return session.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}).one()


def count(session_factory: sessionmaker[Session], sql: str = "SELECT count(*) FROM jobs") -> int:
    with session_factory() as session:
        return int(session.execute(text(sql)).scalar_one())


# --- Enqueueing: the outbox and the dedupe key (R9c, AC9) -------------------------------------


def test_r9c_a_job_exists_only_if_the_change_that_enqueued_it_committed(
    uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    kept = NewJob.create(id=new_id(), kind="send_message", now=NOW, clinic_id=clinic_id)
    lost = NewJob.create(id=new_id(), kind="send_message", now=NOW, clinic_id=clinic_id)

    with uow_factory() as uow:
        assert uow.jobs.enqueue(kept)
        uow.commit()
    with uow_factory() as uow:
        assert uow.jobs.enqueue(lost)
        # leaving without commit() rolls the job back with the rest of the change

    assert count(session_factory) == 1
    assert row(session_factory, kept.id).state == "queued"


def test_ac9_a_live_job_blocks_its_key_and_a_cancelled_or_dead_one_does_not(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)

    def again(key: str) -> bool:
        job = NewJob.create(
            id=new_id(), kind="send_message", now=NOW, clinic_id=clinic_id, dedupe_key=key
        )
        with uow_factory() as uow:
            added = uow.jobs.enqueue(job)
            uow.commit()
        return added

    # queued blocks
    first = enqueue(uow_factory, clinic_id, dedupe_key="k-queued")
    assert not again("k-queued")

    # running blocks
    [claimed] = store.claim("w1", NOW, 1)
    assert claimed.id == first.id
    assert not again("k-queued")

    # succeeded blocks (a finished reminder is not sent twice)
    assert store.succeed(claimed, NOW)
    assert not again("k-queued")

    # cancelled does not block
    second = enqueue(uow_factory, clinic_id, dedupe_key="k-cancel")
    [c] = store.claim("w1", NOW, 1)
    assert c.id == second.id and store.cancel(c, NOW, JOB_CLINIC_SUSPENDED)
    assert again("k-cancel")

    # dead does not block
    # older than the job re-enqueued under "k-cancel" above, so it is claimed first
    third = enqueue(uow_factory, clinic_id, dedupe_key="k-dead", run_at=NOW - timedelta(hours=1))
    [d] = store.claim("w1", NOW, 1)
    assert d.id == third.id and store.kill(d, NOW, "MSG_RECIPIENT_INVALID")
    assert again("k-dead")

    assert count(session_factory, "SELECT count(*) FROM jobs WHERE dedupe_key = 'k-cancel'") == 2


# --- Claiming: short, committed, counted (R9, R9a) --------------------------------------------


def test_r9a_a_claim_counts_the_attempt_and_is_committed_before_any_handler_runs(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    job = enqueue(uow_factory, clinic_id)

    [claimed] = store.claim("worker-a", NOW, 10)

    assert claimed.id == job.id and claimed.attempts == 1 and claimed.locked_by == "worker-a"
    stored = row(session_factory, job.id)  # read through another connection: it is committed
    assert (stored.state, stored.attempts, stored.locked_by) == ("running", 1, "worker-a")
    assert stored.locked_at == NOW


def test_r9a_no_row_lock_is_held_while_a_handler_would_run(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    job = enqueue(uow_factory, clinic_id)
    store.claim("worker-a", NOW, 10)

    # While a slow handler runs, anything else must be able to lock the row at once.
    with session_factory() as other:
        got = other.execute(
            text("SELECT id FROM jobs WHERE id = :id FOR UPDATE NOWAIT"), {"id": job.id}
        ).scalar_one()
        other.rollback()
    assert got == job.id


def test_r9_only_due_jobs_are_claimed_oldest_first_up_to_the_limit(
    uow_factory: UowFactory, store: SqlAlchemyJobStore
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    late = enqueue(uow_factory, clinic_id, run_at=NOW + timedelta(minutes=5))
    old = enqueue(uow_factory, clinic_id, run_at=NOW - timedelta(minutes=30))
    newer = enqueue(uow_factory, clinic_id, run_at=NOW - timedelta(minutes=10))
    newest = enqueue(uow_factory, clinic_id, run_at=NOW - timedelta(minutes=1))

    first = store.claim("w", NOW, 2)
    assert [j.id for j in first] == [old.id, newer.id]
    assert [j.id for j in store.claim("w", NOW, 10)] == [newest.id]  # `late` is not due yet
    assert [j.id for j in store.claim("w", NOW + timedelta(minutes=5), 10)] == [late.id]


def test_r9d_a_claimed_job_carries_its_own_clinic_and_a_system_job_none(
    uow_factory: UowFactory, store: SqlAlchemyJobStore
) -> None:
    a, b = a_stored_clinic(uow_factory), a_stored_clinic(uow_factory)
    job_a = enqueue(uow_factory, a, payload={"reminder_id": "r-a"})
    job_b = enqueue(uow_factory, b, payload={"reminder_id": "r-b"})
    system = enqueue(uow_factory, None)

    claimed = {j.id: j for j in store.claim("w", NOW, 10)}

    assert claimed[job_a.id].clinic_id == a and claimed[job_a.id].payload == {"reminder_id": "r-a"}
    assert claimed[job_b.id].clinic_id == b
    assert claimed[system.id].clinic_id is None


def test_ac3_two_workers_and_a_hundred_due_jobs_run_each_job_exactly_once(
    uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    with uow_factory() as uow:
        for _ in range(100):
            assert uow.jobs.enqueue(
                NewJob.create(id=new_id(), kind="send_message", now=NOW, clinic_id=clinic_id)
            )
        uow.commit()

    start = threading.Barrier(2)
    taken: dict[str, list[UUID]] = {"w1": [], "w2": []}
    errors: list[BaseException] = []

    def work(name: str) -> None:
        mine = SqlAlchemyJobStore(session_factory)
        try:
            start.wait(timeout=10)
            while True:
                batch = mine.claim(name, NOW, 7)
                if not batch:
                    return
                for job in batch:
                    taken[name].append(job.id)  # the "handler"
                    assert mine.succeed(job, NOW)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=work, args=(n,)) for n in taken]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == []
    everything = taken["w1"] + taken["w2"]
    assert len(everything) == 100 and len(set(everything)) == 100  # none twice, none missed
    assert count(session_factory, "SELECT count(*) FROM jobs WHERE state = 'succeeded'") == 100
    assert count(session_factory, "SELECT max(attempts) FROM jobs") == 1


# --- Outcomes apply only while the worker holds the job (R9b, R10) ----------------------------


def test_r9b_outcomes_move_the_job_and_clear_the_lock(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    later = NOW + timedelta(minutes=5)

    job = enqueue(uow_factory, clinic_id)
    [claimed] = store.claim("w", NOW, 1)
    assert store.heartbeat(claimed, NOW + timedelta(minutes=1))
    assert row(session_factory, job.id).locked_at == NOW + timedelta(minutes=1)
    assert store.retry(claimed, NOW, later, "MSG_PROVIDER_RATE_LIMIT")
    r = row(session_factory, job.id)
    assert (r.state, r.run_at, r.last_error_code, r.locked_by) == (
        "queued",
        later,
        "MSG_PROVIDER_RATE_LIMIT",
        None,
    )
    assert store.claim("w", NOW, 1) == []  # not due until `later`

    [again] = store.claim("w", later, 1)
    assert again.attempts == 2
    assert store.succeed(again, later)
    r = row(session_factory, job.id)
    assert (r.state, r.finished_at, r.locked_at) == ("succeeded", later, None)


def test_r9b_a_released_job_goes_back_without_counting_the_attempt(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    job = enqueue(uow_factory, a_stored_clinic(uow_factory))
    [claimed] = store.claim("w", NOW, 1)

    assert store.release(claimed, NOW)

    r = row(session_factory, job.id)
    assert (r.state, r.attempts, r.locked_by) == ("queued", 0, None)


def test_r10_a_worker_that_lost_its_lock_cannot_change_the_job(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    job = enqueue(uow_factory, a_stored_clinic(uow_factory))
    [slow] = store.claim("slow-worker", NOW, 1)
    store.reap(NOW + timedelta(minutes=10), *REAP)  # the slow worker's lock expired...
    [fast] = store.claim("fast-worker", NOW + timedelta(hours=1), 1)  # ...and another took over
    assert fast.id == job.id and fast.attempts == 2

    # Every outcall from the old holder is refused, and nothing changes.
    now = NOW + timedelta(hours=1)
    assert not store.succeed(slow, now)
    assert not store.retry(slow, now, now, "X")
    assert not store.kill(slow, now, "X")
    assert not store.cancel(slow, now, "X")
    assert not store.heartbeat(slow, now)
    assert not store.release(slow, now)
    r = row(session_factory, job.id)
    assert (r.state, r.locked_by, r.attempts) == ("running", "fast-worker", 2)

    assert store.succeed(fast, now)


# --- The reaper and crash-safe attempts (R9a, R10, AC8) ---------------------------------------


def test_ac8_a_crashed_claim_is_reaped_with_the_attempt_already_counted(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    job = enqueue(uow_factory, a_stored_clinic(uow_factory))
    store.claim("doomed", NOW, 1)  # the worker dies here: no outcome is ever written

    assert store.reap(NOW + timedelta(minutes=4), *REAP).requeued == 0  # lock still fresh
    result = store.reap(NOW + timedelta(minutes=6), *REAP)

    assert (result.requeued, result.dead) == (1, 0)
    r = row(session_factory, job.id)
    assert (r.state, r.attempts, r.last_error_code, r.locked_by) == (
        "queued",
        1,
        JOB_LOCK_EXPIRED,
        None,
    )
    assert r.run_at == NOW + timedelta(minutes=6, seconds=60)  # the first back-off


def test_ac8_a_job_that_keeps_crashing_ends_dead_instead_of_looping(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    job = enqueue(uow_factory, a_stored_clinic(uow_factory), max_attempts=3)

    for attempt in (1, 2, 3):
        at = NOW + timedelta(hours=3 * attempt)
        [claimed] = store.claim("doomed", at, 1)
        assert claimed.attempts == attempt
        store.reap(at + timedelta(minutes=6), *REAP)  # the worker died; the reaper finds it

    r = row(session_factory, job.id)
    assert (r.state, r.attempts, r.last_error_code) == ("dead", 3, JOB_LOCK_EXPIRED)
    assert r.finished_at is not None
    assert store.claim("doomed", NOW + timedelta(days=30), 10) == []  # nothing left to run


def test_r10_a_job_with_a_live_heartbeat_is_not_reaped(
    uow_factory: UowFactory, store: SqlAlchemyJobStore
) -> None:
    enqueue(uow_factory, a_stored_clinic(uow_factory))
    [claimed] = store.claim("w", NOW, 1)
    assert store.heartbeat(claimed, NOW + timedelta(minutes=4))  # a long handler renewing

    assert store.reap(NOW + timedelta(minutes=8), *REAP).requeued == 0
    assert store.reap(NOW + timedelta(minutes=10), *REAP).requeued == 1


# --- The database refuses bad rows (R9d, AC10) ------------------------------------------------

_INSERT = text(
    "INSERT INTO jobs (id, clinic_id, kind, payload, state, run_at, attempts, max_attempts,"
    " locked_by, locked_at, created_at, updated_at)"
    " VALUES (:id, :clinic_id, :kind, '{}', :state, :now, :attempts, :max_attempts,"
    " :locked_by, :locked_at, :now, :now)"
)


def _insert(session_factory: sessionmaker[Session], **overrides: Any) -> None:
    values: dict[str, Any] = {
        "id": new_id(),
        "clinic_id": None,
        "kind": PURGE_KIND,
        "state": "queued",
        "attempts": 0,
        "max_attempts": 5,
        "locked_by": None,
        "locked_at": None,
        "now": NOW,
    }
    values.update(overrides)
    with session_factory() as session:
        session.execute(_INSERT, values)
        session.commit()


def test_ac10_the_database_refuses_a_job_with_no_clinic_unless_it_is_a_system_kind(
    uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    _insert(session_factory)  # a system kind, no clinic: fine
    _insert(session_factory, clinic_id=clinic_id, kind="send_message")  # a clinic kind: fine

    with pytest.raises(IntegrityError, match="ck_jobs_system_kind"):
        _insert(session_factory, kind="send_message")  # no clinic, not a system kind
    with pytest.raises(IntegrityError, match="ck_jobs_system_kind"):
        _insert(session_factory, clinic_id=clinic_id)  # a system kind with a clinic


def test_ac10_the_system_kinds_in_the_database_are_the_ones_in_the_code(
    uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        definition = session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = 'ck_jobs_system_kind'"
            )
        ).scalar_one()
    in_database = set(re.findall(r"'([a-z0-9_]+)'::text", definition))
    assert in_database == set(SYSTEM_KINDS)  # a kind added in one place only fails here


def test_the_database_keeps_the_lock_columns_and_attempt_counts_consistent(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(IntegrityError, match="ck_jobs_lock_when_running"):
        _insert(session_factory, state="running")  # running with no holder
    with pytest.raises(IntegrityError, match="ck_jobs_lock_when_running"):
        _insert(session_factory, locked_by="w", locked_at=NOW)  # a holder on a queued job
    with pytest.raises(IntegrityError, match="ck_jobs_attempts_range"):
        _insert(session_factory, attempts=6)
    with pytest.raises(IntegrityError, match="ck_jobs_attempts_range"):
        _insert(session_factory, max_attempts=21)
    with pytest.raises(IntegrityError, match="ck_jobs_state"):
        _insert(session_factory, state="failed")  # the spec has no `failed` state
    with pytest.raises(IntegrityError, match="ck_jobs_kind_format"):
        _insert(session_factory, kind="Purge-It")


# --- The first real job: retention (R9e; DATA_MODEL "Retention and erasure") ------------------


def _token(user_id: UUID, expires: datetime, *, replaced_by: UUID | None = None) -> RefreshToken:
    return RefreshToken(
        id=new_id(),
        user_id=user_id,
        family_id=new_id(),
        token_hash=f"hash-{new_id()}",
        expires_at=expires,
        created_at=expires - timedelta(days=14),
        updated_at=expires - timedelta(days=14),
        replaced_by_id=replaced_by,
    )


def _alive(session_factory: sessionmaker[Session], table: str) -> set[UUID]:
    with session_factory() as session:
        return set(session.execute(text(f"SELECT id FROM {table}")).scalars())


def test_retention_deletes_tokens_30_days_after_expiry_and_not_a_second_before(
    uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    user = a_user()
    day = timedelta(days=1)
    old = _token(user.id, NOW - 30 * day - timedelta(seconds=1))
    edge = _token(user.id, NOW - 30 * day)  # exactly 30 days: kept (strictly older goes)
    recent = _token(user.id, NOW - 29 * day)
    live = _token(user.id, NOW + 5 * day)
    with uow_factory() as uow:
        uow.users.add(user)
        for token in (old, edge, recent, live):
            uow.refresh_tokens.add(token)
        uow.commit()

    purge = PurgeExpired(uow=uow_factory(), clock=FakeClock(NOW), ids=FakeIds())
    counts = purge.execute()

    assert counts.refresh_tokens == 1
    assert _alive(session_factory, "refresh_tokens") == {edge.id, recent.id, live.id}


def test_retention_deletes_a_rotated_chain_together_and_keeps_a_token_a_live_one_points_to(
    uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    user = a_user()
    long_ago = NOW - timedelta(days=60)
    # Both expired long ago and A -> B: they can go in one statement despite the foreign key.
    b_old = _token(user.id, long_ago)
    a_old = _token(user.id, long_ago - timedelta(days=1), replaced_by=b_old.id)
    # A recent token whose successor is old: the old successor must stay, or the key breaks.
    b_kept = _token(user.id, long_ago)
    a_recent = _token(user.id, NOW - timedelta(days=2), replaced_by=b_kept.id)
    with uow_factory() as uow:
        uow.users.add(user)
        for token in (b_old, a_old, b_kept, a_recent):
            uow.refresh_tokens.add(token)
        uow.commit()

    PurgeExpired(uow=uow_factory(), clock=FakeClock(NOW), ids=FakeIds()).execute()

    assert _alive(session_factory, "refresh_tokens") == {b_kept.id, a_recent.id}


def test_retention_deletes_expired_links_but_keeps_revoked_links_that_have_not_expired(
    uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    rx, user = _chain(uow_factory)
    uid: UUID = user.id  # type: ignore[attr-defined]

    def link(created: datetime, *, ttl_days: int, revoke: bool) -> Any:
        made = _link(rx, uid)
        made.created_at = made.updated_at = created
        made.expires_at = created + timedelta(days=ttl_days)
        if revoke:
            made.revoke(created)
        return made

    expired_31 = link(NOW - timedelta(days=35), ttl_days=4, revoke=True)  # expired 31 days ago
    expired_29 = link(NOW - timedelta(days=33), ttl_days=4, revoke=True)  # expired 29 days ago
    unexpired_revoked = link(NOW - timedelta(days=10), ttl_days=90, revoke=True)
    active = link(NOW - timedelta(days=1), ttl_days=90, revoke=False)
    with uow_factory() as uow:
        for made in (expired_31, expired_29, unexpired_revoked, active):
            uow.tenant(rx.clinic_id).patient_links.add(made)
        uow.commit()

    counts = PurgeExpired(uow=uow_factory(), clock=FakeClock(NOW), ids=FakeIds()).execute()

    assert counts.patient_links == 1
    assert _alive(session_factory, "patient_links") == {
        expired_29.id,
        unexpired_revoked.id,
        active.id,
    }


def test_retention_keeps_finished_jobs_30_days_and_dead_ones_90_and_never_live_ones(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    day = timedelta(days=1)

    def finished(how: str, ended: datetime) -> UUID:
        job = enqueue(uow_factory, clinic_id, run_at=ended - timedelta(hours=1))
        [claimed] = store.claim("w", ended, 1)
        assert claimed.id == job.id
        {
            "succeeded": lambda: store.succeed(claimed, ended),
            "cancelled": lambda: store.cancel(claimed, ended, JOB_CLINIC_SUSPENDED),
            "dead": lambda: store.kill(claimed, ended, "MSG_RECIPIENT_INVALID"),
        }[how]()
        return job.id

    old_ok = finished("succeeded", NOW - 31 * day)
    old_cancelled = finished("cancelled", NOW - 31 * day)
    recent_ok = finished("succeeded", NOW - 29 * day)
    dead_60 = finished("dead", NOW - 60 * day)  # dead jobs are kept for investigation
    dead_91 = finished("dead", NOW - 91 * day)
    queued = enqueue(uow_factory, clinic_id, run_at=NOW + day).id

    counts = PurgeExpired(uow=uow_factory(), clock=FakeClock(NOW), ids=FakeIds()).execute()

    assert counts.jobs == 3
    kept = _alive(session_factory, "jobs")
    assert {old_ok, old_cancelled, dead_91}.isdisjoint(kept)
    assert {recent_ok, dead_60, queued} <= kept


def test_retention_writes_one_system_audit_event_with_counts_only(
    uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    user = a_user()
    with uow_factory() as uow:
        uow.users.add(user)
        uow.refresh_tokens.add(_token(user.id, NOW - timedelta(days=45)))
        uow.commit()

    PurgeExpired(uow=uow_factory(), clock=FakeClock(NOW), ids=FakeIds()).execute()

    with session_factory() as session:
        [event] = session.execute(
            text("SELECT * FROM audit_events WHERE action = 'retention.purged'")
        ).all()
    assert event.actor_type == "SYSTEM" and event.actor_user_id is None
    assert event.clinic_id is None
    assert event._mapping["metadata"] == {
        "refresh_tokens": "1",
        "patient_links": "0",
        "jobs": "0",
        "webhook_events": "0",
        "email_tokens": "0",
        "notifications": "0",
        # M6b-P3b: a count of dose records, never their content.
        "dose_records": "0",
        "patient_notifications": "0",
    }


def test_a_job_of_a_suspended_clinic_is_cancelled_not_run_and_its_key_is_free_again(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    job = enqueue(uow_factory, clinic_id, dedupe_key="reminder:42")
    with session_factory() as session:
        session.execute(text("UPDATE clinics SET status = 'SUSPENDED'"))
        session.commit()
    ran: list[ClaimedJob] = []
    runner = RunJob(
        store=store,
        handlers={"send_message": ran.append},
        uow=uow_factory(),
        clock=FakeClock(NOW),
        rand=NEVER,
    )

    [claimed] = store.claim("w", NOW, 1)
    runner.execute(claimed)

    r = row(session_factory, job.id)
    assert (r.state, r.last_error_code) == ("cancelled", JOB_CLINIC_SUSPENDED)
    assert ran == []
    # R9c: cancelling frees the key for the day the clinic is unsuspended.
    with uow_factory() as uow:
        assert uow.jobs.enqueue(
            NewJob.create(
                id=new_id(),
                kind="send_message",
                now=NOW,
                clinic_id=clinic_id,
                dedupe_key="reminder:42",
            )
        )
        uow.commit()


# --- The health view ---------------------------------------------------------------------------


def test_v_job_health_counts_due_scheduled_running_stale_and_dead_by_kind(
    uow_factory: UowFactory, store: SqlAlchemyJobStore, session_factory: sessionmaker[Session]
) -> None:
    clinic_id = a_stored_clinic(uow_factory)
    now = datetime.now(UTC)
    kind = "send_message"
    enqueue(uow_factory, clinic_id, run_at=now - timedelta(minutes=10))  # due, the oldest
    enqueue(uow_factory, clinic_id, run_at=now - timedelta(minutes=2))  # due
    enqueue(uow_factory, clinic_id, run_at=now + timedelta(hours=1))  # scheduled
    stale = enqueue(uow_factory, clinic_id, run_at=now - timedelta(hours=1))
    [claimed] = store.claim("w", now - timedelta(minutes=30), 1)  # running with an old lock
    assert claimed.id == stale.id
    dying = enqueue(uow_factory, clinic_id, run_at=now - timedelta(hours=2))
    [to_kill] = store.claim("w", now, 1)
    assert to_kill.id == dying.id and store.kill(to_kill, now, "MSG_RECIPIENT_INVALID")

    with session_factory() as session:
        health = session.execute(
            text("SELECT * FROM v_job_health WHERE kind = :kind"), {"kind": kind}
        ).one()

    assert (health.due, health.scheduled, health.running, health.stale) == (2, 1, 1, 1)
    assert (health.dead, health.dead_24h) == (1, 1)
    assert 590 <= health.oldest_due_age_seconds <= 700
    assert set(health._fields).isdisjoint({"payload", "clinic_id", "id"})  # no clinic data in it
