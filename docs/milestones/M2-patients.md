# M2 — Patients: design notes

| Field | Value |
|---|---|
| Status | In progress — M2-P1 to P3 confirmed (P3 on 5 Oct 2026 after a re-check); M2-P4 approved 5 Oct 2026 (1A, 2A) and implemented, awaiting confirmation; P5 next |
| Spec | `docs/specs/patients.md` (Approved 2026-10-03) |
| Covers | FR-PAT-01..06, FR-PAT-08, FR-MSG-05 (opt-out state), NFR-08 |
| Issue / branch / PR | #21 · `m2/21-patients` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | Register, find and update patients; a shared phone is surfaced, not silently duplicated; lookup over 10,000 patients has p95 < 500 ms |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Patient domain, clinic code allocation, migration `0006`, tenancy-scoped repository, indexes, the 10,000-patient lookup test | Below |
| P2 | Register / edit / lookup endpoints, the duplicate-phone flow, `patient_code_prefix` on clinic creation | Below (M2-P2 section) |
| P3 | Consent, language preference, opt-out and opt-in | Below (M2-P3 section) |
| P4 | Ops CSV import with a dry-run report | Below (M2-P4 section) |
| P5 | Web: global search, registration drawer, profile | Designed at its start |

Each phase is designed, approved, implemented, verified and confirmed before the next starts.

---

## M2-P4 — Ops CSV import with a dry-run report

**Status: approved by the developer 5 Oct 2026 with 1A and 2A; implemented the same day, awaiting confirmation.** Covers FR-PAT-08,
FR-OPS-02; spec patients R8, §7 (`patient.imported`, the checklist), §10 (`patient.import_dry_run`).
One endpoint, one use case, one audit action, contract 0.8.0, no migration. API only in M2: the ops
procedure is RUNBOOK §10; an upload screen is not in the M2 plan.

### Endpoint

`POST /api/v1/ops/clinics/{clinic_id}/patient-imports?dry_run=true|false`, `@ops` (clinic staff are
refused even as owners), unknown clinic `404`. The body is the raw CSV as `Content-Type: text/csv`
(`curl --data-binary @patients.csv`). `dry_run` defaults to **true**, so a forgotten flag writes
nothing. Both modes answer `200` with the same report; a commit fills `imported`.

### The file

| Part | Rule |
|---|---|
| Encoding, size | UTF-8, an Excel BOM accepted; at most 2 MB (this route only, `413 REQ_REQUEST_ENTITY_TOO_LARGE`) and 5,000 data rows |
| Header | Exactly `name, phone, sex, dob_or_age, guardian_name, language`, any order and case. A missing or unknown column rejects the file, so a stray "diagnosis" column is never silently dropped |
| `phone` | Normalised as in registration (R1) |
| `sex` | `F`/`M`/`O`/`U` or the words, any case; blank → `UNDISCLOSED` (choice 2A) |
| `dob_or_age` | A whole number 0–120 is an age recorded on the clinic's today; otherwise a date `YYYY-MM-DD`, `DD/MM/YYYY` or `DD-MM-YYYY` (day first: Indian lists; US order is not accepted) |
| `guardian_name` | Required under 18 (R3) |
| `language` | `en`/`hi`/`english`/`hindi`; blank → `en` |
| Consent | Always false and "not asked" (R8) |

File-level problems (header, no rows, too many rows, not UTF-8, not parseable as CSV) are
`422 PAT_IMPORT_INVALID` with `details.problems`; bad rows are reported, not fatal.

### Report (same shape for dry run and commit)

```json
{
  "dry_run": true,
  "rows": 812, "valid": 790, "invalid": 22, "possible_duplicates": 31,
  "already_registered": 4, "imported": 0, "codes": [],
  "errors":     [{"row": 14, "field": "phone", "reason": "is not a valid phone number"}],
  "duplicates": [{"row": 37, "kind": "existing_patient", "matches": 2},
                 {"row": 52, "kind": "earlier_row", "same_as_row": 9}]
}
```

- Row numbers are spreadsheet rows (header = row 1).
- Nothing from the file is echoed: reasons are fixed strings; no names, phones or existing patients'
  codes (ops cannot browse patients, spec §2). `codes` lists only the codes this import created.
  The `errors` and `duplicates` lists stop at 500 entries; the counts are always complete.
- **Possible duplicate:** the phone is already in the clinic, or on an earlier row. A warning,
  not an error: imported and flagged (choice 1A, like `confirm_new`).
- **Already registered:** same phone *and* same name (case and spacing ignored) as an existing
  patient or an earlier row. Always skipped, so re-running an import does not double the list.

### Use case `ImportPatients` (`application/patients/import_patients.py`)

