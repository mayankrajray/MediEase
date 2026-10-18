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
| (no clinic) | `ops@mediease.example` |

Every seeded doctor gets a Monday–Saturday 10:00–13:00 schedule (15-minute slots, 12 tokens), once,
so `GET /api/v1/sessions?date=<a weekday>` has sessions to show. On `/queue` (M3-P5) the front desk books with *Book*,
adds walk-ins and moves patients through the day; the owner edits hours, leave and extra sessions
on `/settings/schedule`. Outside 10:00–13:00 add an extra session there to have a session running now. `sample-clinic` also gets six synthetic patients, once (while it has none): Asha, Arun and Meera Rao
share the phone `+919000000101` (Meera is 6 and registered with Asha as guardian), Bina Shah is
known only by age, Chetan Verma prefers Hindi, and Deepa Nair is an adult on her own number. Try
`GET /api/v1/patients?q=9000000101` or register a new person on that number to see the duplicate
flow.

`doctor@sample-clinic.example` therefore belongs to two clinics: signing in as them shows the clinic
chooser and switcher in the web app. The seed refuses to run unless `APP_ENV=local` and is
idempotent **per clinic**: a clinic that exists is left alone, so a database seeded before
`sample-clinic-two` existed only gains the new clinic.

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
**Confirm:** `v_job_health.due` and `stale` fall to 0; message statuses progress.

### 7. Messaging provider outage (M5)
1. Confirm on the provider status page; our logs show `MSG_PROVIDER_UNAVAILABLE`.
2. Jobs retry with backoff automatically — do not requeue manually during the outage.
3. If the outage exceeds 2 hours during clinic hours, enable SMS fallback for consented patients
   (`MESSAGING_SMS_FALLBACK_ENABLED=true`) and inform pilot clinics.
**Confirm:** after recovery, `messages` in `QUEUED` drain; failure rate < 5%.

### 8. WhatsApp template rejected or quality rating dropped
1. Rejected: read the rejection reason, adjust wording (utility, no promotional language), resubmit,
   bump `template_version` in `templates.yaml`.
2. Quality dropped: pause broadcasts (P1 feature), review opt-out rates per clinic, reduce
   non-essential sends, and check for duplicate sends in `messages`.
**Confirm:** template status approved / quality rating recovered in Meta Business Manager.

### 9. Webhooks failing
1. Look for `webhook.signature_invalid` or 5xx on `/webhooks/*`.
2. Verify the app secret in the secret store matches Meta's app settings.
3. Verify the reverse proxy passes the raw body unchanged.
4. Missed events: statuses can be reconciled by the reconciliation job (M5-P3) for the last 24 h.

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
4. The owner invites the doctor and front desk themselves
   (`POST /api/v1/clinic/staff`), or ops does it with the same body as above.
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
**When:** a clinic asks "who changed this?", or an incident needs a timeline. There is no API for
it yet (FR-AUD-03 is a later, owner-facing feature), so this is a `make psql` procedure.

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
