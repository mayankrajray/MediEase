# Spec: Patients

| Field | Value |
|---|---|
| Requirements | FR-PAT-01..06, FR-PAT-08, FR-MSG-05 (opt-out state) |
| Milestone / phases | M2 / P1–P5 |
| Status | Draft |
| Last updated | 2026-09-15 |

## 1. Context
Records are on paper and unreadable during a consultation (A11, A12). Families often share one
phone, and paediatric clinics (A3) deal with parents, not patients.

## 2. Actors and permissions
Owner, doctor and front desk can register, view and edit demographics and consent. Ops can import
via CSV but cannot browse patients.

## 3. Domain model
`Patient` with value objects `PhoneNumber` (E.164, India default region), `Age` (from DOB or
recorded age + registration date), `Consent` (`whatsapp`, `sms`, `recorded_at`, `recorded_by`),
`Language` (`en`, `hi`). Patient code allocated from the clinic sequence under a row lock.

## 4. Behaviour
- **R1** Phone input is normalised: spaces, dashes and a leading `0` are removed; 10-digit Indian
  mobiles get `+91`. Invalid input → `PAT_PHONE_INVALID`.
- **R2** Creating a patient whose phone already exists in the clinic returns
  `409 PAT_PHONE_EXISTS` with up to 10 candidate summaries (id, code, name, age) unless the request
  has `confirm_new: true`.
- **R3** If computed age < 18, `guardian_name` is required (`PAT_GUARDIAN_REQUIRED`); the phone is
  treated as the guardian's.
- **R4** Codes are `<prefix>-<zero-padded sequence>` (min 4 digits), never reused.
- **R5** Lookup `q` is interpreted in order: looks like a phone → phone match; matches code pattern
  → code match; otherwise case-insensitive name prefix. Maximum 20 results.
- **R6** Consent defaults to false. Setting consent records who and when. Opt-out sets
  `opted_out_at` and overrides consent until the patient opts back in through the clinic.
- **R7** Editing demographics never changes the code. All edits are audited (`patient.updated`
  with changed field names only, not values).
- **R8** CSV import (ops): columns `name, phone, sex, dob_or_age, guardian_name, language`;
  dry run returns counts of valid, invalid (with row numbers and reasons) and possible duplicates;
  commit imports valid rows only and sets consent false.

## 5. API surface
See API.md "Patients" and "Ops console".

## 6. UI notes
- Global search bar on every clinic screen (keyboard shortcut `/`).
- Registration drawer: name, phone, age/DOB, sex; guardian field appears when age < 18.
- Duplicate phone: list existing patients with "Use this patient" and "Register new family member".
- Consent toggles with a short script the front desk can read aloud.

## 7. Events and side effects
| Trigger | Audit | Analytics |
|---|---|---|
| Create / update / consent change / import | `patient.created` / `patient.updated` / `patient.consent_changed` / `patient.imported` | — |
| Opt-out | `patient.opted_out` | `patient_opted_out` |

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| Landline number | Accepted if valid E.164; WhatsApp sends will fail → SMS fallback later |
| DOB in the future | 422 `REQ_VALIDATION_FAILED` |
| Only age known | Stored as age at registration; displayed age advances with time |
| Two front-desk users create the same patient simultaneously | Both succeed only if `confirm_new`; otherwise the second gets `PAT_PHONE_EXISTS` |

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

## 10. Observability
Events: `patient.duplicate_phone_offered`, `patient.import_dry_run` (counts only).
Never log names or unmasked phones.

## 11. Out of scope
Patient merge, advanced filters (P1), patient self-registration.

## 12. Open questions
- Should the clinic be able to record consent on paper and upload proof? (Post-pilot.)
