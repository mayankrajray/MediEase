# MediEase — API Design

Human-readable companion to `contracts/openapi.yaml`. The YAML is authoritative; this document
explains conventions and lists the planned surface. An endpoint is added to the YAML in the same
change that implements it.

## Conventions

| Topic | Rule |
|---|---|
| Base path | `/api/v1` (browser reaches it via the web origin; see ADR-0006) |
| Format | JSON, `snake_case` fields, UTF-8 |
| Auth | Session cookies (`me_access`, `me_refresh`); CSRF header `X-CSRF-Token` on non-GET |
| Clinic context | Header `X-Clinic-ID` for users in more than one clinic; otherwise implied by membership |
| Tracing | Request header `X-Request-ID` (optional); response header always set |
| Idempotency | `Idempotency-Key` header accepted on POST that create resources; replays return the first response for 24 h |
| Pagination | Cursor-based: `?limit=50&cursor=…` → `{ "items": [...], "next_cursor": "…" \| null }` |
| Time | ISO-8601 with offset in responses (`2026-09-15T09:30:00+05:30`); inputs accepted with offset only |
| Errors | Always the envelope below; codes in [ERRORS.md](ERRORS.md) |
| Not found vs forbidden | Cross-tenant resources return `404` |
| Versioning | Additive changes stay in `v1`; breaking changes need `v2` and an ADR |

### Error envelope

```json
{
  "error": {
    "code": "APT_SLOT_TAKEN",
    "message": "That slot was just booked. Pick another slot.",
    "request_id": "01J8Z5W6X4K7Q2N3R5T8V9Y0AB",
    "details": { "session_id": "…", "slot_start": "2026-09-16T10:30:00+05:30" }
  }
}
```

`message` is safe to show to staff. `details` never contains patient or clinical data.

## Endpoint catalogue

### Platform (M0)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/health` | Liveness | none |
| GET | `/ready` | Readiness incl. database | none |

### Auth and session (M1)

| Method | Path | Purpose | Req | Status |
|---|---|---|---|---|
| POST | `/api/v1/auth/sign-in` | Email/phone + password | FR-AUTH-01, 04 | Implemented (M1-P2) |
| POST | `/api/v1/auth/refresh` | Rotate refresh token | FR-AUTH-02 | Implemented (M1-P2) |
| POST | `/api/v1/auth/sign-out` | Revoke token family | FR-AUTH-02 | Implemented (M1-P2) |
| GET | `/api/v1/me` | Current user, memberships, permissions | FR-AUTH-03 | Implemented (M1-P3) |

**Sign-in** `{"identifier": "<email or phone>", "password": "…"}` → `200` with
`{user, memberships[], session: {access_expires_at, refresh_expires_at}}` and three cookies.
Refresh returns the same body; `/me` returns the same `{user, memberships}` without the session
block. No token ever appears in a body. Each membership carries `clinic_status`, `role` and the
`permissions` that role holds there (PRD §8.1), so the web app needs no second call to decide
what to render.

| Cookie | Path | HttpOnly | Lifetime | Purpose |
|---|---|---|---|---|
| `me_access` | `/api` | yes | `ACCESS_TOKEN_TTL_SECONDS` (15 min) | JWT checked on every request from M1-P3 |
| `me_refresh` | `/api/v1/auth` | yes | `REFRESH_TOKEN_TTL_SECONDS` (14 days, renewed on refresh) | Opaque; rotated on every refresh |
| `me_csrf` | `/` | no | as `me_refresh` | Copied by the web app into `X-CSRF-Token` |

All cookies are `SameSite=Lax` and `Secure` when `COOKIE_SECURE=true`. Every unsafe `/api/*`
request that carries a session cookie needs `X-CSRF-Token` = `me_csrf` (sign-in is exempt).
Auth responses are `Cache-Control: no-store`. The web client must not refresh twice in parallel:
the second refresh presents a rotated token and ends the session (`AUTH_REFRESH_REUSED`).

### Authorisation (M1-P3)

Every route declares one access policy, enforced before it runs; the API refuses to start with an
undeclared route (default deny).

