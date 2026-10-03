# Spec: Patients

| Field | Value |
|---|---|
| Requirements | FR-PAT-01..06, FR-PAT-08, FR-MSG-05 (opt-out state), NFR-08 |
| Milestone / phases | M2 / P1–P5 |
| Status | Approved (developer sign-off 2026-10-03: minors' contact of record is the guardian's phone; the recommendations in §12 accepted) |
| Last updated | 2026-10-03 (approved; decisions D1–D6 recorded in §12; R2 made race-free, R3/R4/R9 tightened, age model and lookup rules specified) |

## 1. Context
Records are on paper and unreadable during a consultation (A11, A12). Families often share one
phone, and paediatric clinics (A3) deal with parents, not patients.

## 2. Actors and permissions
Owner, doctor and front desk can register, view and edit demographics and consent. Ops can import
via CSV but cannot browse patients. Every patient row belongs to one clinic; another clinic's
patient is `404 REQ_NOT_FOUND` (NFR-08, spec identity-and-tenancy R8).

## 3. Domain model
`Patient` (tenant-owned) with value objects:
- `PhoneNumber` — E.164, India default region (already in the domain).
- `Age` — from a date of birth, or from an age recorded on `registered_on` (the clinic-local date
  of registration). `Age.years(on)` is a whole number of years on any date: with a date of birth it
  is the completed years; with a recorded age it is that age plus the whole years elapsed since
  `registered_on`. One of the two is required (`ck_patients_age_known`).
- `PatientCode` — `<prefix>-<sequence>`, e.g. `ME-0142`.
- `Consent` — `whatsapp`, `sms`, `recorded_at`, `recorded_by`; `opted_out_at`.
- `Language` — `en`, `hi`; `Sex` — `FEMALE`, `MALE`, `OTHER`, `UNDISCLOSED`.

The clinic holds `patient_code_prefix` (2–4 upper-case letters) and `next_patient_seq`.

**The contact of record** is the patient's `phone_e164`. For a patient under 18 it is the
guardian's phone, `guardian_name` names the guardian, and consent is recorded against the guardian
(FR-PAT-06). There is no separate guardian phone field.

Invariants:
- **I1** A patient has a name (1–200 characters after trimming), a valid phone, a sex, and either a
  date of birth or a recorded age.
- **I2** A patient under 18 has a `guardian_name`.
- **I3** `(clinic_id, code)` is unique and codes are never reused or edited.
- **I4** A date of birth is not in the future; a recorded age is 0–120.

## 4. Behaviour
- **R1** Phone input is normalised: spaces, dashes and a leading `0` are removed; 10-digit Indian
  mobiles get `+91`. Invalid input → `PAT_PHONE_INVALID`.
- **R2** Creating a patient whose phone already exists in the clinic returns
  `409 PAT_PHONE_EXISTS` with up to 10 candidate summaries (id, code, name, age) unless the request
  has `confirm_new: true`. The candidates are in the response body for the signed-in staff member
  only: never in logs, audit rows or error messages.
- **R3** If the computed age on the registration date is under 18, `guardian_name` is required
  (`PAT_GUARDIAN_REQUIRED`); the phone is the guardian's. Editing a patient re-checks this.
