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
| `PRT_` | Patient portal accounts (M6a-P3) | | | |
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
| `REQ_UNSUPPORTED_MEDIA_TYPE` | 415 | Wrong body format | JSON endpoint called without `Content-Type: application/json` (e.g. an HTML form); the patient import called without `text/csv` (M2-P4) | Client request headers (M1-P2) |
| `REQ_REQUEST_ENTITY_TOO_LARGE` | 413 | The body is too large | The patient import's file is over 2 MB (M2-P4; the limit applies to that route only) | Split the file; RUNBOOK §10 |
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
| `CLN_MEMBER_EXISTS` | 409 | This person is already a member of this clinic | I2: one membership per user per clinic. Refused for an active member. A still-pending invitation is re-issued instead, and from M6a-P5 a deactivated member is invited back (`staff.reinvited`) | `clinic_memberships` for that clinic and user (M1-P5) |
| `CLN_INVITE_RATE_LIMITED` | 429 | Too many invitations for now | M6a-P5: more than 10 invitations in an hour for one clinic (`POST /clinic/staff`), or more than 3 resends in an hour for one member (`POST /clinic/staff/{id}/resend`). `Retry-After` gives the seconds to the next hour | `staff.invite_rate_limited` with `bucket`; `public_rate_limits` rows `staff-invite:<clinic>` / `staff-invite-resend:<membership>` |
| `CLN_INVITE_INVALID` | 404 | This invitation link is not valid | Unknown or malformed secret, or one retired by a newer invitation to the same person | `staff.invite_rejected` with `reason`; `clinic_memberships.invite_token_hash` (M1-P5) |
| `CLN_INVITE_EXPIRED` | 410 | This invitation has expired | Older than 7 days (`INVITE_TTL`); the clinic invites them again | `staff.invite_rejected` `reason=expired`; `invite_expires_at` (M1-P5) |
| `CLN_INVITE_USED` | 410 | This invitation has already been used | The membership is active already: sign in instead. The digest is kept precisely so a replay can say this | `staff.invite_rejected` `reason=used`; `invite_accepted_at` (M1-P5) |
| `CLN_LAST_OWNER` | 409 | A clinic needs at least one owner | Demoting or deactivating the only active owner (R9). Raised by `ClinicMembership.change_role`/`deactivate`; reached over HTTP by `PATCH /api/v1/clinic/staff/{membership_id}` (M1-P4), which records nothing when it refuses | Staff settings; `clinic_memberships` roles and statuses for that clinic |
| `CLN_OWNER_REQUIRED` | 409 | A clinic needs an active owner before it can be activated | Activating a clinic whose owner has not accepted the invite yet (I1) | Ops onboarding; `Clinic.activate` (domain, M1-P1) |
| `CLN_INVALID_TRANSITION` | 409 | That status change isn't allowed | e.g. deactivating a deactivated membership, suspending an onboarding clinic, or (M6a-P5) resending the invitation of a member who is not `INVITED`; `details`: `entity`, `state`, `action` | State machines in `domain/clinics`, `domain/identity` (domain, M1-P1) |

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

## Patient portal and Google sign-in (M6a-P3)

