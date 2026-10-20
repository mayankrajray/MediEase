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
| P3 | WhatsApp Cloud adapter (errors mapped to `MSG_*`, 10 s timeout); `GET`/`POST /webhooks/whatsapp` (raw-body signature, store once, answer within 1 s); statuses only move forward; reconciliation of messages stuck in `SENT` | Below (done; confirmed; the live Meta test needs L-01, L-02) |
| P4 | Reminder rules: follow-up reminders from issued prescriptions (09:00 the day before), revisions move or cancel them, manual reminders, quiet hours 21:00–08:00, consent re-read at send time; pending follow-ups API; the automatic no-show job | Below (done; confirmed) |
| P5 | STOP, UNSUBSCRIBE, रोकें, बंद opt the patient out and confirm; SMS adapter behind a flag (off); cost per message and the ops console's monthly total per clinic | Below (done; confirmed; the real SMS provider needs L-03) |
| P6 | Web: reminder and message status on the patient profile and the consultation; pending follow-ups with *Book follow-up*; failed messages explained with a "call the patient" hint; the ops console's monthly messaging-costs table (P5 decision 7A); Playwright | Below (awaiting approval) |

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

---

## M5-P3 — The WhatsApp Cloud API adapter and webhooks

Approved 18 Oct 2026 with 1A–5A:

| # | Decision |
|---|---|
| 1A | Standard-library HTTP (`urllib`), no new dependency |
| 2A | Store and enqueue in the request; process statuses in the worker |
| 3A | Stored bodies are redacted: no message text, profile names or phone numbers |
| 4A | A status matched by our echoed ID corrects a `FAILED` / `MSG_OUTCOME_UNKNOWN` row (and a `QUEUED` one) to what it proves |
| 5A | Signature first in logic; a per-caller rate limit of 600 a minute and a 1 MB body cap |

Findings that shaped it (Meta's documentation): the Cloud API has no endpoint to read a message's
status, so R15 is rewritten (hourly `reconcile_messages`: re-run stuck events, report
unconfirmed); `biz_opaque_callback_data` is echoed in every status, so each send carries our
message ID. Graph API `v26.0` (July 2026) is the default, overridable by `WHATSAPP_API_VERSION`.

### Result (18 Oct 2026)

Built as designed (`adapters/messaging/whatsapp_cloud.py`, `whatsapp_errors.py`,
`whatsapp_webhook.py`, `application/messaging/webhooks.py`, `delivery/webhooks/whatsapp.py`,
migration `0016`), plus:

- **`docker-compose.yml` passes the messaging settings.** P2's `MESSAGING_*` and
  `RX_LINK_SEND_WINDOW_HOURS` had worked locally only through their defaults; the compose
  environment now lists them and the `WHATSAPP_*` values (`WHATSAPP_GRAPH_URL` only for a fake).
- **The webhook refuses everything without its secrets** (empty app secret: 401; empty verify
  token: 403), so a deployment without WhatsApp configured exposes nothing.
- **An unmapped Meta code is permanent** (`MSG_PROVIDER_REJECTED`), and an expired token is
  `MSG_PROVIDER_AUTH`, logged as an error. Meta's error text is never logged (it can echo
  parameters); the code and HTTP status are.
- **Bug found by the tests** (DEBUG_JOURNAL): P2's `ck_messages_sent_has_provider_id` refused a
  message that Meta accepted and later reported failed; `0016` makes it one-way.

Verification on the rebuilt stack, with the real adapter pointed at a fake Graph API container on
the compose network and signed webhooks posted to the real API (secrets and the provider set in the
shell for that run only; `.env` untouched; the default stack restored and smoke-tested after):

