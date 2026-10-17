# M4 — Visits and digital prescriptions: design notes

| Field | Value |
|---|---|
| Status | In progress — M4 opened 17 Oct 2026; M4-P1 approved (1A–6A), implemented and confirmed by the developer the same day; M4-P2 approved (1A–6A), implemented and confirmed by the developer 18 Oct 2026; M4-P3 approved (1A–5A), implemented and confirmed by the developer 18 Oct 2026; M4-P4 approved (1A-5A) 18 Oct 2026, in implementation |
| Spec | `docs/specs/prescriptions.md` (Approved 2026-10-17, D1–D5) |
| ADR | ADR-0012 (in-house PDF rendering and blob storage behind ports) |
| Covers | FR-VIS-01..03, FR-VIS-05, FR-RX-01..10 |
| Issue / branch / PR | #38 · `m4/38-visits-and-prescriptions` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | A doctor issues a prescription from the queue; the PDF prints correctly; the patient link passes the 360-px acceptance test |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Visit record, history, 24-hour lock and addenda | Below (done, confirmed) |
| P2 | Prescription domain: items, instructions, versions, immutability, pending delivery (R14) | Below (done, confirmed) |
| P3 | Favourites, templates, clinic-history autocomplete | Below (done, confirmed) |
| P4 | `PdfRendererPort`, `BlobStoragePort`, render-once (R18, ADR-0012) | Below (approved 1A-5A) |
| P5 | Patient links, last-4 challenge, bilingual page (R9–R13, R19, R20) | At its start |
| P6 | Web consultation screen, keyboard-first Rx builder | At its start |

---

## M4-P1 — Visit record, history, 24-hour lock and addenda

**Status: approved by the developer 17 Oct 2026 with 1A–6A (every recommendation); implemented the same day (result at the end of this section) and confirmed by the developer.** API only; the consultation screen is P6.
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

### Result (17 Oct 2026)

