# MediEase — Error Catalogue

Every error the API returns has a stable `code`. Codes never change meaning; retired codes are
marked, not reused. Add a row in the same change that introduces a code.

**Columns:** *Code* · *HTTP* · *Meaning* (what the user was told) · *Likely cause* · *Where to look*.
Status: codes marked *(planned)* are designed but not yet implemented; the milestone is in brackets.

## Prefixes

| Prefix | Area | | Prefix | Area |
|---|---|---|---|---|
| `CFG_` | Configuration (start-up only) | | `APT_` | Appointments and schedules |
| `READY_` | Readiness | | `QUE_` | Queue transitions |
| `REQ_` | Generic request problems | | `VIS_` | Visits |
| `AUTH_` | Authentication and session | | `RX_` | Prescriptions |
| `PERM_` | Authorisation | | `LINK_` | Patient links |
| `CLN_` | Clinic administration | | `REM_` | Reminders |
| `PAT_` | Patients | | `MSG_` / `WH_` / `JOB_` | Messaging, webhooks, jobs |
| `SYS_` | Unexpected server errors | | | |

## Platform

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `CFG_INVALID` | — (process exits) | Settings failed validation | Missing/invalid env var | Start-up log `config.invalid` naming the field(s), `.env.example` (M0-P2) |
| `READY_DB_UNAVAILABLE` | 503 | Database not reachable | db down, wrong host, credentials | `make ps`, db logs, DEBUGGING §5.2 *(planned, M0)* |
| `READY_DB_TIMEOUT` | 503 | Database check exceeded 2 s | db overloaded or network | db metrics, slow queries *(planned, M0)* |
| `REQ_VALIDATION_FAILED` | 422 | Request body/query invalid | Client sent wrong shape | `details.fields[]` lists each field and reason *(planned, M0)* |
| `REQ_NOT_FOUND` | 404 | Resource not found | Unknown route (M0-P2); wrong ID **or other clinic's resource** (M1+) | Access log `route` is null for unknown routes; tenancy context for resources — expected for cross-clinic access |
| `REQ_METHOD_NOT_ALLOWED` | 405 | Method not allowed on this URL | Client used the wrong HTTP method | `Allow` response header lists valid methods (M0-P2) |
| `REQ_CONFLICT_IDEMPOTENCY` | 409 | Same `Idempotency-Key` with a different body | Client retry bug | Client code *(planned, M1)* |
| `REQ_RATE_LIMITED` | 429 | Too many requests | Abuse or client loop | `Retry-After` header; rate-limit logs *(planned, M1)* |
| `SYS_UNEXPECTED` | 500 | Something went wrong | Unhandled exception | API log `level=ERROR` (`app.unexpected_error`) with same `request_id`, stack trace (M0-P2) |

Other framework-level 4xx errors without a catalogued code are returned in the envelope as
`REQ_<WERKZEUG_NAME>` (e.g. `REQ_UNSUPPORTED_MEDIA_TYPE`); give them a row here when a feature
starts relying on them. Any 5xx is returned as `SYS_UNEXPECTED` (M0-P2).

## Auth and permissions (M1)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `AUTH_INVALID_CREDENTIALS` | 401 | Wrong login details | Typo; never reveals which field | `auth.sign_in_failed` |
| `AUTH_LOCKED` | 423 | Account temporarily locked | 5 failed attempts (FR-AUTH-04) | `users.locked_until` |
| `AUTH_SESSION_EXPIRED` | 401 | Please sign in again | Access token expired and refresh failed | Refresh flow, cookie jar |
| `AUTH_REFRESH_REUSED` | 401 | Session ended for safety | Rotated refresh token replayed → family revoked | `refresh_tokens.family_id`; possible token theft |
| `AUTH_CSRF_INVALID` | 403 | Request could not be verified | Missing/mismatched `X-CSRF-Token` | Web client, DEBUGGING §5.3 |
| `AUTH_ACCOUNT_DISABLED` | 403 | Account disabled | User or membership deactivated | `users.status`, `clinic_memberships.status` |
| `PERM_DENIED` | 403 | You don't have access to this action | Role lacks permission (same clinic) | PRD permission matrix |
| `PERM_CLINIC_REQUIRED` | 400 | Choose a clinic | Multi-clinic user without `X-Clinic-ID` | Clinic switcher |
| `CLN_SLUG_TAKEN` | 409 | That clinic URL is taken | Duplicate slug | Ops form |
| `CLN_LAST_OWNER` | 409 | A clinic needs at least one owner | Demoting/deactivating the only owner | Staff settings |