| Step | Result |
|---|---|
| 1. Booking for a consenting patient | `messages` row `WHATSAPP / whatsapp_cloud / SENT` with `wamid.FAKE-1`; the fake received `POST /v26.0/1234567890/messages` with a bearer token, template `booking_confirmed_v1`, language `en`, three parameters and our message ID as `biz_opaque_callback_data` |
| 2. `GET` challenge | 200 with the challenge; a wrong token 403 |
| 3. **Failure path.** A body signed with another secret | 401; `webhook_events` count unchanged |
| 4. Signed `delivered`, `read`, then a late `sent` | Message `READ` with both times and `pricing_category = utility`; the late `sent` changed nothing; a redelivered body stored once |
| 5. **Failure path.** Meta answers 131026 for a number | Message `FAILED / MSG_RECIPIENT_INVALID`, job `dead` at once (not retried) |
| 6. `psql` | Stored webhook payloads contain no phone number; `v_message_health` shows the WhatsApp rows and `unconfirmed_24h` |
| 7. API and worker logs | `message.sent`, `messaging.whatsapp_refused`, `webhook.received`, `webhook.signature_invalid`, `webhook.processed`, `message.status_changed`; no patient name, phone number, access token, app secret or Meta error text |

Gates: `make lint typecheck contract-check` clean; API 1493 tests at 98.36% (core gate holds);
web 426. No change to `contracts/openapi.yaml` (webhooks are outside it, API.md says why).

Not verified: Meta itself — a message to the WhatsApp test number and its real webhooks need L-01
(account and number) and L-02 (approved templates); RUNBOOK §9 has the tunnel steps. The Hindi
wording still awaits L-02.

---

## M5-P4 — Reminder rules, pending follow-ups and the automatic no-show

Approved 18 Oct 2026 with 1A–6A:

| # | Decision |
|---|---|
| 1A | One reminder per prescription chain, moved in place; each move bumps `revision`, each job carries its revision, an older job does nothing; no job is edited |
| 2A | Quiet hours: the job defers the reminder to the next 08:00 under a new revision and enqueues a fresh job; the job queue is unchanged |
| 3A | Once sent, a reminder's visible status is its message's |
| 4A | No-show: a 5-minute system sweep returns clinic IDs only and enqueues one per-clinic job |
| 5A | Manual reminders: a doctor and a follow-up date, due by the same rule |
| 6A | No clinic phone: manual reminders refused (`REM_CLINIC_PHONE_MISSING`), automatic ones `FAILED` with that code at send time |

Defaults kept fixed for the pilot: 09:00 the day before, quiet hours 21:00–08:00; no-show bookings
keep their reminders.

### Result (19 Oct 2026)

Built as designed (`domain/reminders/`, `application/reminders/`,
`application/appointments/no_show.py`, `adapters/db/reminders.py`,
`delivery/http/reminders.py`, migration `0017`, contract 0.19.0), plus:

- **The 60-minute boundary is inclusive** in the domain, the per-clinic query and the sweep
  ("at session end + 60 minutes", R10); a test covers one second before and the exact minute.
- **A deferred reminder keeps a refused message row** for its next job (`Skip(close=False)` in the
  sender), so a send refused just before 21:00 is retried at 08:00 rather than lost.
- **One pending row per patient**: the latest overdue follow-up, so a patient with two old chains
  is listed once.
- **Reviewed cross-clinic read**: `SqlAlchemyNoShowSweep` (clinic IDs only), recorded in the
  tenancy suite beside the P3 message lookup.

Verification on the rebuilt stack (`make up`, `make smoke`; migration `0017`):

| Step | Result |
|---|---|
| 1. Issue with follow-up tomorrow (14:52 IST) | One reminder `SCHEDULED`, revision 1, due now (09:00 today had passed), its job queued for the same time |
| 2. Its job run in daytime | `follow_up_due` sent through the console with clinic name, doctor, `Tue 20 Oct 2026` and the clinic phone; reminder `SENT`; `GET /patients/{id}/reminders` shows `SENT` |
| 3. **AC2 on the stack.** A manual reminder's job forced due while the clinic's zone (switched to Pacific/Auckland for the step, then restored) was at 22:22 | Deferred: revision 2, due 08:00 local the next morning, a new job queued for 08:00, the old job succeeded, no message |
| 4. **Failure paths.** Manual reminder without consent; cancel twice | 409 `REM_NO_CONSENT`; scheduled 201 (due 03:30 UTC = 09:00 IST), moved (revision 2), cancelled, then 409 `REM_NOT_SCHEDULED` |
| 5. `GET /follow-ups/pending` | 200 (none on the seeded data) |
| 6. Automatic no-show | The 22 bookings left `BOOKED` by earlier checks, in sessions that ended over an hour before, became `NO_SHOW` on the worker's own sweep: 22 history rows with no user and 22 SYSTEM audit events |
| 7. Worker logs | `message.sent`, `reminder.deferred`, `no_show.sweep`, `no_show.marked`; no patient name or prescription text |

