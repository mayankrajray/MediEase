# Spec: Reminders and messaging

| Field | Value |
|---|---|
| Requirements | FR-REM-01, 02, 04, 05, 06 (P5, behind a flag), 07; FR-MSG-01..05, 07; FR-APT-06; NFR-13 |
| Milestone / phases | M5 / P1–P6 |
| Status | Approved (developer sign-off 2026-10-18: the M5 plan with decisions 1A–5A and four refinements to the job queue, R9–R11 and R9a–R9e) |
| Last updated | 2026-10-20 (M5-P6: R16 and §6 made precise for the screens; M5-P5: R14 and R18 made precise, R19 added for the SMS fallback; M5-P4: R2, R5 and R17 made precise; M5-P3: R15 rewritten — WhatsApp has no status lookup; M5-P2: R6 names P2's keys and the unknown-outcome rule; earlier: approved; §3 job lifecycle gains `cancelled` and drops `failed`; R9–R11 made precise; R9a–R9e, AC8–AC11 added) |

## 1. Context
Post-visit follow-up depends on memory (A14); patients forget follow-ups and vaccination dates
(A3); health-camp information is sent by hand (A1). Reminders must arrive, must never be sent
twice, and must respect consent.

## 2. Actors and permissions
Staff schedule, edit and cancel reminders. The system schedules follow-ups from prescriptions.
Patients opt out by replying STOP.

## 3. Domain model
- `Reminder` (`SCHEDULED → SENT → DELIVERED → READ`; `FAILED`, `CANCELLED`, `SKIPPED_NO_CONSENT`)
- `Message` (`QUEUED → SENT → DELIVERED → READ`; `FAILED`)
- `Job` (`queued → running → succeeded`; `running → queued` to retry; `dead` when attempts are
  used up or the failure is permanent; `cancelled` when the work no longer applies, e.g. a
  suspended clinic or a reminder that was revised). There is no separate `failed` state: a failed
  attempt either goes back to `queued` with a later `run_at` or becomes `dead`.
- `MessageTemplate` (data from `templates.yaml`)

Initial message definitions in `templates.yaml` (`en` and `hi`). All are Meta-approved utility
templates except `opt_out_confirmed`, which is a free-form reply sent inside the customer-service
window the patient's own STOP message opens:

| Key | Variables | Purpose |
|---|---|---|
| `booking_confirmed` | clinic_name, doctor_name, date_time_or_token | FR-APT-06 |
| `rx_ready` | clinic_name, link | FR-RX-06 |
| `rx_updated` | clinic_name, link | FR-RX-09 |
| `follow_up_due` | clinic_name, doctor_name, follow_up_date, clinic_phone | FR-REM-01 |
| `opt_out_confirmed` | clinic_name | FR-MSG-05 (non-template service reply) |

## 4. Behaviour

### Scheduling
- **R1** Issuing a prescription with `follow_up_date` creates a `FOLLOW_UP` reminder due at
  `follow_up_date − 1 day, 09:00` clinic time; if that is already past, due now (subject to R4).
- **R2** Revising a prescription moves or cancels the follow-up reminder to match the new version.
  M5-P4 (decision 1A): one reminder per chain, moved in place; each move bumps `revision`, and the
  send job made for an older revision does nothing. A reminder already sent is not changed; a new
  date then gets a new reminder.
- **R3** Staff can create a manual follow-up reminder for any patient with consent; without consent
  → `REM_NO_CONSENT`.

### Sending
- **R4** Quiet hours 21:00–08:00 clinic time: a due job is rescheduled to the next 08:00
  (`MSG_QUIET_HOURS_DEFERRED`, info).
- **R5** At send time the worker re-reads consent and opt-out; if not allowed → reminder
  `SKIPPED_NO_CONSENT`, no message row. M5-P4: R4 is applied both when the reminder is scheduled
  and at send time; a job that finds itself in the quiet hours defers the reminder to the next
  08:00 under a new revision and enqueues a fresh job (decision 2A). A clinic without a phone
  cannot send `follow_up_due`: manual reminders are refused and automatic ones end `FAILED` with
  `REM_CLINIC_PHONE_MISSING` (decision 6A). Once sent, a reminder shows its message's status
  (decision 3A).
- **R6** A message row is created with a unique `idempotency_key` before calling the provider
  (P2: `booking_confirmed:<appointment_id>` and `rx_link:<prescription_id>`; P4: `follow_up_due:<reminder_id>`, one message per
  reminder however often it moves); a unique constraint prevents a second send for the same key. A
  row found still marked as being sent at a retry means the outcome is unknown: it becomes `FAILED`
  (`MSG_OUTCOME_UNKNOWN`) and is never sent again (M5-P2 decision 4A, at most once). A provider
  timeout is an unknown outcome, not a retryable error.
- **R7** Provider timeouts: 10 s. Retryable errors (`MSG_PROVIDER_RATE_LIMIT`,
  `MSG_PROVIDER_UNAVAILABLE`) back off 1, 5, 15, 60 minutes, then `dead`. Non-retryable errors
  (`MSG_TEMPLATE_*`, `MSG_RECIPIENT_INVALID`) fail immediately.
- **R8** Message variables are validated against the template schema before sending; they may only
  include clinic name, doctor display name, dates/times, token numbers, the clinic phone and signed
  links.

### Jobs
- **R9** Workers claim up to 10 due jobs per poll using `FOR UPDATE SKIP LOCKED`, poll every 2
  seconds when idle, and heartbeat `locked_at` every 60 seconds for long jobs.
- **R9a** *Short claim, crash-safe attempts.* The claim is its own transaction: it moves the jobs
  `queued → running`, **increments `attempts`**, sets `locked_by` and `locked_at`, and commits
  **before** any handler runs. No row lock is held across a handler or network I/O. The handler
  runs in its own unit of work; the outcome (succeeded, retry, dead) is a third short
  transaction that only applies while the job is still `running` under this worker's lock. A job
  that hard-crashes the worker has therefore already counted the attempt.
- **R9b** *Retries.* A retryable failure goes back to `queued` with `run_at` = now + 1, 5, 15 or
  60 minutes after attempts 1–4 (plus up to 10% jitter), keeping `last_error_code`. When
  `attempts >= max_attempts` (default 5), or the failure is permanent, the job becomes `dead`
  (`job.dead` with the error code). An unknown kind is retryable (`JOB_HANDLER_MISSING`: an api
  newer than the worker during a deploy).
- **R9c** *Idempotent enqueueing.* `dedupe_key` is unique only among jobs that are `queued`,
  `running` or `succeeded` (a partial unique index). A `cancelled` or `dead` job never blocks
  enqueueing the same logical key again, e.g. a follow-up reminder revised in P4 or a clinic
  that is unsuspended.
- **R9d** *System jobs.* A job either belongs to a clinic (`clinic_id` set; the handler gets that
  clinic's scope only) or is one of an explicit list of system kinds with `clinic_id` null
  (P1: `purge_expired_auth_and_links`). A database CHECK enforces the pairing both ways; adding a
  system kind is a migration. Jobs of a suspended clinic are `cancelled`
  (`JOB_CLINIC_SUSPENDED`), not run.
- **R9e** *Recurring jobs.* A scheduler step in the worker enqueues each recurring job once per
  period, with `dedupe_key = <kind>:<period start>`, so several workers never double it.
- **R10** Jobs still `running` with `locked_at` older than 5 minutes are recovered by the reaper:
  back to `queued` (with the R9b delay and `JOB_LOCK_EXPIRED`) while attempts remain, otherwise
  `dead`. A crash loop therefore ends in `dead` after `max_attempts`, never loops for ever.
- **R11** Every job carries the `request_id` of the change that created it (the scheduler makes
  one per tick); worker logs bind it with the job's ID and kind. Payloads hold IDs only.
- **R11a** *Health.* After each poll iteration that reached the database successfully, the worker
  rewrites a heartbeat file in a small tmpfs at `/tmp` (the root filesystem is read-only). The
  container's health check fails when the file is older than 90 seconds, so a worker whose
  database connection is dead turns unhealthy.

### Webhooks
- **R12** `GET /webhooks/whatsapp` answers Meta's verification challenge using the configured verify token.
- **R13** `POST /webhooks/whatsapp` verifies the signature against the raw body, stores the event in
  `webhook_events` (unique `event_key`, the SHA-256 of the body; redacted to IDs and statuses),
  responds 200 within 1 second, and processes status updates in a job, idempotently (status only
  moves forward: SENT → DELIVERED → READ; FAILED is terminal). A status that matches no message
  yet is retried with the job back-off, then recorded as `WH_UNMATCHED`.
- **R14** Inbound messages whose trimmed, case-insensitive text is `STOP`, `UNSUBSCRIBE`, `रोकें`
  or `बंद` opt out every patient in every clinic with that phone who received a message from us,
  and send `opt_out_confirmed`. Other inbound text is not stored. M5-P5 (decisions 1A–3A): the
  keyword is matched in the request before redaction (Unicode NFC, text messages only); only a STOP
  keeps the sender's number, encrypted with the messages' keys, until its processing job runs. In
  each clinic that has sent a message to a patient with that number, every patient whose current
  number it is is opted out (so a family sharing a phone goes together, §8); a clinic that never
  wrote to the number is left alone. A hidden number (a WhatsApp username) is found through our
  message the reply answered; otherwise `WH_STOP_UNMATCHED` and nothing changes. Each affected
  clinic replies once per STOP, naming itself, unless 24 hours have passed (the service window).
- **R15** *Reconciliation (M5-P3, rewritten for WhatsApp).* The Cloud API has no endpoint to read a
  message's status: statuses arrive only by webhook. So an hourly system job
  (`reconcile_messages`) re-enqueues stored webhook events that never processed (older than 10
  minutes) and reports messages still `SENT` 24 hours after sending (`messages.reconciled`,
  `v_message_health.unconfirmed_24h`). Each send carries our message ID as
  `biz_opaque_callback_data`, which Meta echoes in every status, so a status finds its message
  even when the worker died before saving Meta's ID; such a status corrects a `QUEUED` row or a
  `FAILED` / `MSG_OUTCOME_UNKNOWN` row to the status it proves (decision 4A of P3), and a
  prescription link still `PENDING` becomes `SENT`. A real `FAILED` from the provider stays final.

### Visibility and cost
- **R16** Reminder and message statuses are visible on the patient profile and visit screen.
  M5-P6 (decisions 1A–3A): the visit screen shows the issued prescription's reminder as a chip
  beside its follow-up date; the profile lists the patient's reminders (move, cancel, add a manual
  one) and their message history, status only, from `GET /patients/{id}/messages`.
- **R17** The pending follow-ups list shows patients whose follow-up date passed without a completed
  visit on or after that date, ordered by oldest first. M5-P4: one row per patient (their latest
  overdue follow-up, from the latest issued version of its chain), the visit's date read in the
  clinic's time zone, paginated (`limit` 1–100, `offset`), with that chain's reminder status.
- **R18** Each message records `cost_paise` from a configurable price table by channel and category;
  the ops console aggregates per clinic per month. M5-P5 (decisions 5A–7A): the cost is
  `cost_millipaise` (integer, 1 paisa = 1,000; Meta's utility rate is 11.5 paise), from
  `prices.yaml` (by channel and category from an effective date, excluding GST). WhatsApp is priced
  when delivery is reported, at the webhook's category, 0 when Meta says it is not billable; a
  failure 0 (not an unknown outcome); the console 0; an SMS per segment at acceptance. An unknown
  price stays null and is counted as unpriced. `GET /ops/messaging-costs?month=YYYY-MM` reads each
  clinic's month in its own time zone and rounds to paise at each total.
- **R19** *SMS fallback (FR-REM-06, M5-P5 decision 4A; off unless `MESSAGING_SMS_FALLBACK_ENABLED`).*
  A follow-up reminder whose WhatsApp message ends `FAILED` with a definite non-delivery
  (`MSG_RECIPIENT_INVALID`, `MSG_PROVIDER_REJECTED`, or a rate-limit or outage after the last
  attempt) — at send time or by webhook — gets one SMS (`sms:<reminder>`), if the patient consented
  to SMS, outside the quiet hours. Never after `MSG_OUTCOME_UNKNOWN`. The reminder then shows the
  SMS's status. Only a console SMS provider exists until L-03; it is refused in production.

## 5. API surface
See API.md "Reminders and messaging".

## 6. UI notes
- Reminder chip on the visit: "Follow-up reminder · 16 Sep, 9:00 · Scheduled". M5-P6: shown as
  "Follow-up reminder · Wed, 16 Sep, 09:00 · Scheduled", the status in words (not colour alone).
- Pending follow-ups page with one-click "Book follow-up". M5-P6: `/follow-ups`; the booking drawer
  opens with the patient, the doctor and today chosen, so Confirm books it.
- Failed messages show a plain explanation and a "Call patient" hint. M5-P6: one sentence per
  code (`features/reminders/labels.ts`), never the code; *Call patient* is a `tel:` link on the
  profile.

## 7. Events and side effects
| Trigger | Audit | Analytics |
|---|---|---|
| Reminder scheduled / cancelled | `reminder.scheduled` / `reminder.cancelled` | `reminder_scheduled` |
| Message status change | — | `message_status_changed` |
| Opt-out | `patient.opted_out` | `patient_opted_out` |

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| Worker crashes after provider accepted but before DB update | Retry hits the unique idempotency key → no second send; reconciliation fixes status |
| Duplicate webhook | Ignored by `event_id` |
| Status webhook arrives before our DB write commits | Stored event is retried by the processor after 30 s |
| Patient number shared by two patients | One opt-out applies to both (same phone), in each clinic that messaged the number (M5-P5) |
| Clinic suspended | Jobs for that clinic are skipped and marked `cancelled` (`JOB_CLINIC_SUSPENDED`) |
| Worker killed mid-job | The attempt already counts (R9a); the reaper requeues it after 5 minutes, or marks it `dead` at `max_attempts` (R10) |

## 9. Acceptance criteria
- **AC1 (FR-REM-01)** Given an Rx issued with follow-up 20 Sep, then a reminder exists due
  19 Sep 09:00 IST (03:30 UTC).
- **AC2 (FR-REM-04)** Given a job due at 22:15 IST, then it is rescheduled to 08:00 IST next day.
- **AC3 (NFR-13)** Given two workers and 100 due jobs, then each job runs exactly once.
- **AC4 (NFR-13)** Given a simulated crash after provider acceptance, then a retry does not create
  a second provider call.
- **AC5 (FR-MSG-05)** Given an inbound "stop", then the patient is opted out and the next scheduled
  reminder becomes `SKIPPED_NO_CONSENT`.
- **AC6 (FR-MSG-03)** Given a webhook with an invalid signature, then 401 `WH_SIGNATURE_INVALID`
  and nothing is stored beyond a log event.
- **AC7 (FR-MSG-04)** Given the leakage test, then no message variable contains item or diagnosis text.
- **AC8 (R9a, R10)** Given a job whose worker dies after the claim, then the reaper requeues it
  with the attempt counted, and after `max_attempts` such crashes it is `dead`.
- **AC9 (R9c)** Given a cancelled job with key K, then a new job with key K can be enqueued; given
  a queued or succeeded job with key K, then a second enqueue of K does nothing.
- **AC10 (R9d)** Given a job with no clinic and a kind that is not a system kind, then the
  database refuses it.
- **AC11 (R11a)** Given a worker that cannot reach the database, then its heartbeat goes stale and
  the container becomes unhealthy.

## 10. Observability
Events: `job.claimed`, `job.succeeded`, `job.retry_scheduled`, `job.dead`, `job.cancelled`,
`job.lock_expired`, `job.lost_lock`, `worker.started`, `worker.stopped`, `message.sent`,
`message.failed`, `webhook.received`, `webhook.signature_invalid`, `reminder.skipped_no_consent`,
and from M5-P5 `webhook.stop_unmatched`, `patient.opted_out`, `reminder.sms_fallback_enqueued`,
`messaging.console_sms_accepted`, `message.unpriced`.
Metrics: queue depth, oldest job age, messages by status, failure rate by error code
(`v_job_health` from P1, `v_message_health` from P2).

## 11. Out of scope
Medicine-course reminders (FR-REM-03), SMS fallback on by default (FR-REM-06), broadcasts,
appointment reminders, clinic-owned sender numbers.

## 12. Open questions
- Should follow-up reminders include a booking link once the public page exists (M7)?
- Exact Hindi wording for templates — review with pilot clinics (L-02).
