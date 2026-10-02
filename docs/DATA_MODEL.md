# MediEase — Data Model

Target schema for the MVP (M1–M5). Tables are created milestone by milestone through Alembic;
the **Milestone** column says when each table appears. Update this file in the same change as
any migration.

## Conventions

| Rule | Detail |
|---|---|
| Primary keys | `id uuid` (UUIDv7, time-ordered) |
| Tenancy | Every tenant-owned table has `clinic_id uuid not null references clinics(id)`; composite indexes lead with `clinic_id` |
| Timestamps | `created_at`, `updated_at` as `timestamptz` (UTC) on every table |
| Soft state | Status enums instead of deletes for clinical and appointment data; hard deletes only via the erasure procedure |
| Enums | PostgreSQL `text` + `CHECK` constraint (easier migrations than native enums) |
| Money | `bigint` paise |
| Phones | `text` E.164, validated at the boundary |
| JSON | `jsonb` only for genuinely variable shapes (vitals, advice, payloads); never for data we query by |
| Names | `snake_case`, plural table names |

## Migration history

Alembic revisions in `apps/api/migrations/versions/` (how to add one: `apps/api/migrations/README.md`).

| Revision | Change | Milestone |
|---|---|---|
| `0001` | Empty baseline. Creates no tables; only `alembic_version` exists after `upgrade head` | M0-P3 |
| `0002` | `clinics`, `users`, `clinic_memberships`, `doctors` (columns marked *P1* below; the rest arrive with the phase or milestone that uses them) | M1-P1 |

Constraint names follow one convention (`adapters/db/models/base.py`): `pk_<table>`,
`fk_<table>_<column>_<referred table>`, `uq_<table>_<columns>`, `ck_<table>_<name>`,
`ix_<table>_<columns>`. An `IntegrityError` therefore names the rule that was broken.
`tests/integration/db/test_migrations.py::test_models_match_migrations` fails if the models and
the migrations drift apart.

## Entity-relationship overview

```mermaid
erDiagram
    CLINICS ||--o{ CLINIC_MEMBERSHIPS : has
    USERS ||--o{ CLINIC_MEMBERSHIPS : holds
    USERS ||--o{ REFRESH_TOKENS : owns
    CLINICS ||--o{ DOCTORS : employs
    USERS |o--o| DOCTORS : "may be"
    CLINICS ||--o{ PATIENTS : registers
    DOCTORS ||--o{ DOCTOR_SCHEDULES : defines
    DOCTORS ||--o{ SCHEDULE_EXCEPTIONS : has
    DOCTORS ||--o{ SESSIONS : runs
    SESSIONS ||--o{ APPOINTMENTS : contains
    PATIENTS ||--o{ APPOINTMENTS : books
    APPOINTMENTS ||--o{ APPOINTMENT_STATUS_HISTORY : tracks
    APPOINTMENTS |o--o| VISITS : becomes
    PATIENTS ||--o{ VISITS : attends
    VISITS ||--o{ VISIT_ADDENDA : amends
    VISITS ||--o{ PRESCRIPTIONS : produces
    PRESCRIPTIONS ||--o{ PRESCRIPTION_ITEMS : lists
    PRESCRIPTIONS |o--o| PRESCRIPTIONS : supersedes
    DOCTORS ||--o{ RX_FAVOURITES : saves
    DOCTORS ||--o{ RX_TEMPLATES : saves
    PATIENTS ||--o{ PATIENT_LINKS : receives
    PATIENTS ||--o{ REMINDERS : receives
    REMINDERS |o--o| MESSAGES : sends
    PATIENTS ||--o{ MESSAGES : receives
    CLINICS ||--o{ JOBS : queues
    CLINICS ||--o{ AUDIT_EVENTS : records
```

---

## M1 — Identity, tenancy, audit

Every table has `id uuid` (UUIDv7 from `IdPort`), `created_at` and `updated_at` (`timestamptz`,
set by the application). *P1* = created by migration `0002`.

