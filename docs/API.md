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
| GET | `/api/v1/auth/google/start` | Start a Google sign-in for `intent=staff\|patient`; seals the flow into `me_oidc` and redirects to Google (or to the callback with the local fake) | FR-AUTH-07, FR-PRT-01 | Implemented (M6a-P3) |
| GET | `/api/v1/auth/google/callback` | Finish it: staff cookies for an existing staff user (linked by verified email once, then by `sub`), portal cookies for a patient; redirects to `next`, or back to the sign-in page with a `reason` | FR-AUTH-07, FR-PRT-01 | Implemented (M6a-P3) |
| GET | `/api/v1/me` | Current user, memberships, permissions; from M6a-P6 each membership's `doctor_id` (the member's doctor profile, or null) | FR-AUTH-03, FR-UX-06 | Implemented (M1-P3, M6a-P6) |
| POST | `/api/v1/auth/password-reset` | `{email}` → always 202 `{accepted: true}`; the worker emails a 30-minute link to an eligible staff user | FR-AUTH-05 | Implemented (M6a-P4) |
| POST | `/api/v1/auth/password-reset/complete` | `{token, password}` → 204; ends every session of the account | FR-AUTH-05 | Implemented (M6a-P4) |

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

### Patient portal accounts (M6a-P3)

Own cookies (`me_pt_access` path `/api/v1/portal`, `me_pt_refresh` path `/api/v1/portal/auth`,
`me_pt_csrf`), audience `mediease-portal`, policy `@patient` (ADR-0015). Sign-up and sign-in are
exempt from `X-CSRF-Token`; refresh and sign-out send `me_pt_csrf`. A staff session is 401 here
and a portal session is 401 on every staff route.

| Method | Path | Purpose | Req | Status |
|---|---|---|---|---|
| POST | `/api/v1/portal/auth/sign-up` | Name, email, password; 201 with the account and portal cookies | FR-PRT-01 | Implemented (M6a-P3) |
| POST | `/api/v1/portal/auth/sign-in` | Email and password | FR-PRT-01 | Implemented (M6a-P3) |
| POST | `/api/v1/portal/auth/refresh` | Rotate the portal refresh token | FR-AUTH-02 | Implemented (M6a-P3) |
| POST | `/api/v1/portal/auth/sign-out` | Revoke the portal session | FR-AUTH-02 | Implemented (M6a-P3) |
| GET | `/api/v1/portal/me` | The signed-in account, with its portal `language` (linked records: below, M6b-P1) | FR-PRT-01 | Implemented (M6a-P3) |
| POST | `/api/v1/portal/auth/password-reset` | As staff; a Google-only account gets a "use Google" notice | FR-AUTH-05 | Implemented (M6a-P4) |
| POST | `/api/v1/portal/auth/password-reset/complete` | As staff; also verifies the email | FR-AUTH-05 | Implemented (M6a-P4) |
| POST | `/api/v1/portal/auth/verify-email` | `{token}` → 204 (the emailed page POSTs; a GET verifies nothing) | FR-AUTH-08 | Implemented (M6a-P4) |
| POST | `/api/v1/portal/auth/verify-email/resend` | `@patient`; 202 `{accepted}`; 3 an hour | FR-AUTH-08 | Implemented (M6a-P4) |

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
| GET | `/api/v1/clinic/staff` | List staff with roles; from M6a-P5 also email, phone, invitation expiry and a doctor-profile flag | OWNER (`STAFF_MANAGE`) | Implemented (M1-P3, M6a-P5) |
| POST | `/api/v1/clinic/staff` | Invite staff, or invite a deactivated member back; emailed when they have an email address (`delivery: email`), else the link once (`delivery: link`); 10 an hour per clinic | OWNER (`STAFF_MANAGE`) | Implemented (M1-P5, M6a-P5) |
| POST | `/api/v1/clinic/staff/{membership_id}/resend` | A pending invitation again; the old link stops working; 3 an hour per member | OWNER (`STAFF_MANAGE`) | Implemented (M6a-P5) |
| PATCH | `/api/v1/clinic/staff/{membership_id}` | Change role and/or deactivate | OWNER (`STAFF_MANAGE`) | Implemented (M1-P4, M1-P5) |
| GET | `/api/v1/clinic/audit-events` | Audit log | OWNER | Not built at this path: the owner's audit log is `/api/v1/audit-events` (M6a-P8, "Audit log" below) |