1. Read the CSV and parse every row with the domain's rules (`domain/patients/import_row.py`): pure.
2. Fetch every patient on any of the file's phones in one query (`PatientRepository.find_by_phones`).
3. Dry run: log `patient.import_dry_run` (counts only) and return the report; no lock, no write.
4. Commit, one transaction: lock the clinic row (as R9, so an import and a front-desk registration
   serialise), build the report again against the data as it is now, insert the importable rows
   in file order with consecutive codes, one `patient.imported` audit row each (`code`,
   `import_id`), the checklist's `patients_imported_at` the first time, commit. Any failure
   imports nothing.

### Decisions

| Decision | Reason |
|---|---|
| Raw `text/csv`, not multipart | One file, the simplest `curl`, no form parsing |
| No import table or job; synchronous | 5,000 rows is seconds, inside gunicorn's 30 s; background work waits for M5's worker |
| No dry-run token for the commit | The commit re-validates against current data itself; `dry_run=true` by default is the guard |
| One audit row per patient | Each patient's origin is on record, as `patient.created` does |
| Exact duplicates skipped, phone-only ones imported (1A) | Re-running a file is the likely mistake; families on one phone are the normal case |
| Blank sex is `UNDISCLOSED` (2A) | Paper lists often lack it; the front desk corrects it later |
| Body limit on this route only | Every other endpoint takes small JSON; a global 2 MB would loosen them |

### Files

| Layer | Files |
|---|---|
| Domain | `patients/import_row.py`, `audit/actions.py` (`PATIENT_IMPORTED`) |
| Ports / adapters | `PatientRepository.find_by_phones` + SQLAlchemy and fake versions |
| Application | `patients/import_patients.py`, `patients/errors.py` (`ImportInvalid`) |
| Delivery | `http/ops.py` (route, size limit), `errors.py`, `bootstrap.py` |
| Contract / docs | `openapi.yaml` 0.8.0 + web types, `API.md`, `ERRORS.md`, `DATA_MODEL.md`, RUNBOOK §10, CHANGELOG |
| Fixture | `scripts/fixtures/patients-import-sample.csv` (synthetic) |

### Tests

- **Domain:** each column (BOM, day-first dates, age 0 and 120, a future date of birth, blanks,
  unknown values), the header rules.
- **Use case:** a dry run writes nothing; a commit inserts only importable rows in file order;
  the same file twice imports nothing the second time; a file problem imports nothing; the commit
  re-checks data changed after the dry run; the checklist is written once.
- **PostgreSQL / HTTP:** ops only (desk and owner 403), unknown clinic 404, 415 for JSON, 413 over
  2 MB, 422 on a bad header; an import and a registration of the same phone serialise; 5,000 rows
  well inside the limit; no names or phones in logs, audit rows, the report or errors.
- **Contract:** the operation, the report, 413/415/422.

### Verify

```bash
make up && make seed
# as ops@mediease.example, with sample-clinic's id from GET /api/v1/ops/clinics:
curl -s -b jar -X POST -H "X-CSRF-Token: $CSRF" -H 'Content-Type: text/csv' \
  --data-binary @scripts/fixtures/patients-import-sample.csv \
  "$API/api/v1/ops/clinics/$CLINIC/patient-imports"                # dry run: 10 rows, 2 invalid
#   ...?dry_run=false                                              # imported + codes
#   the same file again with dry_run=false                         # imported 0
#   Content-Type: application/json -> 415; a bad header -> 422 PAT_IMPORT_INVALID
make lint typecheck test
```

### Result (5 Oct 2026)

`make lint typecheck test` in WSL: ruff, format, import-linter (4 contracts kept) and mypy clean;
847 API tests pass (93 new: 49 domain, 21 use case on PostgreSQL, 17 HTTP, 4 contract, plus the
repository, tenancy and route-policy guards) at 99.09% package and 99% `domain/` + `application/`
coverage; web 25 files / 256 tests, types regenerated, `gen:api:check` clean; the contract passes
`openapi-spec-validator`; `make smoke` passes. On the rebuilt compose stack with `make seed`, as
the ops user against `sample-clinic` with the sample file: the default is a dry run (10 rows, 8
valid, rows 8 and 9 invalid with the column and reason, row 3 an `earlier_row`, rows 10 and 11
`already_registered`), the commit imports 6 with consecutive codes, the same file again imports 0,
JSON is 415, a bad header 422 with the problems, 2.2 MB is 413, the front desk 403, an unknown
clinic 404; the front desk then finds the family by phone with the guardian set and consent "not
asked"; six `patient.imported` rows with actor `OPS`, one `import_id` and the request ID; no name
or phone in the API log.

Taken while implementing: one insert per row made 5,000 rows take 9 s, so the patient repository
gained `add_many` and the audit writer `record_many` (batched inserts in the same transaction;
`record` and `add` now call them) and it takes under 2 s. `record_first_patient` is shared with
registration. CSV is parsed with `strict=True`, because the default reader silently accepts an
unterminated quote and swallows the rest of the file; a row with cells beyond the header is
refused rather than trimmed. The contract describes the body as `text/csv: {}`: in OpenAPI 3.1 a
raw file body is the media type alone, and a string schema makes the validator reject bytes.