## Patients (M2)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `PAT_PHONE_INVALID` | 422 | Phone number is not valid | Not normalisable to E.164 | Input value (masked in logs) |
| `PAT_PHONE_EXISTS` | 409 | Patients already use this number | Family member or duplicate; `details.candidates` lists patient IDs | Registration flow (FR-PAT-02) |
| `PAT_GUARDIAN_REQUIRED` | 422 | Guardian needed for a minor | Age < 18 without guardian | FR-PAT-06 |
| `PAT_IMPORT_INVALID` | 422 | Import file has errors | Bad columns/rows; report attached | Import dry-run report |

## Appointments and queue (M3)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `APT_SLOT_TAKEN` | 409 | That slot was just booked | Concurrent booking (FR-APT-04) — expected under contention | DEBUGGING §5.5 if it happens without contention |
| `APT_SESSION_FULL` | 409 | This session is full | Capacity reached | `sessions.booked_count` vs `capacity` |
| `APT_SESSION_CLOSED` | 409 | Doctor not available then | Leave exception or closed session | `schedule_exceptions` |
| `APT_OUTSIDE_SCHEDULE` | 422 | Time is outside the doctor's hours | Slot not generated by schedule | Schedule settings; timezone (§5.4) |
| `APT_IN_PAST` | 422 | Can't book in the past | Clock/timezone or user error | Clock port, clinic timezone |
| `APT_NOT_MODIFIABLE` | 409 | Appointment can't be changed now | Already completed/cancelled | `appointments.status` |
| `QUE_INVALID_TRANSITION` | 409 | That status change isn't allowed | e.g. `COMPLETED → ARRIVED` | State machine in spec; `details.from/to` |

## Visits and prescriptions (M4)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `VIS_LOCKED` | 409 | Visit is locked; add an addendum | Edit after 24 h (FR-VIS-05) | `visits.locked_at` |
| `VIS_ALREADY_EXISTS` | 409 | Visit already started | Second start for same appointment | `visits.appointment_id` |
| `RX_NOT_DRAFT` | 409 | Prescription already issued; revise instead | Edit after issue (FR-RX-09) | `prescriptions.status` |
| `RX_EMPTY` | 422 | Add at least one medicine or advice | Issue with no content | Draft body |
| `RX_DOCTOR_INCOMPLETE` | 422 | Doctor profile missing registration details | Registration number/qualification empty | Doctor settings (FR-ORG-02) |
| `RX_PDF_FAILED` | 500 (job) | PDF could not be created | Renderer/font/storage error | `render_pdf` job, worker logs |

## Patient links (M4)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `LINK_INVALID` | 404 | This link isn't valid | Tampered/garbled token, or signing key rotated | DEBUGGING §5.9 |
| `LINK_EXPIRED` | 410 | This link has expired | Past 90 days | `patient_links.expires_at` |
| `LINK_REVOKED` | 410 | This link is no longer active | Revoked by staff | `patient_links.revoked_at` |
| `LINK_CHALLENGE_FAILED` | 401 | Those digits don't match | Wrong last 4 digits | `patient_links.failed_challenges` |
| `LINK_LOCKED` | 423 | Too many attempts — contact the clinic | 5 failed challenges | Staff can reset |

## Reminders, messaging, webhooks, jobs (M5)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `REM_NO_CONSENT` | 409 | Patient hasn't agreed to messages | Consent false or opted out | Patient consent |
| `REM_IN_PAST` | 422 | Reminder time has passed | Client/timezone | Clock, clinic timezone |
| `MSG_TEMPLATE_NOT_FOUND` | — (job) | Template missing at provider | Name/language not approved | Meta template manager, `templates.yaml` |
| `MSG_TEMPLATE_PARAMS` | — (job) | Template variables mismatch | Count/order differs from approved template | DEBUGGING §5.7 |
| `MSG_RECIPIENT_INVALID` | — (job) | Number can't receive WhatsApp | Not on WhatsApp / invalid | SMS fallback (FR-REM-06) |
| `MSG_PROVIDER_RATE_LIMIT` | — (job) | Provider throttled us | Burst sending | Job retries with backoff |
| `MSG_PROVIDER_UNAVAILABLE` | — (job) | Provider error / timeout | Outage | RUNBOOK "Messaging provider outage" |
| `MSG_QUIET_HOURS_DEFERRED` | — (info) | Deferred to 08:00 | FR-REM-04 — expected | Job `run_at` |
| `WH_SIGNATURE_INVALID` | 401 | Webhook rejected | Wrong secret or body re-serialised | DEBUGGING §5.8 |
| `WH_UNKNOWN_EVENT` | 200 (ignored) | Event type not handled | New provider event | `webhook_events` |
| `JOB_MAX_ATTEMPTS` | — (job) | Job moved to dead | Repeated failure; see `last_error_code` | Ops console dead jobs |
| `JOB_HANDLER_MISSING` | — (job) | No handler for job kind | Deploy mismatch between api and worker | Worker version |
