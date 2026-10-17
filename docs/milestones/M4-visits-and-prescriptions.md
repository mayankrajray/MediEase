# M4 — Visits and digital prescriptions: design notes

| Field | Value |
|---|---|
| Status | In progress — M4 opened 17 Oct 2026; the M4-P1 design approved the same day with 1A–6A, in implementation |
| Spec | `docs/specs/prescriptions.md` (Approved 2026-10-17, D1–D5) |
| ADR | ADR-0012 (in-house PDF rendering and blob storage behind ports) |
| Covers | FR-VIS-01..03, FR-VIS-05, FR-RX-01..10 |
| Issue / branch / PR | #38 · `m4/38-visits-and-prescriptions` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | A doctor issues a prescription from the queue; the PDF prints correctly; the patient link passes the 360-px acceptance test |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Visit record, history, 24-hour lock and addenda | Below (approved) |
| P2 | Prescription domain: items, instructions, versions, immutability, pending delivery (R14) | At its start |
| P3 | Favourites, templates, clinic-history autocomplete | At its start |
| P4 | `PdfRendererPort`, `BlobStoragePort`, render-once (R18, ADR-0012) | At its start |
| P5 | Patient links, last-4 challenge, bilingual page (R9–R13, R19, R20) | At its start |
| P6 | Web consultation screen, keyboard-first Rx builder | At its start |

---

## M4-P1 — Visit record, history, 24-hour lock and addenda

**Status: approved by the developer 17 Oct 2026 with 1A–6A (every recommendation); in implementation.** API only; the consultation screen is P6.
Covers FR-VIS-01, 02, 03, 05; spec R1–R3, R16, R17; AC6, AC7 (for visits), AC9.

### Concepts

1. **The visit hangs off the queue.** M3 already says who is with the doctor: the appointment in
   `IN_CONSULTATION`. A visit is the clinical record of that appointment, one per appointment
   (a unique index), owned by the session's doctor. The queue stays the single record of the day;
   the visit never moves the queue except when it completes (decision 2).
2. **Who writes, who reads.** Writing needs `CLINICAL_WRITE` **and** being the visit's doctor (the
   doctor row whose `user_id` is the caller). Reading needs `CLINICAL_VIEW`: every doctor and owner
   of the clinic, never front desk (spec §2). A front-desk call to a clinical route is `403
   PERM_DENIED`, from the permission matrix, before anything is loaded.
3. **The lock is time, not a job.** Completing sets `completed_at` and `locked_at = completed_at +
   24 h`. "Locked" is `now >= locked_at`, decided in the domain with the injected clock; nothing has
   to run at the 24-hour mark. Between completion and lock the doctor may still correct the record;
   after it, edits are `409 VIS_LOCKED` and only addenda are accepted (R3, AC6).
4. **Addenda are append-only.** An addendum has an author, a time and a body, and never changes:
   the domain has no update, and a database trigger refuses `UPDATE`, `DELETE` and `TRUNCATE` on
   `visit_addenda`, as `audit_events` does (M1-P4). Allowed on a completed visit, locked or not; an
   open visit is simply edited.
5. **Read audit at the view, not the row (R16).** The consultation screen's data comes from **one**
   call, `GET /api/v1/visits/{id}`, which returns the visit, its addenda and the patient's last 10
   visits; it writes one `visit.viewed` row. A patient's history list writes one
   `patient.visits_viewed`. Writes return the updated record, so saving never triggers a read row,
   and nothing clinical polls. Metadata: IDs and counts only.