Gates: `make lint typecheck contract-check test` — API 1516 tests at 98.33% (core gate holds),
web 426.

Not verified: per-clinic quiet hours or send times (not built); the Hindi wording (L-02).

---

## M5-P5 — Opt-out by reply, SMS fallback, cost ledger

Designed 20 Oct 2026; approved the same day with 1A–7A. Recommendations are marked (rec).

Facts the design rests on:

- The webhook stores inbound messages as ID, type and time only, and processing ignores them.
  Nothing keeps the sender's number. `patients.phone_e164` is plain and indexed only after
  `clinic_id`.
- `Patient.opt_out` and the `patient.opted_out` audit event exist (M2). `OptOutSource` already has
  `inbound_message`. `may_receive_whatsapp` is false once a patient is opted out, so AC5 (the next
  reminder `SKIPPED_NO_CONSENT`) follows from the P4 send check with no further change.
- `opt_out_confirmed` is already in `templates.yaml` as a service message, which the WhatsApp
  adapter sends as text.
- `messages.cost_paise` and `channel` (`WHATSAPP`, `SMS`, `CONSOLE`) exist but are unused.
  `pricing_category` comes from the status webhook.
- Since 31 Mar 2026, WhatsApp webhooks also carry a business-scoped user ID. Users who adopt a
  username may hide their number, so `from` can be missing.
- Meta charges per delivered message. India's utility rate is ₹0.1150, which is 11.5 paise. Since
  1 Oct 2026, service replies are billed after 1,000 free per number per month.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Where the sender's number lives | The STOP keyword is matched in the request, before redaction. Only a STOP message keeps `stop: true` and the sender's number encrypted with the messages' Fernet keys (plus `context_id` when it replies to us). The worker rewrites the payload without the number once it has processed it. Other inbound text keeps ID, type and time only | B: opt out inside the request (breaks P3 2A's store-then-process, and a database error would lose the STOP). C: a phone HMAC column on patients (a new key, a backfill and upkeep on every phone edit) |
| 2 | Who is opted out | Every patient, in any clinic, whose current number is the sender's and who has at least one message we sent (`sent_at` set). This uses a reviewed cross-clinic lookup that returns clinic and patient IDs only, on a new index `patients(phone_e164)`. Without a number but with `context_id`, the number comes from the message replied to. Otherwise the result is `WH_STOP_UNMATCHED` (logged; nothing changes). Each opt-out is idempotent and records a SYSTEM `patient.opted_out` event with source `inbound_message` | B: every patient with that number, messaged or not (R14 limits it to those we wrote to) |
| 3 | The confirmation | One `opt_out_confirmed` per affected clinic, naming that clinic. It goes out as a per-clinic job `send_opt_out_confirmation` with key `opt_out_confirmed:<clinic_id>:<inbound id>`, at most once per STOP per clinic. It is sent even though the patient is now opted out, and also to a patient opted out already, so a repeated STOP is still answered. It is skipped (`MSG_NOT_APPLICABLE`) if the job runs more than 24 hours after the STOP, when the service window has closed. New source type `OPT_OUT` | B: a single reply with no clinic name (a new template, and the patient may not know which clinic) |
| 4 | SMS fallback | Build the flow and a console SMS adapter now; the real adapter waits for L-03 (provider, DLT template IDs, sender ID). `MESSAGING_SMS_FALLBACK_ENABLED` defaults to false. When it is on, a reminder's WhatsApp message that ends `FAILED` with a definite non-delivery enqueues one `send_sms_fallback` job, keyed `sms:<reminder_id>`. That happens when the send fails directly or when the webhook later reports a failure. The codes are `MSG_RECIPIENT_INVALID`, `MSG_PROVIDER_REJECTED`, and a rate-limit or unavailable error after the last attempt, but never `MSG_OUTCOME_UNKNOWN` or a skip. The job re-reads `may_receive_sms` and the quiet hours (deferring as in P4 2A). It then sends the reminder's SMS body (new `sms` bodies in `templates.yaml`, en and hi, one segment, no link) as a second message row on channel `SMS`. Fallback on with the console SMS provider is refused in production. It applies to reminders only (FR-REM-06) | B: write a real provider adapter now (untestable without L-03). C: defer SMS to M6 (the flow and the flag can be built and tested now) |
| 5 | Cost precision | Replace the unused `cost_paise` with `cost_millipaise` (bigint, so money stays an integer; 11.5 paise = 11 500). Ops totals are rounded to paise at the total. R18 is reworded | B: integer paise per message (each utility message would be counted at 12 paise, 4% high) |
| 6 | Price table and when cost is set | `adapters/messaging/prices.yaml` in the repo: prices by channel and category with `effective_from` dates, excluding GST, loaded like the templates. A WhatsApp message is priced when a status first proves delivery, at the price for its category on that date. The price is 0 if Meta reports `billable: false` (so redaction also keeps `pricing.billable`), and a `FAILED` message is also 0. Console messages are always 0. An SMS is priced at acceptance per segment. An unknown category leaves the cost null, logs `message.unpriced`, and counts as unpriced in the totals | B: an env var (hard to version by date). C: a database table edited by ops (needs screens and audit for a few changes a year) |
| 7 | Ops monthly total | `GET /api/v1/ops/messaging-costs?month=YYYY-MM` (ops only). It returns, per clinic and channel: messages sent, priced, unpriced, and `cost_paise`. The month is read in each clinic's time zone on `sent_at`, through a reviewed cross-clinic ops read. The API comes in P5; the ops web table comes in P6 with the other screens | B: only a per-clinic endpoint (ops wants every clinic side by side) |