- **R4** Codes are `<prefix>-<zero-padded sequence>` (at least 4 digits, growing past 9999), never
  reused. The prefix is 2–4 upper-case letters; ops may set it when creating the clinic, otherwise
  it is derived from the clinic name (initials, padded from the name's letters). It cannot change
  once the clinic has a patient.
- **R5** Lookup `q` is interpreted in order: looks like a phone (7 or more digits once spaces,
  dashes and `+` are removed) → exact match on the normalised number; matches the code pattern
  (2–4 letters, optional hyphen, digits) → exact code match; otherwise case-insensitive name
  prefix. Maximum 20 results, ordered by name.
- **R6** Consent defaults to false and "not asked" (`consent_recorded_at` null) differs from "asked and
  declined" (recorded, both false). Setting consent records who and when, and for a minor it is the
  guardian's. Opt-out sets `opted_out_at` and overrides consent until the patient opts back in
  through the clinic with the explicit opt-in action, which takes the new consent. Consent cannot
  be edited while opted out (`PAT_OPTED_OUT`, M2-P3 decision A), and opt-in without an opt-out is
  `PAT_NOT_OPTED_OUT`.
- **R7** Editing demographics never changes the code. All edits are audited (`patient.updated`
  with changed field names only, not values).
- **R8** CSV import (ops): columns `name, phone, sex, dob_or_age, guardian_name, language`;
  dry run returns counts of valid, invalid (with row numbers and reasons) and possible duplicates;
  commit imports valid rows only and sets consent false.
- **R9** Creating a patient is serialised per clinic: the clinic row is locked first, then the
  phone is checked, then the code is allocated and the patient inserted, all in one transaction.
  Two staff members registering the same phone at the same moment therefore cannot both pass the
  duplicate check, and codes are gap-free except for rolled-back transactions.
- **R10** A phone number is required: a child with no guardian phone cannot be registered. The
  clinic records the number of whoever answers for the child.

## 5. API surface
See API.md "Patients" and "Ops console".

## 6. UI notes
- Global search bar on every clinic screen (keyboard shortcut `/`).
- Registration drawer: name, phone, age/DOB, sex; guardian field appears when age < 18 and the
  phone label changes to "Parent or guardian's phone".
- Duplicate phone: list existing patients with "Use this patient" and "Register new family member".
- Consent toggles with a short script the front desk can read aloud.

## 7. Events and side effects
| Trigger | Audit | Analytics |
|---|---|---|
| Create / update / consent change / import | `patient.created` / `patient.updated` / `patient.consent_changed` / `patient.imported` | — |
| Opt-out / opt-in | `patient.opted_out` / `patient.opted_in` | `patient_opted_out` (a log event until M6) |

The first import or registration also writes the onboarding checklist's `patients_imported_at`
(FR-OPS-04; the first registration sets it when no import happened).

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| Landline number | Accepted if valid E.164; WhatsApp sends will fail → SMS fallback later |
| DOB in the future | 422 `REQ_VALIDATION_FAILED` |
| Only age known | Stored as age at registration; displayed age advances with time |
| Two front-desk users create the same patient simultaneously | The second waits for the first (R9) and gets `PAT_PHONE_EXISTS` unless `confirm_new` |
| A child turns 18 | The guardian name stays; nothing forces a change |
| A child with no guardian phone | Refused (R10): the clinic records a number that answers for the child |
| Another clinic's patient ID or code | `404 REQ_NOT_FOUND`; never a 403 (identity-and-tenancy R8) |
| Lookup text that is digits but too short for a phone (`0142`) | Not a phone, and not a code (a code always has its letters): read as the start of a name |

## 9. Acceptance criteria
- **AC1 (FR-PAT-02)** Given a patient on `+919000000001`, when registering with `090000 00001`,
  then 409 `PAT_PHONE_EXISTS` lists that patient.
- **AC2 (FR-PAT-06)** Given DOB making the patient 6 years old and no guardian, then 422
  `PAT_GUARDIAN_REQUIRED`.
- **AC3 (FR-PAT-03)** Given 1,000 concurrent-ish creations, then codes are unique and gap-free per
  clinic except for rolled-back transactions.
- **AC4 (FR-PAT-04)** Given 10,000 patients in one clinic, then lookup p95 < 500 ms in the perf test.
- **AC5 (FR-PAT-05)** Given an opted-out patient, then `whatsapp_consent` edits do not re-enable
  sending until `opted_out_at` is cleared through the explicit opt-in action.
- **AC6 (FR-PAT-02, R9)** Given two simultaneous registrations of the same new phone without
  `confirm_new`, then exactly one succeeds and the other is `409 PAT_PHONE_EXISTS`.
- **AC7 (NFR-08)** Given patients in clinics A and B, then A's staff cannot read, list, find by
  phone or code, or edit any of B's patients (404 / absent from lists).

## 10. Observability
Events: `patient.duplicate_phone_offered`, `patient.import_dry_run` (counts only).
Never log names or unmasked phones.

## 11. Out of scope
Patient merge, advanced filters (P1), patient self-registration, a separate guardian phone,
editing a clinic's code prefix once it has patients.

## 12. Decisions and open questions
Resolved at approval (2026-10-03):
- **D1** Under-18s belong to the guardian's phone: the contact of record and the consent are the
  guardian's (developer's decision).
- **D2** The code prefix is per clinic, set when the clinic is created (optional, derived from the
  name otherwise), fixed once the clinic has patients.
- **D3** The duplicate-phone check is race-free by construction (R9), and `confirm_new` is the only
  way to register a second person on a shared phone.
- **D4** Age is stored as a date of birth or an age plus the registration date, and computed on
  read (`Age.years(on)`).
- **D5** Audit rows and logs never hold names or phone numbers; `patient.updated` lists field
  names only.
- **D6** Phase order: P1 domain, migration, indexes and the 10,000-patient lookup test; P2 the
  endpoints and duplicate flow; P3 consent and opt-out; P4 import; P5 web.

Still open (post-pilot): should the clinic be able to record consent on paper and upload proof?
