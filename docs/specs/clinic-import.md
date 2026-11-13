# Spec: Clinic import from CSV files

| Field | Value |
|---|---|
| Requirements | FR-ORG-01..03 (clinic, people, doctors), FR-PAT-01, FR-APT-01, FR-VIS-01, FR-RX-01, FR-BIL-02..03, FR-REM-01 (as data); NFR-16 (no real data outside production) |
| Milestone / phases | M9-P1 / C2 (design `docs/milestones/M9-deploy-demo.md`) |
| Status | Implemented 13 Nov 2026 |
| Owner | Developer |
| Last updated | 2026-11-13 |

## 1. Context
The Phase 2 demo needs a clinic that looks like a real partner's: people, two weeks of visits,
prescriptions, bills and follow-ups, and upcoming appointments. The design partners' own usage
will be prepared the same way. The developer fills CSV files (from Excel or Google Sheets, saved
as **CSV UTF-8**) and runs the import on the server; the files never pass through an AI tool or
the repository. A complete invented example ships in
`apps/api/src/mediease_api/delivery/cli/demo_clinic/`: copy that folder and edit it.

## 2. Running it
| Where | Command |
|---|---|
| Locally, the bundled demo | `make import-clinic DEMO=1` |
| Locally, your folder | `make import-clinic DIR=/path/to/folder` (add `DRY_RUN=1` to only check) |
| On the server | RUNBOOK §37 (the folder is mounted read-only into a one-off API container) |

## 3. Behaviour
- **R1** One transaction. Any problem stops the import, writes nothing, and names the file, line
  and column (`visits.csv line 4, column doctor_email: is not a doctor in staff.csv`). The value
  itself is never printed or logged.
- **R2** Refused when the clinic's slug or any login email already exists. A clinic is imported
  once; to redo it, use a new slug (or restore the database).
- **R3** In staging and production the slug must be typed to confirm (or given with
  `--confirm <slug>`). `--dry-run` checks everything and writes nothing.
- **R4** Each login gets a generated 16-character password (or `--password` for all, at least 12
  characters). Passwords are hashed with Argon2id and printed once, at the end. Patient app logins
  are created with the email already verified and linked to their patient record.
- **R5** Everything goes through the domain's rules: a visit is booked into its doctor's session
  of that day (from `schedules.csv`), arrives, is seen, written up, prescribed (issued) and billed
  at its own time; bills are numbered in visit order; payments cannot exceed the bill.
- **R6** History is not sent: no prescription link or confirmation is messaged for a past visit.
  A follow-up date still ahead gets its reminder as if the prescription were issued now; an
  upcoming appointment gets its reminders as if booked now (in the app for a linked patient
  login, and on WhatsApp only when messaging is on and the patient agreed).
- **R7** A follow-up date already past, with no visit since, appears in *Pending follow-ups*.
- **R8** An `OPS` row creates the platform ops user who verifies the clinic and its doctors, so
  the public page, search and online booking work. Without one, the clinic stays unverified.
- **R9** The clinic is on the Clinic Plus plan without a trial countdown.

## 4. The files
One folder, one file per kind. The first row is the header (column names in any order; unknown
columns are refused, so a typo is caught). Empty rows and rows whose first cell starts with `#`
are skipped. Several values in one cell are separated by `;`.

**Dates** are `2026-11-10`, or relative to the import day: `today`, `today-3`, `today+2`.
Relative dates keep "the last two weeks" true whenever the import runs. **Times** are 24-hour
`HH:MM`, clinic time (India). **Money** is rupees (`500`, `499.50`). **Yes/no** is `yes` or `no`.
**Phones** are Indian mobile numbers (`+919000000301` or `9000000301`). `ref` columns are your
own short labels (`P01`, `V01`) that other files point to; they are not stored.

### clinic.csv (exactly one row)
| Column | Required | Values |
|---|---|---|
| name | yes | The clinic's name |
| slug | yes | Lower-case words joined by hyphens, 3–63 characters; its public page is `/c/<slug>` |
| phone, address_line, city, state, pincode | no | `pincode`: six digits |
| specialties | no | `General Medicine;Paediatrics` |
| booking_mode | no | `TOKENS` (default) or `SLOTS` |
| consultation_fee_rupees, follow_up_fee_rupees | no | Default prices of the two standard services |

