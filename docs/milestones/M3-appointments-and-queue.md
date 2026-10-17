# M3 — Appointments and daily queue: design notes

| Field | Value |
|---|---|
| Status | In progress — M3-P1 approved 17 Oct 2026 (1A–6A plus the developer's refinements) implemented and confirmed by the developer the same day; M3-P2 approved (1A–7A) and in implementation |
| Spec | `docs/specs/appointments-and-queue.md` (Approved 2026-10-17, D1–D16) |
| Covers | FR-APT-01..07, FR-QUE-01..05 |
| Issue / branch / PR | #36 · `m3/36-appointments-and-queue` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | Front desk books in ≤ 3 interactions; the concurrent double-booking test passes; the queue refreshes on every open screen within 5 s |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Doctor schedules, exceptions, sessions generated per clinic-local date; slot and token mode | Below |
| P2 | Booking, reschedule, cancel under a session row lock | Below (approved) |
| P3 | Queue state machine, transitions, walk-ins | Designed at its start |
| P4 | Live queue (ETag polling) | Designed at its start |
| P5 | Web: queue board, booking flow, schedule settings | Designed at its start |

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

**Status: approved by the developer 17 Oct 2026 with 1A–7A (spec D10–D16).** The recommended
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
