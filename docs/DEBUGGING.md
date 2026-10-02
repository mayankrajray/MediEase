# MediEase — Debugging Guide

How to find out **what happened, where, and why** — for humans and AI agents alike.
Read this before investigating any failure, and search [DEBUG_JOURNAL.md](DEBUG_JOURNAL.md) for the
symptom first. Error codes are explained in [ERRORS.md](ERRORS.md); operational procedures are in
[RUNBOOK.md](RUNBOOK.md).

> Some commands reference services that arrive in later milestones (`api` in M0, `worker` in M5).
> The sections say which.

---

## 1. The method (short version)

1. **Reproduce** with the smallest input and capture the `request_id`.
2. **Locate** the layer using the symptom table (§4).
3. **Read the evidence**: logs for that `request_id`, the error `code`, the related row
   (appointment, job, message).
4. **Hypothesise**, and name the observation that would disprove it.
5. **Fix the root cause** and add a failing-then-passing test.
6. **Record** in `DEBUG_JOURNAL.md`.

## 2. Tracing one request end to end

Every request has a `request_id` (ULID). It is:

| Where | How to see it |
|---|---|
| Browser | Response header `X-Request-ID`; shown in the error toast as "Ref: …" |
| API logs | field `request_id` |
| Error response body | `error.request_id` |
| Jobs enqueued by that request | `jobs.request_id` |
| Worker logs for those jobs | field `request_id` (copied from the job) |
| Messages sent | `messages.request_id` |
| Audit entries | `audit_events.request_id` |

```bash
# All log lines for one request, across api and worker (M5+)
docker compose logs --no-log-prefix api worker | jq -c 'select(.request_id=="01J8Z5W6X4K7Q2N3R5T8V9Y0AB")'

# Everything the database knows about that request (no clinical columns)
make psql
select 'job' src, id, kind, state, last_error_code, created_at from jobs where request_id = '…'
union all
select 'msg', id, template_key, status, error_code, created_at from messages where request_id = '…'
union all
select 'audit', id, action, entity_type, null, occurred_at from audit_events where request_id = '…'
order by 6;
```

## 3. Logs

### 3.1 Shape

```json
{"timestamp":"2026-09-15T04:02:11.482Z","level":"INFO","event":"appointment.booked",
 "request_id":"01J8Z…","clinic_id":"0191…","user_id":"0191…","route":"POST /api/v1/appointments",
 "status":201,"duration_ms":38,"appointment_id":"0191…","source":"FRONT_DESK"}
```

Required fields: `timestamp`, `level`, `event`, `request_id`. Contextual: `clinic_id`, `user_id`,
`route`, `status`, `duration_ms`, `job_id`, `job_kind`, `provider`, `provider_message_id`,
`error_code`.

**Never present:** patient names, phone numbers (masked only), notes, diagnoses, medicine names,
tokens, passwords, cookies. If you see one, it is a security bug — fix it and journal it.

### 3.2 Useful commands

```bash
make logs                                   # follow all services
docker compose logs -f api | jq -c .        # pretty-print API logs
docker compose logs api | jq -c 'select(.level=="ERROR")'
docker compose logs api | jq -c 'select(.error_code=="APT_SLOT_TAKEN")'
docker compose logs api | jq -c 'select(.duration_ms > 500)'   # slow requests
docker compose logs worker | jq -c 'select(.event|startswith("job."))'
```

### 3.3 Event naming

`<area>.<what_happened>` in past tense: `auth.sign_in_failed`, `appointment.booked`,
`queue.transition_rejected`, `rx.issued`, `patient_link.challenge_failed`, `job.claimed`,
`job.retry_scheduled`, `job.dead`, `message.sent`, `message.failed`, `webhook.signature_invalid`,
`ready.db_unavailable`, `config.invalid`.

### 3.4 Turning on more detail safely