ADR-0015. Portal routes use the portal cookies (`me_pt_access`, `me_pt_refresh`, `me_pt_csrf`)
and audience `mediease-portal`; the staff codes above (`AUTH_SESSION_EXPIRED`,
`AUTH_REFRESH_REUSED`, `AUTH_CSRF_INVALID`, `AUTH_LOCKED`, `AUTH_ACCOUNT_DISABLED`) mean the same
for a portal session, logged as `portal.*` instead of `auth.*`. A staff token on a portal route,
or a portal token on a staff route, is `AUTH_SESSION_EXPIRED` (`auth.rejected` / `portal.rejected`
`reason=invalid_token`).

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `PRT_INVALID_CREDENTIALS` | 401 | The email or password is incorrect | Unknown email, a Google-only account (no password), or a wrong password; never says which | `portal.sign_in_failed` with `reason` (`unknown_email`, `wrong_password`, `locked`) and `account_id` when known |
| `PRT_EMAIL_TAKEN` | 409 | An account with this email already exists | Sign-up with an email a password account already uses (one per email, `uq_patient_accounts_password_email`). Accepted enumeration risk, rate limited (decision 7). A Google account with the same email is separate and never merged | `portal.sign_up_refused` `reason=email_taken` |
| `AUTH_RATE_LIMITED` | 429 | Too many attempts; wait a minute | Over 10 portal sign-ups, 30 portal sign-ins or 30 Google starts/callbacks per minute from one caller (salted IP fingerprint); from M6a-P4 also 5 reset requests or 10 reset/verify completions per minute, and more than 3 verification resends an hour for one account. `Retry-After` gives the seconds | `auth.rate_limited` with `bucket` (`portal-sign-up`, `portal-sign-in`, `google`, `password-reset-staff`, `password-reset-patient`, `password-reset-complete`, `verify-email`); `public_rate_limits` |
| `AUTH_GOOGLE_FAILED` | redirect | Google sign-in did not finish | The callback answers with a redirect to `/sign-in` or `/portal/sign-in` and `?reason=` instead of an envelope: `google_failed` (flow cookie missing, expired or tampered with, `state` mismatch, ID token refused, email not verified, fake provider without a login hint), `google_cancelled` (Google returned `error`, e.g. `access_denied`), `account_disabled`, `too_many_attempts` | `google.failed` with `intent` and `reason` (`flow_invalid`, `state_mismatch`, `provider_error`, `id_token_invalid`, `nonce_mismatch`, `token_refused`, `jwks_unreachable`, `email_not_verified`, `fake_login_hint_missing`, …) |
| `AUTH_GOOGLE_NO_STAFF_ACCOUNT` | redirect | No MediEase staff account uses this Google address | Staff Google sign-in whose verified email matches no staff user, or a platform ops user (who may not use Google). Google never creates staff access (FR-AUTH-07); redirect reason `google_no_account` | `google.failed` `intent=staff` `reason=unknown_email` or `platform_ops`; invite the address first |

## Emailed links and account email (M6a-P4)

ADR-0016. A reset request always answers 202 `{"accepted": true}`; whether an email went out is
only in the log (`auth.password_reset_requested` `sent=true|false`).

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `AUTH_TOKEN_INVALID` | 404 | This link is not valid any more | Unknown, already used, superseded by a newer link to the same account, for another kind of account (a staff link on the portal), or sent to an address the account no longer has; one answer for all | `auth.email_token_rejected`; `email_tokens` `used_at` / `superseded_at` for the account (never search by the token) |
| `AUTH_TOKEN_EXPIRED` | 410 | This link has expired | A reset link after 30 minutes, a verification link after 24 hours | `email_tokens.expires_at`; ask for a new link |
| `EMAIL_SMTP_UNREACHABLE` | job | The worker could not reach the SMTP server | Provider down, wrong `SMTP_HOST`/`SMTP_PORT`, or locally the `mailpit` container stopped; retried with back-off, each retry with a new link | `email.failed` (WARNING) with `reason`, `attempt`; `jobs.last_error_code` for kind `send_auth_email` or (M6a-P5) `send_staff_invite`; RUNBOOK §20 |
| `EMAIL_SMTP_AUTH_REFUSED` | job (dead) | The SMTP login was refused | Wrong `SMTP_USERNAME`/`SMTP_PASSWORD`; not retried | `email.failed`; the provider's SMTP key page |
| `EMAIL_SMTP_RECIPIENT_REFUSED` | job (dead) | The provider refused the address | An address the provider has suppressed (earlier bounce or complaint); not retried | The provider's suppression list |
| `EMAIL_SMTP_<code>` | job | Another SMTP answer | 4xx is retried (e.g. `EMAIL_SMTP_451`), 5xx is not (e.g. sending domain not verified) | `email.failed`; the provider's logs (L-11) |

