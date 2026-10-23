# Changelog

All notable changes are recorded here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow milestones until the
first production release.

## [Unreleased]

### Changed
- CI (#19): web `npm audit` now blocks on production dependencies only (`--omit=dev`); the
  full-tree audit still runs but is non-blocking. Reason: braces advisory GHSA-vfj7-8cjw-p6xm
  (CVE-2026-93687, braces ≤ 3.0.3) has no patched version and is reachable only through
  `eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` → `micromatch` (dev-only, not in
  the web image). Revisit when braces is patched or Next drops `fast-glob`. `make audit` mirrors CI.

### Added
- M6a-P5 (#49): the owner's Team page (FR-ORG-07, decisions 1A–8A). `/team` (sidebar *Team*,
  owners only) lists every member with role, status, email or phone, invitation expiry and a
  *Doctor profile* badge, as a table from 768 px and cards below. Owners invite (an email address
  gets an email from the worker, new clinic job `send_staff_invite`, with the secret made at send
  time and never shown; phone-only shows the link once), resend (the old link stops working at
  once), change a role (warned before demoting themselves), deactivate (not their own row) and
  invite a deactivated member back (`DEACTIVATED → INVITED`, `staff.reinvited`). Limits: 10
  invitations an hour per clinic, 3 resends per member (`CLN_INVITE_RATE_LIMITED`). Contract
  0.25.0 (fuller `StaffMember`, `TeamInvitation`, `POST /clinic/staff/{id}/resend`). No
  migration and no new dependency. Ops invitations still show the link (until M6c). (FR-AUTH-08, FR-AUTH-05; ADR-0016
  Accepted, decisions 1A–8A). An `EmailPort` with one standard-library SMTP adapter (Brevo free
  for the pilot, L-11; Resend or SES Mumbai by settings), and a pinned Mailpit container
  (`axllent/mailpit:v1.32.0`) catching mail locally at localhost:8025. Requests enqueue the new
  system job `send_auth_email`; the worker makes the single-use token (stored as a digest in
  `email_tokens`, migration `0021`) and sends, so no secret is ever stored. Patients verify a
  password account's email from a page that POSTs (banner and resend, 3 an hour, on `/portal`);
  staff and patients reset a forgotten password (`/forgot-password`, `/portal/forgot-password`)
  with the same 202 for any address, a 30-minute link, the lockout cleared, every session ended
  and a "password changed" email; Google-only patients get a "use Google" notice. Contract
  0.24.0. No new Python or npm dependency. Also: the FR-REM-07 journey no longer tries to cancel
  an earlier booking whose session has ended (it failed on reruns after clinic hours).
- M6a-P3 (#49): patient accounts and Google sign-in (FR-AUTH-07, FR-PRT-01; ADR-0015 Accepted,
  decisions 1A–8A). Patients sign up with a name, email and password (the staff policy) or with
  Google, in `patient_accounts` apart from staff users, with their own sessions: cookies
  `me_pt_access`/`me_pt_refresh`/`me_pt_csrf`, JWT audience `mediease-portal`, routes under
  `/api/v1/portal/` behind a new `@patient` policy; each kind of token is 401 on the other's
  routes (a permanent suite enumerates every route). Google is an OpenID Connect code flow with
  PKCE run by the API (`/api/v1/auth/google/start`, `/callback`; the ID token checked against
  Google's keys, `iss`, `aud`, `exp`, `nonce`): staff are linked once by verified email and then
  by `sub`, never created, and ops users may not use it; patients get a verified account. A
  local-only fake provider (`GOOGLE_OIDC_PROVIDER=fake`, refused when deployed) runs the same
  flow without L-09. Sign-up, sign-in and Google are rate limited per caller
  (`AUTH_RATE_LIMITED`). Migration `0020` (three tables, actor type `PATIENT`); contract 0.23.0.
  Web: *Continue with Google* on `/sign-in`, and `/portal/sign-in`, `/portal/sign-up` and the
  `/portal` account page at 360 px, with the proxy sending portal visitors to the portal's own
  sign-in. No new dependency.
- M6-P2 (#49): every clinic, ops and sign-in screen on the design system (decisions 1A–8A). Lists
  (queue, patient search, follow-ups, ops clinics, a patient's appointments and messages) are
  tables from 768 px and cards below, from one markup with explicit ARIA roles; drawers and
  dialogs slide or fade in with CSS only (none with reduced motion); the queue, follow-ups and
  reminders glide when they reorder, with Motion's layout features loaded on first use; form
  fields share components/ui/Field; the clinic and ops consoles share one responsive Shell;
  sign-in, invitations and the clinic chooser sit in a centred card. The patient page takes the
  colours only (153 KB first visit). No API change.
- M6-P1 (#49): the design system and *Today* (decisions 1A–6A, decision 2 amended by the
  developer). Tokens in Tailwind's `@theme` (teal brand, slate, one accent per status, system
  fonts); our own primitives in `apps/web/src/components/ui/` (Button, Card, StatTile,
  StatusBadge, PageHeader, EmptyState, Skeleton, Tabs), with Tabs on `@radix-ui/react-tabs` 1.2.1
  for its keyboard and ARIA behaviour; `motion` 14.4.0 through `LazyMotion` with reduced motion
  honoured, in the clinic and ops shells only (never `/p/…`). The clinic shell is responsive: a
  sidebar from 1024 px, a Menu drawer below. New `GET /api/v1/dashboard/today` (contract 0.22.0):
  counts shaped by role, a 7-day strip with `USAGE_METRICS_VIEW`, ETag and 304. Clinic members
  now land on `/today`; the queue keeps `/queue`. Web tests run on half the cores (a load-timing
  fix, DEBUG_JOURNAL 20 Oct 2026).
- M5 closed (#40): P1–P6 complete. Pending, with credentials to follow: the live WhatsApp test
  through Meta's test number (L-01, L-02) and the real SMS provider (L-03).
- M5-P6 (#40): the reminder and message screens (FR-REM-02, 05, 07; FR-MSG-04; spec R16-R18).
  The consultation shows the issued prescription's reminder as a chip beside its follow-up date;
  the patient profile lists reminders (move, cancel, add a manual one) and the message history,
  status only, from the new `GET /api/v1/patients/{id}/messages` (contract 0.21.0); failed
  messages say why in plain words with *Call patient*. `/follow-ups` lists overdue follow-ups with
  *Book follow-up* in two interactions. The ops console gains `/ops/messaging-costs`. `make seed`
  adds one overdue follow-up; a new Playwright journey file covers the three screens.
- M5-P5 (#40): opting out by reply, the SMS fallback and message costs (FR-MSG-05, FR-REM-06; spec
  R14, R18, R19; AC5). A WhatsApp reply of STOP, UNSUBSCRIBE, रोकें or बंद opts the sender out in
  every clinic that has messaged that number (a family sharing the phone together), with a SYSTEM
  `patient.opted_out` audit event, and each such clinic replies `opt_out_confirmed`; only a STOP
  keeps its sender's number, encrypted, until processed (migration `0018`: `ix_patients_phone_e164`,
  source type `OPT_OUT`). Behind `MESSAGING_SMS_FALLBACK_ENABLED` (off), a follow-up reminder
  WhatsApp definitely could not deliver gets one SMS if the patient consented to SMS; only a
  console SMS provider exists until L-03, refused in production. Each message records its cost in
  millipaise from `prices.yaml` (migration `0019`), and ops read every clinic's month with
  `GET /api/v1/ops/messaging-costs?month=YYYY-MM`. Contract 0.20.0, web types regenerated. New
  error code `WH_STOP_UNMATCHED`.
- M5-P4 (#40): follow-up reminders and the automatic no-show (FR-REM-01, 02, 04, 05, 07; spec
  R1–R5, R17; appointments R10; AC1, AC2). Issuing a prescription with a follow-up date schedules
  a reminder for 09:00 clinic time the day before (`reminders`, migration `0017`); revisions move
  or cancel the chain's one reminder, and every move gives the reminder a new revision so an
  older send job does nothing. Nothing is sent 21:00–08:00 clinic time (deferred to 08:00);
  consent is read again at send time (`SKIPPED_NO_CONSENT`); the reminder then shows its message's
  status. Staff schedule, move and cancel reminders (`/api/v1/patients/{id}/reminders`,
  `/api/v1/reminders/{id}`), and `/api/v1/follow-ups/pending` lists patients whose follow-up date
  passed without a completed visit. Every 5 minutes, bookings still `BOOKED` an hour after their
  session become `NO_SHOW` (history with no user, SYSTEM audit), one job per clinic. Contract
  0.19.0, web types regenerated. New error codes `REM_CLINIC_PHONE_MISSING`, `REM_NOT_SCHEDULED`;
  audit actions `reminder.scheduled`, `reminder.rescheduled`, `reminder.cancelled`.
- M5-P3 (#40): the WhatsApp Cloud API provider and its webhooks (FR-MSG-03; spec R7, R12, R13,
  R15; AC6). `MESSAGING_PROVIDER=whatsapp_cloud` sends approved templates through Graph API
  `v26.0` (standard-library HTTP, 10 s timeout) with our message ID echoed back in every status;
  Meta's error codes map to `MSG_*` (throttling and outages retried, the rest permanent, a timeout
  never resent). `GET /webhooks/whatsapp` answers Meta's challenge for our verify token; `POST`
  checks `X-Hub-Signature-256` on the raw body before anything else (401, nothing stored), stores
  each body once redacted to IDs and statuses (`webhook_events`, migration `0016`, kept 7 days)
  and processes it in a job: statuses only move forward, and a status proves an unknown outcome
  was delivered. An hourly job re-runs stuck events and counts unconfirmed messages
  (`v_message_health.unconfirmed_24h`). New settings `WHATSAPP_*` (all required with the WhatsApp
  provider), error codes `WH_VERIFY_FAILED`, `WH_RATE_LIMITED`, `WH_UNMATCHED`,
  `MSG_PROVIDER_AUTH`, `MSG_PROVIDER_REJECTED`. `docker-compose.yml` now passes the messaging
  settings of P2 and P3 to the containers.
- M5-P2 (#40): messaging through a `MessagingPort` (FR-MSG-01, 02, 04; FR-APT-06; spec
  reminders-and-messaging R5-R8, AC4, AC7; prescriptions R14, R15). A booking or reschedule for a
  patient who allows WhatsApp enqueues a confirmation in its own transaction; issuing a prescription
  whose link is `PENDING` enqueues the link (`rx_ready`, or `rx_updated` for a revision). The worker
  sends each at most once: the `messages` row (migration `0015`) is written with a unique
  idempotency key before the provider is called, a refusal is retried, and an unknown outcome
  (timeout, crash mid-call) is `FAILED` with `MSG_OUTCOME_UNKNOWN` and never resent. Consent is read
  again at send time; a link more than 24 hours old, or without consent, is `EXPIRED` and audited
  as SYSTEM. Templates live in `adapters/messaging/templates.yaml` (en and hi), checked at worker
  start; variables are typed, so nothing clinical can be sent, and the signed link is never stored.
  Phone numbers on messages are Fernet-encrypted. Only the console provider exists so far (refused
  in production). New: `v_message_health`, settings `MESSAGING_PHONE_KEYS` and
  `RX_LINK_SEND_WINDOW_HOURS`, error codes `MSG_OUTCOME_UNKNOWN`, `MSG_NO_CONSENT`,
  `MSG_NOT_APPLICABLE`, audit action `prescription.link_expired`; dependencies `cryptography`
  50.0.2 and `pyyaml` 6.0.3 (and `types-pyyaml` for mypy).
- M5-P1 (#40): the job queue and the background worker (NFR-13; spec reminders-and-messaging R9-R11,
  R9a-R9e, R11a; AC3, AC8-AC11; ADR-0005). A `jobs` table (migration `0014`) saved in the same
  transaction as the change that needs it. The worker, a new `worker` container on the API image
  (non-root, read-only root filesystem, no capabilities), claims due jobs with `SKIP LOCKED` in a
  short transaction that is committed, with the attempt counted, **before** the handler runs: no
  row lock is held across a handler, and a worker that dies mid-job still uses an attempt. Failed
  jobs retry after 1, 5, 15 and 60 minutes, then go `dead`; a reaper recovers jobs from dead
  workers (or kills them at `max_attempts`); a job whose clinic is suspended is `cancelled`. A
  repeated `dedupe_key` is ignored only while the first job is queued, running or done, so cancelled
  work never blocks it. Jobs with no clinic are limited by the database to system kinds. The first
  real job purges refresh tokens and patient links 30 days after they expired and finished jobs
  after 30 days (dead ones after 90), recording one `retention.purged` audit event. The worker's
  health check reads a heartbeat file in a tmpfs that it rewrites only after a poll that reached
  the database. New: `make worker`, `v_job_health`, settings `WORKER_POLL_SECONDS` and
  `WORKER_BATCH_SIZE`, error codes `JOB_HANDLER_ERROR`, `JOB_LOCK_EXPIRED`, `JOB_CLINIC_SUSPENDED`.
- M5 (#40) opened: the messaging and reminders spec is Approved. See docs/milestones/M5-messaging-and-reminders.md.
- M4 (#38) complete: visits and digital prescriptions, P1–P6 below, in PR #39.
- M4-P6 (#38): the consultation screen and the keyboard-first prescription builder (FR-VIS-02,
  03, 05; FR-RX-01..06, 09; spec §6, D2, D6; NFR-09; decisions 1A–6A). On the doctor's own queue
  row *Start* opens `/visits/{id}`: the patient's earlier visits (with *Repeat*), notes and
  vitals, and the builder. One entry row, then Tab and Enter, adds each medicine; frequency takes
  `101`, `1-0-1`, S, O or C; suggestions are the doctor's favourites and the clinic's own history
  (a favourite brings its whole line); *More* edits form, strength, quantity, preparation and
  storage phrases, warnings and notes. Everything autosaves with the revision guard, and a
  change from another tab stops saving and offers *Reload*. *Review and issue* previews the
  patient page in English or Hindi; afterwards *Print*, the QR code of the patient link with
  *Copy link*, and *Revise*. Front desk sees "Prescription issued" on the queue row and prints
  from it or from the patient profile, which also lists the visits for clinical roles. API:
  `GET /api/v1/prescriptions/{id}/preview` and two content-free queue fields (contract 0.18.0).
  New dependency `qrcode` 1.5.4 (the QR image, in the browser). Also fixed: the main navigation
  marked every item as the current page.
- M4-P5 (#38): patient prescription links and the patient page (FR-RX-07, 08; spec R9–R13, R19,
  R20, AC2, AC3; decisions 1A–6A). Issuing version 1 creates the chain's link; revisions reuse it
  and the page shows the latest version with "Updated by your doctor on …". `/p/{token}` asks for
  the last 4 digits of the patient's phone (five wrong answers lock the link until the clinic
  resets it), then shows one card per medicine in English or Hindi (a switch on the page), the
  doctor's text as written, at 360 px and about 147 KB on a first visit. Tokens are HMAC-SHA256
  with rotating keys (`PATIENT_LINK_SIGNING_KEYS`); staff with `RX_PRINT` get, reset and replace
  links. `scripts/inspect_link_token.py` reads a token offline. Also: each prescription records
  the printed layout it was issued with (`layout_version`), so a later layout change never
  alters it. Migration `0013`, contract 0.17.0.
- M4-P4 (#38): printable prescription PDFs, front desk printing included (FR-RX-04, 06; spec R8,
  R16, R18, R20, D6, AC8, AC10; decisions 1A-5A; ADR-0012). `GET /api/v1/prescriptions/{id}/pdf`
  renders a version on its first download, in-house with WeasyPrint and vendored Noto Sans and
  Noto Sans Devanagari fonts, stores it write-once in blob storage (local `blobs` volume; an
  S3-compatible adapter tested against an in-process fake, wired in M6) and serves the stored
  file afterwards, so concurrent first downloads cause one render. The PDF has the letterhead,
  the doctor's registration, the patient, every line with its instructions, advice, the follow-up
  and the footer, on A5 or A4 (new clinic setting `rx_paper_size`). Labels and dosage phrases come
  from an English and Hindi phrasebook (the Hindi to be reviewed by a clinician, L-07); the doctor's
  text prints as written. New permission `RX_PRINT` (every role): front desk prints the current
  version and finds it with `GET /api/v1/patients/{id}/prescriptions` (no content). New codes
  `RX_NOT_ISSUED`, `RX_PDF_BUSY`, `RX_PDF_FAILED`; audit `prescription.pdf_downloaded`. The API
  image gains Pango, HarfBuzz and fontconfig. Migration `0012`, contract 0.16.0.
- M4-P3 (#38): favourites, templates and medicine suggestions (FR-RX-05, FR-RX-10; spec R7, AC5;
  decisions 1A-5A). Each doctor keeps favourites (one line with its usual instructions) and
  templates (lines, advice, a follow-up interval), named uniquely and saved with a `revision`.
  `GET /api/v1/medicine-suggestions?q=` suggests the doctor's favourites, then medicine names this
  clinic has issued, ranked by distinct visits; nothing else is ever suggested. Draft lines carry the
  favourite and the draft the template they came from; issuing counts each use once. New codes
  `RX_NAME_TAKEN`, `RX_LIBRARY_FULL`. Migration `0011`, contract 0.15.0.
- M4-P2 (#38): prescriptions (FR-RX-01..03, 06, 09; spec R4-R6, R14, R17, R20; decisions 1A-6A).
  A visit has one prescription chain: the doctor creates a draft, saves it whole with its
  `revision` (medicines with dose, frequency and timing codes, preparation and storage phrases,
  advice, a follow-up date), and issues it. Issuing freezes it with the doctor and clinic as
  printed, the patient's language and a pending-delivery marker (`PENDING` or `NOT_CONSENTED`;
  nothing is sent until M5). An issued version never changes (`409 RX_NOT_DRAFT`, enforced by
  database triggers as well); revising makes version n+1 and issuing it supersedes the old one.
  The consultation view includes the visit's prescriptions and each history visit's medicines.
  Migration `0010`, contract 0.14.0.- M4-P1 (#38): visits (FR-VIS-01..03, 05; spec prescriptions R1-R3, R16, R17; decisions 1A-6A).
  The doctor starts the visit of an appointment in consultation (`POST /api/v1/visits`), records
  the chief complaint, findings, diagnosis, notes and vitals (`PATCH` with the `revision` seen,
  `409 VIS_STALE` otherwise) and completes it, which also completes the appointment. 24 hours
  after completion the visit is locked (`409 VIS_LOCKED`) and takes addenda only; addenda are
  append-only in the database. `GET /api/v1/visits/{id}` returns the consultation view (visit,
  addenda, patient, last 10 visits) and `GET /api/v1/patients/{id}/visits` the history in pages.
  Doctors and owners read, only the visit's doctor writes, front desk sees nothing. Each clinical
  read writes one audit row for the view; no clinical text reaches logs or audit metadata.
  Migration `0009`, contract 0.13.0.- M3 (#36) complete: appointments and the daily queue, P1-P5 below, merged in PR #37 (17 Oct 2026).
- M3-P5 (#36): the appointment and queue screens (FR-APT-01, 03, 05; FR-QUE-01, 03, 04; D27-D32).
  `/queue` is the live board: one doctor's day (a doctor sees their own), refreshed every 5 s,
  rows in token or slot order with the next step as one click (*Arrived*, *Start*, *Complete*)
  and *No-show*, *Cancel*, *Reschedule* in a menu. *Book* takes at most three interactions (AC6);
  *Add walk-in* one patient pick. Each action is reported with the patient and the time.
  `/settings/schedule` (owners) edits weekly hours, leave, extra sessions and the booking mode,
  and lists booked sessions a change kept. The patient profile lists their appointments. Two new
  Playwright journeys: AC6 and AC4.
- M3-P4 (#36): the live queue (FR-QUE-03; spec R12, D23-D26). `GET /api/v1/queue` sends a strong
  `ETag` (a hash of the body) and answers a matching `If-None-Match` with a bodiless `304`, through
  the web origin too. The web app gets `apiGetConditional`, a polling module (every 5 s, paused
  while the tab is hidden, 30 s after an error) and a `useQueue` hook for P5's queue board. The
  queue stays `no-store`. Contract 0.12.0; a Playwright check of the 304 through the web origin.
- M3-P3 (#36): the daily queue (FR-QUE-01, 02, 04; spec R9-R11, D17-D22).
  `POST /api/v1/appointments/{id}/transitions` takes `{from, to}`: `from` must be the current status,
  so a stale tab cannot move a patient who has already moved (`409 QUE_INVALID_TRANSITION`, AC3).
  Transitions happen on the session's day; a no-show once it has started (`409 QUE_WRONG_TIME`).
  `POST /api/v1/queue/walk-ins` adds a walk-in to the running or next session today, arrived at
  once (`409 QUE_NO_SESSION` when there is none). `GET /api/v1/queue` lists a day's sessions with
  their appointments, patients and waits. Audit action `appointment.status_changed`; contract 0.11.0.
- M3-P2 (#36): booking, cancel and reschedule (FR-APT-03..05, FR-APT-07; spec R3-R8, D10-D16).
  `POST /api/v1/appointments` books a patient into a session: the next token in token mode, a
  free slot in slot mode. A session row lock serialises bookings and partial unique indexes back
  them, so two parallel requests for the last place give one 201 and one 409. Tokens are never
  reused after a cancellation. `POST .../cancel` takes a reason; `POST .../reschedule` moves a
  booking to any open session in one transaction, linking the new appointment to the old.
  `GET /api/v1/appointments/{id}` returns the status history, and
  `GET /api/v1/patients/{id}/appointments` a patient's appointments. Sessions a leave or schedule
  change leaves with bookings are now `CLOSED` to new ones (or resized when only the capacity
  changed), and slots show `available`. New codes `APT_ALREADY_BOOKED`, and the existing `APT_*`
  codes are now raised. Migration `0008`, contract 0.10.0. No confirmation message until M5.
- M3-P1 (#36): doctor schedules and sessions (FR-APT-01, FR-APT-02; spec appointments R1-R4,
  R14-R20). The owner sets a doctor's weekly blocks with `PUT /api/v1/clinic/doctors/{id}/schedule`
  (ops during onboarding with `PUT /api/v1/ops/clinics/{id}/doctors/{id}/schedule`). Times are the
  clinic's wall clock. An end at or before the start is the next day, and a block lasts 15
  minutes to 12 hours, so 13:00-10:00 is `422 SCH_INVALID_BLOCK` while 23:00-01:00 is accepted.
  Overlap is checked across midnight and from Sunday into Monday (`409 SCH_OVERLAP`).
  Whole-day leave and extra sessions are added and removed under `.../schedule-exceptions`.
  `GET /api/v1/sessions?date=` generates a date's sessions the first time it is read. It is
  idempotent: concurrent reads create one set, and a session belongs to the date it starts on. It
  lists slots in slot mode and the next token in token mode.
  No change drops a booking: affected future sessions without bookings are removed, and booked ones
  come back as `kept_sessions`. Clinics have a `booking_mode` (`TOKENS` by default). Changing it is
  refused while a block lacks the new mode's value (`409 SCH_MODE_INCOMPATIBLE`).
  New permission `SCHEDULES_MANAGE` (owners), audit actions `schedule.changed`,
  `schedule.exception_added` and `schedule.exception_removed`, migration `0007`, contract 0.9.0.
  `make seed` gives every seeded doctor a Monday-Saturday 10:00-13:00 schedule.
- M2-P5 (#21): the patient screens (FR-PAT-01..06, FR-MSG-05). A header search (`/` focuses it)
  looks patients up by phone, code or name start, one request per pause in typing, with masked
  phones in the list; `/patients?q=` lists the matches. The Register patient drawer shows the
  guardian field, and calls the phone the guardian's, once the age is under 18 on the clinic's
  date; a phone the clinic already has lists the family on it, to use one of them or register a
  new family member (`confirm_new`). The profile `/patients/{id}` shows the code, the phone in full
  for dialling and an in-place edit that sends only what changed; another clinic's patient reads
  "Patient not found". The Messages panel tells "not asked", "declined" and "allowed" apart,
  records consent with a read-aloud script, confirms an opt-out and then offers only "Opt back
  in". The Create clinic wizard takes an optional patient code prefix. The web API client sends
  PUT and PATCH (with CSRF), query strings and cancellable requests. No API or contract change.
- M2-P5: the first Playwright journey (`apps/web/e2e/patients-duplicate-phone.spec.ts`,
  TESTING.md §3): `make e2e` runs it in the official Playwright image against the seeded stack, and
  the CI `smoke` job runs it on every PR. `@playwright/test` 1.64.1 (dev only). `make smoke` also
  checks that `/patients` and the patient API refuse visitors without a session.

- M2-P4 (#21): ops CSV patient import (FR-PAT-08, FR-OPS-02, spec R8).
  `POST /api/v1/ops/clinics/{id}/patient-imports` takes the raw file as `text/csv` (UTF-8, at most
  2 MB and 5,000 rows, columns `name, phone, sex, dob_or_age, guardian_name, language`). It is a dry
  run unless `?dry_run=false`. The report gives spreadsheet row numbers, counts, the column and a fixed
  reason for each invalid row, and possible duplicates, never a cell's value or an existing patient's
  identity. A commit re-checks everything under the clinic lock (as registration does), imports valid
  rows in file order with consecutive codes and consent "not asked", skips rows whose phone and name
  match an existing patient or an earlier row (so a re-run is harmless), imports and flags rows that
  only share a phone (families), writes one `patient.imported` audit row each and the checklist's
  `patients_imported_at`. Blank sex is `UNDISCLOSED`; dates are ISO or day-first. A file that cannot
  be read is `422 PAT_IMPORT_INVALID` with the problems; over 2 MB is `413`. 5,000 rows import in about
  2 s (batched inserts: `PatientRepository.add_many`, `AuditWriter.record_many`). Contract 0.8.0.
  Sample file: `scripts/fixtures/patients-import-sample.csv`.
- M2-P3 (#21): consent, opt-out and opt-in (FR-PAT-05, FR-PAT-06, FR-MSG-05). `PUT /api/v1/patients/{id}/consent`
  records whether the patient may be messaged on WhatsApp and SMS, with who and when (the guardian's
  answer for a minor); "asked and declined" is told apart from "never asked". `POST .../opt-out` stops all
  messages and is idempotent; `POST .../opt-in` is the explicit way back and takes the new consent, so
  re-submitting a form cannot undo an opt-out (AC5). Editing consent while opted out is `409 PAT_OPTED_OUT`.
  The patient body gains `whatsapp_allowed`, `sms_allowed`, `opted_out_at` and `consent_recorded_by`.
  Each change is an audit row (`patient.consent_changed`, `patient.opted_out`, `patient.opted_in`) with the
  flags and `given_by`, never a name. The patient row is read `FOR UPDATE` so an opt-out and a consent edit
  cannot interleave. Contract 0.7.0.
- Tests and CI can no longer hang: `pytest-timeout` (pinned, dev only) fails any API test that runs longer
  than 120 s with every thread's stack, and every CI job has a `timeout-minutes` limit. Added after a
  deadlocked test (a thread barrier whose second thread was never started) stalled a run for half an hour.

- M2-P2 (#21): patients over HTTP (FR-PAT-01..04). `POST /api/v1/patients` registers (phone normalised
  to E.164, the guardian rule for under-18s, a clinic code like `SC-0001`); `GET /api/v1/patients?q=`
  looks up by phone, code or name prefix (at most 20); `GET` and `PATCH /api/v1/patients/{id}` read and
  correct one. Registering a phone the clinic already has is `409 PAT_PHONE_EXISTS` with up to 10
  candidates, and `confirm_new` registers another person on it. Registration locks the clinic row
  first, so two simultaneous registrations of one new number have one winner and codes stay gap-free;
  a refusal takes no code. Contract 0.6.0.
- M2-P2: `patient.created` and `patient.updated` audit events (the code, or the changed field names;
  never a name or a phone number), the onboarding checklist's first-patient time, the clinic-local
  "today" for ages, and `patient_code_prefix` on clinic creation (ops may choose it; otherwise it is
  derived from the name) and in `Clinic` responses.
- M2-P2: `make seed` adds six synthetic patients to `sample-clinic` (a family sharing a phone, a child
  with a guardian, an adult known only by age, a Hindi-speaking patient), once.

- M2-P1 (#21): the patient model (FR-PAT-01, 03, 05, 06): `Patient` with the guardian rule for
  under-18s (the phone is the guardian's), `Age` computed from a date of birth or a recorded age,
  consent and opt-out state, clinic-scoped codes (`ME-0142`) allocated from a counter on the clinic
  that is locked while a number is taken, and the pure lookup classification (phone, code, name
  prefix). Migration `0006` adds the `patients` table with its lookup indexes and gives every
  existing clinic a code prefix derived from its name. `PAT_GUARDIAN_REQUIRED` is mapped to 422.
- M2-P1: a 10,000-patient lookup test (spec AC4) that times phone, code and name-prefix lookups
  through the repository and plans their SQL with sequential scans disabled, a 40-registration
  concurrency test for gap-free codes, and tenancy cases for patients in the permanent suite.
- Patients spec Approved (3 Oct 2026, decisions D1–D6): the minor's contact of record is the
  guardian's phone, registration is race-free by locking the clinic row, the age model, the code
  prefix rules and the lookup rules are specified.

- Planning pack: PRD, CLAUDE.md, AGENTS.md, TASKS.md, SPECS.md, architecture, data model, API
  design, debugging guide, error catalogue, runbook, security and compliance notes, ADR-0001 to
  ADR-0009, feature specs for M1–M5, and the repository skeleton.
- Local PostgreSQL service in `docker-compose.yml` and base `Makefile` targets (M0-P1).
- `NEXT_STEPS_PLAN.md`: approved M0 implementation plan with workflow prerequisites and progress log.
- ADR-0010: issue-driven workflow, one commit per logical change, rebase merges, CODEOWNERS approval.
- `.gitattributes`: LF line endings in the index and working tree on every platform (M0-P1).
- `docs/specs/identity-and-tenancy.md` Approved; M1 plan (`NEXT_STEPS_PLAN.md`) and design notes
  (`docs/milestones/M1-identity-tenancy-audit.md`); M1-P1 active (#19).
- M1-P1 (#19): domain model — `Clinic` (`ONBOARDING → ACTIVE ↔ SUSPENDED`, I1), `Doctor` (I3),
  `User`, `ClinicMembership` with roles and the last-owner rule (R9); `PhoneNumber` (E.164,
  masked) and `EmailAddress` value objects; domain codes `CLN_OWNER_REQUIRED`,
  `CLN_INVALID_TRANSITION`.
- M1-P1: `IdPort` with a UUIDv7 generator; repository and unit-of-work ports.
- M1-P1: migration `0002` (`clinics`, `users`, `clinic_memberships`, `doctors`); SQLAlchemy models,
  `TenantScopedRepository`, repositories and unit of work; permanent tenancy suite in
  `tests/tenancy/`; models-vs-migrations drift test.
- M1-P1: coverage gate ≥ 80% on `domain/` + `application/` in `make test-api` and CI (NFR-14).
- M1-P2 (#19): sign-in by email or phone (FR-AUTH-01) with Argon2id hashing (argon2-cffi 25.1.0),
  constant-time handling of unknown accounts, and lockout for 15 minutes after 5 consecutive
  failures (FR-AUTH-04, `AUTH_LOCKED` 423 with `Retry-After`).
- M1-P2: sessions (FR-AUTH-02): 15-minute HS256 access JWT (PyJWT 2.15.1) and 14-day rotating
  refresh token stored as SHA-256; replaying a rotated token revokes the whole family
  (`AUTH_REFRESH_REUSED`); sign-out revokes the family. `POST /api/v1/auth/sign-in`, `/refresh`,
  `/sign-out` in `contracts/openapi.yaml` 0.2.0.
- M1-P2: `HttpOnly` path-scoped cookies `me_access`, `me_refresh` and a `me_csrf` double-submit
  token checked on every unsafe `/api/*` request with session cookies (`AUTH_CSRF_INVALID`).
- M1-P2: migration `0003` (users credentials and lockout; `refresh_tokens`); clock port; request
  validation with `REQ_VALIDATION_FAILED` / `details.fields`; domain error → HTTP status mapping.
- M1-P2: settings `JWT_SIGNING_KEY` (≥ 32 characters, required), `ACCESS_TOKEN_TTL_SECONDS`,
  `REFRESH_TOKEN_TTL_SECONDS`; `make seed` with synthetic local demo users; RUNBOOK §17
  (locked-out account).
- M1-P3 (#19): authorisation on every route (FR-AUTH-03). Each route declares an access policy
  (`@public`, `@authenticated`, `@clinic(Permission.X)`, `@ops`) and one `before_request` hook
  enforces it; `create_app` refuses to start if any route has none, and an undeclared route is
  refused rather than served (default deny).
- M1-P3: the PRD §8.1 permission matrix as domain data (`Permission`, `ROLE_PERMISSIONS`,
  `permissions_for`); an owner with a linked doctor profile also gets `CLINICAL_WRITE`.
- M1-P3: every request re-reads the session, the user and the membership (R7), so sign-out ends
  access at once (`AUTH_SESSION_EXPIRED`) and a deactivated member or disabled user is refused on
  their next request (`AUTH_ACCOUNT_DISABLED`, AC4). New reads
  `RefreshTokenRepository.is_family_live` and `MembershipRepository.list_staff`.
- M1-P3: clinic resolution (R6) from the single membership or `X-Clinic-ID`; ambiguous, malformed
  and foreign values all answer `PERM_CLINIC_REQUIRED` (400). New codes `PERM_DENIED` (403),
  `PERM_CLINIC_REQUIRED` (400) and `CLN_SUSPENDED` (403); ops users are refused on clinic routes
  and clinic staff on ops routes (R10).
- M1-P3: `GET /api/v1/me` (user, memberships with clinic status, role and permissions) and
  read-only `GET /api/v1/clinic`, `/clinic/doctors`, `/clinic/doctors/{doctor_id}`,
  `/clinic/staff` in `contracts/openapi.yaml` 0.3.0 with the `X-Clinic-ID` parameter and a
  `me_access` cookie security scheme; sign-in and refresh bodies now carry the same membership
  shape. Lists return `{"items": [...]}` and are unpaginated by design at this size.
- M1-P3: HTTP tenancy suite (`tests/tenancy/test_http_isolation.py`) proving AC3 end to end, with
  a guard that fails when a new clinic route taking a resource ID has no cross-clinic case.
- M1-P4 (#19): append-only audit log (FR-AUD-01, FR-AUD-02). `audit_events` (migration `0004`)
  records who did what, to which record, when, with the `request_id` and a salted HMAC of the
  caller's IP; `metadata` holds IDs and enums only. Rows are written through the same unit of
  work as the change, so a failed audit insert fails the change (spec R11).
- M1-P4: the database refuses to rewrite history — two triggers reject `UPDATE`, `DELETE` and
  `TRUNCATE` with `AUD_APPEND_ONLY` for every non-superuser role (AC6); lifting the guard is an
  approved, recorded procedure (RUNBOOK §18). A dedicated least-privilege database role remains
  on the M6-P1 list as defence in depth.
- M1-P4: recorded actions — `auth.signed_in`, `auth.sign_in_failed` (known accounts only),
  `auth.signed_out`, `auth.refresh_reused` and `staff.role_changed`.
- M1-P4: `PATCH /api/v1/clinic/staff/{membership_id}` (owners, `STAFF_MANAGE`) changes a member's
  role (FR-ORG-04, AC5); the last active owner cannot be demoted (`409 CLN_LAST_OWNER`), a no-op
  change records nothing, and the new role applies to the member's next request. Contract 0.4.0.
- M1-P4: `v_clinic_activity` support view (FR-OPS-04): per-clinic staff counts, last sign-in and
  7/30-day event counts, with no clinical column.
- M1-P4: setting `AUDIT_IP_SALT` (≥ 32 characters, required) and `IpHasher`; RUNBOOK §18
  (reading the audit log), DEBUGGING §5.3b ("who changed this?").
- M1-P5 (#19): ops onboarding (FR-OPS-01): `POST/GET /api/v1/ops/clinics`,
  `GET /api/v1/ops/clinics/{id}`, `POST /ops/clinics/{id}/doctors` and
  `POST /ops/clinics/{id}/staff-invites`. Ops only (R10); the clinic is named in the path.
- M1-P5: single-use staff invitations (FR-ORG-04). An `INVITED` membership carries the digest of
  a 32-byte secret with a 7-day expiry; the acceptance URL is returned once.
  Public `GET /api/v1/auth/invites/{token}` and `POST .../accept` let the invitee set a password
  (≥ 12 characters, a domain rule) and are signed in; accepting an owner's invitation activates
  an `ONBOARDING` clinic (I1). New codes `CLN_MEMBER_EXISTS` (409), `CLN_SLUG_TAKEN` (409),
  `CLN_INVITE_INVALID` (404), `CLN_INVITE_EXPIRED` and `CLN_INVITE_USED` (410).
- M1-P5: owner management (FR-ORG-01/02/04): `PATCH /api/v1/clinic`, `POST /clinic/doctors`,
  `PATCH /clinic/doctors/{id}`, `POST /clinic/staff`, and `PATCH /clinic/staff/{id}` now takes a
  role, a status (`DEACTIVATED` only), or both. A doctor profile links only to an active member
  without one already.
- M1-P5: `onboarding_checklists` (migration `0005`) records the first time each step happens and
  never overwrites it (FR-OPS-04, spec R12), which is the G4 measurement; new audit actions
  `clinic.created`, `clinic.activated`, `clinic.updated`, `doctor.added`, `doctor.updated`,
  `staff.invited`, `staff.accepted`, `staff.deactivated`. Contract 0.5.0 (17 paths);
  setting `PUBLIC_BASE_URL` is now validated (absolute, https when deployed) and RUNBOOK §10
  carries the real onboarding commands.
- M1-P6 (#19): web sign-in (FR-AUTH-01, FR-AUTH-04): `/sign-in` with one identifier field and a
  password, the API's own message with its Ref, a lock that says how long to wait and disables the
  button, and an allow-listed `?reason=` (session ended, ended for safety, account deactivated).
  `/invite/[token]` accepts a staff invitation and signs the invitee in; for an invitation to an
  existing account it asks for that account's current password (see Fixed).
- M1-P6: clinic choice and the dashboard shell (FR-AUTH-03, spec R6, R10). `/select-clinic` for
  people in several clinics, a header switcher shown only to them (`X-Clinic-ID`, per tab, last
  choice remembered as `mediease.clinic_id`), navigation filtered by permission, sign-out, a
  no-access state, a suspended-clinic screen, and an empty `/queue`. `/ops` is a placeholder for
  platform staff; the Create clinic wizard is planned separately. `/` now redirects to `/queue`.
- M1-P6: the API client sends POST with `X-CSRF-Token` (from `me_csrf`), `X-Clinic-ID`, path
  parameters, 204 responses and `Retry-After`; an expired access token is refreshed once, with the
  refresh shared per tab and serialised across tabs by a Web Lock (refresh tokens are single use).
- M1-P6: the proxy sends a visitor with no `me_csrf` cookie to `/sign-in?next=…` (a hint, not a
  security check); `make smoke` checks the sign-in page and that redirect.
- M1-P6: `make seed` adds a second synthetic clinic, `sample-clinic-two`, with the demo doctor as a
  member of both, and is now idempotent per clinic (an already-seeded database gains only the new
  clinic).
- CI (#19): the web `npm audit` gate blocks on production dependencies (`--omit=dev`); the
  full-tree audit is non-blocking (see Changed).

- M1-P7 (#19): the ops console (FR-OPS-01, FR-OPS-04, spec §6). `/ops` lists every clinic with its
  status, start time in the clinic's own zone, which onboarding steps happened and the time from
  start to first invitation; `/ops/clinics/new` is the Create clinic wizard (clinic → doctors →
  owner invitation) with the elapsed onboarding time from the checklist, field errors beside their
  fields, and the acceptance link shown once with a Copy button. `?clinic=<id>` continues a clinic
  that is still being set up. Web only; the API is unchanged.

### Fixed
- Web tests (#38): the patient search's "/" shortcut test pressed once before its listener was
  attached under a loaded run; it now presses until the search has the focus.
- Web (#38): the booking drawer's patient search lost the focus after the jsdom 30.1.2 bump, failing
  CI's web job on `main` and the M4 PR. `Drawer` and `Dialog` now focus a field marked
  `data-autofocus` once the dialog is open (DEBUG_JOURNAL 2026-10-18).
- Web tests that checked where focus moved before the effect that moves it had run, which failed
  about one run in four under load (SignInForm, AcceptInviteForm, the Create clinic wizard).
- CI (#21): the secrets scan failed on `main` after the M1 merge and on PR #22. The reviewed
  gitleaks false positive (the synthetic test password) was fingerprinted by its M1-branch commit,
  and rebase-merging gave that commit a new SHA on `main`. `.gitleaksignore` now names the commit`s
  SHA on `main` (and keeps the old one for clones that still have the branch), with a note on why
  fingerprints must be re-pointed after a rebase merge.
- Security (spec R13, contract 0.5.1): accepting a staff invitation for an account that already has a
  password used to overwrite that password and sign the caller in, so an owner who invited another
  clinic's user could take over the account. It now requires the account's current password,
  never changes it, shares the sign-in lockout (`401 AUTH_INVALID_CREDENTIALS`, `423 AUTH_LOCKED`)
  and records `account: new | existing` on `staff.accepted`. The web invitation page asks for the
  current password accordingly.

### Upgrade notes
- M1-P2: existing local `.env` files need `JWT_SIGNING_KEY` of at least 32 characters (copy the
  line from `.env.example`); otherwise `make up` stops with `CFG_INVALID`.
- M1-P4: existing local `.env` files need `AUDIT_IP_SALT` of at least 32 characters (copy the
  line from `.env.example`); otherwise `make up` stops before starting a container, because
  compose requires the variable.
- `.github/CODEOWNERS`: default owners for every path (M0-P1, W-6).
- API package `mediease_api` (M0-P2): `pyproject.toml` with pinned runtime and dev dependencies;
  typed `AppSettings` + `load_settings()` that fail fast on invalid config (`CFG_INVALID`, naming
  each rejected field); structlog JSON logging for app and framework records with `request_id`
  in contextvars; `X-Request-ID` middleware (safe inbound IDs echoed, otherwise a ULID; access log
  with route template and `duration_ms`); error envelope with `REQ_NOT_FOUND`,
  `REQ_METHOD_NOT_ALLOWED` and `SYS_UNEXPECTED`; `GET /health`; Flask app factory (`create_app`)
  and gunicorn `wsgi` entrypoint; 31 unit and integration tests.
- `Makefile` targets `install-api`, `test`, `test-api`, `lint`, `typecheck` (M0-P2).
- Database readiness (M0-P3): SQLAlchemy 2 engine (psycopg 3) behind a `DatabaseCheck` port;
  `GET /ready` runs `SELECT 1` within a 2-second budget and returns 200 or 503
  `READY_DB_UNAVAILABLE` / `READY_DB_TIMEOUT`; `ready.check_failed` warning log.
- Alembic with an empty baseline revision `0001`; `migrations/env.py` reads the settings (M0-P3).
- Minimal non-root API `Dockerfile` (`python:3.12.15-slim-trixie`, gunicorn `--preload`) (M0-P3).
- Compose `migrate` (one-off `alembic upgrade head`) and `api` (healthcheck `/ready`) services;
  `make up` builds and starts db → migrate → api; `make migrate` (M0-P3).
- Contract tests validating `/health` and `/ready` against `contracts/openapi.yaml`; real-PostgreSQL
  integration tests for readiness and migrations; 55 tests in total (M0-P3).
- Web app (M0-P4): Next.js 16 App Router project in `apps/web` (TypeScript strict, ESLint, Tailwind 4),
  exact versions in `package-lock.json`, Node 24.21.0 in `.nvmrc`.
- API types generated from `contracts/openapi.yaml` (`npm run gen:api`, `make contract`) with a
  drift gate (`make contract-check`, CI) (M0-P4).
- Web API client `src/lib/api/client.ts`: `X-Request-ID` on every call, 5 s timeout, typed
  `ApiError`; web-side codes `WEB_API_UNREACHABLE` and `WEB_API_BAD_RESPONSE` (M0-P4).
- Same-origin proxy: `/api/*`, `/health`, `/ready` rewritten to `API_INTERNAL_URL` (ADR-0006);
  security headers with a per-request nonce CSP (M0-P4).
- `/status` page: healthy, degraded and API-down states, each with "Ref: <request_id>" (M0-P4).
- `make install-web`, `test-web`, `dev-web`; `make lint typecheck test` cover API and web; CI web
  job enabled with Node from `.nvmrc` (M0-P4).
- Container images (M0-P5): multi-stage, non-root API and web images with digest-pinned bases,
  Debian security updates applied and package managers removed from the runtime stage; web
  liveness route `/livez`.
- Full compose stack (M0-P5): `web` service after `api` is healthy; `migrate`, `api` and `web` run
  with a read-only root filesystem, no capabilities and `no-new-privileges`. `make smoke`
  (`scripts/smoke.sh`) checks the running stack, including those properties.
- CI gates (M0-P5): image build + Trivy scan, fresh-clone smoke test, gitleaks secrets scan,
  `pip-audit`, `npm audit`, import-linter layer contracts, API coverage gate ≥ 90%; `make audit`.
- Dependabot for pip (`apps/api`), npm (`apps/web`) and Docker base images (M0-P5).

### Verified
- M0-P1 closed: `db` starts healthy, `select 1` returns 1 in UTC, `down` keeps `pgdata`, and an
  empty `POSTGRES_PASSWORD` is refused before any container starts (#6).
- **M0 — Foundation closed** (#14): a fresh clone with an empty volume runs
  `cp .env.example .env && make up` to `db`, `api`, `web` healthy and `migrate` exited 0 in 77 s;
  `make smoke` passes; CI is green on the PR.

### Changed
- Workflow (ADR-0011): one issue, one branch (`m<milestone>/<issue#>-<slug>`) and one PR per
  milestone; every phase is committed to the milestone branch and the PR stays a draft until the
  milestone is done. Supersedes ADR-0010's per-phase issue, branch and PR. `CLAUDE.md`,
  `AGENTS.md`, `CONTRIBUTING.md`, the PR template and `/close-phase` updated.
- `DATABASE_URL` must use the `postgresql+psycopg://` scheme; anything else fails start-up with
  `CFG_INVALID` (M0-P3).
- `CLAUDE.md`: new "Commit Standards"; "Git Workflow" now issue → branch → PR with no direct pushes
  to `main`, pushes only with permission and merges only by authorised maintainers; Docker start-up
  order declared with `depends_on` (`api` waits for `migrate`).
- `AGENTS.md`, `CONTRIBUTING.md`, PR template, `TASKS.md`, M0 design notes updated to match.
- M0-P3 now includes a minimal API `Dockerfile` so the `migrate` service can run before P5.