The doctor and staff lists return `{"items": [...]}` with no cursor: a clinic has one to four
doctors and a handful of staff, so the paginated envelope above starts with the first list that
can grow (patients, M2).

**Role change and deactivation** `PATCH /api/v1/clinic/staff/{membership_id}`
`{"role": "DOCTOR"}`, `{"status": "DEACTIVATED"}` or both → `200` with the updated member. Each
change writes its own audit event in the same transaction as the change (FR-AUD-01, spec R11).
The last active owner can neither be demoted nor deactivated (`409 CLN_LAST_OWNER`). Setting the
role a member already holds changes nothing and records nothing. `status` accepts `DEACTIVATED`
only; bringing somebody back is a new invitation (M6a-P5). A new role applies from the member's
next request, and a deactivated member's next request is refused (FR-ORG-04, AC4). From M6a-P6
both invitation routes take an optional `doctor_id` for an `OWNER` invitation: that unlinked,
active doctor profile is linked to the invitee at once ("Doctor 1", FR-ONB-08) and counts once
they accept (422 on `doctor_id` otherwise).

**Appointment reminder settings (M6a-P8, FR-APT-08; contract 0.28.0).** `GET` and `PATCH
/api/v1/clinic` carry `reminder_evening_before` (boolean, default true: 19:00 clinic time the day
before) and `reminder_hours_before` (0–6, default 2; 0 is off; 422 `REQ_VALIDATION_FAILED`
outside). Changing them needs `CLINIC_MANAGE` and is audited as `clinic.updated` with the field
names only. A change applies to bookings made or moved after it.

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
| GET | `/api/v1/ops/messaging-costs?month=YYYY-MM` | Each clinic's messages and their cost in a month (spec R18) | Implemented (M5-P5) |

**Messaging costs (M5-P5, decisions 5A-7A).** `month` is required (`YYYY-MM`, else 422
`REQ_VALIDATION_FAILED`) and read in each clinic's own time zone on the sending time. The answer
lists every clinic that sent messages that month, with per-channel `messages`, `priced`,
`unpriced` and `cost_paise`, and the month's total `cost_paise`. Money is excluding GST, kept in
millipaise and rounded half up to paise at each total; a message whose cost is not yet known is
`unpriced`, never guessed. Prices come from `adapters/messaging/prices.yaml`. Counts and money
only: no message, patient or number.

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
`DELETE` and `TRUNCATE` in the database itself (FR-AUD-02). Until M6a-P8 there was no endpoint:
reading it was a documented `make psql` procedure (RUNBOOK §18). From M6a-P8 owners read it in
the app (below); ops still use RUNBOOK §18.

### Audit log (M6a-P8)

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET | `/api/v1/audit-events?from&to&category&actor_user_id&cursor` | The clinic's audit log, 50 a page, newest first (`AUDIT_VIEW`, owners) | FR-AUD-03 |
| GET | `/api/v1/audit-events/export?from&to` | The same range as CSV (`AUDIT_VIEW`, owners) | FR-AUD-03, FR-AUD-01 |

Contract 0.28.0. `AUDIT_VIEW` is held by owners only: doctors and the front desk get 403
`PERM_DENIED`.

- **Range.** `from` and `to` are clinic calendar days (`YYYY-MM-DD`), both included; the default
  is the last 7 days. More than 92 days is 422 `AUD_RANGE_TOO_LONG`.
- **List.** `{items, next_cursor, from, to, timezone, categories}`. `next_cursor` is a keyset
  cursor on `(occurred_at, id)`, null on the last page. `categories` lists `{value, label}`:
  `SIGN_IN`, `TEAM`, `PATIENTS`, `APPOINTMENTS`, `CLINICAL`, `PRESCRIPTIONS`, `MESSAGES`,
  `SCHEDULE`, `SETTINGS`.
- **Entry.** `id`, `occurred_at`, `action`, `action_label`, `category`, `actor {type, user_id,
  label, role}`, `entity_type`, `entity_id`, `patient_code` and the allow-listed `metadata`. The
  actor's label is the member's current name, or "Former team member", "MediEase support",
  "System", "Patient (prescription link)" or "Patient (portal)". Labels come from
  `domain/audit/catalogue.py`. The IP fingerprint is never returned.
