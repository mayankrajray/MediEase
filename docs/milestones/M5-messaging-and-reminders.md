# M5 — Messaging and reminders: design notes

| Field | Value |
|---|---|
| Status | In progress — M5 opened 18 Oct 2026 after M4 merged (PR #39); plan and spec approved; M5-P1 approved (1A–5A with four refinements), in implementation |
| Spec | `docs/specs/reminders-and-messaging.md` (Approved 2026-10-18) |
| ADR | ADR-0005 (PostgreSQL-backed job queue), ADR-0007 (messaging port, WhatsApp first) |
| Covers | FR-MSG-01..05, FR-MSG-07, FR-REM-01, 02, 04, 05, 07, FR-APT-06, NFR-13 |
| Issue / branch / PR | #40 · `m5/40-messaging-and-reminders` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | A reminder scheduled in the app is delivered through the WhatsApp test number, status flows back through the webhook, and opt-out stops further sends |
| Outside dependencies | L-01 (Meta business account, number) and L-02 (approved templates) for P3; L-03 (SMS, DLT) only for P5's SMS fallback |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | The job queue and the worker: `jobs`, short committed claims with `SKIP LOCKED`, retries, `dead`, `cancelled`, the reaper, recurring jobs, the first real job (retention purge), `v_job_health`, the `worker` container | Below (approved) |
| P2 | `MessagingPort`, the console adapter, `templates.yaml`; `messages` (encrypted phone, IDs only, unique idempotency key); a send job; booking confirmations and the M4 prescription links still `PENDING` (issued in the last 24 hours, R15 of the M4 spec) through it; `v_message_health` | At its start |
| P3 | WhatsApp Cloud adapter (errors mapped to `MSG_*`, 10 s timeout); `GET`/`POST /webhooks/whatsapp` (raw-body signature, store once, answer within 1 s); statuses only move forward; reconciliation of messages stuck in `SENT` | At its start; needs L-01, L-02 |
| P4 | Reminder rules: follow-up reminders from issued prescriptions (09:00 the day before), revisions move or cancel them, manual reminders, quiet hours 21:00–08:00, consent re-read at send time; pending follow-ups API; the automatic no-show job | At its start |
| P5 | STOP, UNSUBSCRIBE, रोकें, बंद opt the patient out and confirm; SMS adapter behind a flag (off); cost per message and the ops console's monthly total per clinic | At its start |
| P6 | Web: reminder and message status on the patient profile and the consultation; pending follow-ups with *Book follow-up*; failed messages explained with a "call the patient" hint; Playwright | At its start |

---

## M5-P1 — The job queue and the worker

**Status: approved by the developer 18 Oct 2026 with 1A–5A and four refinements (short claim
transaction with crash-safe attempts; a partial unique index on `dedupe_key`; the heartbeat in a
tmpfs, written only after a successful poll; the tenancy guard accounting for system jobs).**
Covers NFR-13; spec R9–R11, R9a–R9e, R11a; AC3, AC8–AC11; ADR-0005. API and runtime only; no HTTP
contract change.

### Data (migration `0014`, expand-only)

`jobs` — not a tenant table in the repository sense: a reviewed exception like `audit_events`
(below).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | UUIDv7 from `IdPort` |
| `clinic_id` | uuid null FK `clinics` | Null only for system kinds (CHECK, R9d) |
| `kind` | text | `^[a-z][a-z0-9_]{2,63}$` |
| `payload` | jsonb | IDs and enums only (R11) |
| `state` | text | `queued`, `running`, `succeeded`, `dead`, `cancelled` |
| `run_at` | timestamptz | When it may next run |
| `attempts`, `max_attempts` | smallint | `0 <= attempts <= max_attempts`, `max_attempts` 1–20, default 5 |
| `last_error_code` | text null | `JOB_*`, later `MSG_*` |
| `locked_by`, `locked_at` | text, timestamptz null | Both set exactly when `running` |
| `request_id` | text null | R11 |
| `dedupe_key` | text null | Partial unique (R9c) |
| `created_at`, `updated_at`, `finished_at` | timestamptz | `finished_at` set on succeeded, dead, cancelled |

Constraints and indexes:
- `ck_jobs_state`, `ck_jobs_kind_format`, `ck_jobs_attempts_range`, `ck_jobs_lock_when_running`
  (`(state = 'running') = (locked_by IS NOT NULL AND locked_at IS NOT NULL)`).
- `ck_jobs_system_kind`: `(clinic_id IS NULL) = (kind IN ('purge_expired_auth_and_links'))`.
- `ix_jobs_claim` on `(run_at)` `WHERE state = 'queued'`; `ix_jobs_running` on `(locked_at)`
  `WHERE state = 'running'` (the reaper); `ix_jobs_clinic_id`.
- `uq_jobs_dedupe_key` unique on `(dedupe_key)` `WHERE state IN ('queued', 'running', 'succeeded')`.

`v_job_health` (no clinic or patient data): per kind, jobs due, scheduled, running, stale
(running with a lock older than 5 minutes), dead, dead in the last 24 hours, and the age of the
oldest due job.

### Domain (`domain/jobs/`)

- `JobState`, `SYSTEM_KINDS` (frozen set; the CHECK's list), `JobKind` format check.
- `RetryPolicy`: delays 1, 5, 15, 60 minutes after attempts 1–4 (60 after that), jitter up to 10%
  from an injected random value; `decide(attempts, max_attempts, failure)` → retry at a time, or
  dead with a code.
- `JobFailure(code, retryable)`; codes `JOB_HANDLER_MISSING`, `JOB_HANDLER_ERROR`,
  `JOB_LOCK_EXPIRED`, `JOB_MAX_ATTEMPTS`, `JOB_CLINIC_SUSPENDED`.
- `Recurring(kind, period)` and `period_start(now, period)`: the dedupe key of a period.
- `RetentionPolicy`: refresh tokens and patient links 30 days after expiry; finished jobs
  (`succeeded`, `cancelled`) 30 days after `finished_at`; `dead` jobs 90 days (kept longer to
  investigate).

### Ports and application

- `ports/jobs.py`:
  - `JobQueue` on the unit of work (`uow.jobs.enqueue(NewJob)`): the transactional outbox. A job is
    saved with the change that caused it, or not at all; a live duplicate `dedupe_key` does
    nothing (`INSERT … ON CONFLICT DO NOTHING` against the partial index).
  - `JobStore` for the worker (outside any unit of work, each call its own short transaction):
    `claim(worker, now, limit)`, `heartbeat(job, worker, now)`, `succeed`, `retry`, `kill`,
    `cancel` (each only while `running` under that worker; otherwise `job.lost_lock`), and
    `reap(now, stale_after)`.
- `uow.retention.purge(cutoffs)`: deletes expired refresh tokens (never one an unexpired token
  still points to), expired patient links across clinics, and old finished jobs, returning the
  counts. A reviewed cross-clinic exception, like the audit writer: it deletes by expiry only and
  never reads a row's content.
- `application/jobs/`:
  - `JobHandlers`: the registry from kind to handler. A handler gets the payload and a context:
    the job's clinic scope for a clinic job, no tenant scope for a system job.
  - `RunJob`: suspended clinic → `cancel`; unknown kind → retryable `JOB_HANDLER_MISSING`; a
    handler's `JobFailure` as it says; any other exception → retryable `JOB_HANDLER_ERROR` (logged
    with the exception type only); then `RetryPolicy.decide`.
  - `ScheduleRecurring`: enqueues each recurring job for the current period (R9e).
  - `PurgeExpired` (the `purge_expired_auth_and_links` handler, daily): runs the purge and records
    one `retention.purged` audit event as `SYSTEM` with the counts only.

### Worker (`delivery/worker/`)

- `python -m mediease_api.delivery.worker`; `bootstrap.build_worker(settings)` composes it.
- One loop per process: every iteration runs the scheduler step (at most once a minute), the
  reaper (at most once a minute), then claims up to `WORKER_BATCH_SIZE` (10) jobs and runs them one
  after another; idle, it sleeps `WORKER_POLL_SECONDS` (2).
- While a handler runs, a background thread renews `locked_at` every 60 seconds (R9).
- After an iteration whose database calls all succeeded, it rewrites the heartbeat file
  (`/tmp/mediease-worker-heartbeat`); a failed iteration logs `worker.poll_failed`, backs off and
  does not touch it (R11a).
- `python -m mediease_api.delivery.worker.health` exits 0 only when the file is under 90 seconds
  old (the container's health check).
- SIGTERM or SIGINT: finish the current job, then exit 0 (`worker.stopped`).
- Logs: `job.claimed`, `job.succeeded`, `job.retry_scheduled`, `job.dead`, `job.cancelled`,
  `job.lock_expired`, `job.lost_lock`, bound to `job_id`, `job_kind`, `request_id`, `worker_id`.

### Runtime

- Compose `worker`: the API image, `command: ["python", "-m", "mediease_api.delivery.worker"]`,
  hardened (read-only, `cap_drop: ALL`, no new privileges), `tmpfs: /tmp` (small: `size=1m`),
  after `migrate` succeeded and `db` is healthy, the health check above, `stop_grace_period: 30s`.
  `make up` waits for it to be healthy.
- `make worker` runs a worker in the foreground (a second one is safe: `SKIP LOCKED`).
- `make smoke` adds the worker to the running-and-healthy, non-root, read-only and
  no-capabilities checks.
- Settings `WORKER_POLL_SECONDS` (1–60, default 2) and `WORKER_BATCH_SIZE` (1–100, default 10).

### Tenancy guard (refinement 4)

`jobs` joins `NOT_TENANT_SCOPED` with a reviewed-exception comment, and the suite gains:
- the database refuses a clinic-less job of a non-system kind and a clinic job of a system kind;
- the kinds in `ck_jobs_system_kind` (read from the database) equal `SYSTEM_KINDS` in code, so
  adding one in one place only fails the build;
- a clinic job's handler is given only its own clinic's scope, and a job of clinic B is never
  run with clinic A's.

### Tests

- Unit: retry delays and jitter bounds, `decide` at every attempt, period keys, the kind format,
  `RunJob` outcomes with fakes, the worker loop with a fake store and clock (heartbeat only after
  a good iteration, SIGTERM finishes the current job).
- PostgreSQL:
  - AC3: two workers on threads, 100 due jobs, each handler runs exactly once.
  - R9a: during a handler the claimed row is `running`, already counted, and **not locked**
    (`SELECT … FOR UPDATE NOWAIT` from another connection succeeds).
  - AC8: a claim with no outcome is reaped after 5 minutes with the attempt counted; at
    `max_attempts` it is `dead`.
  - Retry and dead transitions; an outcome after the lock was lost changes nothing.
  - AC9: the partial unique index (queued, running, succeeded block; cancelled, dead do not); an
    enqueue rolled back with its unit of work leaves no job.
  - AC10: the system-kind CHECK both ways.
  - Retention boundaries: 30 days to the second; a revoked but unexpired token or link is kept; a
    token chain is deleted without breaking `replaced_by_id`; one audit event with counts only.
  - Migration `0014` up and down; models match migrations.
- Stack: the worker is healthy, non-root, read-only, with no capabilities; AC11 by stopping `db`.

### Verify (on the rebuilt stack)

1. `make up`: `worker` healthy; `make smoke` passes with the worker in its checks.
2. Within a minute the scheduler enqueues today's `purge_expired_auth_and_links`; it succeeds, an
   expired synthetic token from 31 days ago is gone, and `retention.purged` is in `audit_events`.
3. A job of an unknown kind (inserted with `psql`) retries with `JOB_HANDLER_MISSING`; moving its
   `run_at` forward each time, it is `dead` after five attempts and shows in `v_job_health`.
4. **Failure path:** a row left `running` by a "crashed" worker (`locked_at` 10 minutes ago) is
   reaped and run, with the earlier attempt counted.
5. `docker compose stop db`: within 90 seconds the worker is unhealthy; `start db`: healthy again.

### Decisions (approved 18 Oct 2026)

| # | Question | Chosen |
|---|---|---|
| 1 | Jobs that belong to no clinic | **A** `clinic_id` null only for an explicit list of system kinds, enforced by a CHECK |
| 2 | Recurring jobs | **A** a scheduler step in the worker, once per period through `dedupe_key` |
| 3 | Jobs of a suspended clinic | **A** a `cancelled` state |
| 4 | First real job | **A** the retention purge of expired tokens and links |
| 5 | Worker health | **A** a heartbeat file the container checks |

Refinements, from the developer: (a) the claim increments `attempts` and commits before the
handler, so no lock is held across I/O and a crash still counts toward `max_attempts`; (b)
`dedupe_key` unique only among `queued`, `running` and `succeeded`, so cancelled work never blocks
the same key later; (c) the heartbeat file in a tmpfs `/tmp`, rewritten only after a successful
poll; (d) the tenancy guard accounts for clinic-less system jobs.