API only, as designed. `make lint typecheck contract-check` clean (Ruff, import-linter 4/4,
mypy, ESLint, tsc, generated types current); `make test`: API **1078 tests** at 99.05% (41 more
than M3: domain rules, visits over HTTP on PostgreSQL, the contract, repository and HTTP tenancy
cases for the new routes, the migration), web 344. `make up` applied
`0009`; `make seed` and `make smoke` passed. The verify steps on the stack, as the seeded
doctor and front desk: start 201 and again 409 `VIS_ALREADY_EXISTS` with the same `visit_id`;
`PATCH` 200 (revision 2) and a stale one 409 `VIS_STALE`; front desk 403 `PERM_DENIED`; complete
200 with the appointment `COMPLETED` and `locked_at = completed_at + 24 h`; after moving the
completion 25 hours back, `PATCH` 409 `VIS_LOCKED` and an addendum 201; `UPDATE visit_addenda`
refused with `VIS_ADDENDUM_APPEND_ONLY`; the visit's audit rows `visit.started, visit.updated,
visit.completed, visit.viewed, visit.addendum_added` with no clinical text in any metadata.

Taken while implementing:
- `VIS_NOT_YOURS` is checked before "already exists", so starting someone else's visit does not
  reveal that one exists. A caller without an active doctor profile is never a visit's doctor.
- Completing on a later day than the session (D19) completes the visit but leaves the
  appointment where it is; the queue cannot move outside the session's day.
- Clinical cross-clinic cases run as each clinic's doctor (an owner would be refused with 403
  before the scope is reached); `GET /visits/{id}` and the history run as the owner, who reads.
- The history list pages by `before=<visit id>` (keyset on `started_at, id`), `next_before` in
  the response.
- The test reset lifts the addenda trigger the same deliberate way as `audit_events`.
- Not done here: the consultation screen and a visits section on the patient profile (P6);
  prescriptions in the history (P2).

---

## M4-P2 — Prescription domain: items, instructions, versions, immutability

**Status: approved by the developer 17 Oct 2026 with 1A–6A (every recommendation); implemented the same day (result at the end of this section) and confirmed by the developer.** API only; the builder screen is P6, the PDF
P4, the patient page P5. Covers FR-RX-01, 02, 03, 06 (the issue step), 09; spec R4–R6, R14,
R17, R20 (language at issue); AC1, AC4, AC7 (for prescriptions).

### Concepts

1. **A chain per visit.** A visit produces one prescription *chain*: version 1, then any
   revisions. Each version is its own row (`version`, `supersedes_id`), so an issued version is
   never touched again and the patient link (P5) can always resolve "the latest issued" (R11).
   At most one draft per chain at a time (decision 1).
2. **Draft → Issued → Superseded.** A draft is the doctor's working copy, saved whole with the
   revision it was made on (`RX_STALE`, as visits). Issuing freezes it: content, the doctor and
   clinic as printed (snapshots), the language the PDF and page will use, and the pending-delivery
   marker, all in one transaction (R5). Revising copies the latest issued version into a new
   draft; issuing that draft marks the old version `SUPERSEDED` (R6).
3. **Immutable twice over (AC1).** The domain refuses any change to a non-draft
   (`RX_NOT_DRAFT`); database triggers refuse it too, so even a direct SQL `UPDATE` of an issued
   version's content fails. The only columns that may still change after issue are operational:
   `status` to `SUPERSEDED`, `pdf_object_key` once (P4) and the delivery marker (R14, M5).
4. **Structured where it helps the patient, verbatim where it is the doctor's.** Frequency and
   timing are closed vocabularies (spec §3); preparation and storage are lists of phrase codes with
   an amount or a number of days. Everything else (medicine name, form, strength, dose, quantity,
   warnings, notes, advice) is free text, stored and later shown exactly as written (R20). Nothing
   validates a medicine or a dose: no drug data, ever (FR-RX-10, principle 6).
5. **Snapshots at issue.** The doctor's name, qualification, registration number and council, and
   the clinic's name, address and phone, are copied into the issued version. A later change to the
   doctor's profile or the clinic never alters a prescription already given to a patient (R8).
   Issuing refuses an incomplete doctor (`RX_DOCTOR_INCOMPLETE`, AC4). Since M1 the fields are
   required (invariant I3), so this guards blank or placeholder values and data imported or
   corrected outside the app.
6. **Language at issue (R20).** The prescription's `language` is the patient's preference when it is
   issued; the PDF is rendered once in it (P4). The patient page may still switch (R19, P5).
7. **Pending delivery (R14).** On issue: `link_delivery = PENDING` and
   `link_delivery_requested_at = issued_at` when the patient allows WhatsApp or SMS
   (`whatsapp_allowed`/`sms_allowed`, M2), else `NOT_CONSENTED`. Issuing a newer version moves the
   older one's `PENDING` to `SUPERSEDED`, so M5 only ever sees the latest. M5 adds `SENT` and
   `EXPIRED` (the 24-hour guard, R15); the CHECK lists them now so the column never needs widening.
8. **Same rules for reads and logs as visits.** Readers hold `CLINICAL_VIEW`; only the visit's
   doctor writes. One audit row per view; writes audited with counts, versions and field names,
   never item text (R16, R17).

### Data (migration `0010`, expand-only)

| Table | Columns (all carry `clinic_id`) | Constraints |
|---|---|---|
| `prescriptions` | `id`, `visit_id`, `patient_id`, `doctor_id`, `version smallint`, `supersedes_id null`, `status`, `revision integer`, `advice jsonb`, `follow_up_date date null`, `language null`, `issued_at null`, `doctor_snapshot jsonb null`, `clinic_snapshot jsonb null`, `pdf_object_key null`, `link_delivery null`, `link_delivery_requested_at null`, `created_by`, timestamps | `status IN (DRAFT, ISSUED, SUPERSEDED)`; `UNIQUE (visit_id, version)`; one draft per visit (partial unique index `WHERE status = 'DRAFT'`); issued ⇔ `issued_at`, `language`, both snapshots and `link_delivery` set; `version = 1` ⇔ `supersedes_id IS NULL`; `link_delivery IN (PENDING, NOT_CONSENTED, SUPERSEDED, SENT, EXPIRED)`; index `(clinic_id, patient_id, issued_at DESC)` |
| `prescription_items` | `id`, `prescription_id`, `position smallint`, `medicine_name`, `form`, `strength`, `dose`, `frequency`, `frequency_text`, `timing`, `duration_days`, `quantity`, `preparation jsonb`, `storage jsonb`, `warnings`, `notes` | `UNIQUE (prescription_id, position)`; `frequency` and `timing` CHECKs (spec §3); `CUSTOM` frequency ⇔ `frequency_text`; `duration_days` 1–365 or null; text length bounds |
| triggers | `prescriptions_immutable` (BEFORE UPDATE/DELETE), `prescription_items_frozen` (BEFORE INSERT/UPDATE/DELETE), TRUNCATE refused on both | Raise `RX_NOT_DRAFT` unless the row (or its parent) is a draft; after issue only the operational columns may change, each only in its allowed direction |

`DATA_MODEL.md` already sketches both tables; P2 adds `revision`, `clinic_snapshot`, the delivery
columns, `frequency_text`, and renames the item's `free_text` to `notes`.

Limits (they stop accidents, not doctors): 40 items; medicine name 200 characters; form,
strength, dose, quantity 100; warnings 500; item notes 1,000; up to 5 preparation and 4 storage
phrases per item; advice lists (`diet`, `activity`, `return_if`) up to 10 entries of 300
characters, advice notes 2,000; follow-up date after the issue date and at most a year ahead.

### Domain and application

| Where | What |
|---|---|
| `domain/prescriptions/vocabulary.py` | `Frequency`, `Timing`, `PreparationCode`, `StorageCode` enums and the phrase shapes (spec §3); no wording here (the phrasebook is P4/P5) |
| `domain/prescriptions/prescription.py` | `Prescription.draft_for(visit)`, `replace(body, seen_revision)`, `issue(doctor, clinic, patient_language, consent, now)`, `revise_from(issued)`, `supersede(by)`, `PrescriptionItem`, `Advice`, `DoctorSnapshot`, `ClinicSnapshot`, `LinkDelivery` |
| `domain/prescriptions/errors.py` | `RX_NOT_DRAFT`, `RX_EMPTY`, `RX_DOCTOR_INCOMPLETE`, `RX_STALE`, `RX_ALREADY_EXISTS`, `RX_DRAFT_EXISTS`, `RX_NOT_LATEST` |
| `application/prescriptions/` | `CreateDraft`, `ReplaceDraft`, `DiscardDraft`, `IssuePrescription`, `RevisePrescription`, `GetPrescription` (one `prescription.viewed`) |
| `application/visits/use_cases.py` | `GetConsultation` gains the visit's prescriptions and, per history visit, its latest issued version with item lines — still one read, one audit row (R2, R16) |
| `domain/audit/actions.py` | `prescription.created`, `.updated`, `.discarded`, `.issued`, `.revised`, `.viewed` |

Locking: every write locks the prescription row `FOR UPDATE`; issuing a revision also locks the
version it supersedes (older first, by version), so two issues in the same chain serialise.
Creating a draft locks the visit row, so two "new prescription" clicks make one.

### API (contract 0.14.0)

| Method | Path | Permission | Behaviour |
|---|---|---|---|
| POST | `/api/v1/visits/{id}/prescriptions` | `CLINICAL_WRITE`, the visit's doctor | An empty draft, version 1; `409 RX_ALREADY_EXISTS` (with its ID) when the visit has one; `409 VIS_LOCKED` on a locked visit |
| GET | `/api/v1/prescriptions/{id}` | `CLINICAL_VIEW` | The version with items, advice, snapshots, delivery state and the chain's versions; one `prescription.viewed` |
| PUT | `/api/v1/prescriptions/{id}` | as POST | `{revision, items, advice, follow_up_date}` replaces the draft; `409 RX_NOT_DRAFT`, `409 RX_STALE` |
| DELETE | `/api/v1/prescriptions/{id}` | as POST | Discards a draft (never issued); `409 RX_NOT_DRAFT` otherwise |
| POST | `/api/v1/prescriptions/{id}/issue` | as POST | `{revision}`; `422 RX_EMPTY`, `422 RX_DOCTOR_INCOMPLETE`; returns the issued version |
| POST | `/api/v1/prescriptions/{id}/revise` | as POST | From the latest issued version: a new draft, version n+1, copying the content; `409 RX_DRAFT_EXISTS` (with its ID), `409 RX_NOT_LATEST` |

### Tests

- **Domain:** vocabulary and limits; replace with a stale revision; issue snapshots, language
  and delivery (`PENDING` vs `NOT_CONSENTED`); `RX_EMPTY`; `RX_DOCTOR_INCOMPLETE` for blank
  fields (AC4); revise copies content and bumps the version; supersede moves `PENDING`.
- **AC1 on PostgreSQL:** `PUT` an issued version → 409 `RX_NOT_DRAFT`; a direct SQL `UPDATE` of
  `advice`, of an item, an `INSERT` of an item and a `DELETE` → refused by the triggers; the
  allowed operational updates (supersede, `pdf_object_key` once) succeed.
- **Chains:** two concurrent issues of the same draft give one 200 and one 409; two concurrent
  revisions give one draft; a superseded version cannot be revised (`RX_NOT_LATEST`).
- **R16/AC7:** one `prescription.viewed` per read; the consultation view still writes one row
  with prescriptions in it; sentinel item text absent from logs, audit metadata and errors.
- **Permissions and tenancy:** front desk 403 everywhere; an owner reads, cannot write; another
  clinic's prescription 404 (the cross-tenant suite gains the new routes).
- **Contract:** every route against `openapi.yaml`; `make contract-check`.

### Verify (on the rebuilt stack, with `make seed`)

1. Start a visit (P1); `POST /visits/{id}/prescriptions` → 201 draft v1; again → 409
   `RX_ALREADY_EXISTS` with the same ID.
2. `PUT` the PRD §8.6 sample (Syrup X, 5 ml, `1-0-1`, `AFTER_FOOD`, 5 days, `SHAKE_WELL`,
   `DILUTE_IN_WATER` 10 ml) → 200; with the old revision → 409 `RX_STALE`.
3. `issue` → 200: `doctor_snapshot`, `clinic_snapshot`, `language`, `link_delivery` as the
   patient's consent says. `PUT` again → 409 `RX_NOT_DRAFT`. **Failure path.**
4. `psql`: `UPDATE prescriptions SET advice = '{}' WHERE id = …` → error `RX_NOT_DRAFT`.
5. `revise` → 201 draft v2; issue it → v1 is `SUPERSEDED` with `link_delivery` `SUPERSEDED`.
6. Front desk `GET /prescriptions/{id}` → 403; `audit_events` for the chain has no item text.

### Decisions for approval

| # | Question | Options | Recommendation |
|---|---|---|---|
| 1 | Prescriptions per visit | **A** one chain per visit (v1, then revisions; at most one draft) · **B** several independent prescriptions per visit | **A**: one thing for the patient link, the PDF and the history to point at; a second list of medicines is a revision |
| 2 | When may it be written? | **A** create, edit and issue until the visit locks (24 h after completion); revise an issued version at any time, by the visit's doctor · **B** revisions also stop at the lock | **A**: a correction found later is exactly what versions are for (FR-RX-09), and the old version stays as it was |
| 3 | Saving a draft | **A** `PUT` the whole draft with its `revision` (`RX_STALE`) · **B** item-level `PATCH`es, last write wins | **A**: matches the builder (it holds the whole list) and the visit's guard |
| 4 | Structured instructions | **A** items as rows; frequency and timing enums; preparation and storage as phrase-code lists (jsonb) with an amount or days · **B** the whole body as one jsonb document | **A**: rows let P3 rank medicine names by use and let the trigger guard each line; phrase codes are what P4/P5 translate |
| 5 | Clinic details on the prescription | **A** snapshot the clinic's name, address and phone at issue, with the doctor's · **B** read the clinic live when rendering | **A**: an issued prescription prints and reads exactly as it was given |
| 6 | Front desk's "a prescription was issued" | **A** in P5/P6, where its actions live (show the QR, resend), as a non-clinical status on the queue row · **B** now, as a separate endpoint | **A**: nothing in P2 needs it, and it changes the queue's ETagged body only once |

### Result (17–18 Oct 2026)

API only, as designed. `make lint typecheck contract-check` clean; `make test`: API **1121 tests**
at 99.01% (43 more than P1: 17 domain rules, 14 prescriptions over HTTP on PostgreSQL, the
contract, repository and HTTP tenancy cases for the new routes, the migration), web 344. `make
up` applied `0010`; `make seed` and `make smoke` passed. The verify steps on the stack, as the
seeded doctor and front desk with the PRD §8.6 sample: a draft 201 and again 409
`RX_ALREADY_EXISTS` with the same ID; `PUT` 200 (revision 2) and a stale one 409 `RX_STALE`;
issue 200 with both snapshots, language `en` and `link_delivery` `PENDING` (the patient had
consented); `PUT` after issue 409 `RX_NOT_DRAFT`; direct SQL `UPDATE` of the advice and of an
item both refused with `RX_NOT_DRAFT`; revise 201 v2, issuing it left v1 `SUPERSEDED` with its
delivery `SUPERSEDED`; front desk 403; the chain's audit rows carry no item text.

Taken while implementing:
- The window of decision 2A applies to the draft being written: version 1 is created, saved and
  issued only until the visit locks (`409 VIS_LOCKED`); a revision's draft may be saved and issued
  at any time.
- Items are rewritten whole on every save (new IDs each time), matching decision 3A; a revision
  copies the issued items into new rows.
- `RX_DOCTOR_INCOMPLETE` lists the blank printed fields in `details.fields`.
- Issuing a revision locks the version it supersedes before the draft, so two issues in a chain
  serialise; two concurrent issues give one 200 and one 409, two revisions one draft.
- The consultation view loads every prescription on the screen in one query and still writes one
  audit row; history lines carry their latest issued medicines only.
- The test reset lifts the prescription triggers the same deliberate way as the audit and addenda
  ones (`GUARDED_TABLES` in `tests/conftest.py`).
- Verifying after midnight found that the previous run's extra session ran past 00:00 and
  overlapped a new one (`SCH_OVERLAP`, correct behaviour); the verify script now uses whichever
  session is running, also one dated yesterday.

---

## M4-P3 — Favourites, templates and clinic-history autocomplete

**Status: approved by the developer 18 Oct 2026 with 1A–5A (every recommendation); implemented the same day (result at the end of this section) and confirmed by the developer.** API only; the builder uses it in P6. Covers
FR-RX-05, FR-RX-10; spec R7; AC5.

### Concepts

1. **Speed from the doctor's own habits, never from outside data.** Three aids for the builder,
   all made of what this clinic's doctors have written themselves: *favourites* (one medicine line
   with its usual instructions), *templates* (a whole prescription body: lines and advice), and
   *suggestions* while typing a medicine name. There is no drug list, no dose, no interaction
   check, no external source (FR-RX-10, principle 6). AC5 is the guard: a name the clinic never
   prescribed is never suggested.
2. **Favourites and templates belong to a doctor** (decision 1). They are the doctor's working
   tools, not clinical records about a patient, so they are edited freely, versioned by a
   `revision` like drafts, and deleted for real.
3. **Same shape as a draft.** A favourite holds exactly one `PrescriptionItem` body; a template
   holds `items` and `advice` (and an optional "follow up in N days"). They are validated by the
   P2 domain rules, so anything saved can be inserted into a draft unchanged. Applying one is the
   builder's job: it copies the body into the draft it then `PUT`s (P2), so issued prescriptions
   stay the only clinical record.
4. **What counts as "used" (decision 3).** A draft's `PUT` may say which favourite each line and
   which template the body came from (`favourite_id`, `template_id`, stored as plain IDs, not
   foreign keys, because issued rows never change and a deleted favourite must not touch them).
   Issuing counts them: `use_count + 1`, `last_used_at = issued_at`. Saving a draft five times
   counts nothing.
5. **Suggestions rank the clinic's history (R7, decision 2).** For a prefix of 2 or more
   characters, case-insensitive, from the start of the name: first the doctor's favourites
   (by use), then medicine names that appear on the clinic's **issued** prescriptions (issued or
   superseded, never drafts), ranked by the number of distinct visits they were prescribed in,
   then most recent. Names are grouped case- and space-insensitively and shown in their most
   recent spelling. At most 10. A typo in a discarded draft never becomes a suggestion.
6. **Not patient data in the audit sense.** Suggestions and favourites name medicines, not
   patients; reading them is not a view of anyone's record (R16 is about patient content), and the
   builder asks on every keystroke. Changes to favourites and templates are audited with IDs only
   (decision 4).

### Data (migration `0011`, expand-only)

| Table | Columns (all carry `clinic_id`) | Constraints |
|---|---|---|
| `rx_favourites` | `id`, `doctor_id`, `name`, `item jsonb`, `revision`, `use_count`, `last_used_at null`, timestamps | name 1–100; unique per doctor, case-insensitive (`lower(name)`); `use_count >= 0` |
| `rx_templates` | `id`, `doctor_id`, `name`, `items jsonb`, `advice jsonb`, `follow_up_days smallint null`, `revision`, `use_count`, `last_used_at null`, timestamps | as favourites; `follow_up_days` 1–365 |
| `prescription_items` | + `favourite_id uuid null` | No foreign key (see concept 4) |
| `prescriptions` | + `template_id uuid null` | No foreign key; the P2 immutability trigger already covers new columns (it compares the whole row) |
| index | `ix_prescription_items_clinic_id_medicine_name` on `(clinic_id, lower(medicine_name) text_pattern_ops)` | The M2 pattern for name prefixes; no extension |

Limits: 200 favourites and 50 templates per doctor; a template holds up to 40 lines (P2's limit).

### Domain and application

| Where | What |
|---|---|
| `domain/prescriptions/library.py` | `Favourite` and `Template`: name rules, the body validated through `PrescriptionItem.create` / `Advice.create`, `replace(…, seen_revision)`, `record_use(at)` |
| `domain/prescriptions/suggestions.py` | Pure ranking: merge favourites and history counts, group by normalised name, cap at 10 |
| `domain/prescriptions/prescription.py` | `PrescriptionItem.favourite_id`, `Prescription.template_id` (provenance, copied into revisions) |
| `application/prescriptions/library.py` | `List/Create/Replace/DeleteFavourite`, the same for templates, `SuggestMedicines` |
| `application/prescriptions/use_cases.py` | `IssuePrescription` records the uses of the favourites and template it names (the caller's own; a stale ID is ignored) |
| `domain/audit/actions.py` | `rx_favourite.created/.updated/.deleted`, `rx_template.created/.updated/.deleted` |

### API (contract 0.15.0)

| Method | Path | Permission | Behaviour |
|---|---|---|---|
| GET | `/api/v1/rx-favourites` | `CLINICAL_WRITE` | The caller's favourites by use, then name |
| POST | `/api/v1/rx-favourites` | `CLINICAL_WRITE` | `{name, item}` → 201; `409 RX_NAME_TAKEN`; `409 RX_LIBRARY_FULL` |
| PUT | `/api/v1/rx-favourites/{id}` | `CLINICAL_WRITE`, its doctor | `{revision, name, item}`; `409 RX_STALE` |
| DELETE | `/api/v1/rx-favourites/{id}` | `CLINICAL_WRITE`, its doctor | 204 |
| GET/POST/PUT/DELETE | `/api/v1/rx-templates[/{id}]` | the same | `{name, items, advice, follow_up_days}` |
| GET | `/api/v1/medicine-suggestions?q=` | `CLINICAL_WRITE` | `q` 2–50 characters; up to 10 `{name, source: FAVOURITE \| HISTORY, favourite_id?, uses}` |
| PUT | `/api/v1/prescriptions/{id}` | as P2 | Items may carry `favourite_id`, the body `template_id` |

Another doctor's favourite or template is `404` (only its owner sees it). `CLINICAL_WRITE`
because only a prescribing doctor needs them; owners who are not doctors and front desk get 403.

### Tests

- **AC5:** a clinic that prescribed "Drug P" but not "Drug Q" (another clinic did, and a draft
  here did): "Dru" suggests "Drug P" only. Cross-clinic history never appears.
- **Ranking:** favourites first; then distinct visits (a revised prescription counts once),
  then recency; grouping of "syrup x" and "Syrup  X"; the cap; `q` of 1 character is a 422.
- **Library:** name uniqueness per doctor (another doctor may reuse it), limits, stale revision,
  bodies checked by the P2 rules, another doctor's items 404, front desk 403.
- **Use counts:** issuing a prescription built from a favourite and a template counts each once;
  saving drafts counts nothing; deleting a favourite leaves the issued prescription untouched.
- **Performance:** suggestions over 20,000 issued lines in one clinic answer within 150 ms p95 on
  the local PostgreSQL (the index is used).
- **Contract, tenancy suites, permissions; `make contract-check`.**

### Verify (on the rebuilt stack, with `make seed`)

1. As the doctor, save a favourite "Fever syrup" (the PRD sample line) → 201; the same name again
   → 409 `RX_NAME_TAKEN`.
2. Issue a prescription using it (P2 routes with `favourite_id`); `GET /rx-favourites` shows
   `use_count` 1.
3. `GET /medicine-suggestions?q=syr` → "Syrup X" first, `source` `FAVOURITE`; `q=Dru` → nothing.
4. Front desk `GET /medicine-suggestions?q=syr` → 403. **Failure path.**
5. A template with two lines and advice; `PUT` with an old revision → 409 `RX_STALE`.

### Decisions for approval

| # | Question | Options | Recommendation |
|---|---|---|---|
| 1 | Whose favourites and templates? | **A** each doctor's own · **B** shared by the clinic | **A**: as the data model sketches; habits differ between doctors, and a shared list needs an owner to curate it |
| 2 | Which history feeds suggestions? | **A** medicine names on issued (and superseded) prescriptions of the clinic, any doctor, ranked by distinct visits · **B** also drafts · **C** only the caller's own prescriptions | **A**: what the clinic has actually given (R7); drafts carry typos; the clinic's colleagues' names help a new doctor |
| 3 | How is "use" counted for ranking favourites? | **A** at issue, from the `favourite_id` / `template_id` the draft carries · **B** a separate "applied" call from the builder · **C** no counts, alphabetical | **A**: counts what was really prescribed, no extra call, no double counting |
| 4 | Audit | **A** changes to favourites and templates audited with IDs only; suggestions and lists not audited · **B** audit the lists and suggestions too | **A**: no patient record is read, and suggestions are asked per keystroke |
| 5 | Matching | **A** from the start of the name, case-insensitive (the M2 index pattern, no extension) · **B** any word in the name (needs the `pg_trgm` extension) | **A**: doctors type names from the start; B can follow if pilots ask, with its own ADR for the extension |

### Result (18 Oct 2026)

API only, as designed. `make lint typecheck contract-check` clean; `make test`: API **1146 tests**
at 98.89% (domain rules for favourites, templates and ranking; 8 over HTTP on PostgreSQL including
AC5 and the performance check; the contract; repository and HTTP tenancy cases; the migration),
web 344. `make up` applied `0011`; `make seed` and `make smoke` passed. On the stack as the seeded
doctor: a favourite 201 and the same name in capitals 409 `RX_NAME_TAKEN`; a prescription issued
with that favourite's line left its `use_count` at 1; `q=syr` gave the favourite first, `q=Dru`
nothing (AC5); front desk 403; a template with two lines, and a stale replace 409 `RX_STALE`.
Suggestions over 20,000 issued lines answered within the 150 ms p95 budget in the suite.

Taken while implementing:
- Favourite and template names collapse inner spaces when saved, so the database's
  `lower(name)` index and the domain agree that "Fever  syrup" and "fever syrup" are one name.
- A name that is both a favourite and in the history is shown once, as the favourite.
- Repeated lines from one favourite in one prescription count as one use; a deleted or another
  doctor's favourite or template named by a draft counts nothing and is otherwise ignored.
- Suggestions ask the database for twice the limit and rank in the domain, so favourites can
  displace history without a second query.
- The new index uses the M2 `text_pattern_ops` form, so Alembic's model comparison prints the same
  harmless "operator clause" warning it already prints for the patient-name index.
- A test left a database connection open and the table reset waited for it; every test now
  closes its connections (`with db.connect()`).

---

## M4-P4 — PDF rendering and blob storage

**Status: approved by the developer 18 Oct 2026 (1A-5A, every recommendation).** API, the API image and compose; printing from
the screens is P6. Covers FR-RX-04, FR-RX-06 (the printable PDF); spec R8, R16, R18, R20, D1, D3,
D6; ADR-0012; AC8, AC10.

The developer answered P2's open question on 18 Oct 2026 (spec D6): once a prescription is
issued, front desk may print it or hand a copy to the patient, as reception does with an e-parchi
today, without seeing its content on screen.

### Concepts

1. **Two ports, nothing outside the infrastructure (ADR-0012).** `PdfRendererPort.render(document)
   -> bytes` and `BlobStoragePort.put/get/exists`. Adapters: WeasyPrint (pinned, 70.x) with fonts
   vendored in the repository; a local volume (dev, CI, tests); an S3-compatible client for
   production, configured but not used until M6. Tests use an in-memory storage and a fake
   renderer for use cases, and real WeasyPrint for the adapter and the end-to-end checks.
2. **Render once, on first download (R18, AC8).** `GET /api/v1/prescriptions/{id}/pdf` locks the
   prescription row; if it has no `pdf_object_key`, it builds the document, renders, stores under
   `rx/{clinic_id}/{prescription_id}/v{version}.pdf` (write once, atomic) and records the key (the
   P2 trigger allows it once). Concurrent first downloads wait on the row lock and then find the
   key: one render. Waiting longer than 10 s is `503 RX_PDF_BUSY` with `Retry-After: 2`. A render or
   storage failure is `500 RX_PDF_FAILED`, logged without content, and nothing is stored, so the
   next download tries again.
3. **What is printed is fixed by issue, how it looks by the first render.** Content, doctor,
   clinic letterhead and language come from the issued version (P2 snapshots, R8, R20). The
   patient's name, code, age at the issue date and sex are read when the PDF is first rendered,
   then fixed in the file. The paper size is the clinic's setting at first render (decision 3).
4. **Bilingual by phrasebook, free text verbatim (R20, D5).** `domain/prescriptions/phrasebook.py`
   holds every label and structured phrase (frequency, timing, preparation, storage, headings) in
   English and Hindi; P5's patient page uses the same book. A completeness test fails if a code
   lacks a phrase in either language. Free text (medicine names, doses, warnings, notes, advice)
   is printed exactly as written. No machine translation anywhere.
5. **Printing is not viewing (D6).** A new permission `RX_PRINT` (front desk, doctors, owners)
   downloads the PDF of an issued prescription; drafts are never printable (`409 RX_NOT_ISSUED`).
   Front desk finds what to print in a list without clinical content (decision 2). Every download
   is one `prescription.pdf_downloaded` audit row with the version and the role, never content.
6. **Safe rendering.** Jinja2 with autoescaping builds the HTML from the document view model; the
   WeasyPrint URL fetcher refuses every URL except the vendored fonts and the stylesheet, so no
   value can make the renderer fetch anything. The PDF carries no title or metadata with clinical
   content (the title is "Prescription"). Responses are `application/pdf`, `Cache-Control:
   private, no-store`, `Content-Disposition: inline; filename="prescription-<code>-v<n>.pdf"`.

### What the PDF shows (R8, PRD §8.6)

Letterhead (clinic name, address, phone), doctor (name, qualification, registration number and
council), patient (name, code, age, sex), date of issue, and "Revised prescription (version n)"
when n > 1. One block per medicine: name, form and strength, dose, *when* (frequency and timing
phrases, or the custom text), *how long*, quantity, *how to give* (preparation phrases with their
amounts), *storage*, warnings and notes. Advice (diet, activity, "come back immediately if…",
notes), the follow-up date, page numbers, and the footer "Digitally generated via MediEase". A5
portrait by default; long prescriptions paginate (more than 15 lines is tested).

### Image, settings and compose

| Change | Detail |
|---|---|
| `apps/api/Dockerfile` | Runtime stage installs `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0` and `fontconfig` from the pinned trixie base (Pango 1.56 ≥ 1.44); `XDG_CACHE_HOME=/tmp` so fontconfig writes only to the tmpfs; Trivy keeps scanning |
| Fonts | Noto Sans and Noto Sans Devanagari, Regular and Bold (SIL OFL 1.1), in `adapters/pdf/fonts/` with `OFL.txt` and their SHA-256 in a `SOURCES.md`; a test checks the hashes |
| Dependencies | `weasyprint==70.x` and `jinja2` (already installed by Flask, now named), `boto3` for the S3 adapter; dev: `pypdf` (text checks), `moto[s3]` (in-process S3). Exact pins at implementation |
| Settings | `BLOB_STORAGE=local\|s3` (local by default), `BLOB_LOCAL_DIR=/var/lib/mediease/blobs`; `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, credentials from the environment, required only for `s3`; `.env.example` documents them |
| Compose | A named volume `blobs` on the API at `/var/lib/mediease/blobs`, owned by the app user; the root filesystem stays read-only |
| Migration `0012` | `clinics.rx_paper_size text not null default 'A5'` (`A5`\|`A4`); `PATCH /clinic` and the ops create gain it |