- **Export.** `text/csv` with `Content-Disposition: attachment; filename=audit-<slug>-<from>-<to>.csv`.
  Columns: Time, Person, Role, Category, Action, Record type, Record ID, Patient code, Details.
  At most 92 days and 20,000 rows, else 422 `AUD_RANGE_TOO_LONG`. A cell starting with `=`, `+`,
  `-`, `@`, a tab or a carriage return is prefixed with `'`.
- **Audit.** Each export is audited as `audit.exported` (metadata `from`, `to`, `rows`); reading
  the list is not. `Cache-Control: no-store`.
- **Tenancy.** Both routes read through `SqlAlchemyAuditReader`, reached only as
  `uow.tenant(clinic).audit_log`: the events, memberships and patients it joins are filtered by the
  request's clinic (a reviewed exception in the tenancy suite, with its own case).

### Patient portal: linking and the patient's records (M6b-P1)

Contract 0.29.0; spec `docs/specs/patient-portal.md`. Patient routes are `@patient` (the portal
cookies); every response is `Cache-Control: no-store`.

| Method | Path | Purpose | Req | Status |
|---|---|---|---|---|
| GET | `/api/v1/portal/links` | The account's linked clinics: the clinic (name, phone, address, city), the record's first name and code, method, since | FR-PRT-02 | Implemented (M6b-P1) |
| DELETE | `/api/v1/portal/links/{link_id}` | Unlink one; 200 `{id, revoked_at}` | FR-PRT-02 | Implemented (M6b-P1) |
| POST | `/api/v1/portal/links/prescription` | `{token, phone_last4}`: link the record a prescription link names; verified accounts only (403 `PRT_UNVERIFIED_ACCOUNT`); the page's own last-4 check and lockout | FR-PRT-06 (c) | Implemented (M6b-P1) |
| GET | `/api/v1/portal/invites/{token}` | Who a clinic's invite is for (clinic, first name, code) | FR-PRT-06 (b) | Implemented (M6b-P1) |
| POST | `/api/v1/portal/invites/{token}/accept` | Link the invited record (201) | FR-PRT-06 (b) | Implemented (M6b-P1) |
| GET | `/api/v1/portal/appointments` | Grouped by clinic, upcoming first then past; at most 50 per clinic; no reason or notes | FR-PRT-03 | Implemented (M6b-P1) |
| GET | `/api/v1/portal/prescriptions` | Each chain's latest issued version (doctor, date, version) | FR-PRT-03 | Implemented (M6b-P1) |
| GET | `/api/v1/portal/prescriptions/{rx_id}?lang=en\|hi` | The patient page, as the prescription link shows it | FR-PRT-03 | Implemented (M6b-P1) |
| GET | `/api/v1/portal/prescriptions/{rx_id}/pdf` | The same PDF the clinic prints (rendered once) | FR-PRT-03 | Implemented (M6b-P1) |
| GET | `/api/v1/portal/reminders` | Kind, date, due time and visible status | FR-REM-05 | Implemented (M6b-P1) |
| GET | `/api/v1/portal/medicine-plan?date=` | One day's plan by slot, then "As the doctor wrote"; default today, ±30 days (else 422) | FR-REM-03 | Implemented (M6b-P3) |
| GET | `/api/v1/portal/medicine-plan/courses` | Each current version's course with the reminder choices per line and slot | FR-REM-03 | Implemented (M6b-P3) |
| PUT | `/api/v1/portal/medicine-plan/doses` | Mark a dose Taken or Skipped (409 `PRT_DOSE_NOT_MARKABLE` outside its window; 422 untimed line, slot or day) | FR-REM-03 | Implemented (M6b-P3b), not audited |
| DELETE | `/api/v1/portal/medicine-plan/doses?prescription_id&item_id&on_date&slot` | Clear a dose's mark within its window | FR-REM-03 | Implemented (M6b-P3b) |
| GET | `/api/v1/portal/medicine-plan/history?prescription_id=` | A version's doses by day with counts per state | FR-REM-03 | Implemented (M6b-P3b) |
| PUT | `/api/v1/portal/medicine-plan/reminders` | A reminder choice for one line and slot (422 untimed line or slot it lacks; 404 out of scope or not current) | FR-REM-03 | Implemented (M6b-P3), stored only |
| POST | `/api/v1/patients/{patient_id}/portal-invite` | Staff: a single-use invite `{url, expires_at}`, shown once (7 days; supersedes the pending one) | FR-PRT-06 (b) | Implemented (M6b-P1), `PATIENTS_MANAGE` |
| GET | `/api/v1/patients/{patient_id}/portal` | Staff: `NOT_LINKED`, `INVITED` (with expiry) or `LINKED` (method, since); never the account's details | FR-PRT-06 | Implemented (M6b-P1), `PATIENTS_MANAGE` |
| DELETE | `/api/v1/patients/{patient_id}/portal-link` | Staff: end the link; returns the new status | FR-PRT-06 | Implemented (M6b-P1), `PATIENTS_MANAGE` |