| Policy | Who | Failure |
|---|---|---|
| public | anyone (`/health`, `/ready`, `/api/v1/auth/*`) | — |
| authenticated | any signed-in user (`/api/v1/me`) | `401 AUTH_SESSION_EXPIRED` |
| clinic + permission | a member of the request's clinic holding that permission | `403 PERM_DENIED` |
| ops | `is_platform_ops` users (`/api/v1/ops/*`, M1-P5) | `403 PERM_DENIED` |

The session, the user's status and the membership are re-read on every request (spec R7): nothing
is cached, so signing out ends access immediately (`401`) and deactivating a member or disabling a
user takes effect on their next request (`403 AUTH_ACCOUNT_DISABLED`).

Clinic context (R6): the clinic is the caller's only active membership, or the one named in
`X-Clinic-ID`. A missing choice, a malformed value and a clinic the caller has no membership in
all return `400 PERM_CLINIC_REQUIRED` — identical answers, so the API never confirms that a clinic
exists. A `SUSPENDED` clinic returns `403 CLN_SUSPENDED`, and `/me` still lists it with its status.
Any tenant resource outside the request's clinic returns `404 REQ_NOT_FOUND` (R8).

### Clinic administration (M1)

| Method | Path | Purpose | Role | Status |
|---|---|---|---|---|
| GET | `/api/v1/clinic` | Clinic settings | every role (`CLINIC_VIEW`) | Implemented (M1-P3) |
| PATCH | `/api/v1/clinic` | Edit clinic settings | OWNER (`CLINIC_MANAGE`) | Implemented (M1-P5) |
| GET | `/api/v1/clinic/doctors` | List doctors | every role (`DOCTORS_VIEW`) | Implemented (M1-P3) |
| POST | `/api/v1/clinic/doctors` | Add a doctor | OWNER (`CLINIC_MANAGE`) | Implemented (M1-P5) |
| GET | `/api/v1/clinic/doctors/{doctor_id}` | One doctor | every role (`DOCTORS_VIEW`) | Implemented (M1-P3) |
| PATCH | `/api/v1/clinic/doctors/{doctor_id}` | Edit or deactivate a doctor | OWNER (`CLINIC_MANAGE`) | Implemented (M1-P5) |
| GET | `/api/v1/clinic/staff` | List staff with roles | OWNER (`STAFF_MANAGE`) | Implemented (M1-P3) |
| POST | `/api/v1/clinic/staff` | Invite staff | OWNER (`STAFF_MANAGE`) | Implemented (M1-P5) |
| PATCH | `/api/v1/clinic/staff/{membership_id}` | Change role and/or deactivate | OWNER (`STAFF_MANAGE`) | Implemented (M1-P4, M1-P5) |
| GET | `/api/v1/clinic/audit-events` | Audit log | OWNER | FR-AUD-03 (P1) — backlog; not in the P0 permission matrix |

The doctor and staff lists return `{"items": [...]}` with no cursor: a clinic has one to four
doctors and a handful of staff, so the paginated envelope above starts with the first list that
can grow (patients, M2).

**Role change and deactivation** `PATCH /api/v1/clinic/staff/{membership_id}`
`{"role": "DOCTOR"}`, `{"status": "DEACTIVATED"}` or both → `200` with the updated member. Each
change writes its own audit event in the same transaction as the change (FR-AUD-01, spec R11).
The last active owner can neither be demoted nor deactivated (`409 CLN_LAST_OWNER`). Setting the
role a member already holds changes nothing and records nothing. `status` accepts `DEACTIVATED`
only: the lifecycle is `INVITED → ACTIVE → DEACTIVATED` with no way back in M1, so somebody
removed by mistake is invited again. A new role applies from the member's next request, and a
deactivated member's next request is refused (FR-ORG-04, AC4).

**Staff invitations** `POST /api/v1/clinic/staff` (and the ops equivalent below) →
`201` with the member and `accept_url`. An email address or phone number is required, because
that is how they sign in. Somebody who already has a MediEase account keeps it and gains a
membership ("one user, two memberships"); somebody already in this clinic is `409
CLN_MEMBER_EXISTS`; a still-pending invitation is re-issued, which retires the previous link.

### Staff invitations — public (M1)

| Method | Path | Purpose | Status |
|---|---|---|---|
| GET | `/api/v1/auth/invites/{token}` | What this invitation is for | Implemented (M1-P5) |
| POST | `/api/v1/auth/invites/{token}/accept` | Join and sign in: sets a new password, or proves the existing one | Implemented (M1-P5; existing accounts M1-P5 amendment, spec R13) |

