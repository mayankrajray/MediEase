# M5 — Messaging and reminders: design notes

| Field | Value |
|---|---|
| Status | In progress — M5 opened 18 Oct 2026 after M4 merged (PR #39); plan and spec approved; M5-P1 approved (1A–5A with four refinements) implemented and confirmed by the developer 18 Oct 2026; M5-P2 design proposed |
| Spec | `docs/specs/reminders-and-messaging.md` (Approved 2026-10-18) |
| ADR | ADR-0005 (PostgreSQL-backed job queue), ADR-0007 (messaging port, WhatsApp first) |
| Covers | FR-MSG-01..05, FR-MSG-07, FR-REM-01, 02, 04, 05, 07, FR-APT-06, NFR-13 |
| Issue / branch / PR | #40 · `m5/40-messaging-and-reminders` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | A reminder scheduled in the app is delivered through the WhatsApp test number, status flows back through the webhook, and opt-out stops further sends |
| Outside dependencies | L-01 (Meta business account, number) and L-02 (approved templates) for P3; L-03 (SMS, DLT) only for P5's SMS fallback |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | The job queue and the worker: `jobs`, short committed claims with `SKIP LOCKED`, retries, `dead`, `cancelled`, the reaper, recurring jobs, the first real job (retention purge), `v_job_health`, the `worker` container | Below (done; confirmed) |
| P2 | `MessagingPort`, the console adapter, `templates.yaml`; `messages` (encrypted phone, IDs only, unique idempotency key); a send job; booking confirmations and the M4 prescription links still `PENDING` (issued in the last 24 hours, R15 of the M4 spec) through it; `v_message_health` | Below (done; confirmed) |
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

### Result (18 Oct 2026)

Built as designed, with these additions and differences:

- **`release` on the store.** A worker told to stop gives back the jobs it claimed but has not
  started (`queued` again, the attempt not counted) instead of leaving them for the reaper. The job
  in hand finishes first.
- **`retention.purged` audit action.** The only new `AuditAction`; written as `SYSTEM` with the
  three counts, no user, no clinic.
- **Logs are console-formatted locally**, JSON elsewhere (the existing logging setup), so the
  event names below appear as `job.claimed`, `job.retry_scheduled`, `job.dead`, `job.lock_expired`,
  `job.lost_lock`, `worker.started`, `worker.poll_failed` and `worker.stopped`.
- **Two bugs found while testing**, both in `docs/DEBUG_JOURNAL.md`: `rowcount` is not reliable for an
  ORM `INSERT … ON CONFLICT` (enqueue now uses `RETURNING`), and a frozen dataclass cannot be raised
  as an exception (`JobFailure` is a plain exception class).

Verification on the rebuilt stack (`make up`, `make seed`, `make smoke`; migration `0014`):

| Step | How | Result |
|---|---|---|
| 1 | `make up`, `make smoke` | `worker` healthy, uid 999 (not root), read-only root, no capabilities |
| 2 | The scheduler's daily key; a refresh token expired 31 days ago planted; a purge queued by SQL | Today's `purge_expired_auth_and_links:20261018T000000Z` succeeded on its own; the planted token was deleted; one `retention.purged` row, `SYSTEM`, no user, no clinic, `{"jobs": "0", "patient_links": "0", "refresh_tokens": "1"}` |
| 3 | An unknown kind for the sample clinic, made due again after each attempt | `JOB_HANDLER_MISSING` each time; back-offs 61 s, 301 s, 985 s, 3701 s (1, 5, 15, 60 minutes plus jitter); `dead` on the fifth attempt, never claimed again; `v_job_health` shows `dead = 1, dead_24h = 1` |
| 4 | **Failure path.** A purge job left `running` by a "ghost" worker with a 10-minute-old lock | Reaped to `queued` with `JOB_LOCK_EXPIRED`, run again and succeeded with `attempts = 2` |
| 5 | **Failure path.** `docker compose stop db` | Unhealthy after 122 s (the 90 s heartbeat limit plus the health check's interval), the container kept running and logged `worker.poll_failed` with a growing back-off; healthy 31 s after `start db` |

Gates: `make lint typecheck contract-check test` — API 1382 tests at 98.4% coverage (the 80% gate
for `domain/` + `application/` holds), web 426. The P3 suggestions performance test failed once on
the full run (p95 over its 150 ms bound while the machine was loaded) and passed alone, as noted in
the M4 PR; it is left unchanged.

Not verified here: a worker on more than one host (the two-worker claim is tested with threads on
one PostgreSQL), and behaviour with real provider calls (P2 and P3).

---

## M5-P2 — `MessagingPort`, the console adapter, templates and the send jobs

Approved 18 Oct 2026 with 1A–6A and leave to apply improvements found while building:

| # | Decision |
|---|---|
| 1A | The phone on `messages` is Fernet ciphertext (`to_phone_encrypted`; `MESSAGING_PHONE_KEYS`, first key encrypts, all decrypt) |
| 2A | Templates in `adapters/messaging/templates.yaml`, PyYAML `safe_load`, checked at worker start |
| 3A | Pending prescription links are sent by a job enqueued at issue, in the issue's transaction (no cross-clinic sweeper) |
| 4A | At most once: a row found still marked as started at a retry, a timeout or any unexpected provider error is `FAILED` with `MSG_OUTCOME_UNKNOWN`, never resent |
| 5A | The signed link is stored as `[link]`; the URL exists only in memory |
| 6A | Confirmations for front-desk booking and reschedule; not walk-ins |

### Result (18 Oct 2026)

Built as designed (`domain/messaging/`, `ports/messaging.py`, `adapters/messaging/`,
`adapters/security/phone_cipher.py`, `adapters/db/messages.py`, migration `0015`,
`application/messaging/`), with these improvements over the proposal:

- **Timeouts are unknown outcomes**, not retryable: only a provider's explicit refusal
  (`MSG_PROVIDER_RATE_LIMIT`, `MSG_PROVIDER_UNAVAILABLE`) is retried, since a timed-out request
  may have been delivered.
- **The last attempt fails the message.** A retryable refusal on the final attempt marks the row
  `FAILED` with that code, so no row is left `QUEUED` behind a dead job.
- **Consent lost means `EXPIRED`, as prescriptions R15 says** (the database trigger allows only
  `PENDING → SUPERSEDED | SENT | EXPIRED`); the audit metadata gives the reason (`too_old`,
  `no_consent`, `no_link`). The window is the setting `RX_LINK_SEND_WINDOW_HOURS` (1–24).
- **No job for a patient who cannot be messaged** at booking time; consent is still read again at
  send time. A confirmation is also skipped once the session is over.
- **`source_type` / `source_id` on `messages`**, so P6 can show the status on the appointment or
  prescription without another table.
- **Console refused by the worker, not by settings**, in production: a settings rule would have
  made every production configuration invalid until P3, including the API's, which never sends.
- **Encryption in the application layer** (a `PhoneCipherPort` used by the sender), so the unit of
  work needs no key.
- **Bug found on the stack** (DEBUG_JOURNAL): the console adapter numbered its IDs per process, so a
  restarted worker reused `console-00000001` and the outcome write hit
  `uq_messages_provider_message_id` after the "send" — which, correctly, ended that message as
  `MSG_OUTCOME_UNKNOWN`. IDs are now random UUIDs; a unit test covers two adapters.

Verification on the rebuilt stack (`make up`, `make seed`, `make smoke`; migration `0015`; a script
signing in as the seeded owner, desk and doctor on an extra session today):

| Step | Result |
|---|---|
| 1. Booking for a consenting patient | One job, `succeeded` at attempt 1; one `messages` row `CONSOLE / console / booking_confirmed v1 / SENT`, variables `clinic_name`, `doctor_name`, `date_time_or_token = "Sun 18 Oct 2026, 8:50 PM, token 4"` |
| 2. Booking for an opted-out patient | No job, no message |
| 3. **Failure path.** Worker stopped, booking made, patient opted out, worker started | The job succeeded and sent nothing (`message.skipped`), no row |
| 4. Prescription issued for a consenting patient (sentinel text in items and advice) | `rx_ready` row `SENT`, variables `{"clinic_name": …, "link": "[link]"}`; `prescriptions.link_delivery = SENT` |
| 5. `psql` | `to_phone_encrypted` is a 100-character Fernet token without the number |
| 6. `v_message_health` | Counts by channel, template and status, including the row from the bug above (`FAILED`, `outcome_unknown = 1`) |
| 7. Worker logs | `message.sent`, `message.skipped`, `messaging.console_accepted`; no patient name, phone number, sentinel text or `/p/` link |

AC4 (a crash after the provider accepted) is proved by
`tests/integration/test_messaging_db.py::test_ac4_…` (the provider accepts, then the "worker"
dies with a `BaseException`; the retry makes no second call and fails the row as unknown), not on
the stack: the window between the call and the commit is too small to hit by killing a container.

Gates: `make lint typecheck contract-check` clean; API 1445 tests at 98.47% (core gate holds);
web 426 — in the combined `make test` run two web tests (`PrintAndLink`, `Workspace`) timed out
under load and passed alone three times and in a full `make test-web`; P2 changes no web code.
No HTTP contract change.

Not verified: a real provider (P3); the Hindi wording (L-02).