Set `LOG_LEVEL=DEBUG` in `.env` and restart the service. `DEBUG` may add SQL timings and
provider response codes — **never** request/response bodies. SQL parameter logging stays off in
every environment (`DB_ECHO_PARAMS=false` is enforced by settings validation).

## 4. Symptom → where to look

| Symptom | Likely layer | First checks |
|---|---|---|
| Service exits at start with `config.invalid` | Settings | Message names the missing/invalid variable; compare `.env` with `.env.example` |
| `/health` OK but `/ready` 503 | Database / dependency | `error.code` in body; `make ps` shows db healthy?; `DATABASE_URL` host is `db` inside compose, `localhost` outside |
| `migrate` container exits non-zero | Migrations | `docker compose logs migrate`; see RUNBOOK "Migration failed" |
| Browser shows signed-out right after sign-in | Cookies | Calling API directly instead of via `/api` proxy? `Secure` cookie on http? See §5.3 |
| `403 AUTH_CSRF_INVALID` on every POST | CSRF | Web client not sending `X-CSRF-Token`; cookie path mismatch |
| `404` for a record you can see in the database | Tenancy | Wrong `X-Clinic-ID` or user not a member of that clinic — expected behaviour |
| Times off by 5 h 30 m | Timezone | A naive datetime or server-local "now" somewhere; see §5.4 |
| Two patients booked into one slot | Concurrency | Session row lock missing or bypassed; unique index present? §5.5 |
| Queue screen stale | Polling / ETag | Network tab: 304 forever? ETag not changing on transition |
| Reminder shows `SCHEDULED` long after due time | Worker / jobs | Worker running? oldest queued job age; §5.6 |
| Reminder `SKIPPED_NO_CONSENT` | Consent | Patient consent flags / opt-out — expected behaviour |
| Message `FAILED` with `MSG_TEMPLATE_*` | Provider templates | Template name/language/variables vs `templates.yaml`; §5.7 |
| Status never moves past `SENT` | Webhooks | Webhook reachable? signature verification failing? §5.8 |
| Patient link says expired/invalid | Links | Token expiry, revocation, or signing key rotated; §5.9 |
| PDF missing or blank | PDF adapter / storage | `render_pdf` job state; storage path; fonts for Hindi |
| Slow patient search | Query / index | `EXPLAIN ANALYZE`; index leading with `clinic_id` used? |

## 5. Playbooks for known failure types

### 5.1 Configuration fails at start-up
Settings are validated once in `config/settings.py`. The error lists each invalid field.
Do not add defaults to make it pass — fix `.env` and, if the variable is new, `.env.example`.

### 5.2 Readiness failing
`/ready` runs `SELECT 1` with a 2-second budget (connect, pool wait and query) and reports
`READY_DB_UNAVAILABLE` or `READY_DB_TIMEOUT`. Check `make ps`, then `docker compose logs db`.
Inside containers the host is `db`; from your laptop it is `localhost`.

- The API logs `ready.check_failed` (WARNING) with `code`, `cause` (the exception type, e.g.
  `OperationalError`, `ConnectionTimeout`, `QueryCanceled`) and `request_id`. Filter
  `docker compose logs api` by that event.
- `api` shows `(unhealthy)` in `make ps` while `/ready` fails: its healthcheck is `/ready`. It is
  not restarted for that; it turns healthy again once the database answers.
- `migrate` exited non-zero → `api` never starts: `docker compose logs migrate` (RUNBOOK
  "Migration failed").

### 5.3 Auth cookies not sticking
- The browser must call `http://localhost:3000/api/...` (web origin), which rewrites to the API.
  Calling `:8000` directly makes cookies cross-site.
- In local development `COOKIE_SECURE=false`; in any HTTPS environment it must be `true`.
- Check the `Set-Cookie` response header in dev tools, then the cookie jar for path and expiry.

### 5.4 Timezone errors
- Database columns are `timestamptz`; Python datetimes must be timezone-aware (`datetime.now(UTC)`
  via the clock port — never `datetime.now()` or `utcnow()`).
