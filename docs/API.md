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
| GET | `/api/v1/clinic/doctors` | List doctors | every role (`DOCTORS_VIEW`) | Implemented (M1-P3) |
| GET | `/api/v1/clinic/doctors/{doctor_id}` | One doctor | every role (`DOCTORS_VIEW`) | Implemented (M1-P3) |
| GET | `/api/v1/clinic/staff` | List staff with roles | OWNER (`STAFF_MANAGE`) | Implemented (M1-P3) |
| PATCH | `/api/v1/clinic` | Edit clinic settings | OWNER | M1-P5 |
| POST | `/api/v1/clinic/doctors` | Add a doctor | OWNER | M1-P5 |
| PATCH | `/api/v1/clinic/doctors/{doctor_id}` | Edit doctor | OWNER | M1-P5 |
| POST | `/api/v1/clinic/staff` | Invite staff | OWNER | M1-P5 |
| PATCH | `/api/v1/clinic/staff/{membership_id}` | Change role / deactivate | OWNER | M1-P4 (role change) / M1-P5 |
| GET | `/api/v1/clinic/audit-events` | Audit log | OWNER | FR-AUD-03 (P1) — backlog; not in the P0 permission matrix |

The doctor and staff lists return `{"items": [...]}` with no cursor: a clinic has one to four
doctors and a handful of staff, so the paginated envelope above starts with the first list that
can grow (patients, M2).

### Ops console (M1, M2, M6)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/ops/clinics` | Create clinic + owner invite (FR-OPS-01) |
| GET | `/api/v1/ops/clinics` | List with onboarding state |
| GET | `/api/v1/ops/clinics/{clinic_id}/health` | Usage metrics, no clinical data (FR-OPS-03) |
| POST | `/api/v1/ops/clinics/{clinic_id}/patient-imports?dry_run=true` | CSV import (FR-PAT-08) |
| GET | `/api/v1/ops/jobs?state=dead` | Dead jobs |

### Patients (M2)

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET | `/api/v1/patients?q=` | Lookup by phone, code or name prefix | FR-PAT-04 |
| POST | `/api/v1/patients` | Register (returns `409 PAT_PHONE_EXISTS` with candidates unless `confirm_new=true`) | FR-PAT-01/02 |
| GET/PATCH | `/api/v1/patients/{patient_id}` | Profile / edit | FR-PAT-01 |
| PUT | `/api/v1/patients/{patient_id}/consent` | Consent, language, opt-out | FR-PAT-05 |
| GET | `/api/v1/patients/{patient_id}/timeline` | Appointments, visits, Rx, reminders | FR-VIS-03 |

### Schedules, appointments, queue (M3)

| Method | Path | Purpose | Req |
|---|---|---|---|
| GET/PUT | `/api/v1/doctors/{doctor_id}/schedule` | Weekly schedule | FR-APT-01 |
| POST | `/api/v1/doctors/{doctor_id}/schedule-exceptions` | Leave / extra session | FR-APT-01 |
| GET | `/api/v1/sessions?doctor_id=&date=` | Sessions with availability | FR-APT-02 |
| POST | `/api/v1/appointments` | Book (slot or token) | FR-APT-03/04 |
| POST | `/api/v1/appointments/{id}/reschedule` | Reschedule | FR-APT-05 |
| POST | `/api/v1/appointments/{id}/cancel` | Cancel with reason | FR-APT-05 |
| GET | `/api/v1/queue?doctor_id=&date=` | Queue (supports `ETag` / `If-None-Match`) | FR-QUE-01/03 |
| POST | `/api/v1/appointments/{id}/transitions` | `{ "to": "ARRIVED" }` | FR-QUE-02 |
| POST | `/api/v1/queue/walk-ins` | Add walk-in to today | FR-QUE-04 |

### Visits and prescriptions (M4)

| Method | Path | Purpose | Req |
|---|---|---|---|
| POST | `/api/v1/visits` | Start visit (from appointment or walk-in) | FR-VIS-01 |
| GET/PATCH | `/api/v1/visits/{visit_id}` | Clinical record | FR-VIS-02 |
| POST | `/api/v1/visits/{visit_id}/complete` | Complete | FR-VIS-05 |
| POST | `/api/v1/visits/{visit_id}/addenda` | Addendum after lock | FR-VIS-05 |
| POST | `/api/v1/visits/{visit_id}/prescriptions` | Create draft | FR-RX-01 |
| PUT | `/api/v1/prescriptions/{rx_id}` | Replace draft body | FR-RX-01..03 |
| POST | `/api/v1/prescriptions/{rx_id}/issue` | Issue (immutable) → PDF + link jobs | FR-RX-06 |
| POST | `/api/v1/prescriptions/{rx_id}/revise` | New version superseding | FR-RX-09 |
| GET | `/api/v1/prescriptions/{rx_id}/pdf` | Short-lived download URL | FR-RX-06 |
| GET/POST/DELETE | `/api/v1/rx-favourites` | Favourites | FR-RX-05 |
| GET/POST/DELETE | `/api/v1/rx-templates` | Templates | FR-RX-05 |
| GET | `/api/v1/medicine-suggestions?q=` | From this clinic's history only | FR-RX-10 |

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