- **M6b-P2 (contract 0.30.0).** `PATCH /api/v1/portal/me {language: en|hi}` changes the account's portal language (logged as `portal.language_changed`, not audited); sign-up takes an optional `language`, else the `me_pt_lang` cookie the signed-out pages set, else `en` (a new Google account reads the same cookie). Links' `clinic` and each appointment group carry the clinic's `timezone` (groups also its `phone_e164`); `GET /portal/prescriptions/{rx_id}` without `?lang` uses the account's language.
- **M6b-P3 (contract 0.31.0).** `frequency` is a 0/1 pattern of 3 or 4 slots (the input may be `101` or `1 0 1`; all zeros or other digits are 422 on `items.N.frequency`) or SOS, ONCE, CUSTOM. Lines gain `duration_kind` and, in responses, the engine's `slots` and non-blocking `line_warnings`; drafts take `starts_on` and a revision's draft returns `previous_starts_on`. `PATCH /portal/me` also takes `slot_times`; the account carries them. The patient page gains the Medicine schedule (`schedule*`, empty before layout 2). Plan reads and reminder choices are not audited; logs carry IDs only.
- **M6b-P3b (contract 0.32.0).** The plan's timed entries carry `mark` (`status` TAKEN / SKIPPED / NOT_RECORDED / UPCOMING, `marked_at`, `markable`) and every entry the clinic's `timezone`. Dose records are private to the account (no staff or ops route), not audited, and logged with IDs and counts only.
- **Scope (NFR-18).** Every patient read goes through `PortalScope`: the account's active links,
  read per request, each a (clinic, record) pair; a suspended clinic is left out. An ID outside it
  (another clinic, another record in the same clinic, a revoked link, a draft or superseded
  version) is 404 `REQ_NOT_FOUND`, never 403. `tests/tenancy/test_portal_scope.py` fails when a new
  `@patient` route with an ID has no cross-account case.
- **Linking.** Nothing links automatically (not by phone, email or name). An invite is one answer
  when unknown, used, superseded or expired: 404 `PRT_INVITE_INVALID`. A record with another
  account, or an account already linked in that clinic, is 409 `PRT_ALREADY_LINKED` (an invite
  stays usable). The prescription route answers `LINK_CHALLENGE_FAILED` / `LINK_LOCKED` like the
  page, and its wrong answers count towards the page's lock.
- **Audit.** `patient.portal_invited` (STAFF), `patient.portal_linked` (PATIENT, with the method),
  `patient.portal_unlinked` (PATIENT or STAFF), on the `patient` entity; a wrong last-4
  `patient_link.challenge_failed` (PATIENT). Reading the portal is not audited (decision 7A).

### Patients (M2)

| Method | Path | Purpose | Req | Status |
|---|---|---|---|---|
| GET | `/api/v1/patients?q=` | Lookup by phone, code or name prefix (at most 20, ordered by name) | FR-PAT-04 | Implemented (M2-P2) |
| GET | `/api/v1/my-patients?q=&limit=&offset=` | Patients the caller has seen as a doctor, latest visit first (`CLINICAL_VIEW` and a doctor profile, else 409 `CLN_NO_DOCTOR_PROFILE`); who and when only | FR-UX-02, FR-UX-06 | Implemented (M6a-P6) |
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
| GET | `/api/v1/appointments/to-move?doctor_id=` | Bookings to move: live appointments in closed sessions (`APPOINTMENTS_MANAGE`) — **M6a-P8** | FR-APT-09 |

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