6. **Clinical text never leaves the record (R17).** Logs and audit rows carry IDs, statuses and the
   *names* of changed fields. Validation errors name the field and the rule ("must be at most 5,000
   characters"), never echo the value. A sentinel test proves it end to end.
7. **Stale tabs cannot overwrite.** A doctor may have the visit open on two screens. Each visit has
   a `revision`; `PATCH` must send the revision it saw and gets `409 VIS_STALE` with the current one
   otherwise (decision 4), the same idea as M3's `{from, to}` transitions.

### Data (migration `0009`, expand-only)

| Table | Columns (all carry `clinic_id` + FK, composite FKs to the same clinic) | Constraints |
|---|---|---|
| `visits` | `id`, `patient_id`, `doctor_id`, `appointment_id`, `status`, `chief_complaint`, `findings`, `diagnosis`, `notes` (text null), `vitals jsonb not null default '{}'`, `revision integer not null default 1`, `started_at`, `completed_at null`, `locked_at null`, `created_by`, timestamps | `status IN (OPEN, COMPLETED)`; `UNIQUE (appointment_id)`; completed ⇔ `completed_at` and `locked_at` set; `locked_at = completed_at + 24 h` (CHECK); text lengths bounded; index `(clinic_id, patient_id, started_at DESC)` for history |
| `visit_addenda` | `id`, `visit_id`, `author_user_id`, `body text`, `created_at` | body 1–5,000 chars; index `(visit_id, created_at)`; append-only trigger `VIS_ADDENDUM_APPEND_ONLY` |
| `audit_events` | — | No change: the new actions are values of the existing `action` column |

Vitals are a closed set of optional numbers with units fixed by the key: `bp_systolic`,
`bp_diastolic` (mmHg), `pulse` (/min), `temp_c`, `weight_kg`, `height_cm`, `spo2` (%),
`resp_rate` (/min). Each has a bound that only catches typing errors (for example `temp_c` 25–45,
`spo2` 50–100); these are input checks, not clinical ranges, and nothing interprets the values.

`DATA_MODEL.md` already describes `visits` and `visit_addenda`; P1 adds `appointment_id` as
`not null`, `revision`, `started_at`, `created_by` and `resp_rate`.

### Domain and application

| Where | What |
|---|---|
| `domain/visits/visit.py` | `Visit.start(appointment, session, doctor, …)` (only `IN_CONSULTATION`, R1), `edit(changes, seen_revision, now)`, `complete(now)`, `is_locked(now)`, `add_addendum(…)`; returns the changed field names for audit |
| `domain/visits/vitals.py` | `Vitals` value object: the closed key set, units, input bounds |
| `domain/visits/errors.py` | `VisitAlreadyExists`, `VisitNotStartable`, `VisitLocked`, `VisitStale`, `VisitNotOpen`, `NotVisitDoctor` |
| `application/visits/` | `StartVisit`, `UpdateVisit`, `CompleteVisit`, `AddAddendum`, `GetConsultation` (visit + addenda + last 10, one audit row), `ListPatientVisits` (one audit row) |
| `ports/repositories.py` | `VisitRepository`, `VisitAddendumRepository` (tenancy-scoped, like every repository) |
| `adapters/db/` | models, repositories, wiring in `bootstrap.py` |
| `domain/audit/actions.py` | `visit.started`, `visit.updated`, `visit.completed`, `visit.addendum_added`, `visit.viewed`, `patient.visits_viewed` |
| `domain/identity/permissions.py` | No change: `CLINICAL_VIEW` and `CLINICAL_WRITE` exist since M1 |

Locking: `StartVisit` locks the appointment's session as M3 does, then the appointment, so a
*Start* racing a *Cancel* or a second *Start visit* serialise; the unique index is the backstop.
`UpdateVisit` and `AddAddendum` lock the visit row `FOR UPDATE`.

### API (contract 0.13.0)

| Method | Path | Permission | Behaviour |
|---|---|---|---|
| POST | `/api/v1/visits` | `CLINICAL_WRITE`, the session's doctor | `{appointment_id}` → 201 the visit; `409 VIS_ALREADY_EXISTS` with `visit_id` in `details`; `409 VIS_NOT_STARTABLE` unless `IN_CONSULTATION` |
| GET | `/api/v1/visits/{id}` | `CLINICAL_VIEW` | The consultation view: visit, addenda, `history` (the patient's previous 10 visits, newest first, summary fields); one `visit.viewed` |
| PATCH | `/api/v1/visits/{id}` | `CLINICAL_WRITE`, the visit's doctor | `{revision, chief_complaint?, findings?, diagnosis?, notes?, vitals?}`; `409 VIS_STALE`, `409 VIS_LOCKED` |
| POST | `/api/v1/visits/{id}/complete` | as PATCH | Completes the visit (decision 2); idempotent on a completed visit |
| POST | `/api/v1/visits/{id}/addenda` | `CLINICAL_WRITE`, the visit's doctor (decision 3) | `{body}` → 201; `409 VIS_NOT_COMPLETED` on an open visit |
| GET | `/api/v1/patients/{id}/visits?limit=&before=` | `CLINICAL_VIEW` | Newest first, keyset paging (default 10, max 50); one `patient.visits_viewed` |

New error codes in `ERRORS.md`: `VIS_NOT_STARTABLE`, `VIS_STALE`, `VIS_NOT_COMPLETED`,
`VIS_ADDENDUM_APPEND_ONLY` (database), and `VIS_NOT_YOURS` (403) for a doctor writing another
doctor's visit; `VIS_LOCKED` and `VIS_ALREADY_EXISTS` already exist there.

### Tests

- **Domain:** start only from `IN_CONSULTATION`; edit returns the changed field names; lock at
  exactly 24 h (23:59:59 editable, 24:00:00 locked); complete twice is a no-op; stale revision;
  vitals keys and bounds.
- **AC6:** a visit completed 25 hours ago: `PATCH` 409 `VIS_LOCKED`, addendum 201 (fake clock).
- **AC9 / R16:** one `visit.viewed` per `GET /visits/{id}` whatever the history length; none for
  `PATCH`, complete or addendum beyond their own action; one `patient.visits_viewed` per list.
- **AC7 for visits (R17):** sentinel strings in every text field and an addendum; assert absent
  from captured logs, every audit row's metadata, and error bodies of a too-long field.
- **PostgreSQL:** two concurrent `POST /visits` for one appointment: one 201, one 409; the addenda
  trigger refuses `UPDATE`/`DELETE`/`TRUNCATE`; the CHECKs hold.
- **Tenancy:** clinic B's doctor gets 404 for clinic A's visit and history; front desk 403 on every
  clinical route; an owner who is not a doctor reads but cannot write.
- **Contract:** new routes and schemas in `openapi.yaml`, `make contract-check` clean.

### Verify (on the rebuilt stack, with `make seed`)

1. Desk marks a patient arrived and starts them (M3); the doctor `POST /visits` → 201; a second
   call → 409 `VIS_ALREADY_EXISTS` with the same `visit_id`.
2. `PATCH` notes with the current revision → 200, revision + 1; again with the old one → 409
   `VIS_STALE`.
3. Front desk `GET /visits/{id}` → 403 `PERM_DENIED`. **Failure path.**
4. Complete; `psql`: `locked_at = completed_at + 24 h`. Set `locked_at` in the past via the test
   clock or `psql` on a local copy; `PATCH` → 409 `VIS_LOCKED`; addendum → 201.
5. `psql`: `UPDATE visit_addenda …` fails with `VIS_ADDENDUM_APPEND_ONLY`; `audit_events` has one
   `visit.viewed` per `GET` and no clinical text in `metadata`.

### Decisions for approval

| # | Question | Options | Recommendation |
|---|---|---|---|
| 1 | How does a visit start? | **A** an explicit `POST /visits` by the doctor after *Start* (P6 does both in one click) · **B** the queue's *Start* creates the visit in the same transaction | **A**: *Start* is a queue move anyone may make (`QUEUE_MOVE`), creating a clinical record is not; M3 stays unchanged |
| 2 | What does completing do to the queue? | **A** completing the visit also moves its appointment `IN_CONSULTATION → COMPLETED` in the same transaction (if still there); completing from the queue leaves the visit open for the doctor to finish · **B** the two stay independent | **A**: one click for the doctor, and the board follows; the 24-hour lock starts only when the doctor completes |
| 3 | Who may add an addendum? | **A** the visit's doctor only · **B** any doctor of the clinic | **A**, matching "their own visits only" (§2); a colleague's correction is a new visit |
| 4 | Two tabs editing one visit | **A** `revision` with `409 VIS_STALE` · **B** last write wins | **A**: a lost clinical edit is silent and serious |
| 5 | Walk-ins (FR-VIS-01 "or directly") | **A** a walk-in goes through M3's *Add walk-in* first, so every visit has an appointment (`appointment_id not null`) · **B** allow visits with no appointment | **A**: walk-in already takes one interaction and puts the patient on the board; one path for history, PDFs and analytics |
| 6 | Database guard for the lock | **A** application only (domain + clock); trigger for addenda only · **B** also a trigger refusing clinical `UPDATE` after `locked_at` | **A**: the trigger would compare against the database clock, which the tests' fake clock cannot move; P2's prescription trigger has no such dependency (status, not time) |