## Patients (M2)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `PAT_PHONE_INVALID` | 422 | Phone number is not valid | Not normalisable to E.164 (spec patients R1); `details.fields` names `phone`; the value is never echoed | Register and edit (M2-P2); `make psql` on the request ID, not the number |
| `PAT_PHONE_EXISTS` | 409 | Patients already use this number | The clinic has patients on this phone (families share phones); `details.candidates` lists up to 10 (`id`, `code`, `full_name`, `age_years`) for the signed-in staff member. Resend with `confirm_new: true` to register another person. Also the loser of two simultaneous registrations of one new number (R9, AC6) | Log `patient.duplicate_phone_offered` (a count, never names); registration flow (FR-PAT-02, M2-P2) |
| `PAT_GUARDIAN_REQUIRED` | 422 | A parent or guardian's name is required for a patient under 18 | Age < 18 on the registration (or edit) date without a `guardian_name`; the phone is the guardian's (spec patients R3, D1). Raised by the domain in M2-P1 | FR-PAT-06; the age is computed for the date asked about, not stored |
| `PAT_OPTED_OUT` | 409 | This patient asked not to be messaged. Opt them back in to record new consent. | Recording consent for a patient who is opted out (spec R6, M2-P3 decision A); nothing changed | `GET /patients/{id}` shows `opted_out_at`; the way back is `POST /patients/{id}/opt-in`, which takes the new consent |
| `PAT_NOT_OPTED_OUT` | 409 | This patient has not opted out. Record consent instead. | Opt-in for a patient with no opt-out (M2-P3) | `opted_out` on the patient; use `PUT /patients/{id}/consent` |
| `PAT_IMPORT_INVALID` | 422 | The import file cannot be read. Nothing was imported. | The file as a whole is unusable (spec R8, M2-P4): a header missing a column, naming an unknown or repeated one, not UTF-8, broken CSV quoting, no data rows, or more than 5,000. `details.problems` lists fixed sentences naming columns or positions, never the file's text. Bad *rows* are not this error: they are in the 200 report's `errors` | Log `patient.import_dry_run` / `patient.import_committed` (counts only); RUNBOOK §10; fix the file and dry-run again |

## Appointments and queue (M3)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `SCH_INVALID_BLOCK` | 422 | This block cannot be scheduled | A block or extra session shorter than 15 minutes or longer than 12 hours (an end at or before the start means the next day, so 13:00-10:00 is 21 hours), a slot length that does not divide it, or the value the booking mode needs missing (slot length for SLOTS, capacity for TOKENS). `details.reason` says which; `details.index` points into the request's `blocks` (spec R14, M3-P1) | The request body; the clinic's `booking_mode` |
| `SCH_OVERLAP` | 409 | Two of this doctor's blocks overlap | Two weekly blocks overlap, also across midnight (an overnight block into the next morning) and from Sunday into Monday (`details.first`/`second` index the blocks); or an extra session overlaps what the rules plan that day, the day before or the day after (R15) | `GET /clinic/doctors/{id}/schedule`; the overnight flag on each block |
| `SCH_LEAVE_EXISTS` | 409 | The doctor already has leave on that date | A second whole-day leave for the same doctor and date (R17) | The schedule's `exceptions` |
| `SCH_MODE_INCOMPATIBLE` | 409 | Every current block needs a slot length (or capacity) for this booking mode | Changing `booking_mode` while a block in force or an upcoming extra lacks the new mode's value (R19); nothing changed | Give every block both values, then change the mode |
| `APT_SLOT_TAKEN` | 409 | That slot was just booked | Another active appointment holds it: expected under contention (FR-APT-04, AC1), backed by a partial unique index | `GET /sessions` shows the slot `available: false`; DEBUGGING §5.5 if it happens without contention |
| `APT_SESSION_FULL` | 409 | This session is full | `booked_count` reached `capacity`, also when a parallel booking took the last place (AC1) | `sessions.booked_count` vs `capacity`; the CHECK keeps them consistent |
| `APT_SESSION_CLOSED` | 409 | The doctor is not available then | The session is `CLOSED` (a leave or a changed block left it with bookings, D10), retired, or its doctor is inactive. Existing bookings there can still be cancelled or rescheduled | The schedule's `exceptions`; `kept_sessions` of the change; `sessions.status` |
| `APT_OUTSIDE_SCHEDULE` | 422 | That time is outside the doctor's hours | `slot_start` is not one of the session's slot starts (R3), e.g. 10:30 in a 60-minute grid | The session's `slots`; the offset sent (any offset is compared as an instant) |
| `APT_IN_PAST` | 422 | That time has already passed | Token mode: the session has ended; slot mode: the slot has ended (D12) | Clock, the clinic timezone (§5.4) |
| `APT_NOT_MODIFIABLE` | 409 | This appointment cannot be cancelled/rescheduled now | Cancel from a status other than `BOOKED`/`ARRIVED` or after the session ended (D14); reschedule from anything but `BOOKED` (D15). `details.status` and `details.action` say which | `appointments.status`; the appointment's `history` |
| `APT_ALREADY_BOOKED` | 409 | This patient is already booked in this session | One active appointment per patient per session (D13), also a double-click; `details.appointment_id` is the existing one | `GET /appointments/{id}`; the patient's `/appointments` |
| `QUE_INVALID_TRANSITION` | 409 | That status change isn't allowed | Not an edge of the state machine (e.g. `COMPLETED → ARRIVED`, AC3), or the screen's `from` is no longer the status: another tab moved the patient first (D18). `details.from` is the real status, `details.to` the one asked | The appointment's `history`; refresh the queue |
| `QUE_WRONG_TIME` | 409 | The queue can't be changed for that time now | `details.reason`: `not_today` (not the session's clinic-local date, and not a running overnight session) or `not_started` (a no-show before the session or slot began) (D19) | Clinic timezone (§5.4); the session's `starts_at` |
| `QUE_NO_SESSION` | 409 | The doctor has no session left today | A walk-in with no open session running or still to start today, or a named `session_id` that is not today's or has ended (D21) | `GET /queue` for today; add an extra session |