### Domain, application, delivery

| Where | What |
|---|---|
| `domain/prescriptions/phrasebook.py` | Labels and structured phrases in `en` and `hi`; `phrase(code, lang, **params)` |
| `domain/prescriptions/document.py` | `RxDocument`: the view model the renderer gets (all phrases already resolved), built from the issued version, the patient and the paper size |
| `ports/pdf.py`, `ports/storage.py` | `PdfRendererPort`, `BlobStoragePort` (`put` write-once, `get`, `exists`) |
| `adapters/pdf/weasy.py` + template + CSS + fonts | The renderer, with the restricted URL fetcher |
| `adapters/storage/local.py`, `adapters/storage/s3.py` | Temp file + `fsync` + `os.replace`; S3 `PutObject` with `If-None-Match: *` and server-side encryption |
| `application/prescriptions/pdf.py` | `DownloadPrescriptionPdf` (lock, render once, store, audit), `ListPrintable` |
| `domain/identity/permissions.py` | `RX_PRINT` for every clinic role |
| `delivery/http/prescriptions.py` | `GET /prescriptions/{id}/pdf`, `GET /patients/{id}/prescriptions` |

### API (contract 0.16.0)

| Method | Path | Permission | Behaviour |
|---|---|---|---|
| GET | `/api/v1/prescriptions/{id}/pdf` | `RX_PRINT` | The PDF; renders on first request (R18); `409 RX_NOT_ISSUED` for a draft; `503 RX_PDF_BUSY`; `500 RX_PDF_FAILED` |
| GET | `/api/v1/patients/{id}/prescriptions` | `RX_PRINT` | Decision 2: the patient's issued prescriptions, newest first, **without content**: id, version, status, issued_at, doctor's display name, whether a newer version exists |
| PATCH | `/api/v1/clinic` | as today | Gains `rx_paper_size` |