M4-P6 (contract 0.18.0; P2 decision 6A): each queue entry also carries `visit_id` (or `null`)
and `prescription`, the visit's latest issued version as `{id, version, issued_at}` or `null`.
No clinical content, so front desk sees "Prescription issued" and prints from the row without a
call per row; the `ETag` covers both fields.

M6a-P8 bookings to move (FR-APT-09; contract 0.28.0): `GET /api/v1/appointments/to-move` needs
`APPOINTMENTS_MANAGE` (every role). It lists the `BOOKED` and `ARRIVED` appointments from the
clinic's today on whose session is `CLOSED`, earliest first, at most 200, optionally for one
`doctor_id`. Each item: `id`, `status`, `doctor_id`, `session_id`, `on_date`, `starts_at`,
`slot_start`, `token_number`, `reason` (`LEAVE` when the doctor has leave that day, else
`SCHEDULE_CHANGED`) and `patient {id, code, first_name, phone_masked}`. A derived list: moving or
cancelling a booking takes it off. A leave, a removed extra session or a replaced weekly schedule
that kept booked sessions also tells the active owners and front desk in the app
(`schedule.bookings_to_move`), except the person who made the change.

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
| GET | `/api/v1/prescriptions/{rx_id}/pdf` | The PDF, rendered once per version (spec R18, ADR-0012); `RX_PRINT` | FR-RX-04, 06 | Implemented (M4-P4) |
| GET | `/api/v1/prescriptions/{rx_id}/preview?lang=en\|hi` | A **draft** as the patient will read it (`PatientPrescriptionPage`, the same builder as `/p/{token}`); `CLINICAL_VIEW`; no audit row of its own (part of the consultation view); `RX_NOT_DRAFT` otherwise | spec §6 | Implemented (M4-P6) |
| GET | `/api/v1/patients/{patient_id}/prescriptions` | The patient's current versions to print, without content; `RX_PRINT` | FR-RX-06 | Implemented (M4-P4) |
| GET/POST | `/api/v1/rx-favourites` · PUT/DELETE `…/{favourite_id}` | The caller's favourites | FR-RX-05 | Implemented (M4-P3) |
| GET/POST | `/api/v1/rx-templates` · GET/PUT/DELETE `…/{template_id}` | The caller's templates | FR-RX-05 | Implemented (M4-P3) |
| GET | `/api/v1/medicine-suggestions?q=` | The caller's favourites, then names this clinic issued; at most 10 | FR-RX-10 | Implemented (M4-P3) |
| GET | `/api/v1/rx-vocabulary` | The engine's slot sets (3 and 4 digits) and every code the editor offers | FR-RX-01 | Implemented (M6b-P3), `CLINICAL_VIEW` |

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
M4-P3 rules (spec R7, AC5; decisions 1A-5A; contract 0.15.0): favourites and templates are
each doctor's own (`CLINICAL_WRITE` and a doctor profile; another doctor's are 404). Suggestions
match from the start of the name ignoring case, favourites first (by use) then names on this
clinic's issued prescriptions (by distinct visits, then recency); nothing else is ever suggested.
Draft lines may carry `favourite_id` and the draft `template_id`; issuing counts each once.
Changes are audited with IDs only; lists and suggestions are not audited.
M4-P4 rules (spec R8, R16, R18, D6; decisions 1A-5A; contract 0.16.0): printing is `RX_PRINT`,
held by every role, front desk included (spec D6), who still cannot read a prescription on screen.
A version's PDF is rendered on its first download while its row is locked (a concurrent first
download waits and gets the same file; more than 10 s is `503 RX_PDF_BUSY` with `Retry-After`),
stored write-once, and streamed afterwards with `Cache-Control: private, no-store` — never a
public or pre-signed URL. Drafts are `409 RX_NOT_ISSUED`; a superseded version needs
`CLINICAL_VIEW` too, else `409 RX_NOT_LATEST` (1A). `500 RX_PDF_FAILED` stores nothing, so the
next download tries again. One `prescription.pdf_downloaded` per download (visit, version, role,
whether it rendered). `GET /patients/{id}/prescriptions` lists the current versions without
content (2A). `PATCH /clinic` takes `rx_paper_size` (`A5` default, `A4`), applied at first render
(3A). Labels and dosage phrases are English or Hindi by the prescription's language; the doctor's
text prints as written.

