# Spec: Reminders and messaging

| Field | Value |
|---|---|
| Requirements | FR-REM-01, 02, 04, 05, 07; FR-MSG-01..05, 07; FR-APT-06; NFR-13 |
| Milestone / phases | M5 / P1–P6 |
| Status | Draft |
| Last updated | 2026-09-15 |

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
- `Job` (`queued → running → succeeded | failed → queued (retry) | dead`)
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
- **R3** Staff can create a manual follow-up reminder for any patient with consent; without consent
  → `REM_NO_CONSENT`.

### Sending
- **R4** Quiet hours 21:00–08:00 clinic time: a due job is rescheduled to the next 08:00
  (`MSG_QUIET_HOURS_DEFERRED`, info).
- **R5** At send time the worker re-reads consent and opt-out; if not allowed → reminder
  `SKIPPED_NO_CONSENT`, no message row.
- **R6** A message row is created with `idempotency_key = <reminder_id>:<attempt_group>` before
  calling the provider; a unique constraint prevents a second send for the same key.
- **R7** Provider timeouts: 10 s. Retryable errors (`MSG_PROVIDER_RATE_LIMIT`,
  `MSG_PROVIDER_UNAVAILABLE`) back off 1, 5, 15, 60 minutes, then `dead`. Non-retryable errors
  (`MSG_TEMPLATE_*`, `MSG_RECIPIENT_INVALID`) fail immediately.
- **R8** Message variables are validated against the template schema before sending; they may only
  include clinic name, doctor display name, dates/times, token numbers, the clinic phone and signed
  links.

### Jobs
- **R9** Workers claim up to 10 due jobs per poll using `FOR UPDATE SKIP LOCKED`, poll every 2
  seconds when idle, and heartbeat `locked_at` every 60 seconds for long jobs.
- **R10** Jobs locked for more than 5 minutes without heartbeat are requeued by the reaper.
- **R11** Every job carries the `request_id` of the change that created it; worker logs use it.

### Webhooks
- **R12** `GET /webhooks/whatsapp` answers Meta's verification challenge using the configured verify token.
- **R13** `POST /webhooks/whatsapp` verifies the signature against the raw body, stores the event in
  `webhook_events` (unique `event_id`), responds 200 within 1 second, and processes status updates
  idempotently (status only moves forward: SENT → DELIVERED → READ; FAILED is terminal).
- **R14** Inbound messages whose trimmed, case-insensitive text is `STOP`, `UNSUBSCRIBE`, `रोकें`
  or `बंद` opt out every patient in every clinic with that phone who received a message from us,
  and send `opt_out_confirmed`. Other inbound text is not stored.
- **R15** A reconciliation job re-fetches statuses for messages stuck in `SENT` for more than
  24 hours where the provider supports it.

### Visibility and cost
- **R16** Reminder and message statuses are visible on the patient profile and visit screen.
- **R17** The pending follow-ups list shows patients whose follow-up date passed without a completed
  visit on or after that date, ordered by oldest first.
- **R18** Each message records `cost_paise` from a configurable price table by channel and category;
  the ops console aggregates per clinic per month.

## 5. API surface
See API.md "Reminders and messaging".

## 6. UI notes
- Reminder chip on the visit: "Follow-up reminder · 16 Sep, 9:00 · Scheduled".
- Pending follow-ups page with one-click "Book follow-up".
- Failed messages show a plain explanation and a "Call patient" hint.

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
| Patient number shared by two patients | One opt-out applies to both (same phone) |
| Clinic suspended | Jobs for that clinic are skipped and marked `CANCELLED` |

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

## 10. Observability
Events: `job.claimed`, `job.succeeded`, `job.retry_scheduled`, `job.dead`, `message.sent`,
`message.failed`, `webhook.received`, `webhook.signature_invalid`, `reminder.skipped_no_consent`.
Metrics: queue depth, oldest job age, messages by status, failure rate by error code.

## 11. Out of scope
Medicine-course reminders (FR-REM-03), SMS fallback on by default (FR-REM-06), broadcasts,
appointment reminders, clinic-owned sender numbers.

## 12. Open questions
- Should follow-up reminders include a booking link once the public page exists (M7)?
- Exact Hindi wording for templates — review with pilot clinics (L-02).
