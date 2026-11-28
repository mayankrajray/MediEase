# Spec: Patient data requests (export and erasure)

| Field | Value |
|---|---|
| Requirements | DPDP data principal rights (PRD §9: access, erasure via the clinic), FR-AUD-01 (data exports audited), NFR-07 |
| Milestone / phases | M9 / P3 (design `docs/milestones/M9-deploy-demo.md` §12) |
| Status | Implemented 28 Nov 2026 |
| Owner | Developer |
| Last updated | 2026-11-28 |

## 1. Context
A patient may ask their clinic for their data or to be erased. The clinic is the Data Fiduciary
and answers; MediEase, the processor, carries out the clinic owner's written request. Decisions
(developer, 27 Nov 2026): a support command on the VM, not an owner button; erasure anonymises
and keeps the clinical record; the export is a password-protected zip.

## 2. Actors and permissions
| Actor | Can | Cannot |
|---|---|---|
| MediEase support on the VM | Run `make patient-data` on the owner's written request | Act without it; reach this from any HTTP route (there is none) |
| Clinic owner | Ask, receive the file, tell the patient | Run it themselves (later, if needed) |

## 3. Behaviour
- **R1** `export <slug> <code>` writes a new owner-only AES-256 zip: `README.txt`,
  `record.json` (format `mediease-patient-export/1`; every row about the patient by table, minus
  ciphertext and token digests) and the stored prescription PDFs and visit reports. The password
  is printed once. An existing file is never overwritten.
- **R2** `erase` is refused while the patient has an active appointment today or later, or an open
  booking request; for an erased patient; and unless the code is typed again (or `--confirm`).
- **R3** Erasure, in one transaction: the patient row is anonymised (name "Erased patient", a
  non-mobile placeholder phone, no date of birth but the age at registration, no guardian, no
  consents, opted out); scheduled reminders cancelled; the phone on messages emptied; booking
  requests lose phone, age, sex and reason; patient links and app links revoked, unused invites
  withdrawn; reminder choices and dose marks deleted; staff notification titles say
  "Erased · <code>". A family member sharing the phone keeps it.
- **R4** Kept under the code: visits, addenda, prescriptions and items (immutable), bills, lines,
  payments, reports, the audit log. Stored prescription and receipt PDFs are deleted after the
  commit; a later download draws them again from the anonymised row.
- **R5** Both are audited on the clinic's log (`patient.data_exported`, `patient.erased`, actor
  SYSTEM) with the code and counts; nothing about the patient is printed or logged but the code.

## 4. Acceptance criteria
- **AC1** An export of a demo patient opens only with its password and holds their visits,
  prescriptions, items, bills, lines and appointments, with no ciphertext or token digests.
- **AC2** After erasure no clinic row holds the patient's name or their phone (but a family
  member's own row), their visits and prescriptions are all still there, the stored PDFs are gone,
  another patient is untouched, and a second erasure is refused.
- **AC3** A patient booked tomorrow cannot be erased; a mistyped code changes nothing.

Tests: `tests/integration/test_patient_data.py`.

## 5. Out of scope
An owner-facing button; deleting the person's own patient app account (FR-PRT-10); erasing
clinical records (only after the retention period, with counsel).
