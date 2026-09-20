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

| Method | Path | Purpose | Req |
|---|---|---|---|
| POST | `/api/v1/auth/sign-in` | Email/phone + password | FR-AUTH-01 |
| POST | `/api/v1/auth/refresh` | Rotate refresh token | FR-AUTH-02 |
| POST | `/api/v1/auth/sign-out` | Revoke token family | FR-AUTH-02 |
| GET | `/api/v1/me` | Current user, memberships, permissions | FR-AUTH-03 |

### Clinic administration (M1)

| Method | Path | Purpose | Role |
|---|---|---|---|
| GET/PATCH | `/api/v1/clinic` | Clinic settings | OWNER |
| GET/POST | `/api/v1/clinic/doctors` | List / add doctors | OWNER |
| PATCH | `/api/v1/clinic/doctors/{doctor_id}` | Edit doctor | OWNER |
| GET/POST | `/api/v1/clinic/staff` | List / invite staff | OWNER |
| PATCH | `/api/v1/clinic/staff/{membership_id}` | Change role / deactivate | OWNER |
| GET | `/api/v1/clinic/audit-events` | Audit log (P1) | OWNER |

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