## Visits and prescriptions (M4)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `VIS_LOCKED` | 409 | This visit is locked; add an addendum | An edit from 24 h after completion (FR-VIS-05, AC6), or creating, saving or issuing version 1 of its prescription then (M4-P2, 2A); `details.locked_at` | `visits.locked_at`; the server clock |
| `VIS_ALREADY_EXISTS` | 409 | This consultation already has a visit | A second start for the same appointment (two clicks, two tabs); `details.visit_id` is the existing one: open it | `visits.appointment_id` |
| `VIS_NOT_STARTABLE` | 409 | Start the consultation on the queue first | The appointment is not `IN_CONSULTATION` (decision 1A); `details.status` | The appointment's `history` |
| `VIS_NOT_YOURS` | 403 | Only the visit's doctor can change it | A doctor (or owner-doctor) writing another doctor's visit, or a caller with no active doctor profile (spec §2, 3A) | `doctors.user_id`; the visit's `doctor_id` |
| `VIS_STALE` | 409 | This visit was changed elsewhere; reload it and try again | The `PATCH` sent an older `revision`: another tab saved first (4A); `details.revision` is the current one | Reload the visit |
| `VIS_NOT_COMPLETED` | 409 | Edit the visit directly until it is completed | An addendum on an open visit (R3) | `visits.status` |
| `VIS_ADDENDUM_APPEND_ONLY` | — (database) | — | An `UPDATE`, `DELETE` or `TRUNCATE` of `visit_addenda` (migration 0009); never from the app | The statement's author; RUNBOOK for deliberate corrections |
| `RX_NOT_DRAFT` | 409 | This prescription is already issued; revise it instead | A save, issue or discard of an issued or superseded version (FR-RX-09, AC1); `details.status`. Also raised by the database triggers (migration 0010) for any direct change | `prescriptions.status`; revise from the latest version |
| `RX_EMPTY` | 422 | Add at least one medicine or advice | Issuing a draft with no items and no advice (R4) | The draft's `items`, `advice` |
| `RX_DOCTOR_INCOMPLETE` | 422 | The doctor's profile is missing registration details | A printed field is blank (AC4); `details.fields` names them (comma-separated). The app requires them (I3), so this means data changed outside it | Doctor settings (FR-ORG-02) |
| `RX_STALE` | 409 | This prescription was changed elsewhere; reload it and try again | The `PUT` or issue sent an older `revision` (3A), or a favourite or template `PUT` did (M4-P3); `details.revision` is the current one | Reload it |
| `RX_ALREADY_EXISTS` | 409 | This visit already has a prescription | A second "new prescription" for the visit (1A); `details.prescription_id` | The consultation view's `prescriptions` |
| `RX_DRAFT_EXISTS` | 409 | A revision is already being drafted | Revising while the chain has a draft; `details.prescription_id` is that draft | Continue the draft |
| `RX_NOT_LATEST` | 409 | Revise the latest version | Revising a superseded version; `details.latest_id`. Also printing a superseded version without `CLINICAL_VIEW` (front desk prints only the current one, M4-P4 1A) | The prescription's `versions`, or `GET /patients/{id}/prescriptions` |
| `RX_NOT_ISSUED` | 409 | Only an issued prescription can be printed | A PDF of a draft (spec D6); `details.status` | Ask the doctor to issue it |
| `RX_PDF_BUSY` | 503 | The prescription is being prepared. Try again in a moment | Another download is rendering this version and held the row lock for more than 10 s (R18); `Retry-After: 2` | `rx.pdf_rendered` / `rx.pdf_failed` logs; a stuck transaction (`pg_stat_activity`) |
| `RX_PDF_FAILED` | 500 | The prescription could not be prepared. Try again | Rendering or storing failed (`details.stage`: `render` \| `store`); nothing was stored, so the next download tries again | `rx.pdf_failed` log (IDs and stage only): fonts or Pango in the image, the blob volume's space and permissions, S3 credentials |
| `RX_NAME_TAKEN` | 409 | You already have one with that name | A favourite or template name the doctor already uses, ignoring case and spaces (M4-P3) | `GET /rx-favourites`, `/rx-templates` |
| `RX_LIBRARY_FULL` | 409 | You have reached the limit; delete one first | 200 favourites or 50 templates per doctor; `details.limit` | The doctor's list |