### Patient links (M4-P5) — public, no session

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET | `/api/v1/public/links/{token}` | Validate the token; the clinic's name, the patient's language, locked | FR-RX-08 |
| POST | `/api/v1/public/links/{token}/verify` | `{ "phone_last4": "3210" }` → a 30-minute view token for this link | FR-RX-08 |
| GET | `/api/v1/public/links/{token}/prescription?lang=` | The patient page (latest issued version), with `X-Link-View` | FR-RX-07 |
| GET | `/api/v1/prescriptions/{rx_id}/link` | Staff (`RX_PRINT`): the chain's link for the QR code | FR-RX-08 |
| POST | `/api/v1/prescriptions/{rx_id}/link/reset` · `/replace` | Staff (`RX_PRINT`): unlock, or revoke and make a new one | FR-RX-08 |

M4-P5 rules (spec R9–R13, R19, R20; decisions 1A–6A; contract 0.17.0): one link per chain,
created when version 1 is issued and reused by revisions. Tokens carry R9's claims and an
HMAC-SHA256 (versioned keys, the first signs); anything not exactly ours is `404 LINK_INVALID`.
Five wrong last-4 answers lock the link (`423 LINK_LOCKED`) until staff reset it. The view token
is kept by the patient page's server in an HttpOnly cookie scoped to the page and sent as
`X-Link-View`. Rate limits: 20 requests a minute per link, 300 per caller (`429
LINK_RATE_LIMITED`, `Retry-After`). Responses are `no-store`, `noindex`, `no-referrer`; the token
never reaches the logs. Audit: `patient_link.opened`, `.challenge_failed`, `.locked` as
`PATIENT_LINK`; `.created`, `.reset`, `.replaced` by staff; IDs and versions only.

### Reminders and messaging (M5)

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET/POST | `/api/v1/patients/{patient_id}/reminders` | List / schedule | FR-REM-02 |
| PATCH | `/api/v1/reminders/{reminder_id}` | Reschedule / cancel | FR-REM-02 |
| GET | `/api/v1/follow-ups/pending` | Overdue follow-ups; from M6a-P6 `doctor_id` keeps one doctor's | FR-REM-07, FR-UX-02 |
| GET | `/api/v1/patients/{patient_id}/messages` | Message history (status only) | FR-MSG-04 |
| GET | `/webhooks/whatsapp` | Meta verification challenge | FR-MSG-03 |
| POST | `/webhooks/whatsapp` | Status + inbound (signature verified) | FR-MSG-03/05 |
| POST | `/webhooks/sms/{provider}` | Delivery reports | FR-MSG-03 |

M5-P4 (contract 0.19.0): the three reminder routes and pending follow-ups need
`REMINDERS_SCHEDULE` (every role). `POST` takes `{doctor_id, follow_up_date}` (201; 409
`REM_NO_CONSENT` / `REM_CLINIC_PHONE_MISSING`; 422 `REM_IN_PAST`); `PATCH` takes exactly one of
`{follow_up_date}` or `{cancel: true}` (409 `REM_NOT_SCHEDULED`). A reminder's `status` is its
message's once sent. `GET /follow-ups/pending?limit&offset` returns `{items, limit, offset}`.
M5-P6 (contract 0.21.0): `GET /patients/{id}/messages` (`REMINDERS_SCHEDULE`) returns the
patient's messages newest first, at most 50, status only: `template_key`, `source_type` and
`source_id`, `channel`, `status`, `error_code` and the times; never the variables or the number.
Another clinic's patient is a 404.
M6a-P8 (contract 0.28.0): a reminder carries `kind` (`FOLLOW_UP` or `APPOINTMENT`) and
`appointment_id` (set for `APPOINTMENT`). Appointment reminders are scheduled by the system when a
booking is made or moved, and cancelled when it is cancelled or moved (FR-APT-08). Staff may
cancel one with `PATCH {cancel: true}`; `PATCH {follow_up_date}` on one is 409
`REM_FOLLOWS_APPOINTMENT` ("move the appointment instead"). At send time one whose appointment
changed is cancelled with error code `REM_APPOINTMENT_CHANGED`, and one too late for the visit
with `REM_TOO_LATE`.