### staff.csv (at least one OWNER)
| Column | Required | Values |
|---|---|---|
| email | yes | The login; unique |
| full_name | yes | Doctors as printed: `Dr. Arjun Mehra` |
| role | yes | `OWNER`, `DOCTOR`, `FRONT_DESK` (or `DESK`), or `OPS` (platform ops, in no clinic) |
| phone | no | |
| practises | no | `yes` makes an OWNER also a doctor; every DOCTOR practises |
| qualification, registration_number, registration_council | for doctors | Printed on every prescription |
| specialty | no | |
| languages | no | From the published list, e.g. `English;Hindi` |

### schedules.csv (each doctor's week)
| Column | Required | Values |
|---|---|---|
| doctor_email | yes | A doctor in staff.csv |
| weekday | yes | `MON` … `SUN` |
| start, end | yes | `10:00`, `13:00` |
| slot_minutes | for SLOTS | 5–120, dividing the block evenly |
| capacity | for TOKENS | 1–500 |

Every visit and appointment must fall inside one of its doctor's blocks on that weekday.

### patients.csv
| Column | Required | Values |
|---|---|---|
| ref | yes | `P01` |
| full_name, phone | yes | Family members may share a phone |
| sex | yes | `FEMALE`, `MALE`, `OTHER`, `UNDISCLOSED` (or `F`, `M`, `O`) |
| date_of_birth *or* age_years | one of them | `1992-04-18`, or a whole number |
| guardian_name | for a minor | |
| language | no | `en` (default) or `hi` |
| whatsapp_consent, sms_consent | no | `yes` / `no` (default no) |

### visits.csv (past visits)
| Column | Required | Values |
|---|---|---|
| ref | yes | `V01` |
| patient_ref, doctor_email | yes | |
| date, time | yes | In the past, inside the doctor's schedule |
| chief_complaint, findings, diagnosis, notes | no | As the doctor wrote them |
| bp_systolic, bp_diastolic, pulse, spo2, resp_rate | no | Whole numbers |
| temp_c, weight_kg, height_cm | no | Numbers |
| follow_up_date | no | After the visit's date (R6, R7) |
| advice_diet, advice_activity, advice_return_if | no | `;`-separated lines |
| advice_notes | no | |

A visit with medicines, advice or a follow-up date gets an issued prescription.

### prescription_items.csv (the medicines of each visit, in order)
| Column | Required | Values |
|---|---|---|
| visit_ref, medicine_name | yes | |
| form, strength, dose, quantity, notes | no | As written |
| frequency | no | `1-0-1`, `1-0-1-1`, `SOS`, `ONCE`, or `CUSTOM` with `frequency_text` |
| timing | no | `BEFORE_FOOD`, `AFTER_FOOD`, `WITH_FOOD`, `EMPTY_STOMACH`, `BEDTIME`, `ANY` |
| duration_days | no | 1–365 |
| duration_kind | no | `DAYS` (with days), `UNTIL_REVIEW`, `ONGOING` |

### bill_lines.csv (one row per line of a visit's bill)
| Column | Required | Values |
|---|---|---|
| visit_ref, description, amount_rupees | yes | The unit price |
| service | no | `CONSULTATION`, `FOLLOW_UP`, `PROCEDURE`, `OTHER` |
| quantity | no | Default 1 |
| discount_rupees | no | Off this line |

### payments.csv
| Column | Required | Values |
|---|---|---|
| visit_ref, mode | yes | `CASH`, `UPI`, `CARD` |
| amount_rupees | no | Empty pays the whole balance; a visit without a row stays unpaid |
| reference | no | A UPI or card reference |

### appointments.csv (upcoming)
| Column | Required | Values |
|---|---|---|
| patient_ref, doctor_email, date | yes | Today or later |
| time | for SLOTS | In TOKENS mode, empty means the day's first session that has not ended |
| reason | no | |

### portal_accounts.csv (patient app logins)
| Column | Required | Values |
|---|---|---|
| email, patient_ref | yes | One login per patient record; not a staff email |

## 5. Not imported
Audit history (the import itself is not audited per row), visit addenda and attachments,
uploaded prescriptions, medicine reminders, notification history, credit notes and refunds,
staff invitations. They are created by using the app.

## 6. Acceptance criteria
- **AC1** The bundled demo imports into an empty database: 20 patients, 26 completed visits, 24
  issued prescriptions, 26 issued bills numbered in order, 23 payments, 10 upcoming appointments,
  4 pending follow-ups, 3 follow-up reminders, 1 linked patient login
  (`tests/integration/test_import_clinic.py`).
- **AC2** A second run is refused and changes nothing.
- **AC3** A wrong doctor email or a visit outside every session is reported with file, line and
  column, without the value, and nothing is written.
- **AC4** Production asks for the slug; a wrong answer writes nothing.