## Patient links (M4)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `LINK_INVALID` | 404 | This link isn't valid | Tampered or garbled token, a claim that disagrees with the row, another clinic, or a signing key removed (M4-P5) | DEBUGGING §5.9; `scripts/inspect_link_token.py` |
| `LINK_EXPIRED` | 410 | This link has expired | Past `patient_links.expires_at` (90 days) | Replace the link |
| `LINK_REVOKED` | 410 | This link is no longer active | Replaced by staff | `patient_links.revoked_at` |
| `LINK_CHALLENGE_FAILED` | 401 | Those digits don't match | Wrong last 4 digits; `details.attempts_left` | `patient_links.failed_challenges`, `patient_link.challenge_failed` |
| `LINK_LOCKED` | 423 | Too many attempts. Please contact the clinic | 5 wrong answers; every later attempt, right or wrong (AC3) | Staff reset: `POST /prescriptions/{id}/link/reset` |
| `LINK_CHALLENGE_REQUIRED` | 401 | Enter the last 4 digits of your phone number first | No view token, another link's, a forged one, or the 30 minutes ended | The page asks again |
| `LINK_RATE_LIMITED` | 429 | Too many requests. Please wait a moment | > 20 a minute for one link or > 300 from one caller; `Retry-After` | `public_rate_limits` |
| `LINK_NOT_LOCKED` | 409 | This link is not locked | Reset of a link that is not locked (staff) | The link's `locked` |

## Reminders, messaging, webhooks, jobs (M5)

