# M2 — Patients: design notes

| Field | Value |
|---|---|
| Status | In progress — M2-P1 implemented 3 Oct 2026, awaiting confirmation; P2 next |
| Spec | `docs/specs/patients.md` (Approved 2026-10-03) |
| Covers | FR-PAT-01..06, FR-PAT-08, FR-MSG-05 (opt-out state), NFR-08 |
| Issue / branch / PR | #21 · `m2/21-patients` · one PR for the whole milestone (ADR-0011) |
| Exit criterion | Register, find and update patients; a shared phone is surfaced, not silently duplicated; lookup over 10,000 patients has p95 < 500 ms |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Patient domain, clinic code allocation, migration `0006`, tenancy-scoped repository, indexes, the 10,000-patient lookup test | Below |
| P2 | Register / edit / lookup endpoints, the duplicate-phone flow, `patient_code_prefix` on clinic creation | Designed at its start |
| P3 | Consent, language preference, opt-out and opt-in | Designed at its start |
| P4 | Ops CSV import with a dry-run report | Designed at its start |
| P5 | Web: global search, registration drawer, profile | Designed at its start |

Each phase is designed, approved, implemented, verified and confirmed before the next starts.

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
