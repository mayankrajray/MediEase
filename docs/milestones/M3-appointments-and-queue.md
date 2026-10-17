# M3 — Appointments and daily queue: design notes

| Field | Value |
|---|---|
| Status | In progress — M3-P1 approved 17 Oct 2026 (1A–6A plus the developer's refinements) and in implementation |
| Spec | `docs/specs/appointments-and-queue.md` (Approved 2026-10-17, D1–D9) |
| Covers | FR-APT-01..07, FR-QUE-01..05 |
| Issue / branch / PR | #36 · `m3/36-appointments-and-queue` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | Front desk books in ≤ 3 interactions; the concurrent double-booking test passes; the queue refreshes on every open screen within 5 s |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Doctor schedules, exceptions, sessions generated per clinic-local date; slot and token mode | Below |
| P2 | Booking, reschedule, cancel under a session row lock | Designed at its start |
| P3 | Queue state machine, transitions, walk-ins | Designed at its start |
| P4 | Live queue (ETag polling) | Designed at its start |
| P5 | Web: queue board, booking flow, schedule settings | Designed at its start |

---

## M3-P1 — Doctor schedules, exceptions and sessions

**Status: approved by the developer 17 Oct 2026 with 1A–6A and three refinements** (a maximum block
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