| Code | HTTP | Meaning | Likely cause | Where to look |
|---|---|---|---|---|
| `REM_NO_CONSENT` | 409 | Patient hasn't agreed to messages | Consent false or opted out | Patient consent |
| `REM_IN_PAST` | 422 | The follow-up date is not after today | Client/timezone | Clock, clinic timezone |
| `REM_CLINIC_PHONE_MISSING` | 409 (or on a reminder) | The clinic has no phone number, which `follow_up_due` needs (M5-P4 decision 6A): manual reminders are refused; an automatic one becomes `FAILED` with this code at send time | Phone not entered at onboarding | Clinic settings |
| `REM_NOT_SCHEDULED` | 409 | The reminder was sent, cancelled or skipped and can no longer be changed (M5-P4) | A stale screen | The reminder's status |
| `MSG_TEMPLATE_NOT_FOUND` | — (job) | Template missing at provider | Name/language not approved | Meta template manager, `templates.yaml` |
| `MSG_TEMPLATE_PARAMS` | — (job) | Template variables mismatch | Count/order differs from approved template | DEBUGGING §5.7 |
| `MSG_RECIPIENT_INVALID` | — (job) | Number can't receive WhatsApp | Not on WhatsApp / invalid | A reminder falls back to one SMS when `MESSAGING_SMS_FALLBACK_ENABLED` and the patient consented to SMS (FR-REM-06, M5-P5) |
| `MSG_PROVIDER_RATE_LIMIT` | — (job) | Provider throttled us | Burst sending | Job retries with backoff |
| `MSG_PROVIDER_UNAVAILABLE` | — (job) | Provider error / outage (the provider said so: nothing was sent) | Outage | RUNBOOK "Messaging provider outage" |
| `MSG_OUTCOME_UNKNOWN` | — (job, message) | We cannot tell whether the provider accepted the message: a timeout, a lost connection, or a worker that died during the call or before recording it. Never sent again (M5-P2 decision 4A, at most once); the job is `dead` | Provider latency, a crash, a database error after the call | `messages.error_code`, `v_message_health.outcome_unknown`; call the patient if it matters |
| `MSG_NO_CONSENT` | — (message) | A message refused earlier was not retried: the patient no longer allows WhatsApp (or, for the SMS fallback, SMS) | Opt-out or consent withdrawn between attempts | Patient consent |
| `MSG_NOT_APPLICABLE` | — (message) | A message refused earlier was not retried: what it was about no longer applies (appointment cancelled or over, prescription superseded or its link expired) | Normal | The appointment or prescription |
| `MSG_QUIET_HOURS_DEFERRED` | — (info) | Deferred to 08:00 | FR-REM-04 — expected | Job `run_at` |
| `WH_SIGNATURE_INVALID` | 401 | Webhook rejected | Wrong secret or body re-serialised; or `WHATSAPP_APP_SECRET` is empty (the webhook then refuses everything) | DEBUGGING §5.8 |
| `WH_VERIFY_FAILED` | 403 | Meta's subscription challenge refused (M5-P3) | `WHATSAPP_VERIFY_TOKEN` differs from the token entered in Meta's webhook settings, or is empty | RUNBOOK §9 |
| `WH_RATE_LIMITED` | 429 | More than 600 webhook requests a minute from one caller (M5-P3) | A flood, or a misbehaving proxy; `Retry-After` | `public_rate_limits` |
| `WH_UNMATCHED` | — (event) | A status found no message after the job's five attempts (M5-P3) | A message sent outside this system with our number, or a database restored without recent rows | `webhook_events.error_code` |
| `WH_STOP_UNMATCHED` | — (event, info) | A STOP reply opted nobody out (M5-P5): no clinic has messaged a patient with that number, or the number was hidden and the reply answered none of our messages | A wrong number, a patient whose number changed, a WhatsApp username | `webhook_events.error_code`, `webhook.stop_unmatched` log (no number); opt the patient out by hand if they ask the clinic |
| `MSG_PROVIDER_AUTH` | — (job) | Meta refused our credentials (M5-P3): not retried, logged as an error | `WHATSAPP_ACCESS_TOKEN` expired or lost its permissions; phone number ID wrong | RUNBOOK §9; Meta Business Manager |
| `MSG_PROVIDER_REJECTED` | — (job, message) | Meta refused the message with a code we do not map (M5-P3): not retried | A new or rare Meta error | `messaging.whatsapp_refused` log (`meta_code`) |
| `WH_UNKNOWN_EVENT` | 200 (ignored) | Event type not handled | New provider event | `webhook_events` |
| `JOB_MAX_ATTEMPTS` | — (job) | Job moved to dead | Repeated failure; see `last_error_code` | Ops console dead jobs |
| `JOB_HANDLER_MISSING` | — (job) | No handler for job kind | Deploy mismatch between api and worker: retried like any failure, so a newer API's jobs wait for the worker to catch up | Worker version (`docker compose images worker`) |
| `JOB_HANDLER_ERROR` | — (job) | A handler failed unexpectedly | A bug or an outage inside a handler; retried with back-off. The log has the exception's type only, never its message | `job.handler_error` in the worker log; `last_error_code` |
| `JOB_LOCK_EXPIRED` | — (job) | The worker holding the job stopped renewing its lock | The worker was killed or lost its database; the attempt is already counted, the reaper requeues (or kills at `max_attempts`) | `job.lock_expired` in the log; `docker compose ps worker` |
| `JOB_CLINIC_SUSPENDED` | — (job) | The clinic is suspended | The job was cancelled, not run; a reminder revised or a clinic unsuspended can enqueue its key again | `jobs.state = 'cancelled'` |