## M2-P3 — Consent, language and opt-out

**Status: approved by the developer 3 Oct 2026 with option A; implemented the same day; confirmed 5 Oct 2026 after a re-check (gate, compose flow, CI 7/7 on `e9c5cb9`).** Covers FR-PAT-05, FR-PAT-06 (consent
against the guardian), the state side of FR-MSG-05; spec patients R6, AC5, §7. Three endpoints, two
use cases, three audit actions, contract 0.7.0. No messages are sent in M2: this phase records who
may be messaged, and M5 reads it. Language is already editable through `PATCH /patients/{id}` (P2);
P3 only shows it next to consent.

### Concepts

1. **"Not asked" is not "said no".** A new patient has both flags false and `consent_recorded_at`
   null: nobody has asked yet. Recording consent with both flags false sets the timestamp: they were
   asked and declined. The web app shows the two differently, and M5 treats both as "do not send".
2. **Opt-out wins.** An opt-out (a STOP reply in M5, or the front desk on the patient's request now)
   overrides consent until an explicit opt-in (R6, AC5). Opt-in is its own action, not a side effect
   of ticking a box, so an opt-out can never be undone by accident.
3. **One question for M5.** Whether a patient may be messaged is a domain answer
   (`may_receive_whatsapp`, `may_receive_sms`), not a rule each sender re-derives. The patient body
   carries it, so the screens and M5's sender use the same rule.
4. **For a minor, the guardian answers.** The phone is the guardian's (decision D1), so consent is
   the guardian's (FR-PAT-06). The API records it the same way, and the audit row says on whose
   behalf (`given_by: guardian` or `patient`, from the age on the clinic's today), with no name.
5. **Consent changes are evidence.** DPDP needs to show who recorded what and when. Every change is an
   audit row in the same transaction, with the flags as values (booleans, not personal data), the
   staff member as actor and the request ID.

### Endpoints (all `PATIENTS_MANAGE`, every clinic role; ops refused; another clinic's patient 404)

| Method | Path | Behaviour |
|---|---|---|
| PUT | `/api/v1/patients/{id}/consent` | Body `{"whatsapp": bool, "sms": bool}`, both required. Records them with who and when. While the patient is opted out: `409 PAT_OPTED_OUT` and nothing changes (see open choice 1). `200` with the patient |
| POST | `/api/v1/patients/{id}/opt-out` | No body. Sets `opted_out_at`. Already opted out: `200`, nothing changes, no audit row (idempotent, so a retry or a second STOP is harmless) |
| POST | `/api/v1/patients/{id}/opt-in` | Body `{"whatsapp": bool, "sms": bool}`: the consent given on the way back. Clears the opt-out and records consent in one step. Not opted out: `409 PAT_NOT_OPTED_OUT` |

The patient body gains `whatsapp_allowed` and `sms_allowed` (consent and not opted out),
`opted_out_at` and `consent_recorded_by` (a staff user ID). `opted_out` stays.

### Use cases (`application/patients/consent.py`)

| Use case | Steps, one transaction |
|---|---|
| `RecordConsent` | Load the patient `FOR UPDATE` (so an opt-out and a consent edit cannot interleave) → refuse if opted out → `Patient.record_consent` → save → `patient.consent_changed` with `whatsapp`, `sms`, `given_by` → commit |
| `OptOut` | Load `FOR UPDATE` → `Patient.opt_out` → if it changed: save, `patient.opted_out` with `source: staff` → commit. Takes a `source` so M5's STOP handler reuses it with `source: inbound_message` |
| `OptIn` | Load `FOR UPDATE` → `Patient.opt_in` (refuses if not opted out) → save → `patient.opted_in` with the new flags → commit |

### Decisions

| Decision | Reason |
|---|---|
| Separate endpoints for consent, opt-out and opt-in instead of one `PUT` with an `opted_out` flag | AC5 requires opt-in to be an explicit action; a single document would let a form re-submit undo an opt-out |
| `PUT` consent takes both flags | It records an answer to one question ("may we message you on WhatsApp, on SMS?"); a partial update would leave half an answer with a fresh timestamp |
| The patient row is read `FOR UPDATE` in all three | Consent and opt-out are a tiny state machine; two staff (or staff and M5's STOP handler) acting at once must not leave consent recorded over an opt-out |
| Opt-out is idempotent and writes one audit row only when it changes something | Patients send STOP more than once; the audit trail records the fact, not the retries |
| New error codes `PAT_OPTED_OUT` and `PAT_NOT_OPTED_OUT` (409) instead of reusing `CLN_INVALID_TRANSITION` | The front desk needs the reason in words ("This patient asked not to be messaged; opt them back in first"), and `CLN_` would point an operator at the wrong area |
| `analytics: patient_opted_out` (spec §7) is a log event only | There is no analytics pipeline yet; the event name is fixed now so M6 can count it |
| No seed changes | The six seed patients start "not asked", which is the state to try first; consent and opt-out are two API calls |

### Open choice for approval

**Decision (developer, 3 Oct 2026): option A.**

1. **Consent edits while opted out.** The domain from P1 stores the new flags but they have no effect
   until opt-in (AC5 holds either way).
   - **A (recommended)** — refuse with `409 PAT_OPTED_OUT`. A box ticked on a screen that silently
     does nothing is worse than a clear message, and the opt-in endpoint already takes the consent.
     The domain method gains the same check.
   - **B** — accept and store, as P1 does now, and let the body's `whatsapp_allowed: false` explain it.

### Files

| Layer | Files |
|---|---|
| Domain | `patients/patient.py` (`PatientOptedOut`, `PatientNotOptedOut`, the refusal in `record_consent`, `consent_given_by(today)`), `audit/actions.py` (+3) |
| Ports / adapters | `PatientRepository.get(..., for_update)` and its SQLAlchemy and fake versions |
| Application | `patients/consent.py`, `patients/views.py` (new fields) |
| Delivery | `http/patients.py` (three routes), `bodies.py`, `errors.py` (two codes), `bootstrap.py` |
| Contract / docs | `openapi.yaml` 0.7.0 + regenerated web types, `API.md`, `ERRORS.md`, `DATA_MODEL.md` (audit actions), spec §7, `DEBUGGING.md` ("why is this patient not messageable?"), CHANGELOG |

### Tests

- **Domain:** recording consent sets who and when; declined is distinguishable from never asked;
  consent while opted out is refused and changes nothing; opt-out twice is a no-op; opt-in from not
  opted out is refused; `given_by` is guardian for a minor and patient for an adult, on the boundary
  birthday.
- **HTTP (PostgreSQL):** AC5 end to end (consent → opt-out → consent refused → opt-in with new flags →
  allowed again); the audit rows (one each, flags and `given_by`, no names or phones); idempotent
  opt-out writes one row; validation (both flags required, booleans only); every clinic role may
  record consent; ops 403; another clinic's patient 404 on all three routes (the cross-tenant guard
  requires it); a race between opt-out and a consent edit leaves the patient opted out.
- **Contract:** the three operations, the new body fields and both 409s.

### Verify

```bash
make up && make seed
# as desk@sample-clinic.example, with Asha Rao's id from GET /api/v1/patients?q=asha:
#   PUT  /api/v1/patients/<id>/consent {"whatsapp":true,"sms":false}  -> 200, whatsapp_allowed true
#   POST /api/v1/patients/<id>/opt-out                                 -> 200, whatsapp_allowed false
#   PUT  /api/v1/patients/<id>/consent {"whatsapp":true,"sms":true}    -> 409 PAT_OPTED_OUT
#   POST /api/v1/patients/<id>/opt-in  {"whatsapp":true,"sms":true}    -> 200, both allowed
# make psql: select action, metadata from audit_events where action like 'patient.%' order by occurred_at;
make lint typecheck test
```

### Result (3 Oct 2026)

`make lint typecheck test` equivalents in WSL: ruff, format, import-linter and mypy clean; 754 API
tests pass (31 new: domain, HTTP, race, contract, tenancy guards) at 99.0% package coverage;
`pip-audit` clean; web types regenerated and `gen:api:check` clean, 25 files / 256 tests, tsc and
ESLint clean, no web code changed. On compose through the web origin: a new patient is "not asked";
consent for WhatsApp only makes `whatsapp_allowed` true; opt-out turns both off and keeps the record;
a second opt-out changes nothing; consent while opted out is `PAT_OPTED_OUT`; opt-in with both
restores both; a second opt-in is `PAT_NOT_OPTED_OUT`; the 6-year-old's consent is recorded as
`given_by: guardian`; the audit rows hold flags, `given_by` and `source`, nothing else.

Taken while implementing: `Patient.opt_out` no longer takes `by` (the audit row's actor says who,
and it used to overwrite who had recorded the consent); the three use cases share one base that
loads the patient under `FOR UPDATE`; the opt-out race test had a bug (the second thread was never
started until the first finished, so a barrier waited forever and the run hung for half an hour). It
is fixed, and `pytest-timeout` (pinned, dev only) now fails any API test over 120 s with every
thread's stack, plus a `timeout-minutes` limit on every CI job.
---
## M2-P2 — Register, edit and look up patients

**Status: approved, implemented and confirmed by the developer 3 Oct 2026.** Covers FR-PAT-01, 02, 03, 04
and the staff side of 06; spec patients R1–R3, R5, R7, R9, R10, AC1, AC2, AC3, AC6, AC7. Four
endpoints, four use cases, two audit actions, contract 0.6.0, and a few synthetic patients in
`make seed` so the phase can be tried by hand. No web (P5), no consent writes (P3), no import (P4).

### Concepts

1. **Lock first, decide second (R9).** `RegisterPatient` opens one transaction and takes the
   clinic row `FOR UPDATE` before it looks at anything else. A second registration for the same
   clinic queues on that lock, and when it gets in, the first one's patient is already committed
   and visible, so the duplicate check sees it. That is why AC6 ("exactly one of two simultaneous
   registrations wins") holds without a unique index on phone, which families must be allowed to
   share.
2. **Refusals must not spend a number.** The duplicate check runs *before* the code is taken.
   `PAT_PHONE_EXISTS` is raised with the counter untouched, the transaction rolls back, and no
   code is wasted. Only a registration that will succeed advances `next_patient_seq`.
3. **A 409 that carries data.** `PAT_PHONE_EXISTS` is not just "no": it returns up to 10 candidate
   summaries (id, code, name, age) so the front desk can choose "Use this patient" or "Register
   new family member". The names are in the response body for the signed-in staff member and
   nowhere else: not in the log line (`patient.duplicate_phone_offered` records a count), not in
   the audit trail, not in the exception message.
4. **PII stays out of everything but the response.** The audit row for an edit lists the
   *names* of the changed fields, never values. Log lines carry the patient's ID and code.
5. **"Today" is the clinic's today.** The age shown and the under-18 rule use the clinic-local
   date (`clock.now()` in the clinic's zone), not the server's. A small domain helper does the
   conversion once.

### Endpoints (all need `PATIENTS_MANAGE`, which every clinic role holds; ops are refused, R10)

| Method | Path | Behaviour |
|---|---|---|
| POST | `/api/v1/patients` | Register. Body: `full_name`, `phone`, `sex`, `date_of_birth` *or* `age_years`, `guardian_name`?, `language`?, `confirm_new`? (default false). `201` with the patient; `409 PAT_PHONE_EXISTS` with `details.candidates` unless `confirm_new`; `422 PAT_PHONE_INVALID`, `PAT_GUARDIAN_REQUIRED` or field errors |
| GET | `/api/v1/patients?q=` | Lookup (R5): phone, then code, then name prefix; at most 20, ordered by name. Blank `q` returns an empty list; a missing `q` is `422` |
| GET | `/api/v1/patients/{patient_id}` | One patient; another clinic's ID is `404 REQ_NOT_FOUND` |
| PATCH | `/api/v1/patients/{patient_id}` | Correct demographics (name, phone, sex, date of birth or age, guardian, language). At least one field; the code never changes. A blank `guardian_name` clears it (refused for a minor). `200` with the patient |

The patient body: `id`, `code`, `full_name`, `phone_e164`, `sex`, `date_of_birth`, `age_years`
(as of the clinic's today), `age_is_estimated` (true when only an age was recorded), `is_minor`,
`guardian_name`, `language`, `whatsapp_consent`, `sms_consent`, `opted_out`,
`consent_recorded_at`, `created_at`, `updated_at`. Consent is shown here and written in P3.
Phone numbers are shown in full: staff must dial them (`apps/web/CLAUDE.md`).

Clinic creation (ops): `POST /ops/clinics` accepts an optional `patient_code_prefix` (2–4 upper-case
letters, otherwise derived from the name), and `Clinic` responses show it. The wizard field is P5.

### Use cases (`application/patients/`)

| Use case | Steps, all in one transaction |
|---|---|
| `RegisterPatient` | Lock clinic → parse phone (`PAT_PHONE_INVALID`) → find patients on that phone (limit 10) → if any and not `confirm_new`: log a count and raise `PhoneExists(candidates)` → take the next code → `Patient.create` → add → save the clinic counter → `patient.created` audit → record the checklist's `patients_imported_at` the first time → commit |
| `UpdatePatient` | Load through the clinic scope (`404` otherwise) → `Patient.update_details` → save → if any field changed, one `patient.updated` row listing field names → commit; an edit that changes nothing records nothing |
| `GetPatient` / `LookupPatients` | Read-only; lookup classifies the text with the P1 function and calls the matching repository method |

`patient.created` and `patient.updated` join the closed audit catalogue; entity type `patient`,
entity ID the patient, `clinic_id` from the request. Metadata: the code (not PII) and, for an
edit, the comma-joined field names.

### Decisions

| Decision | Reason |
|---|---|
| Reads use `PATIENTS_MANAGE` too | Every clinic role already holds it; a separate view permission would be a second name for the same set until a role differs. The PRD §8.1 matrix stays normative and the permission table test still covers it |
| Editing a phone does not run the duplicate check | R2 is about creating. A correction that lands on a family's shared number is normal, and blocking it would send staff to re-register |
| Guardian cleared by a blank string, absent means unchanged, `null` means unchanged | JSON has no third state; this keeps PATCH idempotent and the domain rule (`update_details`) already matches |
| No `Idempotency-Key` yet | `API.md` plans it for creating POSTs, but nothing in M1 implements it. The phone check already stops an accidental double submit (the second is `PAT_PHONE_EXISTS`), and the drawer in P5 disables its button while submitting. It becomes its own change when a create cannot be made safe by data (bookings in M3) |
| The candidate list is capped at 10 and ordered oldest first | Spec R2; it is bounded so a shared clinic phone cannot return a thousand patients |
| `make seed` creates six synthetic patients in `sample-clinic` when it has none | A family sharing a number, a child with a guardian, an age-only adult, so every behaviour in this phase can be tried by hand; idempotent by "clinic has no patients" |
| The 409 body goes through the existing error envelope | `details.candidates` is a list, so the delivery mapper gains a branch like the one for validation `fields`; the message stays generic |

### Files

| Layer | Files |
|---|---|
| Domain | `audit/actions.py` (+2), `shared/time.py` (`local_date`), `patients/patient.py` (`PhoneInvalid`, `PhoneExists`) |
| Application | `patients/{register_patient,update_patient,queries}.py`, `clinics/onboard_clinic.py` (`patient_code_prefix`) |
| Delivery | `http/patients.py` (blueprint, four routes, `@clinic(PATIENTS_MANAGE)`), `errors.py` (status + candidates), `http/ops.py` and `bodies.py` (the prefix), `bootstrap.py` |
| Contract / docs | `openapi.yaml` 0.6.0, `API.md`, `ERRORS.md` (`PAT_PHONE_INVALID`, `PAT_PHONE_EXISTS`), `DATA_MODEL.md` (audit actions), `RUNBOOK.md` §1 (seed patients), spec §7, CHANGELOG |
| Seed | `delivery/cli/seed.py` |

### Tests

- **Register (HTTP, real PostgreSQL):** 201 with code `SC-0001` and the clinic-local age; the next is
  `SC-0002`; a minor needs a guardian (AC2) and an adult does not; a bad phone is
  `PAT_PHONE_INVALID` without echoing the value; `090000 00001` finds the patient on
  `+919000000001` (AC1) and `confirm_new` registers the second one; the audit row exists in the
  same transaction and holds the code, no name and no phone; the first registration writes
  `patients_imported_at` and later ones do not move it.
- **Race (AC6, AC3):** two threads registering the same new phone: exactly one `201`, one `409`;
  forty parallel registrations with `confirm_new` get unique, gap-free codes; a refused
  registration spends no number.
- **Edit:** changes only what is sent; the audit row lists field names; an edit that changes
  nothing writes no row; a minor cannot lose the guardian; the code is immutable.
- **Lookup (R5):** phone, code (any case, with or without hyphen), name prefix, the 20 cap, blank
  and missing `q`.
- **Tenancy (AC7):** every new route with an ID joins `CROSS_TENANT_CASES`; another clinic's patient
  is 404 by ID, absent from lookups by phone, code and name; ops and unauthenticated callers are
  refused; the permission matrix test covers the four routes.
- **No PII in logs:** a captured-log test registers and edits a patient and finds neither the name
  nor the phone in any line.
- **Contract:** every operation and the 409 candidate shape; `make contract-check` for the regenerated
  web types.

### Verify

```bash
make up && make seed            # seed adds six synthetic patients to sample-clinic
# as desk@sample-clinic.example (RUNBOOK §1):
#   GET  /api/v1/patients?q=90000          -> matches by phone
#   POST /api/v1/patients {...existing phone...}             -> 409 with candidates
#   POST /api/v1/patients {... "confirm_new": true}          -> 201, next code
#   POST a 6-year-old without guardian_name                  -> 422 PAT_GUARDIAN_REQUIRED
#   PATCH /api/v1/patients/<id> {"full_name": "..."}         -> 200
# make psql: select action, metadata from audit_events where action like 'patient.%';
#            -> codes and field names, no names or phones
make lint typecheck test
```

### Risks

| Risk | Mitigation |
|---|---|
| A long-held clinic lock slows registrations | The transaction does one indexed read, one insert and two small updates; the concurrency test registers forty in a row and the lock is held for milliseconds |
| Candidate names leaking into logs or audit through an exception | The error carries candidates as an attribute used only by the response mapper; a test captures every log line and the audit table |
| The clinic-local date drifting from the API's | One helper, tested across the midnight boundary of `Asia/Kolkata`, as `DEBUGGING.md` §5.4 warns |

---
### Result (3 Oct 2026)

make lint typecheck test equivalents in WSL: ruff, format, import-linter and mypy clean; 723 API
tests pass (59 new: HTTP, race, contract, seed, clinic prefix, local date) at 99.0% package
coverage; web types regenerated, 25 files / 256 tests, tsc and ESLint clean, no web code changed.
The race test runs six rounds of two threads on one new phone and gets exactly one `201` and one
`409` each time; thirty parallel registrations on six clients get `SC-0001`..`SC-0030` with no gap;
a log-capture test registers, duplicates, edits and looks up a patient and finds no name or phone in
any line. On compose, through the web origin: lookup by phone, by code (`sc-3`) and by name prefix;
the duplicate 409; `confirm_new` took `SC-0007` (the refusal had taken nothing); a 6-year-old without
a guardian is `PAT_GUARDIAN_REQUIRED`; ops get 403; the audit rows hold the code and the changed
field name only.

Taken while implementing: `PhoneInvalid` subclasses `InvalidValue`, so `PAT_PHONE_INVALID` reuses
the `details.fields` shape and the web can put it beside the phone field; the candidate list
travels on the exception for the response mapper only, and the view classes hide names and phones
from `repr`; the seed's module-entry test now cleans up after itself, because leftover clinics made
later seed tests order-dependent.

---

## M2-P1 — Patient domain, table and lookup indexes

**Status: designed 3 Oct 2026 and implemented on the strength of the developer's instruction to start
M2 with the recommended decisions (D1–D6 in the spec).** Covers FR-PAT-01, 03, 04 (the data
side), FR-PAT-05/06 (the model), NFR-08; spec I1–I4, R1 (domain), R3, R4, R5 (classification), R9
(the lock order is a P2 use-case rule; P1 provides the lockable clinic counter).

### Concepts

1. **A tenant table, once more.** `patients` carries `clinic_id` and is reached only through a
   `TenantScopedRepository`, exactly like doctors. The permanent tenancy suite already fails when a
   `clinic_id` table has no scoped repository, so this phase has to extend it, not work around it.
2. **The clinic row is the serialisation point.** The clinic holds `next_patient_seq`. To register
   a patient, P2 locks the clinic row (`SELECT … FOR UPDATE`), checks the phone, takes the next
   number and inserts, in one transaction. Two staff members registering at once queue on that
   lock, so codes are gap-free and the duplicate check cannot be raced (spec R9, AC3, AC6). P1
   provides what P2 needs: a `for_update` read of the clinic, a counter on the `Clinic` entity, and
   the repository.
3. **Age is a fact plus a date.** A date of birth never changes; "age 6" does, every year. So we
   store a date of birth *or* an age with the clinic-local date it was recorded on, and compute
   `Age.years(on)` whenever it is needed. The "under 18" rule uses the date the question is asked
   about, not a cached number.
4. **An index must match the query.** Lookup is by exact phone, exact code, or case-insensitive
   name *prefix*. A plain index on `full_name` cannot serve `lower(full_name) LIKE 'ab%'`; an
   expression index with `text_pattern_ops` can. The perf test proves the plan uses the indexes at
   10,000 rows, instead of trusting the design.
5. **PII stays out of the safety nets.** Patient names and phones never appear in `repr`, errors,
   logs or audit metadata. `PhoneNumber` already masks itself; `Patient.__repr__` shows only the
   code and the clinic.

### Domain (`domain/patients/`, standard library only)

| Piece | What it does |
|---|---|
| `Patient` (entity) | `create(...)` validates I1–I4 and R3 (guardian for a minor); `update_details(...)` re-checks them; `record_consent(...)`, `opt_out(...)`, `opt_in(...)` hold the R6 state machine (used by P3's endpoints). Rehydrates through the constructor like the other entities |
| `Age` (value) | `from_birth_date`, `from_recorded_age`; `years(on)`; `is_minor(on)`; validates I4 (not in the future, 0–120) |
| `PatientCode` helpers | `format_code(prefix, seq)` (`ME-0142`, at least 4 digits, grows past 9999), `derive_code_prefix(name)`, `validate_code_prefix`, `looks_like_code(text)` |
| `classify_query(q)` | Spec R5 as a pure function: `PHONE` / `CODE` / `NAME`, with the normalised value |
| `Sex`, `Language` | `StrEnum`s mirrored by DB `CHECK`s |
| errors | `GuardianRequired` → `PAT_GUARDIAN_REQUIRED` (422) |
| `Clinic` (changed) | Gains `patient_code_prefix` and `next_patient_seq`, and `allocate_patient_code()` which returns the next code and advances the counter. The prefix is derived from the name at creation and cannot change once a patient exists (R4) |

### Ports and adapters

- `PatientRepository` (tenant-scoped): `add`, `get`, `update`, `get_by_code`,
  `find_by_phone(phone, limit)`, `search_by_name_prefix(prefix, limit)`, `count`. Every query starts
  from `_scoped_select()`.
- `ClinicRepository.get(clinic_id, *, for_update=False)`; `update` persists the counter.
- `TenantRepositories` gains `patients`; `SqlAlchemyTenantRepositories` and the test fakes follow.
- Migration `0006` (expand-only): `clinics.patient_code_prefix` (backfilled from each clinic's name)
  and `clinics.next_patient_seq`; the `patients` table with its constraints and indexes.

### Schema

`patients`: `id`, `clinic_id`, `code`, `full_name`, `phone_e164`, `sex`, `date_of_birth`,
`age_years_at_registration`, `registered_on`, `guardian_name`, `language`, `whatsapp_consent`,
`sms_consent`, `consent_recorded_at`, `consent_recorded_by`, `opted_out_at`, `created_by`,
`created_at`, `updated_at`.

| Constraint / index | Why |
|---|---|
| `uq_patients_clinic_id_code` | I3: a code is unique within a clinic (also serves code lookup) |
| `ix_patients_clinic_id_phone_e164` | Exact phone lookup and the duplicate check |
| `ix_patients_clinic_id_lower_full_name` on `(clinic_id, lower(full_name) text_pattern_ops)` | Name-prefix lookup |
| `ck_patients_sex`, `ck_patients_language` | Enum columns as `text` + `CHECK` |
| `ck_patients_age_known` | A date of birth or a recorded age is required (I1) |
| `ck_patients_age_years_at_registration_range` | 0–120 (I4) |
| `ck_patients_consent_recorded` | Consent flags true only with a `consent_recorded_at` (R6) |

The `tags` column listed in `DATA_MODEL.md` is left out: it serves FR-PAT-07 (P1 priority), and a
column no code reads is a column that drifts. It joins the table when advanced search does.

### Decisions

| Decision | Reason |
|---|---|
| The code counter lives on `Clinic`, advanced by a domain method and persisted by the clinic repository under a row lock | The invariant (gap-free, never reused) belongs to the clinic; a separate sequence table would add a second thing to lock and keep in step |
| `derive_code_prefix` uses word initials, falling back to the first letters of the name, then `CL` | Deterministic and explainable to ops; ops can override at creation in P2 |
| The migration backfills existing clinics in Python, with its own copy of the derivation | Migrations must not import application code that may change later; the backfill is a one-off |
| `registered_on` is the clinic-local date, supplied by the use case (P2) from the clock and the clinic's timezone | The domain does no time-zone arithmetic beyond what it is given (CLAUDE.md "Time is explicit") |
| Perf test inserts 10,000 rows with one bulk `INSERT`, then times lookups through the repository and checks the plan with `EXPLAIN` | Bulk insert keeps the test near a second; timing through the repository measures what P2 will serve; `EXPLAIN` fails loudly if an index stops matching |
| No seed data or endpoints in P1 | Nothing can create a patient until P2 |

### Files

| Layer | Files |
|---|---|
| Domain | `patients/{patient,age,code,lookup}.py`, `clinics/clinic.py` (counter and prefix) |
| Ports | `repositories.py` (`PatientRepository`, `ClinicRepository.get(for_update)`), `unit_of_work.py` |
| Adapters | `db/models/patients.py`, `db/models/clinics.py`, `db/repositories.py`, `db/unit_of_work.py`, migration `0006` |
| Tests | `unit/domain/test_patients.py`, `integration/db/test_patients.py` (repository + 10,000-patient lookup), `tenancy/test_repository_scoping.py`, `integration/db/test_migrations.py` |
| Docs | `DATA_MODEL.md`, `ERRORS.md`, `CHANGELOG.md`, `TASKS.md`, `NEXT_STEPS_PLAN.md` |

### Tests

Domain: phone and name rules; age from a birth date and from a recorded age (birthdays, leap day,
years elapsing since registration); the minor/guardian rule at the boundary (17 vs 18); consent and
opt-out transitions; code formatting and prefix derivation; query classification (table-driven,
including short digit strings and codes with and without a hyphen); clinic counter allocation.
Integration (PostgreSQL): round trip through the repository; code uniqueness; constraints refuse
bad rows; migration `0006` up and down, including the backfill; the 10,000-patient lookup with p95
and the query plan. Tenancy: clinic A's repository cannot read, find by phone or code, list or
update clinic B's patients and refuses a foreign entity; the "every tenant table has a scoped
repository" guard now includes `patients`.

### Verify

```bash
make lint typecheck test   # includes the 10,000-patient lookup test
make up                    # migrate applies 0006; existing clinics get a prefix
make psql                  # \d patients ; select slug, patient_code_prefix, next_patient_seq from clinics;
```

---

### Result (3 Oct 2026)

`make lint typecheck test` equivalents in WSL: ruff, format, import-linter and mypy clean; 664 API
tests pass (65 new: domain, repository, constraints, migration, tenancy, concurrency, lookup) at
99.1% package coverage. Lookup over 10,000 patients, p95 on a developer laptop: phone 0.8 ms, code
0.7 ms, name prefix 1.8 ms, against the 500 ms budget; the repository's own SQL for all three plans
without a sequential scan. Forty registrations on eight threads received codes `PF-0001` to
`PF-0040` with no gap or repeat. Migration `0006` backfills existing clinics (`Sample Clinic` ->
`SC`) and round-trips. Not in P1 by design: endpoints, audit events, seed patients (P2 onward).

Known limitation: Alembic cannot compare an expression index that carries an operator class and
prints a warning for `ix_patients_clinic_id_lower_full_name`; the lookup test guards the index
instead (it fails if the index stops matching the query).
