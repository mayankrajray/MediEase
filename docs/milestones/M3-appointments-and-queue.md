# M3 — Appointments and daily queue: design notes

| Field | Value |
|---|---|
| Status | Done — P1–P5 implemented and confirmed 17 Oct 2026; merged in PR #37 |
| Spec | `docs/specs/appointments-and-queue.md` (Approved 2026-10-17, D1–D32) |
| Covers | FR-APT-01..07, FR-QUE-01..05 |
| Issue / branch / PR | #36 · `m3/36-appointments-and-queue` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | Front desk books in ≤ 3 interactions; the concurrent double-booking test passes; the queue refreshes on every open screen within 5 s |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Doctor schedules, exceptions, sessions generated per clinic-local date; slot and token mode | Below |
| P2 | Booking, reschedule, cancel under a session row lock | Below (done) |
| P3 | Queue state machine, transitions, walk-ins | Below (done) |
| P4 | Live queue (ETag polling) | Below (done) |
| P5 | Web: queue board, booking flow, schedule settings | Below (implemented) |

---

## M3-P1 — Doctor schedules, exceptions and sessions

**Status: approved by the developer 17 Oct 2026 with 1A–6A and three refinements; implemented the same day and confirmed by the developer (result at the end of this section).** (a maximum block
length so a daytime inversion still fails; cross-day overlap; leave on already-generated dates).
Covers FR-APT-01, FR-APT-02; spec R1–R4 (the token counter's home), R14–R20, AC5.

### Concepts

1. **Rules versus instances.** A weekly block is a rule ("Mondays 10:00–13:00, 15-minute slots"); a
   session is one instance of it ("Mon 20 Oct, 04:30–07:30 UTC"). Bookings (P2) attach to the
   instance, so changing a rule never moves an appointment that already exists.
2. **Clinic-local in, UTC out.** Blocks store wall-clock times. Generation combines a clinic-local
   date with them in the clinic's zone and stores UTC; a session belongs to the date it starts on
   (R2). The domain is given the zone and "today" and never reads a clock.
3. **Overnight without accidents.** An end at or before the start means "next day", but a block may
   last at most 12 hours. 23:00–01:00 (2 h) passes; 13:00–10:00 (21 h, almost certainly a typo) is
   `SCH_INVALID_BLOCK` (R14).
4. **Overlap on the circle of the week.** Each block becomes an interval of minutes since Monday
   00:00, modulo 7 × 1440. Overlap is checked on that circle, so Sunday 22:00–02:00 collides with
   Monday 01:00–05:00, and a Tuesday overnight block with Wednesday morning (R15).
5. **Lazy, idempotent generation.** Reading a date plans its sessions from the rules and inserts the
   missing ones with `ON CONFLICT (doctor_id, starts_at) DO NOTHING`. Two screens asking at once end
   up with one set: the constraint guarantees it, not timing (R1).
6. **Change = reconcile, never cancel.** After a schedule or exception change, each future session
   is compared with the new plan for its date: unchanged ones stay; unbooked ones that differ are
   deleted (regenerated on the next read); booked ones that differ are kept and returned as
   `kept_sessions` for the owner (R16–R18). In P1 nothing is booked yet, but the rule is built and
   tested now (by setting `booked_count` directly) so P2 inherits it.
7. **Serialised per doctor.** A change locks the doctor row `FOR UPDATE`; generation takes
   `FOR SHARE`. Reads run in parallel with each other, but never alongside a change (R20).

### Data (migration `0007`, expand-only)

| Table | Columns (all tenant tables carry `clinic_id` + FK) | Constraints |
|---|---|---|
| `clinics` | + `booking_mode text not null default 'TOKENS'` | `CHECK (SLOTS, TOKENS)` |
| `doctor_schedules` | `doctor_id`, `weekday smallint`, `start_time time`, `end_time time`, `slot_minutes smallint null`, `capacity smallint null`, `valid_from date`, `valid_to date null`, timestamps | weekday 0–6; slot 5–120; capacity 1–500; `valid_to >= valid_from`; index `(clinic_id, doctor_id)` |
| `schedule_exceptions` | `doctor_id`, `on_date date`, `kind`, `start_time`, `end_time`, `slot_minutes`, `capacity`, `note`, timestamps | kind LEAVE/EXTRA; LEAVE has no times, EXTRA has both; one LEAVE per doctor and date (partial unique index) |
| `sessions` | `doctor_id`, `on_date`, `starts_at`, `ends_at`, `mode`, `slot_minutes null`, `capacity`, `booked_count default 0`, `next_token default 1`, `status default 'OPEN'`, timestamps | `UNIQUE (doctor_id, starts_at)`; `ends_at > starts_at`; `0 <= booked_count <= capacity` (no overbooking, D6); slot mode ⇔ `slot_minutes` set; index `(clinic_id, on_date, doctor_id)` |

A replaced schedule closes its blocks (`valid_to = today − 1`) rather than deleting them, so past
dates keep the rules they were generated from; blocks that never took effect are deleted.

### API (contract 0.9.0)

| Method | Path | Permission | Behaviour |
|---|---|---|---|
| GET | `/api/v1/clinic/doctors/{id}/schedule` | `DOCTORS_VIEW` | Current blocks and upcoming exceptions |
| PUT | `/api/v1/clinic/doctors/{id}/schedule` | `SCHEDULES_MANAGE` | Replace the weekly blocks (R14–R16); audited `schedule.changed`; returns the schedule and `kept_sessions` |
| POST | `/api/v1/clinic/doctors/{id}/schedule-exceptions` | `SCHEDULES_MANAGE` | Add `LEAVE` or `EXTRA` (R17, R18); audited; returns it and `kept_sessions` |
| DELETE | `/api/v1/clinic/doctors/{id}/schedule-exceptions/{exception_id}` | `SCHEDULES_MANAGE` | Remove it; audited; returns `kept_sessions` |
| GET | `/api/v1/sessions?date=&doctor_id=` | `APPOINTMENTS_MANAGE` | The date's sessions, generated on first read (R1); every active doctor when `doctor_id` is absent; slots with availability in slot mode, the next token in token mode |
| PUT | `/api/v1/ops/clinics/{clinic_id}/doctors/{id}/schedule` | ops | The same replacement during onboarding (D5) |
| PATCH | `/api/v1/clinic` · POST `/api/v1/ops/clinics` | as today | Gain `booking_mode` (R19) |

New error codes: `SCH_INVALID_BLOCK` (422), `SCH_OVERLAP` (409), `SCH_LEAVE_EXISTS` (409),
`SCH_MODE_INCOMPATIBLE` (409). Dates before today or beyond 180 days are `REQ_VALIDATION_FAILED`.

### Files

| Layer | Files |
|---|---|
| Domain | `scheduling/{blocks,exceptions,sessions,errors}.py`; `clinics/clinic.py` (`BookingMode`); `identity/permissions.py` (`SCHEDULES_MANAGE`); `audit/actions.py` (+3) |
| Ports / adapters | `ScheduleRepository`, `ScheduleExceptionRepository`, `SessionRepository`; `DoctorRepository.get(lock=…)`; models, repositories, unit of work; migration `0007` |
| Application | `scheduling/{schedules,exceptions,sessions,reconcile,views}.py`; `clinics/onboard_clinic.py` (booking mode) |
| Delivery | `http/scheduling.py` (new blueprint), `http/ops.py`, `http/clinic.py`, `bodies.py`, `errors.py`, `bootstrap.py` |
| Contract / docs | `openapi.yaml` 0.9.0 + web types, `API.md`, `ERRORS.md`, `DATA_MODEL.md`, `RUNBOOK.md` §10, CHANGELOG |
| Seed | sample doctors get Monday–Saturday 10:00–13:00 blocks with 15-minute slots and a capacity of 12 |

### Tests

- **Domain:** slot stepping and derived capacity; token capacity; the 12-hour bound (13:00–10:00
  refused, 23:00–01:00 accepted); zero-length and non-dividing slots; overlap within a day, across
  midnight and across Sunday→Monday; LEAVE removes, EXTRA adds; validity windows; AC5 (the
  23:00–01:00 session belongs to its start date, with correct UTC slots); Kolkata midnight at both
  edges; reconciliation (unchanged kept, unbooked changed deleted, booked changed kept).
- **PostgreSQL:** two threads generating one date create one set; constraints refuse bad rows;
  migration up and down.
- **HTTP:** every endpoint; permissions (owner writes; doctor and front desk read; ops only through
  the ops route); leave on generated dates with and without bookings; schedule replacement keeps a
  booked session and returns it; booking-mode change guard; audit rows.
- **Tenancy:** another clinic's doctor, schedule, exception and sessions are 404 or absent; the
  repository and HTTP guards cover the new tables and routes.
- **Contract:** every operation against `openapi.yaml`.

### Verify

```bash
make up && make seed
# as owner@sample-clinic.example (RUNBOOK §1), with a doctor's id from GET /api/v1/clinic/doctors:
#   GET  /api/v1/sessions?date=<next Monday>&doctor_id=<id>   -> one session (seeded block)
#   PUT  .../schedule {"blocks":[{"weekday":0,"start_time":"23:00","end_time":"01:00","capacity":10}]}
#        -> 200; the Monday session is replaced by 23:00 IST (17:30 UTC) - 01:00 the next day
#   PUT  a block 13:00-10:00                                   -> 422 SCH_INVALID_BLOCK
#   PUT  Sunday 22:00-02:00 and Monday 01:00-05:00             -> 409 SCH_OVERLAP
#   POST .../schedule-exceptions {"kind":"LEAVE","on_date":"<that Monday>"} -> the date has no sessions
#   as desk@: the same PUT                                     -> 403 PERM_DENIED
make lint typecheck test && make smoke && make e2e
```

### Risks

| Risk | Mitigation |
|---|---|
| Time-zone mistakes around midnight | One planning function, tested at both Kolkata midnight edges; CI runs with `TZ=America/New_York` |
| Lazy generation racing itself or a change | The unique constraint with `ON CONFLICT DO NOTHING`; the per-doctor lock (R20); a two-thread test |
| A change silently dropping a booking | Booked sessions are never deleted; they come back in `kept_sessions` |
| Generation writes on every read | Only missing sessions are inserted; a date that is already complete costs one indexed read |
### Result (17 Oct 2026)

`make lint typecheck test` on the Linux clone: ruff, format, import-linter (4 contracts kept) and
mypy (129 files) clean; API **911 tests** (64 new: domain, HTTP on PostgreSQL, contract, tenancy,
migration, seed) at 99.08% package and 99% `domain/` + `application/` coverage; web 31 files and
314 tests, ESLint and tsc clean against the regenerated types; the contract validates (0.9.0) and
`gen:api:check` is clean. `make up` rebuilt both images and applied `0007` to the existing local
database; `make seed` gave both seeded doctors their Monday-Saturday schedule; `make smoke` passed.

The verify steps on the stack, as the sample clinic's owner, for the Monday ten days ahead:
- The seeded schedule (6 blocks, TOKENS) generated one session at 04:30 UTC with 12 places and
  token 1.
- Replacing it with 23:00-01:00 returned `overnight: true` and `kept_sessions: []`. The Monday's
  10:00 session was gone, and the new one ran 17:30-19:30 UTC, still dated Monday (AC5).
- 13:00-10:00 was `422 SCH_INVALID_BLOCK` (index 0, the 12-hour reason). Sunday 22:00-02:00 with
  Monday 01:00-05:00 was `409 SCH_OVERLAP` (blocks 0 and 1).
- A leave on that Monday left it with no sessions.
- The front desk's PUT was `403 PERM_DENIED`, while the front desk could still read sessions.
- The audit rows hold counts, kinds, dates and the doctor ID, never the note.

The demo schedule was put back afterwards.

The developer's three refinements are each proved by a test:
- The 12-hour bound: `test_r14_a_daytime_inversion_is_refused_and_a_night_shift_accepted`.
- Cross-day overlap: `test_r15_d7_an_overnight_block_cannot_spill_into_the_next_mornings_block`,
  `test_r15_an_extra_cannot_overlap_the_previous_nights_block` and the week-circle domain tests.
- Leave on generated dates:
  `test_r17_leave_on_a_generated_date_removes_unbooked_and_keeps_booked_sessions`. Bookings are
  stood in for by setting `booked_count`, until P2 books for real.

Concurrent generation: two clients reading one new date at once leave exactly the two planned
sessions (`test_r1_two_screens_reading_one_new_date_create_one_set`).

Taken while implementing:
- The new session schema is `DoctorSession` in the contract, because `Session` already names the
  sign-in session.
- A multi-row `INSERT ... ON CONFLICT` reports `rowcount` as -1 through psycopg, so the generator
  counts the rows from `RETURNING` instead.
- `TenantScopedRepository` gained `_delete_row` (scoped by clinic, `NotFound` otherwise), the first
  tenant delete.
- The booking-mode change lives in `UpdateClinic` with the other clinic settings, and is audited
  as `clinic.updated` with the field name.
- Slots carry only their times in P1; availability per slot arrives with bookings in P2.


---

## M3-P2 — Booking, reschedule and cancel

**Status: approved by the developer 17 Oct 2026 with 1A–7A (spec D10–D16); implemented and accepted the same day (result at the end of this section).** The recommended
options, marked **(rec.)**, are the ones chosen. Covers FR-APT-03 (API side), FR-APT-04, FR-APT-05, FR-APT-07; spec R3–R8, AC1, AC2.

### Concepts

1. **An appointment attaches to a session.** In slot mode it holds one `slot_start`; in token mode
   it takes the session's `next_token`, which only ever goes up (R4, AC2).
2. **One lock order for everything that touches a session.** Booking, cancel and reschedule lock
   the doctor row `FOR SHARE` (the lock generation already takes), then the session row
   `FOR UPDATE`. A schedule change holds the doctor `FOR UPDATE`, so it can never delete a session
   whose `booked_count` is being raised (R20). Reschedule locks its two doctors in ID order, then its
   two sessions in ID order, so two crossing reschedules cannot deadlock.
3. **The database is the last word.** The row lock serialises bookings. The partial unique indexes
   and `booked_count <= capacity` stop a double booking even if the code were wrong (FR-APT-04).
4. **Cancel frees the place, never the token.** Cancelling lowers `booked_count` and frees the slot
   for another booking. `next_token` is unchanged (AC2).
5. **History is rows, not overwrites.** Every status change appends to `appointment_status_history`,
   and a reschedule is a cancelled appointment plus a new one pointing at it (R8, FR-APT-05).

### Decisions for you

| # | Question | Options |
|---|---|---|
| 1 | Sessions P1 kept because they were booked, but that no longer match the rules (leave, a changed block) | **A (rec.)** Reconcile marks them `CLOSED`: existing bookings stay and can be cancelled or rescheduled away, new bookings get `409 APT_SESSION_CLOSED`, and a later change that matches them again reopens them. **B** Leave them `OPEN`, so a leave day still accepts bookings. |
| 2 | A booked session whose block changed only in capacity (e.g. 12 → 20 tokens tomorrow) | **A (rec.)** Adjust it in place when the start, end, mode and slot length are unchanged and the new capacity ≥ `booked_count`; otherwise close it as in 1A. **B** Always close it, so the extra places appear only after its bookings are moved. |
| 3 | Until when can a session be booked? | **A (rec.)** Token mode: until the session ends (desks hand out tokens during the session). Slot mode: until the slot ends. Earlier → `422 APT_IN_PAST`. **B** Only before the session or slot starts. |
| 4 | The same patient twice in one session | **A (rec.)** Refused: `409 APT_ALREADY_BOOKED` with the existing appointment's ID, backed by a partial unique index. This also covers a double-click. The same patient with two doctors on one day is allowed. **B** Allowed. |
| 5 | Cancel reasons (R7) | **A (rec.)** The enum `PATIENT_REQUEST`, `CLINIC_REQUEST`, `DOCTOR_UNAVAILABLE`, `DUPLICATE`, `OTHER`, plus an optional note of up to 200 characters (`OTHER` needs the note). `RESCHEDULED` is set only by reschedule. Allowed from `BOOKED` and `ARRIVED` until the session ends; after that the right status is `NO_SHOW` (P3) → `409 APT_NOT_MODIFIABLE`. **B** Free text only. |
| 6 | Reschedule scope | **A (rec.)** From `BOOKED` only, to any open session of the clinic, including another doctor's or the same session's other slot. The source carries over, and a `CLOSED` source session is fine, since 1A relies on it. **B** The same doctor only. |
| 7 | Booking confirmation (R5 says a `send_booking_confirmation` job "if consented") | **A (rec.)** Deferred to M5, where the jobs table and the messaging port arrive. The spec gains "from M5", and P2 writes no job. **B** Add the jobs table now. |

Fixed by the spec rather than asked:
- Staff choose the source from `FRONT_DESK` (the default), `PHONE` or `WHATSAPP`. `WALK_IN` comes
  with P3's walk-in route, and `PUBLIC_PAGE` with the public booking page (FR-APT-07).
- Opted-out patients can still be booked, because opt-out affects only messages.
- Every role books (`APPOINTMENTS_MANAGE`, spec §2).

### Data (migration `0008`, expand-only)

| Table | Columns (tenant tables carry `clinic_id` + FK) | Constraints |
|---|---|---|
| `appointments` | `session_id`, `doctor_id`, `patient_id`, `slot_start timestamptz null`, `token_number smallint null`, `status`, `source`, `reason text null`, `cancel_reason null`, `cancel_note null`, `cancelled_at null`, `rescheduled_from_id null` (self FK), `arrived_at`, `started_at`, `completed_at` (P3), `created_by`, timestamps | exactly one of `slot_start` / `token_number`; partial unique `(session_id, slot_start) WHERE status <> 'CANCELLED'`; unique `(session_id, token_number)` (never reused); partial unique `(session_id, patient_id) WHERE status <> 'CANCELLED'` (4A); `cancel_reason` set ⇔ `CANCELLED`; indexes `(clinic_id, doctor_id, status)`, `(clinic_id, patient_id, created_at desc)` |
| `appointment_status_history` | `appointment_id`, `from_status null`, `to_status`, `changed_by`, `changed_at`, `request_id` | append-only, like `audit_events` |

`reason` is a short non-clinical note of up to 120 characters ("follow-up"). The screen says so,
and it never appears in logs, audit rows or messages.

### API (contract 0.10.0)

| Method | Path | Behaviour |
|---|---|---|
| POST | `/api/v1/appointments` | `{session_id, patient_id, slot_start?, source?, reason?}`. `slot_start` is required in slot mode and refused in token mode. Returns 201 with the appointment, including its `token_number` or `slot_start` (R5, R6) |
| GET | `/api/v1/appointments/{id}` | One appointment with its status history |
| GET | `/api/v1/patients/{id}/appointments` | The patient's appointments, newest first, paginated like the patient list (FR-APT-05 history) |
| POST | `/api/v1/appointments/{id}/cancel` | `{reason, note?}` (R7) |
| POST | `/api/v1/appointments/{id}/reschedule` | `{session_id, slot_start?}`. Returns 201 with the new appointment, which carries `rescheduled_from_id` (R8) |
| GET | `/api/v1/sessions` | Unchanged route. Each slot gains `available`, and each session its `status` (`CLOSED` per 1A) |

All routes need `APPOINTMENTS_MANAGE`; an appointment, session or patient from another clinic is
404.

New error code: `APT_ALREADY_BOOKED` (409). P2 starts raising the codes ERRORS.md already lists:
`APT_SLOT_TAKEN`, `APT_SESSION_FULL`, `APT_SESSION_CLOSED`, `APT_OUTSIDE_SCHEDULE` (a `slot_start`
off the session's grid), `APT_IN_PAST` and `APT_NOT_MODIFIABLE`.

Audit rows:
- `appointment.booked`, `appointment.cancelled` and `appointment.rescheduled`.
- Entity: the appointment.
- Metadata: session, doctor, patient ID, mode, token or slot, source and cancel reason.
- Never the patient's name, the `reason` or the `cancel_note`.

### Files

| Layer | Files |
|---|---|
| Domain | `appointments/{appointment,errors,status}.py` (booking against a `Session`, cancel, reschedule); `scheduling/sessions.py` (`book`/`release` on `Session`; reconcile closes, reopens and adjusts per 1A/2A); `audit/actions.py` (+3) |
| Ports / adapters | `AppointmentRepository`, `AppointmentHistoryRepository`; `SessionRepository.get(…, lock=)` and `update`; models, repositories, unit of work; migration `0008` |
| Application | `appointments/{book,cancel,reschedule,queries,views}.py` |
| Delivery | `http/appointments.py` (new blueprint), `http/patients.py` (history route), `bodies.py`, `errors.py`, `bootstrap.py` |
| Contract / docs | `openapi.yaml` 0.10.0 + web types; `API.md`, `ERRORS.md`, `DATA_MODEL.md`, `RUNBOOK.md` (§1 seed note if bookings are seeded), CHANGELOG; spec R5 "from M5" (7A) |
| Seed | none: bookings are made by hand on the seeded schedule |

### Tests

- **Domain:**
  - Slot grid alignment; full and taken detection; the token sequence across cancellations (AC2).
  - The past and in-session rules (3A).
  - Cancel and reschedule from each status.
  - The reconcile close, reopen and adjust rules (1A, 2A).
- **PostgreSQL:**
  - AC1: capacity 1 and two threads booking at once give exactly one 201 and one 409, and
    `booked_count = 1`, in slot and in token mode.
  - Twenty threads booking a 12-token session end with 12 bookings, tokens 1–12 and no gaps.
  - A booking racing a schedule change: either the booking wins and the session is kept, or the
    change wins and the booking gets 404 or `APT_SESSION_CLOSED`. A booking is never lost.
  - Two crossing reschedules finish without deadlock.
  - The constraints refuse bad rows; the migration runs up and down.
- **HTTP:**
  - Every route and error code.
  - A leave after a booking closes the session, so a second booking there is refused.
  - Rescheduling out of a closed session; the patient history route.
  - Audit rows without names.
- **Tenancy:** the new tables in the repository guard and the new routes in the HTTP guard.
- **Contract:** every operation.

### Verify

```bash
make up && make seed
# as desk@sample-clinic.example, a seeded TOKENS session next Monday, Asha Rao's patient id:
#   POST /api/v1/appointments {session_id, patient_id}            -> 201, token_number 1
#   the same again                                                 -> 409 APT_ALREADY_BOOKED
#   book two more patients, cancel the second, book a fourth      -> token 4 (AC2)
#   as owner: leave on that Monday                                 -> kept_sessions lists it;
#   GET /sessions shows it CLOSED; a new booking there             -> 409 APT_SESSION_CLOSED
#   POST /appointments/{id}/reschedule to Tuesday's session        -> 201, rescheduled_from_id set
make lint typecheck test && make smoke && make e2e
```

### Risks

| Risk | Mitigation |
|---|---|
| Deadlocks between booking, reschedule and schedule changes | One lock order (doctor, then session, each set in ID order); a crossing-reschedule test |
| A schedule change deleting a session mid-booking | The booking holds the doctor `FOR SHARE`, and deletion needs `FOR UPDATE` plus `booked_count = 0` |
| `booked_count` drifting from the real number of appointments | It changes only in the same transaction as the appointment row; a test compares it with a `COUNT(*)` after the concurrency runs |
| Clinical text in `reason` | 120-character cap, a UI hint, and never logged, audited or messaged |
### Result (17 Oct 2026)

`make lint typecheck test` on the Linux clone: ruff, format, import-linter (4 contracts kept) and
mypy (142 files) clean; API **967 tests** (56 new) at 99.11% package coverage; web lint, tsc and
tests clean against the regenerated types; contract 0.10.0 validates and `contract-check` is
clean. `make up` applied `0008` to the existing local database and `make smoke` passed.

Concurrency, on PostgreSQL with real threads:
- AC1 in token and slot mode: two parallel bookings of the last place or slot give one 201 and
  one 409, and `booked_count = 1`.
- Fifteen parallel bookings of a 12-token session: twelve win, tokens 1–12 with no gaps.
- A booking racing a schedule change: either it wins and the session is kept `CLOSED`, or the
  change wins and the booking gets 404. Two crossing reschedules finish without deadlock.
- After each, `booked_count` equals the session's active appointments. The race tests passed
  30 runs in a row.

The verify steps on the stack, as the sample clinic's front desk and owner: tokens 1, 2, 3; the
same patient again `409 APT_ALREADY_BOOKED`; cancel the second and the next booking gets token 4
(AC2); a leave on that Monday kept the session `CLOSED` with its 3 bookings and refused a new one
(`409 APT_SESSION_CLOSED`); rescheduling out of it to Tuesday returned 201 with
`rescheduled_from_id`. Audit rows held IDs, mode, token and source only. The demo data was put
back afterwards.

Taken while implementing:
- A session that no longer matches the rules, has no bookings, but is referenced by cancelled
  appointments cannot be deleted (foreign key), so it is **retired**: status `CANCELLED`, hidden
  from listing, and revived in place if the rules plan it again, its `next_token` carrying on.
- A booking that waited on the doctor lock while a schedule change deleted its (unbooked) session
  answers 404, found by the race test on its fourth run.
- Reschedule checks the status (`BOOKED` only) before "already there", so a cancelled
  appointment gets `APT_NOT_MODIFIABLE` rather than a validation error.
- The patient appointment list is capped at 50 and has no cursor yet, like the patient lookup.


---

## M3-P3 — Queue transitions, walk-ins and the day's queue

**Status: designed 17 Oct 2026; the developer approved the recommended options in advance
("I accept every design with your recommendation"), recorded as spec D17–D22.** Covers FR-QUE-01,
FR-QUE-02, FR-QUE-04; spec R9–R11, AC3. FR-QUE-05 (opening the visit) waits for M4 (R13); the
live refresh (ETag, 304) is P4.

### Concepts

1. **The state machine is the domain's.** `BOOKED → ARRIVED | NO_SHOW`, `ARRIVED →
   IN_CONSULTATION | NO_SHOW`, `IN_CONSULTATION → COMPLETED`, `NO_SHOW → ARRIVED` (late arrival).
   Cancel stays its own route (P2). Anything else is `409 QUE_INVALID_TRANSITION` with
   `details.from` and `details.to` (R9, AC3). Entering a state sets its timestamp.
2. **A stale screen cannot move the wrong patient.** The request says which status it saw
   (`from`); if the appointment has moved since, the answer is `QUE_INVALID_TRANSITION` with the
   real `from`. Without it, a tab still showing `BOOKED` could mark a patient who has already
   arrived as a no-show.
3. **The queue moves on the day.** Transitions happen on the session's clinic-local date (or while
   an overnight session is still running). A no-show needs the session (token) or the slot to have
   started.
4. **A walk-in is a booking that has already arrived.** It takes the next token, or in slot mode
   the earliest free slot that has not ended (no overbooking, D6), with source `WALK_IN`, and is
   `ARRIVED` at once. It uses the same lock order and checks as P2.

### Decisions (recommended options, approved in advance)

| # | Question | Chosen |
|---|---|---|
| D17 | Who moves the queue | Every role, with `QUEUE_MOVE` (spec §2); the history and audit say who. M4 may restrict `IN_CONSULTATION` once it opens a visit |
| D18 | Guarding against stale screens | `{from, to}` both required; `from` must equal the current status |
| D19 | When the queue may move | On the session's clinic-local date, or until an overnight session ends (`409 QUE_WRONG_TIME`, `reason: not_today`); `NO_SHOW` once the session (token) or slot (slot mode) has started (`reason: not_started`) |
| D20 | Undoing a mistaken transition | None in M3; a mistaken arrival can be marked no-show and back, or cancelled |
| D21 | Which session a walk-in joins | The doctor's open session running now, else the next one to start today; `session_id` may name another of today's. None: `409 QUE_NO_SESSION` |
| D22 | The day's queue read | In P3: `GET /api/v1/queue?date=&doctor_id=` without caching headers; P4 adds the strong `ETag` and 304 |

A `NO_SHOW` keeps its place (token or slot), because a late arrival returns to it.

### Data

No migration: `appointments` already has `arrived_at`, `started_at`, `completed_at`, and history
rows are appended as in P2. `PatientRepository.get_many` reads the queue's patients in one query.

### API (contract 0.11.0)

| Method | Path | Permission | Behaviour |
|---|---|---|---|
| POST | `/api/v1/appointments/{id}/transitions` | `QUEUE_MOVE` | `{from, to}`; 200 with the appointment; audited `appointment.status_changed` |
| POST | `/api/v1/queue/walk-ins` | `QUEUE_MOVE` | `{doctor_id, patient_id, session_id?, slot_start?, reason?}`; 201 with the appointment, `ARRIVED`, source `WALK_IN`; audited `appointment.booked` |
| GET | `/api/v1/queue?date=&doctor_id=` | `APPOINTMENTS_MANAGE` | The date's sessions (generated as `GET /sessions` does), each with its active appointments by token or slot: patient code, name and age, status, timestamps and `wait_minutes` while arrived. `date` defaults to the clinic's today; `include_cancelled=true` adds cancelled ones |

New codes: `QUE_WRONG_TIME` (409), `QUE_NO_SESSION` (409); `QUE_INVALID_TRANSITION` is now
raised.

### Tests

- **Domain:** every allowed and refused transition (AC3: `COMPLETED → ARRIVED`), the stale `from`,
  timestamps, late arrival the same day only, the day window including overnight sessions, the
  no-show start rule, walk-in slot choice.
- **HTTP on PostgreSQL:** each route and error; two tabs making the same transition (one 200, one
  409); a walk-in in token and slot mode and when full; session choice (running, next, none);
  the queue's order, wait times and that it hides cancelled appointments; permissions; audit rows
  without names.
- **Tenancy:** the transitions route in the cross-tenant guard; another clinic's doctor or patient
  is 404 for a walk-in; `PatientRepository.get_many` scoped.
- **Contract:** every new operation.

### Verify

```bash
make up && make seed
# as desk@sample-clinic.example on a day with a seeded session (Monday-Saturday):
#   POST /api/v1/queue/walk-ins {doctor_id, patient_id}            -> 201, ARRIVED, WALK_IN, token n
#   POST /appointments/{id}/transitions {from: ARRIVED, to: IN_CONSULTATION} -> 200, started_at set
#   the same again                                                  -> 409 QUE_INVALID_TRANSITION
#   {from: IN_CONSULTATION, to: COMPLETED}, then {from: COMPLETED, to: ARRIVED} -> 409 (AC3)
#   GET /api/v1/queue                                               -> today's sessions in token order
#   a transition on next week's appointment                         -> 409 QUE_WRONG_TIME
make lint typecheck test && make smoke
```

### Risks

| Risk | Mitigation |
|---|---|
| Two screens moving one patient | The appointment row is locked `FOR UPDATE` and `from` must match |
| Wrong-day transitions from an old tab | The day window (D19), from the clinic's zone, never the server's |
| A walk-in overbooking slot mode | The same session lock and capacity check as a booking; full is `APT_SESSION_FULL` |
| Names leaking from the queue | Names are in the response only (staff need them); logs and audit carry IDs |
### Result (17 Oct 2026)

`make lint typecheck test` on the Linux clone: ruff, format, import-linter (4 contracts kept) and
mypy (144 files) clean; API **1024 tests** (57 new) at 98.94% package coverage; contract 0.11.0
validates, the web types are regenerated and `contract-check` is clean. `make up`, `make seed` and
`make smoke` passed on the rebuilt stack.

The verify steps on the stack, as the sample clinic's front desk, with an extra session running
now (20:30–21:15 on Saturday 17 Oct): a walk-in came back `201 ARRIVED WALK_IN` with token 1;
`ARRIVED → IN_CONSULTATION` set `started_at`; repeating it was `409 QUE_INVALID_TRANSITION` with
the real `from: IN_CONSULTATION`; `COMPLETED → ARRIVED` was `409 QUE_INVALID_TRANSITION` (AC3); the
queue listed the patient by code with status `COMPLETED`; moving Monday's booking today was
`409 QUE_WRONG_TIME` (`not_today`). The audit row held from, to, session and doctor IDs only. The
Monday booking was cancelled afterwards; the completed walk-in and its extra session remain in
the local demo data as today's history.

Two tabs making the same move at once: one 200, one 409 whose `from` is the winner's status
(`test_d18_two_tabs_making_the_same_move_one_wins`).

Taken while implementing:
- The permission is the existing `QUEUE_MOVE` (the design said `QUE_MOVE`; corrected in the notes
  and the spec).
- Tests of today's queue add an extra session running now (`tests/sessions_now.py`), because the
  app runs on the system clock and a fixed weekly block may already have ended.
- A walk-in records two history rows (`→ BOOKED`, `BOOKED → ARRIVED`) and one `appointment.booked`
  audit row with source `WALK_IN`.
- The session list and the queue share one generate-and-list step (`sessions_for_date`).


---

## M3-P4 — Live queue (ETag polling)

**Status: approved by the developer 17 Oct 2026 with 1A–4A (spec D23–D26).** The recommended
options, marked **(rec.)**, are the ones chosen. Covers FR-QUE-03 (API side and the client polling module); spec R12. AC4 (two browsers
within 5 s) is proved end to end by P5's Playwright journey on the queue board.

### Concepts

1. **Poll cheaply, not push.** Every open queue screen asks `GET /api/v1/queue` every 5 seconds
   with `If-None-Match: <last ETag>`. Unchanged → `304 Not Modified` with no body; changed → 200
   with the queue and a new `ETag`. No websockets, no new infrastructure (R12).
2. **A strong ETag means byte-identical.** The tag must change whenever any byte of the body would,
   including a patient's corrected name and the minute-by-minute `wait_minutes`. Otherwise a
   screen would keep a stale row for ever.
3. **Same filters, same tag.** The tag covers the response for one `date`, `doctor_id` and
   `include_cancelled`, so two screens on different doctors never confuse each other's tags.
4. **Privacy stays as it is.** The queue holds names, so it remains `Cache-Control: no-store`:
   browsers and proxies keep no copy. The client holds the last body in memory and sends the tag
   itself.

### Decisions for you

| # | Question | Options |
|---|---|---|
| 1 | How the ETag is computed | **A (rec.)** SHA-256 of the serialised JSON body (first 32 hex characters, quoted). Correct by construction: anything in the body is in the tag. The queries still run on every poll (a few indexed reads per screen every 5 s, measured in the tests). **B** A version tuple from `max(updated_at)` and counts of sessions, appointments and patients: cheaper, but every new field must be remembered in the tuple, and `wait_minutes` would need a minute bucket. |
| 2 | `wait_minutes` changing every minute | **A (rec.)** Keep it in the body: an arrived patient makes the tag change at most once a minute, so a screen gets at most one 200 a minute while patients wait. **B** Drop it and let the screen count from `arrived_at` (a contract change). |
| 3 | Where the polling lives on the web side | **A (rec.)** A small `lib/api/poll.ts` (`pollQueue`) and a `useQueue` hook in `features/queue/`: polls every 5 s with `If-None-Match`, keeps the last body on 304, pauses while the tab is hidden and polls at once when it comes back, backs off to 30 s after errors. Unit-tested with fake timers; P5 builds the board on it. **B** Leave all web work to P5. |
| 4 | Other polled reads | **A (rec.)** Only the queue in M3. `GET /sessions` stays without a tag. **B** The same ETag on `GET /sessions`. |

Fixed rather than asked:
- `If-None-Match: *` and lists of tags are honoured as HTTP says; a weak tag (`W/"..."`) never
  matches, since the tag is strong.
- The web proxy (`next.config` rewrites) passes `ETag` and `If-None-Match` through; P4 checks this
  through the web origin in `make smoke`.

### API (contract 0.12.0)

| Method | Path | Change |
|---|---|---|
| GET | `/api/v1/queue` | Adds `ETag` to 200; takes `If-None-Match`; answers `304` with `ETag`, `Cache-Control: no-store`, `X-Request-ID` and no body when it matches |

No new error codes, no migration, no new permission.

### Files

| Layer | Files |
|---|---|
| Delivery | `delivery/http/etag.py` (strong tag of a body, `If-None-Match` matching), `delivery/http/appointments.py` (`get_queue`) |
| Contract / docs | `openapi.yaml` 0.12.0 + web types; `API.md` (polling), `ARCHITECTURE.md` (request flow note), `DEBUGGING.md` ("the queue does not refresh"), CHANGELOG |
| Web (3A) | `lib/api/poll.ts`, `features/queue/useQueue.ts`, their tests |
| Smoke | `scripts/smoke.sh`: a conditional `GET /api/v1/queue` through the web origin returns 304 |

### Tests

- **Unit:** tag stability (same body, same tag), quoting, `If-None-Match` parsing (`*`, lists, weak
  tags never match).
- **HTTP on PostgreSQL:** 200 with `ETag`; the same request with it → 304, empty body, headers kept;
  the tag changes after a booking, a transition, a cancel, a patient's name correction and, for an
  arrived patient, a minute later (clock moved); different filters give different tags; another
  clinic's tag never matches (it is computed from this clinic's body).
- **Contract:** 200 and 304 against `openapi.yaml`.
- **Web:** polling cadence, 304 keeps the data, hidden tab pauses, error back-off.

### Verify

```bash
make up && make seed
# as desk@sample-clinic.example:
#   curl -i .../api/v1/queue                                  -> 200, ETag: "…"
#   curl -i -H 'If-None-Match: "…"' .../api/v1/queue          -> 304, no body
#   add a walk-in, then the same conditional request          -> 200, a new ETag
#   the same through http://localhost:3000 (the web origin)   -> 304 too
make lint typecheck test && make smoke
```

### Risks

| Risk | Mitigation |
|---|---|
| Polling load | 5 s per open screen; a 304 is a few indexed reads and no body; the tests count queries per poll |
| A stale screen | The tag is the body's hash, so any visible change changes it |
| The proxy dropping the headers | `make smoke` checks a 304 through the web origin |
| Names in a cache | `no-store` stays; the client keeps the body in memory only |
### Result (17 Oct 2026)

`make lint typecheck test` on the Linux clone: ruff, format, import-linter (4 contracts kept) and
mypy (145 files) clean; API **1037 tests** (13 new) at 98.99% package coverage; web ESLint and tsc
clean and the web suite green, with 8 new tests (`poll.test.ts`, `useQueue.test.tsx`, two in
`client.test.ts`); contract 0.12.0 validates and `contract-check` is clean. `make up`, `make seed`,
`make smoke` (now also: `/api/v1/queue` stays 401 without a session, even with `If-None-Match: *`)
and `make e2e` (2 journeys, the new `live-queue-etag.spec.ts` included) passed on the rebuilt
stack.

The verify steps by hand, as the sample clinic's front desk: the queue answered 200 with a
32-hex-character `ETag`; the same request with it was 304 with an empty body, directly on :8000
and through the web origin on :3000; after a walk-in the old tag got 200 and a new tag. The walk-in
joined the extra session left by P3's check and remains in the local demo data.

Taken while implementing:
- `If-None-Match` is compared **weakly**, as RFC 9110 §13.1.2 requires, so `W/"tag"` matches too.
  The design said a weak tag "never matches"; that was wrong and is not what was built.
- The design's risk table said the tests count queries per poll. They do not: a 304 still runs the
  queue's queries (D23 accepts this). Measuring the load belongs to the pilot's monitoring, not a
  unit test.
- `make smoke` runs before `make seed` in CI, so the authenticated 304 through the web origin is
  checked by Playwright (`e2e/live-queue-etag.spec.ts`), which runs after the seed; smoke checks
  the anonymous case.
- `useQueue` keys its state by the filters, so a screen never shows one doctor's queue under
  another's filter; React's lint forbids resetting state inside the effect.


---

## M3-P5 — Screens: queue board, booking, schedule settings

**Status: approved by the developer 17 Oct 2026 with 1A–6A (spec D27–D32).** The recommended options,
marked **(rec.)**, are the ones chosen. Covers FR-APT-03 (≤ 3 interactions, AC6), FR-QUE-01, FR-QUE-03 (AC4 in two browsers),
FR-QUE-04 and the screens for FR-APT-01, FR-APT-05; spec §6 UI notes. Web only: the API is done.
It closes M3, so its last commit carries `Closes #36`.

### Concepts

1. **The queue is the front desk's home page.** `/queue` is already where every role lands. It
   becomes the live board: one doctor's day, rows in token or slot order, each with the patient's
   code, name, age, status and wait, built on `useQueue` (P4). A change made on one screen shows on
   the others within 5 seconds (AC4).
2. **Single clicks for the common path, a menu for the rest** (spec §6). Each row shows the one
   next step as a button: *Arrived*, *Start*, *Complete*. *No-show*, *Cancel* and *Reschedule* sit
   in a row menu. Every action sends the status the row showed (`{from, to}`, D18); a 409 because
   another screen moved first refreshes the row and says so.
3. **Booking in three interactions** (AC6), from the board: *Book* opens a drawer with the patient
   search focused → (1) pick the patient → (2) pick a slot (slot mode; the earliest free one is
   preselected) or accept the next token (token mode, preselected) → (3) *Confirm*. Typing in the
   search does not count as an interaction; the Playwright journey counts the clicks.
4. **Times in the clinic's zone, never the browser's** (apps/web/CLAUDE.md). One formatter
   (`lib/format/time.ts`) turns the API's UTC instants into the clinic's wall clock.
5. **Hiding is convenience, the API is the guard.** Buttons a role cannot use are not shown, but
   every refusal from the API is handled and shown with its message and request ID.

### Decisions for you

| # | Question | Options |
|---|---|---|
| 1 | Which doctor the board shows first | **A (rec.)** A doctor sees their own day; others see the doctor they last chose on this device (local storage), else the first active one; a doctor picker above the board. **B** Always the first doctor. **C** All doctors on one board. |
| 2 | Other dates on the board | **A (rec.)** Previous / next day and a date field. Other days are read-only for transitions (the API refuses them, D19), but booking, cancel and reschedule work on future days. **B** Today only; other days through booking only. |
| 3 | Confirming actions | **A (rec.)** *Arrived*, *Start*, *Complete* are one click (spec §6). *No-show* asks for confirmation, since there is no undo (D20); *Cancel* opens a dialog for the reason (D14); *Reschedule* opens the booking drawer on the target session. **B** Confirm every action. |
| 4 | Walk-ins | **A (rec.)** An *Add walk-in* button on today's board: the same patient search, then one click; the API picks the session and slot (D21). **B** Walk-ins through the booking drawer with source WALK_IN. |
| 5 | Schedule settings | **A (rec.)** `/settings/schedule` for owners (`SCHEDULES_MANAGE`): per doctor, a weekly list of blocks (add, edit, remove, then *Save* sends the whole week, R16), the upcoming leave and extra sessions (add, remove), and the clinic's booking mode (`CLINIC_MANAGE`). After any change, booked sessions the change kept are listed for the owner to reschedule (D4, D10). **B** The weekly blocks only; leave and extras stay API-only until M7. |
| 6 | A patient's appointments | **A (rec.)** A section on the patient profile listing their appointments (date, doctor, token or slot, status), with *Book* for that patient. **B** Not in M3. |

On 3A the developer asked whether *Arrived*, *Start* and *Complete* should also ask for
confirmation, since there is no undo, and left it to whether that is standard and better for the
user. It is not applied: confirmations are for rare, destructive actions; on the steps pressed
dozens of times a day they train people to click *Yes* without reading, which also weakens the
confirmations that matter (*No-show*). Spec §6 asks for single clicks, and the mistakes are
recoverable: a wrong arrival can be marked no-show (or cancelled), and a no-show who turns up is
marked arrived again. Mis-clicks are guarded instead by:
- one next-step button per row, whose accessible name includes the patient ("Mark Asha Rao
  arrived"), with space between rows;
- a status message after every action naming the patient, the new status and the time ("Asha Rao
  marked arrived at 10:42"), announced to screen readers, so a slip is seen at once;
- confirmation kept for *No-show*, and a reason required for *Cancel*.

Fixed rather than asked:
- English only in M3 (the i18n layer arrives later, as for patients).
- New shared primitives go in `components/` (a `Dialog`, a row `Menu`) with keyboard support and
  focus management; the 1366 × 768 front-desk screen is the design target.
- The nav gains *Schedule* for roles holding `SCHEDULES_MANAGE`.

### Files

| Area | Files |
|---|---|
| Board | `features/queue/{QueueBoard,QueueRow,DoctorPicker,DayNav,WalkInDialog}.tsx`, `features/queue/actions.ts`; `app/(clinic)/(workspace)/queue/page.tsx` (replaces `EmptyQueue`) |
| Booking | `features/appointments/{BookDrawer,SlotPicker,CancelDialog,RescheduleDrawer,PatientAppointments}.tsx`, `features/appointments/api.ts` |
| Schedule | `features/schedule/{ScheduleEditor,BlockRow,ExceptionsList,BookingModeSetting,KeptSessions}.tsx`; `app/(clinic)/(workspace)/settings/schedule/page.tsx`; `features/shell/nav.ts` |
| Shared | `components/{Dialog,Menu}.tsx`, `lib/format/time.ts` |
| E2E | `e2e/booking-three-interactions.spec.ts` (AC6), `e2e/queue-two-browsers.spec.ts` (AC4) |
| Docs | `docs/TESTING.md` (the journeys), `docs/RUNBOOK.md` §1 (what to try after `make seed`), M3 notes, CHANGELOG; the M3 exit criterion checked off |

### Tests

- **Component (Vitest + Testing Library):** board rows and the next-step button per status; a 409
  from another screen refreshing the row; the booking drawer's preselection in both modes; slot
  availability; cancel reasons (OTHER needs a note); walk-in errors (`QUE_NO_SESSION`); schedule
  editor validation messages from `SCH_*` codes and the kept-sessions list; clinic-zone time
  formatting at the Kolkata midnight edges; keyboard paths and focus return for dialogs and menus.
- **E2E (Playwright, seed data):** AC6 books in at most 3 interactions from the board; AC4 two
  browser contexts on the board, one marks *Arrived*, the other shows it within 5 s. Both create
  their own session for today (an extra session running now), so they pass at any hour.
- `make lint typecheck test`, `make smoke`, `make e2e`.

### Verify

```bash
make up && make seed
# Front desk (desk@sample-clinic.example) on http://localhost:3000/queue:
#   Book -> pick Asha Rao -> Confirm: token 1 on the board (3 interactions)
#   a second browser as the doctor: Arrived on one, the other shows it within 5 s
#   Start, Complete; No-show asks first; Cancel needs a reason
# Owner (owner@...) on /settings/schedule: change Monday's hours with a booking that day ->
#   the kept session is listed; add leave; switch booking mode
make lint typecheck test && make smoke && make e2e
```

### Risks

| Risk | Mitigation |
|---|---|
| Phase size (three screen areas) | Built and committed as three areas (board, booking, schedule), each with its tests; the phase is reported once |
| Time-zone mistakes in the browser | One formatter, given the clinic's zone; tested at both midnight edges, run with `TZ=America/New_York` in CI as the API is |
| Flaky timing in AC4 | The journey waits on the row's text with a 5-second timeout, not on sleeps |
| A stale row acting on the wrong status | `{from, to}` from the row; the 409 refreshes it |
### Result (17 Oct 2026)

Web only. `make lint typecheck` clean (ESLint, tsc); web suite **344 tests** in 36 files (new:
`QueueBoard.test.tsx` 8, `Booking.test.tsx` 5, `ScheduleSettings.test.tsx` 5, time formatting at
the Kolkata midnight edges, the nav). `make up`, `make seed`, `make smoke` passed, and `make e2e`
passed **4 journeys** three runs in a row on the same database: AC6 (Book → patient → Confirm, 3
interactions), AC4 (the doctor's board showed *Arrived* within one poll, under 6 s), the 304
through the web origin and the M2 patient journey. Screenshots of `/queue` and
`/settings/schedule` at 1366 × 768 were checked by eye.

The exit criterion is met: front desk books in ≤ 3 interactions (AC6); the concurrent
double-booking test passes (AC1, P2); the queue refreshes on every open screen within one 5-second
poll (AC4).

Taken while implementing:
- The safeguards for single-click steps are built as designed: the button names the patient
  ("Mark Asha Rao arrived"), a status message after each action says who, what and when, No-show
  asks first and Cancel needs a reason; a 409 from another screen refreshes the board and says
  who moved the patient.
- `useQueue` now refreshes an expired session like every other call and has `refresh()`, so the
  board asks again at once after an action instead of waiting for the next poll.
- The web client gained `apiDelete` / `sessionDelete` (removing an exception) and `useNow`, a
  minute clock: React's lint forbids reading the clock during render.
- AC4 is asserted at 6 s, not 5 s: the worst case is one 5-second interval plus the request.
- The seeded doctor works in both sample clinics, so the AC4 journey chooses *Sample Clinic* on
  the clinic chooser.
- The journeys leave extra sessions and synthetic patients in the local demo data.
