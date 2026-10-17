# M4 — Visits and digital prescriptions: design notes

| Field | Value |
|---|---|
| Status | In progress — M4 opened 17 Oct 2026; M4-P1 approved (1A–6A), implemented and confirmed by the developer the same day; M4-P2 approved (1A–6A), implemented and confirmed by the developer 18 Oct 2026; M4-P3 designed next |
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
| P3 | Favourites, templates, clinic-history autocomplete | At its start |
| P4 | `PdfRendererPort`, `BlobStoragePort`, render-once (R18, ADR-0012) | At its start |
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
