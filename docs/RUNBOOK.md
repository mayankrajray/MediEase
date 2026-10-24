# MediEase — Operations Runbook

Step-by-step procedures for operating MediEase. Each procedure states **when to use it**, the
**steps**, and **how to confirm** it worked. Production procedures become live in M6; local ones
work from M0.

Severity levels: **SEV1** patient data at risk or clinics cannot work · **SEV2** a core feature
(booking, Rx, reminders) degraded · **SEV3** minor or single-clinic issue.

---

## Contents

1. Local environment reset
2. Deploy a release
3. Roll back a release
4. Migration failed
5. Restore the database
6. Dead or stuck jobs
7. Messaging provider outage
8. WhatsApp template rejected or quality rating dropped
9. Webhooks failing
10. Onboard a clinic (pilot)
11. Offboard a clinic / export data
12. Patient data request (access, correction, erasure)
13. Secret exposure
14. Key rotation (patient-link signing key)
15. Suspected data breach
16. Break-glass production database access
17. Locked-out staff account
18. Read the audit log
19. Google sign-in and patient accounts (M6a-P3)
20. Account emails: Mailpit locally, the SMTP provider in production (M6a-P4)
21. Notifications in the app (M6a-P7)
22. Appointment reminders and bookings to move (M6a-P8)

---

### 1. Local environment reset
**When:** local database is in a bad state.
```bash
make down
docker volume rm mediease_pgdata   # destroys LOCAL data only
make up && make seed
```
**Confirm:** `/ready` returns 200; a seeded user can sign in:
```bash
curl -si -H 'Content-Type: application/json' \
  -d '{"identifier":"owner@sample-clinic.example","password":"MediEase-demo-2026"}' \
  localhost:8000/api/v1/auth/sign-in        # 200 + Set-Cookie me_access, me_refresh, me_csrf
```
`make seed` (M1-P2, extended in M1-P6) creates two synthetic clinics and the ops user, all with the
demo password above (local only; `--password` overrides it):

| Clinic | People |
|---|---|
| `sample-clinic` | `owner@`, `doctor@`, `desk@sample-clinic.example` |
| `sample-clinic-two` | `owner@sample-clinic-two.example`, and `doctor@sample-clinic.example` again as a second membership |
| `sample-family-clinic` (M6a-P6) | `owner@sample-family-clinic.example` (a practising owner: Owner with a linked doctor profile, so the Owner / Doctor switch shows), `doctor@` and `desk@sample-family-clinic.example` |
| (no clinic) | `ops@mediease.example` |

Every seeded doctor gets a Monday–Saturday 10:00–13:00 schedule (15-minute slots, 12 tokens), once,
so `GET /api/v1/sessions?date=<a weekday>` has sessions to show. On `/queue` (M3-P5) the front desk books with *Book*,
adds walk-ins and moves patients through the day; the owner edits hours, leave and extra sessions
on `/settings/schedule`. Outside 10:00–13:00 add an extra session there to have a session running now. `sample-clinic` also gets six synthetic patients, once (while it has none): Asha, Arun and Meera Rao
share the phone `+919000000101` (Meera is 6 and registered with Asha as guardian), Bina Shah is
known only by age, Chetan Verma prefers Hindi, and Deepa Nair is an adult on her own number. Try
`GET /api/v1/patients?q=9000000101` or register a new person on that number to see the duplicate
flow.

M5-P6: Deepa Nair also gets one overdue follow-up, once (while no follow-up is pending): a visit
10 days ago, completed, whose prescription's follow-up date was 3 days ago, so `/follow-ups` has a
row to try *Book follow-up* on. Ops see the month's messaging costs at `/ops/messaging-costs`.

`doctor@sample-clinic.example` therefore belongs to two clinics: signing in as them shows the clinic
chooser and switcher in the web app. The seed refuses to run unless `APP_ENV=local` and is
idempotent **per clinic**: a clinic that exists is left alone, so a database seeded before
`sample-clinic-two` existed only gains the new clinic (`make seed` again adds
`sample-family-clinic` to an older database).