### `clinics`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | *P1* |
| name | text not null | *P1* Shown in messages and letterhead |
| slug | text unique not null | *P1* `uq_clinics_slug`; lower-case words and hyphens, 3–63 chars; public page URL (M7) |
| timezone | text not null default `Asia/Kolkata` | *P1* IANA name, validated by the domain |
| status | text not null | *P1* `ONBOARDING` \| `ACTIVE` \| `SUSPENDED` (`ck_clinics_status`) |
| phone_e164 | text | *P1* |
| address_line, city, state, pincode | text | *P1* PIN code: 6 digits |
| specialties | text[] not null default `{}` | *P1* |
| patient_code_prefix | text not null | M2 — e.g. `ME` → `ME-0142` |
| next_patient_seq | integer not null default 1 | M2 — incremented under row lock |
| booking_mode | text not null | M3 — `SLOTS` \| `TOKENS` |
| plan | text not null default `PILOT` | Billing (post-pilot) — `PILOT` \| `STARTER` \| `CLINIC` |

### `users`
Not tenant-owned: one user can hold memberships in several clinics.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | *P1* |
| full_name | text not null | *P1* |
| email | text unique null | *P1* `uq_users_email`; stored lower-case (`ck_users_email_lower_case`) instead of `citext`, so no extension is needed |
| phone_e164 | text unique null | *P1* `uq_users_phone_e164`; `ck_users_email_or_phone`: `email IS NOT NULL OR phone_e164 IS NOT NULL` |
| is_platform_ops | boolean not null default false | *P1* MediEase staff (R10) |
| status | text not null | *P1* `ACTIVE` \| `DISABLED` (`ck_users_status`) |
| password_hash | text not null | M1-P2 — Argon2id |
| failed_login_count | integer not null default 0 | M1-P2 — FR-AUTH-04 |
| locked_until | timestamptz null | M1-P2 |
| last_login_at | timestamptz null | M1-P2 |

