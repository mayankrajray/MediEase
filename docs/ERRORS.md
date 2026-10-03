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
| `SYS_` | Unexpected server errors | | `WEB_` | Web app → API (raised in the browser/web server, never by the API) |

## Platform

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `CFG_INVALID` | — (process exits) | Settings failed validation | Missing/invalid env var | Start-up log `config.invalid` naming the field(s), `.env.example` (M0-P2) |
| `READY_DB_UNAVAILABLE` | 503 | Database not reachable | db down, wrong host (`db` inside compose, `localhost` outside), wrong credentials | `ready.check_failed` (WARNING) with `cause`; `make ps`, db logs, DEBUGGING §5.2 (M0-P3) |
| `READY_DB_TIMEOUT` | 503 | Database check exceeded 2 s | Connect, pool wait or `SELECT 1` took over 2 s: db overloaded, network, pool exhausted | `ready.check_failed` with `cause` (`ConnectionTimeout`, `QueryCanceled`, `TimeoutError`); db metrics, slow queries (M0-P3) |
| `REQ_VALIDATION_FAILED` | 422 | Request body/query invalid | Client sent wrong shape (Pydantic, M1-P2), or a value failed a domain rule (`InvalidValue`) | `details.fields[]` lists each `field` and `reason`; the value itself is never echoed (M1-P2) |
| `REQ_NOT_FOUND` | 404 | Resource not found | Unknown route (M0-P2); wrong ID **or other clinic's resource** (M1+; repositories raise `NotFound` from M1-P1) | Access log `route` is null for unknown routes; tenancy context for resources — expected for cross-clinic access |
| `REQ_METHOD_NOT_ALLOWED` | 405 | Method not allowed on this URL | Client used the wrong HTTP method | `Allow` response header lists valid methods (M0-P2) |
| `REQ_UNSUPPORTED_MEDIA_TYPE` | 415 | Wrong body format | JSON endpoint called without `Content-Type: application/json` (e.g. an HTML form) | Client request headers (M1-P2) |
| `REQ_CONFLICT_IDEMPOTENCY` | 409 | Same `Idempotency-Key` with a different body | Client retry bug | Client code *(planned, M1)* |
| `REQ_RATE_LIMITED` | 429 | Too many requests | Abuse or client loop | `Retry-After` header; rate-limit logs *(planned, M1)* |
| `SYS_UNEXPECTED` | 500 | Something went wrong | Unhandled exception | API log `level=ERROR` (`app.unexpected_error`) with same `request_id`, stack trace (M0-P2) |

Other framework-level 4xx errors without a catalogued code are returned in the envelope as
`REQ_<WERKZEUG_NAME>` (e.g. `REQ_UNSUPPORTED_MEDIA_TYPE`); give them a row here when a feature
starts relying on them. Any 5xx is returned as `SYS_UNEXPECTED` (M0-P2).

## Web app → API (M0-P4)

Raised by `apps/web/src/lib/api/client.ts`, never by the API. Shown to staff with
"Ref: <request_id>"; the ID is the one the web app sent, so search the API log for it — if it is
absent there, the request never reached the API.

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `WEB_API_UNREACHABLE` | — (status 0) | The API could not be reached | API down or starting, wrong `API_INTERNAL_URL`, DNS, or no answer within 5 s (`details.reason`: `network` or `timeout`) | `make ps`, `docker compose logs api`, `API_INTERNAL_URL` in the web environment |
| `WEB_API_BAD_RESPONSE` | as received | The response was not the contract's JSON | A proxy's HTML error page (502/504), an empty body, or contract drift | Response body in the web server log; `make contract-check`; API contract tests |