No session is involved: the authority is the single-use secret in the URL, which is why these
paths need no `X-CSRF-Token`. The secret is 32 random bytes, stored only as a SHA-256 digest,
valid for 7 days, and shown exactly once — in the response that created the invitation. Accepting
activates the membership, activates an `ONBOARDING`
clinic when the new member is its owner (I1), and returns the sign-in body with cookies set.
What `password` means depends on the account (spec R13): for a **new** account (`has_password:
false`) it is the password being chosen (at least 12 characters); for an **existing** account
(`has_password: true`) it is that account's current password, verified and never changed, because
the link alone must not be able to take an account over (the inviting owner receives the link).
A wrong one is `401 AUTH_INVALID_CREDENTIALS` and counts towards the sign-in lockout (`423
AUTH_LOCKED`); the invitation stays pending.
Unknown secrets are `404 CLN_INVITE_INVALID`; expired and already-used ones say which (`410`), so
the person holding the link knows whether to ask for a new one.

### Ops console (M1, M2, M6)

| Method | Path | Purpose | Status |
|---|---|---|---|
| POST | `/api/v1/ops/clinics` | Create a clinic (FR-ORG-01, FR-OPS-01) | Implemented (M1-P5) |
| GET | `/api/v1/ops/clinics` | List clinics with their onboarding state | Implemented (M1-P5) |
| GET | `/api/v1/ops/clinics/{clinic_id}` | Checklist, staff and doctor count | Implemented (M1-P5) |
| POST | `/api/v1/ops/clinics/{clinic_id}/doctors` | Add a doctor while onboarding | Implemented (M1-P5) |
| POST | `/api/v1/ops/clinics/{clinic_id}/staff-invites` | Invite the owner (or any role) | Implemented (M1-P5) |
| PUT | `/api/v1/ops/clinics/{clinic_id}/doctors/{doctor_id}/schedule` | Set a doctor's weekly schedule while onboarding; `POST /ops/clinics` also takes `booking_mode` | Implemented (M3-P1) |
| GET | `/api/v1/ops/clinics/{clinic_id}/health` | Usage metrics, no clinical data (FR-OPS-03) | M6-P4 |
| POST | `/api/v1/ops/clinics/{clinic_id}/patient-imports?dry_run=true` | CSV import (FR-PAT-08), dry run unless `dry_run=false` | Implemented (M2-P4) |
| GET | `/api/v1/ops/jobs?state=dead` | Dead jobs | M5-P1 |

Ops routes are `@ops`: platform staff only, and clinic staff are refused even as owners (R10).
Ops users have no membership, so the clinic is named in the path; the use cases still reach tenant
rows only through the clinic-scoped repositories. Nothing here returns clinical content.

The **onboarding checklist** on those responses records the first time each step happened and is
never overwritten (FR-OPS-04, spec R12), so the elapsed time for goal G4 is a fact in the
database. `patients_imported_at`, `first_appointment_at` and `first_prescription_at` are written
by M2, M3 and M4.