### `clinic_memberships`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | *P1* |
| clinic_id | uuid FK not null | *P1* |
| user_id | uuid FK not null | *P1* index `ix_clinic_memberships_user_id` (a user's clinics) |
| role | text not null | *P1* `OWNER` \| `DOCTOR` \| `FRONT_DESK` (`ck_clinic_memberships_role`) |
| status | text not null | *P1* `INVITED` \| `ACTIVE` \| `DEACTIVATED` (`ck_clinic_memberships_status`) |
| | | *P1* `uq_clinic_memberships_clinic_id_user_id` — invariant I2 |

### `doctors`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | *P1* |
| clinic_id | uuid FK not null | *P1* index `ix_doctors_clinic_id` |
| user_id | uuid FK null | *P1* Null for a doctor who never signs in; `uq_doctors_clinic_id_user_id` (partial, `WHERE user_id IS NOT NULL`): one profile per user per clinic |
| display_name | text not null | *P1* "Dr. A. Sample" |
| qualification | text not null | *P1* Printed on Rx (I3) |
| registration_number | text not null | *P1* Printed on Rx (FR-ORG-02, I3) |
| registration_council | text not null | *P1* e.g. state medical council (I3) |
| specialty | text | *P1* |
| is_active | boolean not null default true | *P1* |

### `refresh_tokens`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK | |
| family_id | uuid not null | Reuse of a rotated token revokes the whole family |
| token_hash | text unique not null | SHA-256 of the token |
| expires_at, revoked_at | timestamptz | |
| replaced_by_id | uuid null | |

### `audit_events` (append-only)
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| clinic_id | uuid null | Null for platform-level events |
| actor_user_id | uuid null | Null for patient/system actors |
| actor_type | text not null | `STAFF` \| `OPS` \| `PATIENT_LINK` \| `SYSTEM` |
| action | text not null | e.g. `prescription.issued`, `patient_link.opened` |
| entity_type, entity_id | text, uuid | |
| request_id | text | |
| ip_hash | text | Salted hash, never raw IP |
| metadata | jsonb | IDs and enums only |
| occurred_at | timestamptz not null | |

The application database role has `INSERT, SELECT` only on this table. Index:
`(clinic_id, occurred_at desc)`.

### `onboarding_checklists`
`id, clinic_id (unique), started_at, clinic_created_at, doctors_added_at, staff_invited_at,
patients_imported_at, first_appointment_at, first_prescription_at` — measures goal G4.

---

## M2 — Patients

### `patients`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| clinic_id | uuid FK | |
| code | text not null | `UNIQUE (clinic_id, code)` |
| full_name | text not null | |
| phone_e164 | text not null | Contact number (guardian's for minors) |
| sex | text | `FEMALE` \| `MALE` \| `OTHER` \| `UNDISCLOSED` |
| date_of_birth | date null | |
| age_years_at_registration | smallint null | When DOB unknown; `CHECK (date_of_birth IS NOT NULL OR age_years_at_registration IS NOT NULL)` |
| guardian_name | text null | Required when under 18 (application rule) |
| language | text not null default `en` | `en` \| `hi` |
| whatsapp_consent, sms_consent | boolean not null default false | FR-PAT-05 |
| consent_recorded_at | timestamptz null | |
| consent_recorded_by | uuid null | |
| opted_out_at | timestamptz null | FR-MSG-05 |
| tags | text[] default '{}' | P1 filters |
| created_by | uuid FK users | |

Indexes: `(clinic_id, phone_e164)`, `(clinic_id, lower(full_name) text_pattern_ops)`,
`(clinic_id, code)`. Target: FR-PAT-04 p95 < 500 ms at 10k patients per clinic.

---

## M3 — Schedules, appointments, queue

### `doctor_schedules`
`id, clinic_id, doctor_id, weekday (0–6), start_time time, end_time time, slot_minutes smallint
null (SLOTS mode), capacity smallint not null, valid_from date, valid_to date null`

### `schedule_exceptions`
`id, clinic_id, doctor_id, on_date date, kind (LEAVE | EXTRA), start_time, end_time, capacity null, note`

### `sessions` (materialised per doctor per day)
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| clinic_id, doctor_id | uuid FK | |
| on_date | date not null | Clinic-local date |
| starts_at, ends_at | timestamptz | UTC |
| mode | text | `SLOTS` \| `TOKENS` |
| capacity | smallint not null | |
| booked_count | smallint not null default 0 | Maintained under `FOR UPDATE` |
| next_token | smallint not null default 1 | TOKENS mode |
| status | text | `OPEN` \| `CLOSED` \| `CANCELLED` |
| | | `UNIQUE (doctor_id, starts_at)` |

Sessions are generated lazily for a date range when first requested, from schedules + exceptions.

### `appointments`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| clinic_id, session_id, doctor_id, patient_id | uuid FK | |
| slot_start | timestamptz null | SLOTS mode |
| token_number | smallint null | TOKENS mode |
| status | text not null | `BOOKED` \| `ARRIVED` \| `IN_CONSULTATION` \| `COMPLETED` \| `NO_SHOW` \| `CANCELLED` |
| source | text not null | FR-APT-07 |
| reason | text null | Non-clinical short reason |
| cancel_reason | text null | |
| arrived_at, started_at, completed_at | timestamptz null | Wait-time metrics |
| created_by | uuid FK users null | Null for public-page requests |

Constraints: partial unique `(session_id, slot_start) WHERE status <> 'CANCELLED' AND slot_start IS NOT NULL`;
partial unique `(session_id, token_number) WHERE token_number IS NOT NULL`.
Index: `(clinic_id, doctor_id, status)`, `(clinic_id, patient_id, created_at desc)`.

### `appointment_status_history`
`id, clinic_id, appointment_id, from_status, to_status, changed_by, changed_at, request_id`

---

## M4 — Visits and prescriptions

### `visits`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| clinic_id, patient_id, doctor_id | uuid FK | |
| appointment_id | uuid FK null unique | |
| chief_complaint, findings, diagnosis, notes | text | **Clinical** — never logged |
| vitals | jsonb | `{bp_systolic, bp_diastolic, pulse, temp_c, weight_kg, height_cm, spo2}` |
| status | text | `OPEN` \| `COMPLETED` |
| completed_at | timestamptz null | |
| locked_at | timestamptz null | completed_at + 24 h (FR-VIS-05) |

### `visit_addenda`
`id, clinic_id, visit_id, author_user_id, body text, created_at`

### `prescriptions`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| clinic_id, visit_id, patient_id, doctor_id | uuid FK | |
| version | smallint not null default 1 | |
| supersedes_id | uuid FK prescriptions null | FR-RX-09 |
| status | text | `DRAFT` \| `ISSUED` \| `SUPERSEDED` |
| advice | jsonb | `{diet[], activity[], return_if[], free_text}` — clinical |
| follow_up_date | date null | Triggers FR-REM-01 |
| language | text | Patient page language at issue time |
| issued_at | timestamptz null | |
| pdf_object_key | text null | |
| doctor_snapshot | jsonb | Name, qualification, registration number **as printed** |

A database trigger rejects `UPDATE` of clinical columns when `status <> 'DRAFT'`.

### `prescription_items`
`id, clinic_id, prescription_id, position, medicine_name, form, strength, dose, frequency,
timing (BEFORE_FOOD | AFTER_FOOD | WITH_FOOD | EMPTY_STOMACH | BEDTIME | ANY), duration_days,
quantity, preparation, storage, warnings, free_text` — all clinical.

### `rx_favourites` / `rx_templates`
`id, clinic_id, doctor_id, name, body jsonb, use_count, last_used_at`

### `patient_links`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | Also the token's `jti` |
| clinic_id, patient_id | uuid FK | |
| purpose | text | `RX_VIEW` (later: `QUEUE_STATUS`, `BOOKING_MANAGE`) |
| resource_id | uuid | e.g. prescription id (resolves to latest version) |
| expires_at | timestamptz | 90 days (FR-RX-08) |
| revoked_at | timestamptz null | |
| failed_challenges | smallint default 0 | Locks after 5 |
| open_count | integer default 0 | |
| last_opened_at | timestamptz null | |

---

## M5 — Reminders, messages, jobs

### `reminders`
`id, clinic_id, patient_id, kind (FOLLOW_UP | MEDICINE_COURSE | APPOINTMENT | VACCINATION),
due_at, source_type, source_id, status (FR-REM-05 values), message_id null, job_id null,
cancelled_by null, created_by`

### `messages`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| clinic_id, patient_id | uuid FK | |
| channel | text | `WHATSAPP` \| `SMS` \| `CONSOLE` |
| template_key, template_version | text | From `templates.yaml` |
| variables | jsonb | Non-clinical only (clinic name, date, link) |
| to_phone_e164 | text | Encrypted column (application-level) |
| provider | text | |
| provider_message_id | text unique null | Webhook idempotency |
| idempotency_key | text unique not null | |
| status | text | `QUEUED` \| `SENT` \| `DELIVERED` \| `READ` \| `FAILED` |
| error_code | text null | Provider error mapped to `MSG_*` |
| cost_paise | bigint null | FR-MSG-07 |
| request_id | text | |
| sent_at, delivered_at, read_at, failed_at | timestamptz null | |

### `inbound_messages`
`id, clinic_id null, from_phone_hash, provider_message_id unique, kind (OPT_OUT | OTHER),
received_at` — body is not stored except for the matched keyword.

### `webhook_events`
`id, provider, event_id unique, received_at, processed_at, error_code` — dedupe and replay.

### `jobs`
See ARCHITECTURE.md §7. Index for claiming:
`CREATE INDEX jobs_claim_idx ON jobs (run_at) WHERE state = 'queued';`

---

## Retention and erasure

| Data | Retention | Mechanism |
|---|---|---|
| Clinical records (visits, prescriptions) | As required of the clinic by law; clinic-configurable, default indefinite while the clinic is active | Export + delete on contract end |
| Messages | 18 months | Scheduled purge job |
| Audit events | 3 years minimum | Partitioned by month (post-pilot) |
| Refresh tokens | 30 days after expiry | Purge job |
| Patient links | 30 days after expiry | Purge job |

Erasure requests are executed by a reviewed, audited procedure (`scripts/erase_patient.py`, M6)
that respects legally required clinical retention — confirm with counsel (L-04).