Fixed points:

- **Keyword matching.**
  - Only `type: text` messages are checked.
  - The text is NFC-normalised, trimmed and case-folded, then must equal `stop`, `unsubscribe`, `रोकें` or `बंद` exactly.
  - Opting back in stays a staff action with fresh consent (M2); there is no `START` handling.
- **Suspended clinics.** The opt-out still applies to a suspended clinic; the queue cancels its reply job (R9d).
- **Migration `0018`.**
  - The index `patients(phone_e164)`.
  - Source type `OPT_OUT`.
  - `cost_paise` becomes `cost_millipaise`.
  - An index `messages(clinic_id, sent_at)`.
  - The new job kinds are per clinic, so the system-kind CHECK does not change.
- **Docs.**
  - ERRORS gains `WH_STOP_UNMATCHED` (info).
  - API.md gains the ops endpoint.
  - R14 and R18 are updated.
  - SECURITY_AND_COMPLIANCE records where the STOP sender's number is held and for how long.
  - RUNBOOK covers the SMS flag.

Planned verification on the stack, against the fake Graph API from P3:

1. A signed inbound "Stop " from a seeded patient's number opts that patient out, writes one
   SYSTEM audit event, sends one `opt_out_confirmed` and leaves no number in the stored payload.
2. That patient's next reminder becomes `SKIPPED_NO_CONSENT` (AC5).
3. A second clinic with the same number, which has messaged the patient, is opted out too. A
   third clinic, which never messaged the patient, is not.
4. With the flag on, a WhatsApp failure that the fake reports (131026) produces one SMS row,
   sent through the console. With the flag off, it produces none.
5. After a delivered status, `GET /ops/messaging-costs` shows the utility price, and a
   non-billable status shows 0.
6. Failure paths: other inbound text is not stored; an unsigned body gets 401; clinic staff get
   403 on the costs endpoint.

Not verifiable in P5: a real SMS provider (L-03), and a live Meta STOP (L-01, L-02).

### Result (20 Oct 2026)

Built as designed:

- STOP: `domain/messaging/opt_out.py`, `application/messaging/opt_out.py`, and the parser and the
  processor in `whatsapp_webhook.py` and `webhooks.py`. Migration `0018` adds
  `ix_patients_phone_e164` and source type `OPT_OUT`.
- SMS: `domain/messaging/sms.py`, `application/reminders/fallback.py`, `console_sms.py`, and SMS
  wording for `follow_up_due`.
- Costs: `domain/messaging/pricing.py` and `prices.yaml`. Migration `0019` adds
  `cost_millipaise` and `ix_messages_clinic_id_sent_at`.
- Ops: `GET /ops/messaging-costs`, contract 0.20.0.

The build differs from the design in these ways:

- **2A scope, made precise.** In each clinic that has messaged the number, every patient with that
  number is opted out, not only the one who received the message. This follows spec §8, where a
  family sharing a phone is opted out together. A clinic that never wrote to the number is still
  left alone.
- **STOPs are applied before statuses.** A status that is still unmatched makes the job retry, and
  that must never delay an opt-out. Repeating a STOP on a retry changes nothing.
- **A reminder shows its latest message.** Once the SMS exists, the reminder shows the SMS's status
  (P4 decision 3A, applied to two rows).
- **An unknown outcome stays unpriced.** A later webhook may still prove the message was
  delivered, so it is not priced at 0 like other failures.
- **Two migrations instead of one.** The opt-out (`0018`) and the costs (`0019`) went into their
  own commits.

Two bugs were found and fixed:

- **One long line broke `ruff check`.** It was in the pending follow-ups SQL; `e631c00` wraps it.
  Commit `c44ed71` on its own therefore fails `ruff check`.
- **`prices.yaml` was missing from the package.** The worker image failed at start-up; `d695295`
  fixes it. The tests read the source tree, so only `make up` could catch this. Commit `b4da260`
  on its own therefore passes the gates but does not start the worker.

Verification on the rebuilt stack, run with `make up` and `make smoke`, migration `0019`, the real
WhatsApp adapter against the fake Graph API from P3, and the console SMS fallback on:

| Step | Result |
|---|---|
| 1. Delivered status with `utility`, billable | Booking `DELIVERED`, `cost_millipaise` 11500 |
| 2. Signed "  Stop " from the patient's number | The patient and a sibling sharing the number were opted out, with 2 SYSTEM `patient.opted_out` events (`inbound_message`). The second clinic's patient with the same number was not opted out. One `opt_out_confirmed` reply was sent as text naming the clinic (`OPT_OUT`). The processed payload has no `from_encrypted`, no number, no text and no name |
| 3. AC5 | The opted-out patient's manual reminder, forced due, became `SKIPPED_NO_CONSENT` with no message |
| 4. SMS fallback | The fake refused the number (131026), so the WhatsApp message became `FAILED` `MSG_RECIPIENT_INVALID`. One `send_sms_fallback` job ran and one SMS row was `SENT` (`SMS`, `console`, cost 0). The reminder shows `SENT` |
| 5. `GET /ops/messaging-costs?month=2026-10` | 200. Sample Clinic, WhatsApp 3 messages, 1 priced, 12 paise. The total is 12. The unpriced rows are messages sent before P5 |
| 6. Failure paths | Other inbound text: 200, not stored, no error. Unsigned body: 401. STOP from an unknown number: `WH_STOP_UNMATCHED`. Front desk on costs: 403. `month=2026-13`: 422 |
| 7. Logs | No line in the API or worker logs carries a test patient's name or the inbound text |

Gates: `make lint typecheck contract-check test` pass. The API has 1575 tests at 98.27% (the core
gate holds); the web has 426.

Not verified:

- a real SMS provider (L-03);
- a live STOP through Meta (L-01, L-02);
- whether Meta reports `billable: false` for the monthly free service messages (the free
  allowance is not modelled);
- the Hindi SMS wording (L-02).

---

## M5-P6 — Web: reminder and message status, pending follow-ups, ops costs

Designed 20 Oct 2026; awaiting the developer's approval. Recommendations are marked (rec).

Facts the design rests on:

- **No reminder or message UI yet.** The web has no reminder, follow-up or message screen. The
  generated types already contain `Reminder`, `PendingFollowUp` and `OpsMessagingCosts`.
- **Reminder API.** `GET /patients/{id}/reminders` (every role, `REMINDERS_SCHEDULE`) returns
  each reminder's visible status, which is its latest message's status, and its `error_code`. An
  automatic reminder names its prescription chain by version 1's ID; it has no visit ID.
- **Pending follow-ups.** `PendingFollowUp` carries the patient, doctor, visit, prescription,
  follow-up date and reminder status, and has no phone.
- **No message history API.** No route for it exists. `messages` holds only IDs, the template key,
  channel, status, error code and times, with the phone encrypted.
- **Booking.** `BookDrawer` already takes a patient, a doctor and a date, so a prefilled
  *Book follow-up* is a reuse.