**Patient import (M2-P4, spec patients R8).** The body is the CSV file itself, `Content-Type:
text/csv` (`curl --data-binary @patients.csv`), UTF-8, at most 2 MB (`413` beyond) and 5,000 data
rows, with exactly the columns `name, phone, sex, dob_or_age, guardian_name, language` in any order
and case. `sex` is `F`/`M`/`O`/`U` or the words (blank is `UNDISCLOSED`); `dob_or_age` is a whole
number 0–120 (an age recorded on the clinic's today) or a date `YYYY-MM-DD`, `DD/MM/YYYY` or
`DD-MM-YYYY`; `language` is `en`/`hi`/`english`/`hindi` (blank is `en`); a patient under 18 needs
`guardian_name`. It is a **dry run unless `dry_run=false`**. Both modes return the same report:

```json
{"dry_run": true, "rows": 3, "valid": 2, "invalid": 1, "possible_duplicates": 1,
 "already_registered": 0, "imported": 0, "codes": [],
 "errors": [{"row": 4, "field": "phone", "reason": "is not a valid phone number"}],
 "duplicates": [{"row": 3, "kind": "earlier_row", "same_as_row": 2}],
 "errors_truncated": false, "duplicates_truncated": false}
```

Rows are spreadsheet rows (header = 1). `already_registered` rows (same phone and name as an
existing patient or an earlier row) are skipped, so a re-run is harmless; rows that only share a
phone are imported and listed as `existing_patient` (with `matches`, a count) or `earlier_row`.
The commit re-checks everything under the clinic lock and imports in file order with consecutive
codes, consent "not asked". Nothing from the file is echoed and no existing patient is identified:
ops cannot browse patients. A file that cannot be read at all is `422 PAT_IMPORT_INVALID` with
`details.problems`; nothing is imported. Procedure: RUNBOOK §10.

### Audit trail (M1-P4)

Every audited action writes one row to `audit_events` in the same transaction as the change, so a
committed change always has its record. Rows hold IDs, enums, the `request_id` and a salted IP
fingerprint — never names, phone numbers or clinical content. The table refuses `UPDATE`,
`DELETE` and `TRUNCATE` in the database itself (FR-AUD-02). There is no endpoint yet: reading it
is a documented `make psql` procedure (RUNBOOK §18), and the owner-facing view is FR-AUD-03.

### Patients (M2)

| Method | Path | Purpose | Req | Status |
|---|---|---|---|---|
| GET | `/api/v1/patients?q=` | Lookup by phone, code or name prefix (at most 20, ordered by name) | FR-PAT-04 | Implemented (M2-P2) |
| POST | `/api/v1/patients` | Register (returns `409 PAT_PHONE_EXISTS` with candidates unless `confirm_new: true`) | FR-PAT-01/02 | Implemented (M2-P2) |
| GET | `/api/v1/patients/{patient_id}` | One patient | FR-PAT-01 | Implemented (M2-P2) |
| PATCH | `/api/v1/patients/{patient_id}` | Correct demographics | FR-PAT-01 | Implemented (M2-P2) |
| PUT | `/api/v1/patients/{patient_id}/consent` | Record consent (`whatsapp`, `sms`, both required) | FR-PAT-05/06 | Implemented (M2-P3) |
| POST | `/api/v1/patients/{patient_id}/opt-out` | Stop all messages (idempotent) | FR-MSG-05 | Implemented (M2-P3) |
| POST | `/api/v1/patients/{patient_id}/opt-in` | Undo an opt-out, with the consent given on the way back | FR-PAT-05, FR-MSG-05 | Implemented (M2-P3) |
| GET | `/api/v1/patients/{patient_id}/timeline` | Appointments, visits, Rx, reminders | FR-VIS-03 | M4 (visits alone: `/patients/{id}/visits`, M4-P1) |

Every clinic role holds `PATIENTS_MANAGE`, which guards all seven; ops users are refused (R10).
Responses carry personal data and are `Cache-Control: no-store`. The clinic is the request's
(`X-Clinic-ID` for people in several), and another clinic's patient is `404 REQ_NOT_FOUND`.

- **Register.** `phone` is the contact of record (the guardian's for a patient under 18, who then
  needs a `guardian_name`); give a `date_of_birth` *or* an `age_years`. Registration locks the
  clinic row before it checks the phone, so two simultaneous registrations of one new number have
  exactly one winner; a refusal takes no code. `409 PAT_PHONE_EXISTS` carries
  `details.candidates` (up to 10: `id`, `code`, `full_name`, `age_years`), for the signed-in staff
  member only. `201` returns the patient with its code (`ME-0142`).
- **Lookup.** `q` is read as a phone number (7+ digits), then a code (any case, hyphen optional),
  otherwise a name prefix. Blank text returns an empty list; a missing `q` is `422`. The text is
  never logged.
- **Edit.** Only the fields sent change; the code never does; a blank `guardian_name` clears it
  (refused for a minor). The phone is not re-checked for duplicates. The audit row lists field
  *names* only.
- **The patient body** adds `age_years` (on the clinic's today), `age_is_estimated`, `is_minor`
  and the read-only consent state (`whatsapp_consent`, `sms_consent`, `opted_out`,
  `consent_recorded_at`); consent is written in M2-P3.
- **Consent, opt-out, opt-in** (M2-P3). Three separate actions, so re-submitting a form can never
  undo an opt-out (AC5). `PUT .../consent` records an answer with who and when: both flags are
  required, booleans only. Both false is "asked and declined", which differs from never asked
  (`consent_recorded_at` null). For a patient under 18 it is the guardian's answer. While the
  patient is opted out it is `409 PAT_OPTED_OUT`: use opt-in, which takes the new consent.
  `POST .../opt-out` keeps the consent record but overrides it, and is idempotent (a second one
  changes nothing and writes no audit row). `POST .../opt-in` is `409 PAT_NOT_OPTED_OUT` unless there
  is an opt-out. The patient body carries `whatsapp_allowed` and `sms_allowed` (consent given and not
  opted out): the one rule the screens and M5's sender use. Each change is a `patient.consent_changed`,
  `patient.opted_out` or `patient.opted_in` audit row with the flags and `given_by`, never a name.
- **Clinic creation** (`POST /ops/clinics`) accepts an optional `patient_code_prefix` (2–4
  upper-case letters); `Clinic` responses now include it.

### Schedules, appointments, queue (M3)

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET | `/api/v1/clinic/doctors/{doctor_id}/schedule` | Weekly blocks and upcoming exceptions (`DOCTORS_VIEW`) — **M3-P1** | FR-APT-01 |
| PUT | `/api/v1/clinic/doctors/{doctor_id}/schedule` | Replace the weekly blocks (`SCHEDULES_MANAGE`, owners) — **M3-P1** | FR-APT-01 |
| POST | `/api/v1/clinic/doctors/{doctor_id}/schedule-exceptions` | Whole-day leave or an extra session — **M3-P1** | FR-APT-01 |
| DELETE | `/api/v1/clinic/doctors/{doctor_id}/schedule-exceptions/{exception_id}` | Remove one (today or later) — **M3-P1** | FR-APT-01 |
| GET | `/api/v1/sessions?date=&doctor_id=` | A date's sessions, generated on first read (`APPOINTMENTS_MANAGE`) — **M3-P1** | FR-APT-01, 02 |
| POST | `/api/v1/appointments` | Book (slot or token) — **M3-P2** | FR-APT-03, 04, 07 |
| GET | `/api/v1/appointments/{id}` | One appointment with its status history — **M3-P2** | FR-APT-05 |
| POST | `/api/v1/appointments/{id}/reschedule` | Move to another session or slot (201, new appointment) — **M3-P2** | FR-APT-05 |
| POST | `/api/v1/appointments/{id}/cancel` | Cancel with a reason — **M3-P2** | FR-APT-05 |
| GET | `/api/v1/patients/{id}/appointments` | A patient's appointments, newest first (≤ 50) — **M3-P2** | FR-APT-05 |
| GET | `/api/v1/queue?date=&doctor_id=&include_cancelled=` | The day's sessions with appointments, patients and waits — **M3-P3**; `ETag` / `If-None-Match` / 304 — **M3-P4** | FR-QUE-01/03 |
| POST | `/api/v1/appointments/{id}/transitions` | `{ "from": "BOOKED", "to": "ARRIVED" }` (`QUEUE_MOVE`) — **M3-P3** | FR-QUE-02 |
| POST | `/api/v1/queue/walk-ins` | Add a walk-in to today, arrived at once (`QUEUE_MOVE`) — **M3-P3** | FR-QUE-04 |

M3-P1 rules (spec appointments R1–R4, R14–R20; contract 0.9.0):

- **Times** in schedule bodies are the clinic's wall clock, `HH:MM`. An end at or before the start
  means the next day (`overnight: true`), and a block lasts 15 minutes to 12 hours, so `13:00–10:00`
  is `422 SCH_INVALID_BLOCK` while `23:00–01:00` is accepted. Session instants are UTC with an offset.
- **Mode:** SLOTS blocks need `slot_minutes` (dividing the block; capacity is derived), TOKENS blocks
  need `capacity`. The clinic's `booking_mode` is on `GET /clinic` and changed with `PATCH /clinic`
  (refused with `409 SCH_MODE_INCOMPATIBLE` while a current block lacks the new mode's value).
- **Overlap** is checked across midnight and from Sunday into Monday (`409 SCH_OVERLAP`).
- **Changes never drop a booking:** `PUT .../schedule`, a leave and removing an extra delete the
  affected future sessions that nobody booked and return the booked ones as `kept_sessions`.
- **Sessions** for a date from the clinic's today up to 180 days ahead are generated the first time
  the date is read; reading again returns the same IDs.

M3-P2 rules (spec R3–R8, D10–D16; contract 0.10.0; all routes `APPOINTMENTS_MANAGE`):

- **Book** `{session_id, patient_id, slot_start?, source?, reason?}`. Slot mode needs `slot_start`
  (one of the session's slots, any offset); token mode refuses it and returns `token_number`.
  Bookable until the session (tokens) or the slot (slots) ends, else `422 APT_IN_PAST`. One active
  appointment per patient per session (`409 APT_ALREADY_BOOKED`). `source` is `FRONT_DESK`
  (default), `PHONE` or `WHATSAPP`. Parallel bookings of the last place: one 201, one 409.
- **Cancel** `{reason, note?}`: `PATIENT_REQUEST`, `CLINIC_REQUEST`, `DOCTOR_UNAVAILABLE`,
  `DUPLICATE`, `OTHER` (needs a note). From `BOOKED`/`ARRIVED` until the session ends. The place is
  freed; the token is never reused.
- **Reschedule** `{session_id, slot_start?}` from `BOOKED` only, to any open session of the clinic;
  the old appointment becomes `CANCELLED`/`RESCHEDULED` and the new one has `rescheduled_from_id`.
- **Sessions** now carry `status` (`CLOSED` after a leave or change left them booked: no new
  bookings, existing ones can still move) and each slot's `available`.
- No confirmation message yet: it arrives with M5's jobs and messaging (D16).

M3-P3 rules (spec R9–R11, D17–D22; contract 0.11.0):

- **Transitions** `{from, to}`: `BOOKED → ARRIVED | NO_SHOW`, `ARRIVED → IN_CONSULTATION | NO_SHOW`,
  `IN_CONSULTATION → COMPLETED`, `NO_SHOW → ARRIVED`. `from` must be the current status, so a stale
  tab gets `409 QUE_INVALID_TRANSITION` with the real one. Only on the session's day (or while an
  overnight session runs); a no-show once the session or slot has started (`409 QUE_WRONG_TIME`).
  Cancel stays `POST .../cancel`.
- **Walk-ins** `{doctor_id, patient_id, session_id?, slot_start?, reason?}` join the session running
  now, else the next one today (`409 QUE_NO_SESSION` if none): the next token, or the earliest free
  slot that has not ended. Source `WALK_IN`, status `ARRIVED`.
- **Queue** `GET /api/v1/queue`: `date` defaults to the clinic's today; sessions in start order, each
  with its active appointments by token or slot, the patient's code, name and age, and
  `wait_minutes`. Not cached; P4 adds the `ETag`.

M3-P4 live queue (spec R12, D23–D26; contract 0.12.0): `GET /api/v1/queue` answers 200 with a
strong `ETag` (a SHA-256 of the body). Send it back as `If-None-Match` and an unchanged queue is a
bodiless `304` with the same tag. Screens poll every 5 seconds through `lib/api/poll.ts`; the
response stays `Cache-Control: no-store`, so nothing holding names is cached. `If-None-Match` is
compared weakly, as RFC 9110 requires (`*`, lists and `W/` tags work).

### Visits and prescriptions (M4)

| Method | Path | Purpose | Req | State |
|---|---|---|---|---|
| POST | `/api/v1/visits` | Start the visit of an `IN_CONSULTATION` appointment (`CLINICAL_WRITE`, its doctor) | FR-VIS-01 | Implemented (M4-P1) |
| GET | `/api/v1/visits/{visit_id}` | The consultation view: visit, addenda, patient, last 10 visits (`CLINICAL_VIEW`) | FR-VIS-02, 03 | Implemented (M4-P1) |
| PATCH | `/api/v1/visits/{visit_id}` | Notes and vitals with the `revision` seen (`CLINICAL_WRITE`, its doctor) | FR-VIS-02 | Implemented (M4-P1) |
| POST | `/api/v1/visits/{visit_id}/complete` | Complete; also completes the appointment | FR-VIS-05 | Implemented (M4-P1) |
| POST | `/api/v1/visits/{visit_id}/addenda` | Addendum on a completed visit | FR-VIS-05 | Implemented (M4-P1) |
| GET | `/api/v1/patients/{patient_id}/visits?limit=&before=` | A patient's visits, newest first, keyset pages (`CLINICAL_VIEW`) | FR-VIS-03 | Implemented (M4-P1) || POST | `/api/v1/visits/{visit_id}/prescriptions` | Create the chain's first draft | FR-RX-01 | Implemented (M4-P2) |
| GET | `/api/v1/prescriptions/{rx_id}` | One version with its chain | FR-RX-01, 09 | Implemented (M4-P2) |
| PUT | `/api/v1/prescriptions/{rx_id}` | Replace the whole draft with its `revision` | FR-RX-01..03 | Implemented (M4-P2) |
| DELETE | `/api/v1/prescriptions/{rx_id}` | Discard a draft | FR-RX-01 | Implemented (M4-P2) |
| POST | `/api/v1/prescriptions/{rx_id}/issue` | Issue (immutable), snapshots, language, pending-delivery marker (spec R5, R14) | FR-RX-06 | Implemented (M4-P2) |
| POST | `/api/v1/prescriptions/{rx_id}/revise` | New version from the latest issued one | FR-RX-09 | Implemented (M4-P2) |
| GET | `/api/v1/prescriptions/{rx_id}/pdf` | The PDF, rendered once per version (spec R18, ADR-0012) | FR-RX-06 | M4-P4 |
| GET/POST/DELETE | `/api/v1/rx-favourites` | Favourites | FR-RX-05 | M4-P3 |
| GET/POST/DELETE | `/api/v1/rx-templates` | Templates | FR-RX-05 | M4-P3 |
| GET | `/api/v1/medicine-suggestions?q=` | From this clinic's history only | FR-RX-10 | M4-P3 |

M4-P1 rules (spec prescriptions R1-R3, R16, R17; decisions 1A-6A; contract 0.13.0): reads need
`CLINICAL_VIEW` (doctors, owners), writes `CLINICAL_WRITE` and being the visit's doctor, so front
desk gets `403 PERM_DENIED` on every visit route. Responses are `no-store`. Each read that returns
clinical content writes **one** audit row for the whole view (`visit.viewed`,
`patient.visits_viewed`); writes are audited by their own action with the names of changed fields,
never their values. Locked 24 hours after completion (`409 VIS_LOCKED`); then addenda.
M4-P2 rules (spec R4-R6, R14, R16, R17, R20; decisions 1A-6A; contract 0.14.0): the same
permissions, caching and audit rules as visits. One chain per visit, at most one draft. Version 1
is created, saved and issued until the visit locks; an issued version is revised at any time.
Issued versions never change (`409 RX_NOT_DRAFT`, and the database refuses it too). Audit
metadata carries IDs, versions, counts, the language and the delivery state, never item text.
`GET /visits/{id}` now also returns the visit's `prescriptions` and, per history visit, its latest
issued `prescription` (medicines only) — still one read and one audit row.
### Patient links (M4) — public, no session

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET | `/api/v1/public/links/{token}` | Validate token; returns clinic name + challenge required | FR-RX-08 |
| POST | `/api/v1/public/links/{token}/verify` | `{ "phone_last4": "3210" }` → short-lived view session | FR-RX-08 |
| GET | `/api/v1/public/links/{token}/prescription` | Prescription view model (latest version) | FR-RX-07 |

Rate limits: 20 requests/min per IP, 5 failed challenges per link.

### Reminders and messaging (M5)

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET/POST | `/api/v1/patients/{patient_id}/reminders` | List / schedule | FR-REM-02 |
| PATCH | `/api/v1/reminders/{reminder_id}` | Reschedule / cancel | FR-REM-02 |
| GET | `/api/v1/follow-ups/pending` | Overdue follow-ups | FR-REM-07 |
| GET | `/api/v1/patients/{patient_id}/messages` | Message history (status only) | FR-MSG-04 |
| GET | `/webhooks/whatsapp` | Meta verification challenge | FR-MSG-03 |
| POST | `/webhooks/whatsapp` | Status + inbound (signature verified) | FR-MSG-03/05 |
| POST | `/webhooks/sms/{provider}` | Delivery reports | FR-MSG-03 |

Webhook paths are outside `/api/v1` and are routed directly to the API by the reverse proxy.