### Tests

- **AC8:** two concurrent first downloads → the fake renderer is called once and both responses
  carry the same bytes; a third is served from storage.
- **AC10 and R8 with real WeasyPrint:** a Hindi prescription with English free text: the PDF's
  text (`pypdf`) has the Hindi labels and phrases and the free text byte for byte; the PRD §8.6
  sample has "10 ml" under "How to give"; doctor registration and footer present; 16 lines
  paginate; A4 and A5 page sizes.
- **Phrasebook completeness** for every code in both languages; the font hashes.
- **Storage:** local write-once (a second `put` keeps the first bytes), atomic (no partial file
  after a failure), keys cannot escape the base directory; S3 against `moto` (write-once, SSE).
- **Renderer safety:** a value containing `<img src="http://…">` or `file:///etc/passwd` is
  printed as text and no fetch happens.
- **Permissions and audit:** front desk downloads an issued PDF (200) and gets 409 for a draft and
  403 on `GET /prescriptions/{id}`; one `prescription.pdf_downloaded` per download; another
  clinic's PDF 404; no content in logs or audit.
- **Failures:** renderer raises → 500 `RX_PDF_FAILED`, nothing stored, `pdf_object_key` still
  null; lock wait → 503 with `Retry-After`.
- **Image:** `make up` builds with the new libraries, the read-only root filesystem holds, and a
  smoke check downloads a seeded prescription's PDF.