Webhook paths are outside `/api/v1` and are routed directly to the API by the reverse proxy.
They are not in `contracts/openapi.yaml` (the web app never calls them; Meta's format is Meta's).
M5-P3: `GET` returns the `hub.challenge` as `text/plain` for the right `hub.verify_token`, else
403 `WH_VERIFY_FAILED`; `POST` answers 200 `{"status": "received"}` for a correctly signed body
(also for a redelivery), 401 `WH_SIGNATURE_INVALID`, 413 over 1 MB, 429 `WH_RATE_LIMITED`.
M5-P5: an inbound text that is exactly STOP, UNSUBSCRIBE, रोकें or बंद (trimmed, any case) opts the
sender out, in each clinic that has messaged that number, and that clinic replies
`opt_out_confirmed`; nothing else inbound is acted on or stored. `POST /webhooks/sms/{provider}`
waits for a real SMS provider (L-03).
### Dashboards (M6)

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET | `/api/v1/dashboard/today` | *Today*: counts for the caller's role; from M6a-P6 `view=doctor` for a practising owner's Doctor view (409 `CLN_NO_DOCTOR_PROFILE` without a profile) | M6-P1 (decision 5A), M6a-P6 (decision 4A) |

M6-P1 (contract 0.22.0): `CLINIC_VIEW` (every role). Computed in the clinic's zone; today's
sessions are generated first, as `GET /queue` does. A doctor with a doctor profile gets
`scope: DOCTOR` (their own sessions, next patients and counts; `messages_failed` null); front desk
and owners get `scope: CLINIC`. `counts` are active appointments by status (`not_arrived`,
`waiting`, `in_consultation`, `completed`, `no_show`, `total`; cancelled not counted), also per
session. `next_patients` is at most three: those waiting first, then those not yet arrived, with the
patient's code and first name only. `follow_ups_pending` is the clinic's, as
`/follow-ups/pending` lists them. `week` (the last 7 days ending today, oldest first) needs
`USAGE_METRICS_VIEW` and is null without it; in scope `DOCTOR` its `messages_sent` are null. Like
the queue, a strong ETag and a bodiless 304 for `If-None-Match`; `Cache-Control: no-store`.
M6a-P8 (contract 0.28.0): `bookings_to_move` is the number of bookings `GET
/appointments/to-move` lists for the clinic; null in scope `DOCTOR`.

### Notifications (M6a-P7)

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET | `/api/v1/notifications?limit=` | My latest notifications, newest first (default 30, 1–50) | FR-NTF-03 |
| GET | `/api/v1/notifications/summary` | `{unread, latest_id}` for the bell; ETag and 304 | FR-NTF-03 |
| POST | `/api/v1/notifications/{notification_id}/read` | Mark one read (reading again keeps the first time) | FR-NTF-03 |
| POST | `/api/v1/notifications/read-all` | Mark all mine read; `{updated}` | FR-NTF-03 |
| GET/PUT | `/api/v1/notifications/preferences` | My choice per kind, in the app | FR-NTF-05 |

Contract 0.27.0. Every route needs `CLINIC_VIEW` (every role) and acts on the caller's own
notifications in the request's clinic: another member's or another clinic's is a 404
`REQ_NOT_FOUND`. A notification is `{id, kind, title, link, entity_type, entity_id, created_at,
read_at}`; titles come from a typed, non-clinical catalogue. `latest_id` changes when one arrives,
so the summary's ETag does too. `PUT /preferences` takes `{items: [{kind, channel?, enabled}]}`
(channel `IN_APP`, the default; any other is 409 `CLN_INVALID_TRANSITION`; an unknown kind or an
empty list is 422) and returns every kind with its label. A change is audited
(`notification.preferences_changed`); reading is not. `Cache-Control: no-store`.

Notifications are written by the features' own transactions (ADR-0017): a booking, a
reschedule, a cancellation and an arrival or walk-in tell the appointment's doctor; a message
that fails tells the owners and the front desk; an accepted invitation tells the owners. The
member who made the change is never told. From M6a-P8 (contract 0.28.0) the kind
`schedule.bookings_to_move` tells the active owners and front desk when a schedule change kept
booked sessions (link `/bookings-to-move`).