- "Clinic-local date" (e.g. today's queue) is computed with the clinic's `timezone`, not the
  server's. A session near midnight IST is the classic trap.
- The web app formats with the clinic timezone from `/me`, not the browser's.
- Tests freeze time through the clock port; a test that passes only at certain hours is a bug.

### 5.5 Double booking / capacity exceeded
1. Confirm the booking use case locks the session: look for `SELECT … FOR UPDATE` in DEBUG SQL logs.
2. Confirm the partial unique indexes exist: `\d appointments`.
3. Run the concurrency test: `make test-api ARGS="-k fr_apt_04"`.
4. Check whether a code path inserts appointments without going through the use case (scripts, ops import).

### 5.6 Jobs not running (M5+)
```sql
select state, kind, count(*), min(run_at) as oldest_run_at
from jobs group by 1,2 order by 1,2;

select id, kind, attempts, last_error_code, locked_by, locked_at
from jobs where state in ('running','dead') order by updated_at desc limit 20;
```
- `queued` with old `run_at` → worker not running or crashing: `docker compose logs worker`.
- `running` with `locked_at` older than 5 min → worker died mid-job; the reaper will requeue it.
- `dead` → read `last_error_code` in ERRORS.md; fix; requeue from the ops console.

### 5.7 WhatsApp template errors (M5+)
- Template must be **approved** in Meta for the exact name **and** language code.
- Variable count and order must match the approved template; compare with `templates.yaml`.
- Business-initiated messages outside a customer-service window can only be templates.
- Check the provider error code logged as `provider_error_code` and its mapping to `MSG_*`.

### 5.8 Webhooks not arriving or rejected (M5+)
- Local development needs a tunnel to receive Meta webhooks; otherwise use the console adapter.
- `webhook.signature_invalid` → wrong app secret, or the body was re-serialised before verification
  (verify against the **raw** request bytes).
- Duplicates are normal; `webhook_events.event_id` makes processing idempotent.

### 5.9 Patient link problems (M4+)
- Decode the token header/claims locally with `scripts/inspect_link_token.py` (no network) to see
  `purpose`, `exp`, `jti`.
- `LINK_EXPIRED` → issue a fresh link from the visit screen.
- `LINK_LOCKED` → too many wrong last-4 attempts; staff can reset from the patient profile.
- All links invalid at once → the signing key changed; see RUNBOOK "Key rotation".

## 6. Inspecting the database safely

- Use `make psql` against **local** data only. Production access is break-glass (RUNBOOK).
- Prefer selecting IDs, statuses and timestamps. Do not select clinical columns
  (`visits.*` text fields, `prescription_items.*`, `prescriptions.advice`) unless the investigation
  truly requires it — and never paste results into chats, issues or AI tools.
- Handy views expose only non-clinical fields: `v_clinic_activity` (from M1), `v_job_health` and
  `v_message_health` (from M5).

## 7. Debugging with an AI agent

Give the agent evidence, not a vibe:

```
Symptom: Reminder for patient 0191… stuck at SCHEDULED since 09:00 IST.
request_id of the Rx issue: 01J8Z…
Job row: kind=send_reminder, state=queued, run_at=2026-09-16T03:30:00Z, attempts=0
Worker logs (last 50 lines, attached, no PII)
Read docs/DEBUGGING.md §5.6 and docs/DEBUG_JOURNAL.md, form a hypothesis, tell me what
observation would disprove it, and propose a fix with a failing test first. Do not change code yet.
```

Agents must not "fix" by loosening tenancy, catching and ignoring exceptions, raising timeouts
without a reason, or skipping tests.

## 8. After the fix

- Add the test that reproduces the bug.
- Add a `DEBUG_JOURNAL.md` entry.
- If an operator would need this knowledge, update `RUNBOOK.md`; if a new error code appeared,
  update `ERRORS.md`; if the symptom table would have helped, update §4 above.