**`make up` fails with `CFG_INVALID ... JWT_SIGNING_KEY`** (or Compose says
`set JWT_SIGNING_KEY in .env`): `.env` was created before M1-P2. Set `JWT_SIGNING_KEY` in `.env`
to at least 32 characters, e.g. the value from `.env.example` or
`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.

### 2. Deploy a release (M6)
1. Confirm CI is green on the commit and `CHANGELOG.md` is updated.
2. Take an on-demand database snapshot.
3. Run the `migrate` job with the new image tag; wait for exit code 0.
4. Roll `api`, then `worker`, then `web`.
5. Watch: 5xx rate, `/ready`, job queue age for 15 minutes.
**Confirm:** smoke test — sign in, open today's queue, open a test patient link on staging data.

### 3. Roll back a release
1. If the release included a migration, check whether it is backward compatible (the PR must say).
2. Compatible → redeploy the previous image tag for `api`, `worker`, `web`.
3. Not compatible → stop, declare SEV2, restore from the pre-deploy snapshot only with the
   founder's approval (data written since the snapshot will be lost).
**Confirm:** error rate back to baseline.

### 4. Migration failed
1. `docker compose logs migrate` (or the job logs in production). Do **not** start the new app.
2. Alembic migrations run in a transaction; a failed one leaves the schema unchanged. Verify with
   `alembic current`.
3. Fix the migration in a new commit; never edit a migration that has run in production.
**Confirm:** `alembic current` equals `alembic heads`.

### 5. Restore the database (M6)
1. Declare SEV1/SEV2 as appropriate; pause `worker` to stop sends.
2. Restore to a **new** instance from the chosen point in time.
3. Verify row counts and the latest audit events on the new instance.
4. Point `DATABASE_URL` to it; restart `api`, `web`, then `worker`.
5. Check for jobs whose `run_at` passed during the outage — they will send on resume; decide with
   the clinic whether stale reminders should be cancelled.
**Monthly drill:** restore the latest backup to a scratch instance and record the time taken.

**Prescription PDFs (M4-P4).** They are not in the database but in the blob store (local: the
compose volume `blobs`; production from M6: the S3-compatible bucket). Back it up with the
database. A restored database pointing at a file that is missing is not fatal: the next download
renders that version again from its frozen row under the same key (`rx.pdf_missing` in the logs),
so a lost store costs re-renders, never content. Never delete or overwrite an object by hand; the
store is write-once by design.

### 6. Dead or stuck jobs (M5)
1. Is the worker up? `docker compose ps worker` (healthy), `docker compose logs --tail 50 worker`.
   `select * from v_job_health;` shows due, running, stale and dead jobs by kind (DEBUGGING §5.6).
2. Read `last_error_code` in ERRORS.md and fix the cause first.
3. Requeue a dead job once the cause is fixed (the ops console version is M6):
   `update jobs set state='queued', attempts=0, run_at=now(), finished_at=null where id='<id>' and state='dead';`
   It keeps its `dedupe_key`; if a newer live job already holds that key, the update fails on
   `uq_jobs_dedupe_key` and the newer job is the one that will run.
4. `running` jobs with a lock older than 5 minutes belong to a dead worker: the reaper (once a
   minute) requeues them with the attempt counted, or marks them `dead` at `max_attempts`.
5. To pause all work: `docker compose stop worker` (the job in hand finishes, the rest are handed
   back). Start it again to resume; nothing is lost and nothing runs twice.
6. Messages (M5-P2): `select * from v_message_health;`. A `send_*` job that is `dead` with
   `MSG_OUTCOME_UNKNOWN` must **not** be requeued: the provider may already have delivered it, and
   the message row's unique key would refuse a second row anyway. Tell the clinic to call the
   patient if the message mattered. Locally, the console provider writes
   `messaging.console_accepted` to `docker compose logs worker` (variable names only).
7. A `send_rx_link` job that finds a prescription issued more than `RX_LINK_SEND_WINDOW_HOURS` ago
   (24 at most) marks it `EXPIRED` and sends nothing: expected after an outage longer than that.
8. Opt-outs by reply (M5-P5): a STOP (STOP, UNSUBSCRIBE, रोकें, बंद) is applied by the
   `process_webhook_event` job; each opt-out is a SYSTEM `patient.opted_out` audit event with
   source `inbound_message`, and the clinic's `send_opt_out_confirmation` job replies. A
   `webhook_events` row with `WH_STOP_UNMATCHED` opted nobody out (no clinic had messaged that
   number); if the patient asks the clinic, staff opt them out on the patient page. Opting back in
   is always a staff action with fresh consent.
9. Message costs (M5-P5): `GET /api/v1/ops/messaging-costs?month=YYYY-MM` (ops). Prices are
   `apps/api/src/mediease_api/adapters/messaging/prices.yaml`, excluding GST; when Meta changes a
   rate, add an entry with its `effective_from` date (never edit an old one) and deploy. Many
   `unpriced` messages mean an unknown pricing category (`message.unpriced` in the worker log).
**Confirm:** `v_job_health.due` and `stale` fall to 0; message statuses progress.

### 7. Messaging provider outage (M5)
1. Confirm on the provider status page; our logs show `MSG_PROVIDER_UNAVAILABLE`.
2. Jobs retry with backoff automatically — do not requeue manually during the outage.
3. The SMS fallback (`MESSAGING_SMS_FALLBACK_ENABLED=true`, M5-P5) sends one SMS for a follow-up
   reminder whose WhatsApp message ended `FAILED` with a definite non-delivery (an outage counts
   only after the job's last attempt), to patients who consented to SMS. It needs a real SMS
   provider (L-03): with the console provider the worker refuses to start in production. Turning
   it on and off is a worker restart; a fallback job left over after turning it off does nothing.
   Inform pilot clinics if it is used.
**Confirm:** after recovery, `messages` in `QUEUED` drain; failure rate < 5%.

### 8. WhatsApp template rejected or quality rating dropped
1. Rejected: read the rejection reason, adjust wording (utility, no promotional language), resubmit,
   bump `template_version` in `templates.yaml`.
2. Quality dropped: pause broadcasts (P1 feature), review opt-out rates per clinic, reduce
   non-essential sends, and check for duplicate sends in `messages`.
**Confirm:** template status approved / quality rating recovered in Meta Business Manager.

### 9. Webhooks failing
1. Look for `webhook.signature_invalid`, `webhook.verify_failed` or 5xx on `/webhooks/*`.
2. Verify the app secret in the secret store matches Meta's app settings (`WHATSAPP_APP_SECRET`),
   and the verify token matches the one entered in Meta's webhook settings
   (`WHATSAPP_VERIFY_TOKEN`). With either empty the webhook refuses everything.
3. Verify the reverse proxy passes the raw body unchanged and routes `/webhooks/*` to the API.
4. Missed events: Meta retries for a while; stored events that never processed are re-enqueued by
   the hourly `reconcile_messages` job. `select count(*) from webhook_events where processed_at
   is null;` should be near 0. There is no way to ask Meta for a past status (spec R15).
5. Local testing with Meta (M5-P3): run a tunnel to the API, e.g.
   `cloudflared tunnel --url http://localhost:8000` (or ngrok), enter
   `<tunnel>/webhooks/whatsapp` and the verify token in the App Dashboard (WhatsApp >
   Configuration), subscribe to the `messages` field, and set `MESSAGING_PROVIDER=whatsapp_cloud`
   with the five `WHATSAPP_*` values in `.env`. Without Meta, `WHATSAPP_GRAPH_URL` can point the
   adapter at a local fake.

### 10. Onboard a clinic (pilot) — target < 60 minutes
1. Before the visit: collect clinic details, doctor registration numbers, schedules, patient list
   (L-07). Validate the CSV with the import dry run.
2. Create the clinic, its doctors and the owner's invitation. In the browser: sign in as the ops
   user, open **Clinics → Create clinic** and follow the three steps (M1-P7); the page shows the
   elapsed time and the invitation link once. A half-finished clinic is continued from the list
   (**Continue setup**). The same steps as API calls, for scripts and as the fallback (M1-P5):

```bash
# Sign in as the ops account first (RUNBOOK §1 for the local demo users).
curl -s -b jar -X POST -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"name":"Aarogya Clinic","slug":"aarogya-clinic","city":"Jaipur","pincode":"302001"}' \
  "$API/api/v1/ops/clinics"                       # 201, status ONBOARDING

curl -s -b jar -X POST -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"display_name":"Dr. A. Sharma","qualification":"MBBS","registration_number":"RJ-12345",
       "registration_council":"Rajasthan Medical Council"}' \
  "$API/api/v1/ops/clinics/$CLINIC/doctors"       # 201

curl -s -b jar -X POST -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"full_name":"A. Sharma","role":"OWNER","phone":"9000000001"}' \
  "$API/api/v1/ops/clinics/$CLINIC/staff-invites" # 201 with accept_url
```

3. Hand the `accept_url` to the owner **in person or by phone** — it contains a single-use secret,
   is valid for 7 days, and is shown only in that response. A new person sets a password (12 characters
   minimum); a person who already has a MediEase account (invited by a second clinic) enters their
   **current** password instead, which is never changed (spec R13). The clinic becomes `ACTIVE` as
   soon as an owner accepts. If the link is lost or expires,
   invite them again: the new link retires the old one.
4. The owner invites the doctor and front desk themselves from **Team** (`/team`, M6a-P5): an
   invitation to an email address is emailed by the worker (the owner never sees the link), and a
   phone-only one shows its link once to share. **Resend** retires the previous link; a
   deactivated member can be **invited back**. The API is `POST /api/v1/clinic/staff`; ops can
   still invite with the body above and always get the link.
5. Agree the booking mode (slots or tokens, `booking_mode` on `POST /ops/clinics`; `TOKENS` by default)
   and each doctor's weekly hours, then set them (M3-P1). Times are the clinic's wall clock; an end
   before the start is the next day, up to 12 hours a block. Give each block both `slot_minutes` and
   `capacity` if the clinic may switch modes later:

```bash
curl -s -b jar -X PUT -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d '{"blocks":[{"weekday":0,"start_time":"10:00","end_time":"13:00","slot_minutes":15,"capacity":12}]}' \
  "$API/api/v1/ops/clinics/$CLINIC/doctors/$DOCTOR/schedule"   # 200; weekday 0 = Monday
```

   `422 SCH_INVALID_BLOCK` names the block (`details.index`) and the reason; `409 SCH_OVERLAP` names the
   pair. Leave and extra sessions are the owner's (`/api/v1/clinic/doctors/{id}/schedule-exceptions`).
6. Import patients (M2-P4). Ask the clinic to save their list as **CSV UTF-8** with exactly these
   columns (any order): `name, phone, sex, dob_or_age, guardian_name, language`; a template with
   synthetic rows is `scripts/fixtures/patients-import-sample.csv`. Dry-run first (the default),
   fix the rows it reports in the spreadsheet (row numbers match it), dry-run again, then commit:

```bash
curl -s -b jar -X POST -H "X-CSRF-Token: $CSRF" -H 'Content-Type: text/csv' \
  --data-binary @patients.csv \
  "$API/api/v1/ops/clinics/$CLINIC/patient-imports"               # 200, report, nothing written

curl -s -b jar -X POST -H "X-CSRF-Token: $CSRF" -H 'Content-Type: text/csv' \
  --data-binary @patients.csv \
  "$API/api/v1/ops/clinics/$CLINIC/patient-imports?dry_run=false" # 200, imported + codes
```

   Use `--data-binary`, not `-d` (which strips the line breaks). Invalid rows are never imported;
   rows matching an existing patient by phone and name are skipped, so running the same file again
   is harmless; rows that only share a phone (families) are imported and listed under `duplicates`
   for the front desk to review. Over 2 MB or 5,000 rows: split the file. Send imports to the API
   origin (`:8000` locally): over 2 MB it always answers `413 REQ_REQUEST_ENTITY_TOO_LARGE`,
   while through the web origin (`:3000`) an oversized file can occasionally surface as a 500 from
   the proxy (issue #30). Consent is "not asked" for every imported patient: the front desk
   records it at the next visit.
7. Book one real appointment; issue one real prescription; confirm the patient link opens.
8. Record consent practice: the clinic's own patient notice is displayed at the front desk.
**Confirm:** `GET /api/v1/ops/clinics/$CLINIC` shows the checklist with `clinic_created_at`,
`doctors_added_at` and `staff_invited_at` set (and `patients_imported_at` after step 6); the elapsed time between the first and last
timestamp is the G4 measurement. Each step is also in `audit_events` (§18).

### 11. Offboard a clinic / export data
1. Written request from the clinic owner.
2. Generate the export (patients, visits, prescriptions as JSON + PDFs) to an encrypted archive;
   share through an expiring link.
3. After the agreed period, delete clinic data using the reviewed procedure; keep audit events per
   retention policy. Record completion in the audit log.

### 12. Patient data request (access, correction, erasure)
The **clinic** is the Data Fiduciary and responds to the patient; MediEase assists.
1. Receive the request via the clinic owner.
2. Access → export that patient's record. Correction → clinic staff edit demographics; clinical
   corrections are addenda. Erasure → run the erasure procedure, which respects clinical record
   retention obligations (confirm with counsel, L-04).
3. Log the request and completion date; the statutory response window applies.

### 13. Secret exposure
1. Rotate the secret immediately (database password, JWT signing key, provider tokens, webhook
   secret).
2. Redeploy with the new secret. For JWT key rotation, all sessions end — inform clinics.
3. Search logs/history for use of the old secret; if misuse is possible, go to procedure 15.
4. Remove the secret from Git history only with the developer's approval; rotation is what
   actually protects us.

### 14. Key rotation (patient-link signing key)
Keys are versioned (`kid`) in `PATIENT_LINK_SIGNING_KEYS` (`kid:secret,…`, M4-P5). Put the new
key **first** (it signs new links) and keep the old one after it (it still verifies) for 90 days,
then remove it. Emergency rotation (compromise) removes the old key immediately: every existing
link answers `LINK_INVALID`, and staff use *Replace link*
(`POST /api/v1/prescriptions/{id}/link/replace`), which makes a new link under the new key.
`scripts/inspect_link_token.py <token>` shows which `kid` a token uses, offline.

### 15. Suspected data breach — SEV1
1. Contain: revoke access, rotate secrets, block the vector.
2. Preserve evidence: logs, audit events, snapshots. Do not delete anything.
3. Inform the founder immediately and each affected clinic without delay, with what is known.
4. Support clinics in meeting their notification obligations under the DPDP framework (to the
   Board and affected individuals) — counsel involved from the start.
5. Post-incident review within 5 working days; journal entry and control improvements.

### 16. Break-glass production database access
Only for SEV1/SEV2 when no application path exists. Requires the founder's approval, a named
engineer, a time limit, read-only credentials unless a write is essential, and a written record of
every query run. Never export clinical data to a laptop.

### 17. Locked-out staff account (M1-P2)
**When:** a staff member reports "Too many attempts" (`AUTH_LOCKED`).
1. The lock ends by itself 15 minutes after the fifth wrong password (`Retry-After` says how
   long). Advise waiting first.
2. If the user is sure nobody else was guessing, and cannot wait, ops clears the lock (audited
   once M1-P4 lands):
   `UPDATE users SET locked_until = NULL, failed_login_count = 0, updated_at = now() WHERE id = '<user id>';`
3. Repeated lockouts across several accounts in a short time are an attack signal: check
   `auth.sign_in_failed` / `auth.locked` rates and go to procedure 15 if warranted.
4. A sudden `auth.refresh_reused` warning for one user means a refresh token was replayed: the
   session has already been ended; ask the user to sign in again and check the device.
**Confirm:** the user signs in; `users.failed_login_count` is 0.

### 18. Read the audit log (M1-P4)
**When:** a clinic asks "who changed this?", or an incident needs a timeline.

**Owners read it in the app (M6a-P8, FR-AUD-03).** *Audit log* in the owner's menu
(`/settings/audit`) lists the clinic's events newest first, 50 at a time (*Load more*), with the
time in the clinic's zone, the person, the action in words and the record. Filters: a range of up
to 92 days (default the last 7), a category and a person. *Export CSV* downloads the range (at most
20,000 rows) and is itself audited as `audit.exported`. Doctors and the front desk see "The audit
log is for the clinic's owners…". A range that is too long is `AUD_RANGE_TOO_LONG`: choose a
shorter one.

**Ops (no membership) use `make psql`:**

```sql
-- One clinic's recent activity (newest first)
select occurred_at, action, actor_user_id, entity_type, entity_id, request_id, metadata
from audit_events where clinic_id = '<clinic id>' order by occurred_at desc limit 50;

-- Everything one request did, across tables (DEBUGGING §2)
select * from audit_events where request_id = '<request id>';

-- Is this clinic being used at all? (no clinical columns)
select * from v_clinic_activity where clinic_id = '<clinic id>';
```

Rows carry IDs, enums and a salted IP fingerprint only — never names, phone numbers or clinical
content — so this output is safe to quote in a support ticket.

**The table refuses changes.** `UPDATE`, `DELETE` and `TRUNCATE` fail with `AUD_APPEND_ONLY`
(FR-AUD-02). If a correction is genuinely required — a data migration, not a cover-up — it needs
the founder's approval, a written record, and an explicit, temporary lift of the guard inside one
transaction:

```sql
BEGIN;
ALTER TABLE audit_events DISABLE TRIGGER USER;  -- requires the table owner
-- the corrective statement, with its reason recorded in the change ticket
ALTER TABLE audit_events ENABLE TRIGGER USER;
COMMIT;
```

Retention is at least three years (DATA_MODEL "Retention"); monthly partitioning is a post-pilot
step and nothing prunes the table today.

---

### 19. Google sign-in and patient accounts (M6a-P3)
**Locally (no Google client yet, L-09):** `GOOGLE_OIDC_PROVIDER=fake` (the default). Type an
email on `/sign-in` or `/portal/sign-in`, then press *Continue with Google*: the fake signs that
email in as a Google-verified identity. A seeded staff email (`doctor@sample-clinic.example`)
lands on Today; any other email on the staff page gets "No MediEase staff account uses this
Google address"; on the portal any email gets a Google patient account. The API refuses to start
with `fake` when `APP_ENV` is `staging` or `production`.

**With Google (after L-09):** create an OAuth client of type *Web application* in Google Cloud
with the authorized redirect URI `PUBLIC_BASE_URL` + `/api/v1/auth/google/callback` (locally
`http://localhost:3000/api/v1/auth/google/callback`), then set `GOOGLE_OIDC_PROVIDER=google`,
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` and `make up`. Start-up fails with
`CFG_INVALID` if either value is missing.

**A sign-in that bounces back to the sign-in page** carries `?reason=`; the API log has
`google.failed` with `intent` and `reason` for the same request ID (docs/ERRORS.md "Patient
portal and Google sign-in"). Common causes: the 10-minute flow cookie expired (start again), a
redirect URI that does not match the Google client exactly, or a staff address nobody invited.

**A patient forgot their password:** *Forgot password?* on `/portal/sign-in` (M6a-P4, §20). A
Google-only account is emailed a reminder to use *Continue with Google*.

---

### 20. Account emails: Mailpit locally, the SMTP provider in production (M6a-P4)
**Locally:** `make up` starts `mailpit`; the worker sends every verification and reset email
there. Read them at **http://localhost:8025** (nothing leaves the machine). Links point at
`PUBLIC_BASE_URL`.

**An email did not arrive:**
1. `make logs` for `email.failed` (reason and attempt) or `email.skipped` (why it no longer
   applied, e.g. `already_verified`, `no_password`).
2. In `make psql`: `SELECT state, attempts, last_error_code, run_at FROM jobs WHERE kind =
   'send_auth_email' ORDER BY created_at DESC LIMIT 5;`. A `queued` job with a later `run_at` is
   retrying. A `dead` one ended with the code in docs/ERRORS.md "Emailed links".
3. A reset request for an address with no eligible account sends nothing by design (the answer
   is the same 202): check the account exists, is active and has a password.
4. **A staff invitation (M6a-P5).** The owner's *Team* page shows *Sending the email…* until the
   worker has sent it, then *Link expires …*. Look for `email.staff_invite_sent`, or
   `email.skipped email=staff_invite` with `reason` (`not_invited`, `no_email`,
   `not_eligible`), and the jobs of kind `send_staff_invite` as in step 2. The owner can
   *Resend* (3 an hour per member) or invite by phone only to get a link to share.

**Going live (L-11):**
1. Create the Brevo account and verify the sending domain with SPF, DKIM and DMARC.
2. Turn off open and click tracking for transactional mail.
3. Create an SMTP key.
4. Set these, then restart the worker:
   - `EMAIL_PROVIDER=smtp` and `EMAIL_FROM=MediEase <no-reply@<domain>>`;
   - `SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=587`, `SMTP_SECURITY=starttls`;
   - `SMTP_USERNAME` and `SMTP_PASSWORD`.

   `SMTP_SECURITY=none` and `EMAIL_PROVIDER=console` are refused when deployed. To process in
   India instead, point the same settings at Amazon SES in `ap-south-1` (ADR-0016).

### 21. Notifications in the app (M6a-P7)

Staff see a bell in the header with their unread count; it refreshes every 15 seconds.
Notifications are written in the same transaction as the change that caused them (ADR-0017).

**Somebody expected a notification and got none:**
1. **Who is told.** A booking, a move, a cancellation and an arrival or walk-in tell the
   appointment's doctor, and only if that doctor profile is linked to an active member. A failed
   message tells the owners and the front desk. An accepted invitation tells the owners. The
   person who made the change is never told about it.
2. **Their settings.** *Notifications* in the menu (`/settings/notifications`) shows what they
   turned off. In `make psql`: `SELECT kind, enabled FROM notification_preferences WHERE user_id
   = '<user>';` (no row means on).
3. **The rows.** `SELECT kind, title, created_at, read_at FROM notifications WHERE
   recipient_user_id = '<user>' ORDER BY created_at DESC LIMIT 10;`. `make logs` shows one
   `notification.dispatched` per event with `recipients`, `written` and `muted` counts (no
   names).
4. **The patient's WhatsApp** for a booking or a prescription is still the M5 job: see §9 and the
   `send_booking_confirmation` / `send_rx_link` jobs.

Notifications are purged 90 days after creation by the retention job (`purge_expired_auth_and_links`,
whose `retention.purged` log and SYSTEM audit row count `notifications`). Titles never hold clinical text; if one ever
does, handle it as a data-handling incident (§15) and fix the catalogue in
`domain/notifications/notification.py`.

### 22. Appointment reminders and bookings to move (M6a-P8)

A booking gets up to two WhatsApp reminders: the evening before (19:00 clinic time) and a set
number of hours before the visit (default 2). They are `reminders` rows of kind `APPOINTMENT`,
scheduled by the system in the booking's transaction and sent by the `send_reminder` job
(reminders spec R21).

**A patient expected a reminder and got none:**
1. **Who gets them.** Bookings made after M6a-P8 shipped (no backfill), not walk-ins, and only
   patients who allowed WhatsApp at booking (consent is checked again at send time). A reminder
   due less than 60 minutes after the booking, or not before the visit, is not scheduled.
2. **The clinic's settings.** *Appointment reminders* on the Schedule settings page (owners):
   *Evening before* on or off, *Before the visit* 0–6 hours (0 is off). In `make psql`:
   `SELECT reminder_evening_before, reminder_hours_before FROM clinics WHERE id = '<clinic>';`.
   A change applies to bookings made or moved after it.
3. **The rows.**
   ```sql
   SELECT id, status, due_at, revision, error_code, cancelled_at
   FROM reminders WHERE appointment_id = '<appointment id>' ORDER BY due_at;
   ```
   A rescheduled booking's reminders are on the new appointment; the old one's are `CANCELLED`.
4. **The error code.** `REM_APPOINTMENT_CHANGED`: cancelled at send time because the patient had
   arrived or been marked a no-show, or the session was closed by leave or a schedule change.
   `REM_TOO_LATE`: when it could run outside the quiet hours (21:00–08:00) the visit had already
   started, e.g. after a worker outage (reminders that early are not scheduled at all). `REM_CLINIC_PHONE_MISSING`: the clinic has no phone. `SKIPPED_NO_CONSENT`: consent was
   withdrawn. A `SENT` reminder shows its message's status (§9; template `appointment_reminder`).

**Staff try to move an appointment reminder:** 409 `REM_FOLLOWS_APPOINTMENT`. Reschedule the
appointment instead; cancelling the reminder is allowed.

**A patient was not told of a clinic cancellation:** only a cancellation with *Doctor unavailable*
or *Clinic request*, for a patient with WhatsApp consent, sends one (template
`appointment_cancelled`). Check the job:
`SELECT state, run_at, last_error_code FROM jobs WHERE kind = 'send_cancellation_notice' AND
dedupe_key = 'appointment_cancelled:<appointment id>';`. A `run_at` at 08:00 is the quiet hours;
the handler skips when the clinic has no phone or consent changed (`make logs`).

**Bookings to move.** A leave, a removed extra session or a new weekly schedule that keeps booked
sessions closes them (`APT_SESSION_CLOSED` for new bookings). The front desk and owners then see:
- a *Bookings to move* tile on Today (only when there are some);
- a banner on the queue under a closed session that still has patients;
- an in-app notification ("Dr. X on leave 24 Oct: 3 bookings to move"), except the person who
  made the change.

The page `/bookings-to-move` (`GET /appointments/to-move`) lists every `BOOKED` or `ARRIVED`
appointment from today in a `CLOSED` session, earliest first, with *Reschedule* and *Cancel*
(*Doctor unavailable* preselected). It is derived, so a booking leaves the list once it is moved
or cancelled; nothing is cancelled automatically.

Both templates need Meta approval (L-02); until then the console provider sends them locally.

### 23. Patient app links (M6b-P1)

A patient account sees a clinic's records only through an active row in `patient_account_links`
(patient portal spec R9). Staff manage it on the patient's profile, card *Patient app*.

**"I can't link" / "the invitation doesn't work":**
1. **Which invite.** An invite works once, for 7 days, and a newer one replaces it; every failure
   reads "no longer valid" (`PRT_INVITE_INVALID`) on purpose. Ask the front desk to choose
   *Invite again* and hand over the new link or QR code (the link is shown only once).
2. **Already linked.** `PRT_ALREADY_LINKED`: the record has another account, or this account
   already has a record at the clinic. Check in `make psql`:
   ```sql
   SELECT id, account_id, method, created_at FROM patient_account_links
   WHERE clinic_id = '<clinic>' AND patient_id = '<patient>' AND revoked_at IS NULL;
   ```
   If the wrong person linked (for example a relative who knew the phone's last digits), staff
   choose *Unlink* on the profile; the record itself is not changed.
3. **From a prescription link.** *Save to my MediEase* needs a verified email (or Google) and the
   last 4 digits again. Five wrong answers lock the link for the prescription page too: unlock it
   from the prescription's link panel (*Unlock link*, M4-P5).

**Removing access at once** (a lost phone, a dispute): unlink from the profile, or in an emergency
`UPDATE patient_account_links SET revoked_at = now(), revoked_by = 'STAFF' WHERE id = '<link>';`
(record it in the incident notes; the app path also writes `patient.portal_unlinked`). The account
sees nothing of that clinic from its next request.

**Dose records on request (M6b-P3b, R54).** A patient's Taken / Skipped marks are theirs alone; no
screen shows them to the clinic. Until the portal's own data-rights screens exist (FR-PRT-10),
support exports or deletes them when the patient asks from the account's own email:

1. Find the account: `SELECT id FROM patient_accounts WHERE email = lower('<email>');`
2. Export: `make dose-data ARGS="export <account-id> --out /exports/<account-id>.json"`. It
   writes a new file under `.exports/` (gitignored, owner-only on Linux; a Windows-mounted
   folder does not keep the mode). Send it to the patient over the support channel, then
   delete the file. Never paste it into a ticket.
3. Delete: `make dose-data ARGS="delete <account-id> --confirm"`; it prints how many were deleted.

Both log only the account ID and a count. The daily purge also deletes records a year after their
course ends (`keep_until`).

**The medicine plan (M6b-P3).** The *Medicines* tab only lays out the doctor's issued lines; a
patient who says it is wrong is shown what the prescription says (the patient page or PDF), and the
clinic revises the prescription if needed. Times of day are the patient's own (*Account*,
`patient_accounts.morning_time` …). Reminder choices are stored in `medicine_reminder_prefs` and
not sent until M6b-P6; they are deleted when the link ends. Never read or quote a patient's
choices into a ticket beyond their IDs.

**The portal's language (M6b-P2).** Each patient account has a language (`en` or `hi`), chosen
from the switch at the top of every portal screen and kept across devices
(`SELECT language FROM patient_accounts WHERE id = '<account>';`). The signed-out pages follow a
`me_pt_lang` cookie in that browser. A patient who sees the wrong language: the switch fixes it;
nothing for support to change.