- **Seeded data.** A prescription's follow-up date must be after the day it is issued, so the
  seeded data can only have an overdue follow-up if the seed issues it in the past.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Message history | `GET /api/v1/patients/{id}/messages?limit` (every role, `REMINDERS_SCHEDULE`). It returns status only: template key, what it was about (`source_type`, `source_id`), channel, status, error code and times; never variables or the number. Newest first, at most 50. The profile shows it as **Messages**. Contract 0.21.0 | B: reminders only (booking confirmations, prescription links and opt-out replies would stay invisible; R16 asks for message status) |
| 2 | The reminder on the consultation | The screen also loads the patient's reminders, and next to *Follow-up: …* on the issued prescription shows a chip such as "Follow-up reminder · Mon 19 Oct, 09:00 · Scheduled". The chip comes from the reminder whose `prescription_id` is this visit's version 1; the latest wins if there are several. No API change | B: a `reminder` field on the consultation response (couples the visits API to reminders for one chip) |
| 3 | Reminders on the profile | A **Reminders** section showing status chip, follow-up date, due time and source. A `SCHEDULED` reminder can be moved or cancelled, and a manual one can be added by choosing a doctor and a date. P4's routes already do all of this | B: read only (FR-REM-02's manual reminders would have no screen) |
| 4 | Pending follow-ups | New `/follow-ups` page in the clinic nav for every role. Oldest first, 50 a page with *Show more*. The patient links to the profile. *Book follow-up* opens `BookDrawer` with the patient and doctor already chosen and the date set to the clinic's today, so booking takes two interactions. A booked row is marked "Booked …" until the visit is completed, then leaves the list (R17) | B: a filter on the queue (the queue is one day; these are older than today) |
| 5 | Failed messages | One table maps codes to plain English, for example `MSG_RECIPIENT_INVALID` becomes "This number can't receive WhatsApp", `MSG_NO_CONSENT` becomes "Not sent: the patient hasn't agreed to messages", and `MSG_OUTCOME_UNKNOWN` becomes "We can't tell if it arrived". A failed reminder or message shows its sentence and *Call patient*, which is a `tel:` link on the profile, where the number is shown already. No code reaches the screen raw | B: show the code (staff can't act on it) |
| 6 | Ops costs | `/ops/messaging-costs`, linked in the ops nav. It has a month picker that defaults to this month in Asia/Kolkata (single-region pilot). The table shows clinic, messages, unpriced and cost in rupees (`₹0.12`, via a new `lib/format/money.ts` that formats paise), with per-channel rows. Costs are labelled "excluding GST" and unpriced is explained | B: a column on the clinic list (no month, no channels) |
| 7 | e2e data and journeys | The seed adds one synthetic patient whose prescription was issued 10 days ago with a follow-up date 3 days ago (valid as of its issue date), so `/follow-ups` has a row. Three Playwright journeys: issue with a follow-up and then see the chip on the consultation and the reminder on the profile; from `/follow-ups`, *Book follow-up* then Confirm; ops opens messaging costs for this month | B: create the overdue data in the e2e through the API (impossible: the API refuses a past follow-up) |

Fixed points:

- **Times.** Times are shown in the clinic's zone.
- **Accessibility.**
  - Status chips are text, not colour alone.
  - Tables have captions and scoped headers.
  - The month picker is a labelled `<input type="month">`.
- **Design patterns.**
  - Data is fetched through `lib/api` hooks.
  - Every load has an error state with *Try again* and the `Ref`.
  - A failure leaves the screen usable.
- **Patient pages and printouts unchanged.** Nothing changes on patient-facing pages or
  printouts.

Planned verification:

- the gates and `make e2e` with the three new journeys;
- on the stack: a reminder's chip moves from Scheduled to Sent after its job runs, a failed
  message shows its sentence and *Call patient*, and the costs page matches the API;
- failure paths: the API down shows the `Ref`, a stale move shows `REM_NOT_SCHEDULED`'s message,
  and front desk on `/ops` is sent away.

M5's exit criterion also needs a live WhatsApp send and its webhook through Meta's test number,
which waits for L-01 and L-02. P6 can close the code of M5 but cannot meet that criterion. Before
the last commit (`Closes #40`), the developer decides whether M5 closes with the live test
recorded as pending.