## Auth and permissions (M1)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `WEB_CLINIC_NOT_ONBOARDING` | 409 (web) | <clinic> is already set up, so it cannot be continued here | The ops wizard was opened with `?clinic=<id>` for a clinic that is no longer `ONBOARDING` | Clinic status in `/ops`; raised by the web app, never by the API |
| `AUTH_INVALID_CREDENTIALS` | 401 | Wrong login details | Typo, unknown email/phone, or no password set yet; never reveals which. Also a wrong current password when accepting an invitation for an existing account (R13; the audit row carries `via: invite`) | `auth.sign_in_failed` with `reason` (`unknown_identifier`, `no_password`, `wrong_password`) and `user_id` when known (M1-P2) |
| `AUTH_LOCKED` | 423 | Account temporarily locked | 5 consecutive wrong passwords (FR-AUTH-04), counted across sign-in and invitation acceptance for an existing account (R13); `Retry-After` and `details.retry_after_seconds` give the remaining time | `auth.locked` (WARNING); `users.locked_until`. Waiting 15 min unlocks; ops can clear `locked_until` (RUNBOOK §17) (M1-P2) |
| `AUTH_SESSION_EXPIRED` | 401 | Please sign in again | Refresh token missing, unknown, expired or revoked (signed out); from M1-P3 also a missing, invalid or expired `me_access` token, or a session whose refresh-token family is no longer live (sign-out and reuse revocation end access at once) | `auth.refresh_failed` / `auth.rejected` with `reason`; cookie jar; `refresh_tokens` row (M1-P2, M1-P3) |
| `AUTH_REFRESH_REUSED` | 401 | Session ended for safety | A rotated refresh token was presented again → whole family revoked. Possible token theft, or two refreshes racing (the web app serialises them with a Web Lock since M1-P6) | `auth.refresh_reused` (WARNING) with `user_id`, `session_id` (= `refresh_tokens.family_id`) (M1-P2) |
| `AUTH_CSRF_INVALID` | 403 | Request could not be verified | Unsafe `/api/*` request with session cookies but missing/mismatched `X-CSRF-Token` (must equal the `me_csrf` cookie) | Web client; DEBUGGING §5.3 (M1-P2) |
| `AUTH_ACCOUNT_DISABLED` | 403 | Account disabled | Right password, but user disabled or no `ACTIVE` membership (and not ops); on refresh it also revokes the session; from M1-P3 also returned mid-session when the user or their last membership is deactivated (R7, AC4) | `auth.sign_in_failed` / `auth.refresh_failed` / `auth.rejected` with `reason`; `users.status`, `clinic_memberships.status` (M1-P2, M1-P3) |
| `PERM_DENIED` | 403 | You don't have access to this action | The role lacks the permission the endpoint declared (`details.permission`, `details.role`), an ops user called a clinic route, or clinic staff called an ops route (R10) | `perm.denied` with `reason`; PRD §8.1 matrix in `domain/identity/permissions.py` and its table test (M1-P3) |
| `PERM_CLINIC_REQUIRED` | 400 | Choose a clinic | A user with several memberships sent no `X-Clinic-ID`, or sent one that is malformed or not one of their clinics — the same answer either way, so it never reveals that a clinic exists (R6) | `perm.denied` `reason=clinic_required` with `clinic_count`; clinic switcher (M1-P3) |
| `CLN_SUSPENDED` | 403 | This clinic is suspended | The resolved clinic is `SUSPENDED`; `/me` still lists it with its status so the web app can explain why | `perm.denied` `reason=clinic_suspended`; `clinics.status`; ops reactivates (M1-P3) |
| `CLN_SLUG_TAKEN` | 409 | That clinic URL is taken | Another clinic already uses that slug; slugs are unique platform-wide because they appear in public links from M7 | Ops "create clinic" form; `clinics.slug` (M1-P5) |
| `CLN_MEMBER_EXISTS` | 409 | This person is already a member of this clinic | I2: one membership per user per clinic, whatever its status. A still-pending invitation is re-issued instead of refused; a deactivated member cannot be re-invited in M1 | `clinic_memberships` for that clinic and user (M1-P5) |
| `CLN_INVITE_INVALID` | 404 | This invitation link is not valid | Unknown or malformed secret, or one retired by a newer invitation to the same person | `staff.invite_rejected` with `reason`; `clinic_memberships.invite_token_hash` (M1-P5) |
| `CLN_INVITE_EXPIRED` | 410 | This invitation has expired | Older than 7 days (`INVITE_TTL`); the clinic invites them again | `staff.invite_rejected` `reason=expired`; `invite_expires_at` (M1-P5) |
| `CLN_INVITE_USED` | 410 | This invitation has already been used | The membership is active already: sign in instead. The digest is kept precisely so a replay can say this | `staff.invite_rejected` `reason=used`; `invite_accepted_at` (M1-P5) |
| `CLN_LAST_OWNER` | 409 | A clinic needs at least one owner | Demoting or deactivating the only active owner (R9). Raised by `ClinicMembership.change_role`/`deactivate`; reached over HTTP by `PATCH /api/v1/clinic/staff/{membership_id}` (M1-P4), which records nothing when it refuses | Staff settings; `clinic_memberships` roles and statuses for that clinic |
| `CLN_OWNER_REQUIRED` | 409 | A clinic needs an active owner before it can be activated | Activating a clinic whose owner has not accepted the invite yet (I1) | Ops onboarding; `Clinic.activate` (domain, M1-P1) |
| `CLN_INVALID_TRANSITION` | 409 | That status change isn't allowed | e.g. deactivating a deactivated membership, suspending an onboarding clinic; `details`: `entity`, `state`, `action` | State machines in `domain/clinics`, `domain/identity` (domain, M1-P1) |

Domain codes marked *(domain, M1-P1)* are raised by the domain today; they reach HTTP clients
through the error envelope once endpoints use them (M1-P3/P5). Every domain or application codehas its HTTP status in `delivery/errors.py::DOMAIN_ERROR_STATUS`; a code missing there is logged
as `app.unmapped_domain_error` and answered as `SYS_UNEXPECTED`. Input that fails a domain value
rule (phone, email, slug, PIN code, time zone, required text) raises `REQ_VALIDATION_FAILED` with
`details.fields` — never the rejected value. A repository given another
clinic's entity raises `TenancyViolation`, a programming error that surfaces as `SYS_UNEXPECTED`
(see "Platform"), not as a user-facing code.

**Database-level guard (not an API code).** `UPDATE`, `DELETE` and `TRUNCATE` on `audit_events`
fail with `AUD_APPEND_ONLY` (FR-AUD-02, M1-P4). No request can reach it — nothing in the
application issues those statements — so it never appears in an error envelope; it protects
against a bug, a migration mistake or a stolen connection. Lifting it is an approved procedure
(RUNBOOK §18).

## Patients (M2)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `PAT_PHONE_INVALID` | 422 | Phone number is not valid | Not normalisable to E.164 (spec patients R1); `details.fields` names `phone`; the value is never echoed | Register and edit (M2-P2); `make psql` on the request ID, not the number |
| `PAT_PHONE_EXISTS` | 409 | Patients already use this number | The clinic has patients on this phone (families share phones); `details.candidates` lists up to 10 (`id`, `code`, `full_name`, `age_years`) for the signed-in staff member. Resend with `confirm_new: true` to register another person. Also the loser of two simultaneous registrations of one new number (R9, AC6) | Log `patient.duplicate_phone_offered` (a count, never names); registration flow (FR-PAT-02, M2-P2) |
| `PAT_GUARDIAN_REQUIRED` | 422 | A parent or guardian's name is required for a patient under 18 | Age < 18 on the registration (or edit) date without a `guardian_name`; the phone is the guardian's (spec patients R3, D1). Raised by the domain in M2-P1 | FR-PAT-06; the age is computed for the date asked about, not stored |
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