### Verify (on the rebuilt stack, with `make seed`)

1. As the doctor, issue the PRD sample (P2); as front desk, `GET /patients/{id}/prescriptions`
   lists it without items; `GET /prescriptions/{id}/pdf` → 200 `application/pdf`; open it: the
   letterhead, registration number, "How to give: … 10 ml …", footer.
2. `docker compose exec api ls /var/lib/mediease/blobs/rx/<clinic>/<rx>/` shows `v1.pdf`;
   download again: same bytes, no new render in the logs.
3. Front desk `GET /prescriptions/{draft}/pdf` → 409 `RX_NOT_ISSUED`. **Failure path.**
4. Set the patient's language to Hindi, issue another; its PDF has Hindi headings, free text as
   typed.
5. `PATCH /clinic {"rx_paper_size": "A4"}`; a newly issued prescription's PDF is A4, earlier ones
   stay as rendered.

### Decisions for approval

| # | Question | Options | Recommendation |
|---|---|---|---|
| 1 | Which versions may front desk print? | **A** the latest issued version; a superseded one only by doctors and owners (`CLINICAL_VIEW`) · **B** any issued or superseded version | **A**: reception hands over what is current; older versions are records for clinicians |
| 2 | How does front desk find what to print? | **A** `GET /patients/{id}/prescriptions` without content, now (P6 adds a print button on the queue row and the profile) · **B** only from the queue in P6 | **A**: printing works as soon as P4 lands, and the list is the same data P6 needs |
| 3 | Paper size | **A** a clinic setting (A5 default, A4), applied when a version is first rendered and fixed in the file · **B** chosen per download | **A**: one stored file per version (render once); clinics print on one stationery |
| 4 | Hindi wording | **A** ship the English and Hindi phrasebook now, the Hindi marked for review by a native-speaking clinician at a pilot clinic (L-07) before patients see it · **B** English-only PDFs until reviewed | **A**: R20 and AC10 need it, and the review fits L-07; wording is data, so a correction is a one-line change |
| 5 | The S3-compatible adapter | **A** build and test it now (boto3, `moto` in-process), wired in M6 · **B** port and local adapter now, S3 in M6 | **A**: as ADR-0012 and your refinement ask ("ready for prod"); it is small and tested without the network |
