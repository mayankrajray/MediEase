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

---

### 1. Local environment reset
**When:** local database is in a bad state.
```bash
make down
docker volume rm mediease_pgdata   # destroys LOCAL data only
make up && make migrate && make seed
```
**Confirm:** `/ready` returns 200; seed clinic can sign in.

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

### 6. Dead or stuck jobs (M5)
1. Ops console → Jobs → Dead, or DEBUGGING §5.6 queries.
2. Read `last_error_code` in ERRORS.md and fix the cause first.
3. Requeue from the console (sets `state=queued`, `attempts=0`, keeps `dedupe_key`).
4. For `running` jobs stuck > 5 min with no live worker, the reaper requeues automatically.
**Confirm:** queue age alert clears; message statuses progress.

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
2. Ops console → Create clinic → doctors → owner invite. Checklist timestamps start.
3. Set booking mode (slots/tokens) and schedules with the doctor.
4. Import patients; resolve duplicates with the front desk.
5. Book one real appointment; issue one real prescription; confirm the patient link opens.
6. Record consent practice: the clinic's own patient notice is displayed at the front desk.
**Confirm:** onboarding checklist shows all steps; total time recorded for goal G4.

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
Keys are versioned (`kid`). Add the new key as primary, keep the old key for verification for
90 days, then remove it. Emergency rotation (compromise) removes the old key immediately — all
existing links fail with `LINK_INVALID`; clinics resend links from the visit screen.

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
