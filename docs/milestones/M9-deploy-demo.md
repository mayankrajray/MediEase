# M9-P1 — Go live for the Phase 2 demo on Google Cloud (design)

| Field | Value |
|---|---|
| Status | **Approved by the developer 13 Nov 2026** (Option A below; answers Q1–Q6 in §8). Issue #75, branch `m9/75-deploy-demo` |
| Goal | A public HTTPS address with test logins and realistic data, for the demo video, the mentor's live review and the design partners, working until 31 Mar 2027 (Phase 2 deliverables §1, §2) |
| Deadline | Submission 15 Nov 2026, 23:59 IST; live on 14 Nov so the video can be recorded on 15 Nov |
| Later phases | M9-P2 to P5 in `TASKS.md`; uploads to Cloud Storage (C6); the move to `mediease.care` in December |

## 1. Decisions (developer, 13 Nov 2026)

1. **WhatsApp is switched off in production** with an explicit `MESSAGING_PROVIDER=disabled`
   while Meta's setting blocks sending. Reminders reach app users in the app and by pop-up alert
   (M7e-E4). WhatsApp comes back by changing the setting once Meta allows it.
2. **The assistant uses Groq now** (`LLM_PATIENT_DATA_ALLOWED=true`), before the legal review.
   Caveat accepted: the mentor and the video use the demo clinic's synthetic data, and the
   trusted clinics are told before they use the assistant with real patients.
3. **`seed --demo` may run in production**, explicitly, to load one demo clinic and the
   mentor's test logins (`mentor.staff@demo.example` style, invented addresses).
4. **No domain until December.** The address is `https://mediease.duckdns.org` (free DuckDNS
   name pointing at the VM's static IP); `mediease.care` comes later through Cloudflare.
5. **Hosting on Google Cloud, Option A:** one Compute Engine VM running the existing Docker
   Compose stack, PostgreSQL included. Oracle (card refused) and Railway (30-day trial, 1 GB per
   service, SMTP blocked) were dropped. Option B (Cloud SQL) costs about ₹26,000–28,600 for 90
   days against ₹19,700 for Option A and needs database connection changes; it is the upgrade
   path once real clinic data arrives.

## 2. Shape

```
Internet ──443/80──▶ VPC firewall ──▶ VM e2-standard-2, asia-south1, static IPv4
                                       Docker Compose (docker-compose.yml + infra/gcp override)
                                         caddy  :80/:443, Let's Encrypt for mediease.duckdns.org
                                           └─ web :3000 (same-origin proxy) ─▶ api :8000
                                         worker          reminders, email, push, sweeps
                                         upload-worker   scans and reads uploaded prescriptions
                                         clamav          internal network only
                                         db              PostgreSQL 16, volume pgdata
                                         migrate         one-off, on every deploy
                       VM service account ─▶ gs://<backups bucket> (private, asia-south1)
SSH only through IAP (35.235.240.0/20) · daily disk snapshot, 7 kept
Outside: Brevo SMTP :587, Google sign-in, Groq, browser push services
```

Why each piece:

- **The web on the VM, not Vercel.** The browser talks to one origin; no 4.5 MB request limit
  on uploads; `API_INTERNAL_URL=http://api:8000` stays as built today.
- **Caddy.** Free TLS with automatic renewal and HSTS, instead of a Cloud Load Balancer (about
  $18 a month). In December the site name changes in one line.
- **PostgreSQL in Docker.** Same as `make up`; not reachable from outside; nightly `pg_dump` to
  Cloud Storage and a daily disk snapshot.
- **Files on the VM disk** (`BLOB_STORAGE=local`, the `blobs` volume, in the snapshot) for the
  demo. Cloud Storage's S3-compatible API does not honour `If-None-Match` on uploads, so our
  write-once guarantee would silently weaken; a small Cloud Storage adapter using
  `if_generation_match=0` and the VM's service account follows after the demo (C6).
- **x86_64.** Our images are amd64; T2A Arm is not offered in Mumbai and C4A costs more.

## 3. Machine and cost

e2-standard-2 (2 vCPU, 8 GB), Ubuntu 24.04 LTS x86_64, 40 GB pd-balanced, regional static IPv4
(Premium tier), Shielded VM, OS Login, a dedicated service account, deletion protection, 2 GB
swap. Measured memory at idle is about 0.9 GB for the apps; ClamAV needs up to about 2.4 GB while
it reloads signatures and `next build` about 2 GB, so 4 GB (e2-medium) is too tight.

| Item | 90 days (₹, at ₹95.23 per $) |
|---|---|
| e2-standard-2 ($0.0805/h) | 16,559 |
| 40 GB pd-balanced ($0.12/GB-month) | 1,352 |
| Static IP in use ($0.005/h) | 1,028 |
| Snapshots, Cloud Storage, internet traffic (estimates) | ~771 |
| **Total** | **~19,710**, about ₹8,860 of the ₹28,569 credit left |

The Free Trial is the hard cap: nothing is charged unless the account is upgraded. The budget
(₹20,000, credits excluded, alerts at 25/50/75/90% and 100% forecast) only warns. A stopped VM
still pays for its disk and IP (about ₹805 a month). After 12 Feb 2027 the developer upgrades to
a paid account to keep the site live until 31 Mar 2027 (Q6; about ₹10,300 at this size).

## 4. Settings on the VM

`/opt/mediease/.env`, owner-only (`chmod 600`), never in git, written by the developer. Names
only here; values are generated on the VM (`openssl rand`), never shown to the agent.

| Setting | Value |
|---|---|
| `APP_ENV` | `production` |
| `PUBLIC_BASE_URL` | `https://mediease.duckdns.org` |
| `PUBLIC_HOST` (new, for Caddy) | `mediease.duckdns.org` |
| `COOKIE_SECURE` | `true` |
| `POSTGRES_*`, `DATABASE_URL` | a new strong password |
| `JWT_SIGNING_KEY`, `AUDIT_IP_SALT`, `PATIENT_LINK_SIGNING_KEYS`, `MESSAGING_PHONE_KEYS` | new production values |
| `TRUSTED_PROXY_SECRET`, `CLIENT_IP_HEADER` | Caddy sets the client address header (A11) |
| `MESSAGING_PROVIDER` | `disabled` (decision 1; C1) |
| `EMAIL_PROVIDER=smtp`, `SMTP_*`, `EMAIL_FROM` | Brevo on port 587, sender `mediease.official@gmail.com` until the domain (Q5) |
| `GOOGLE_OIDC_PROVIDER=google`, client ID and secret | redirect URI `https://mediease.duckdns.org/api/v1/auth/google/callback` |
| `LLM_PROVIDER=groq`, `LLM_*`, `LLM_PATIENT_DATA_ALLOWED=true` | decision 2 |
| `PUSH_PROVIDER=webpush`, `VAPID_*` | a **new** pair from `make vapid-keys` |
| `BLOB_STORAGE` | `local` |
| `PUBLIC_READS_PER_MINUTE` | `60` |

`make config-check LIVE=1` on the VM shows each as set or not set and calls each service once.

## 5. Code changes (this phase)

| # | Change | Why |
|---|---|---|
| C1 | `MESSAGING_PROVIDER=disabled`: an adapter that sends nothing; each WhatsApp send is recorded as not sent with the stable code `MSG_CHANNEL_DISABLED`, ends the job normally (no retry, no SMS fallback, no "message failed" alert to the desk), allowed in production; `make config-check` says so. The console adapter stays refused in production | Decision 1 |
| C2 | `make import-clinic` (spec `clinic-import`): one clinic with its people and recent history from a folder of CSV files, built through the domain's rules in one transaction; a complete invented demo clinic is bundled (`DEMO=1`: Kesar Bagh Family Clinic, Lucknow; two doctors, a desk, an owner, 20 patients, 26 visits over two weeks with prescriptions, bills and payments, 4 overdue follow-ups, 10 upcoming appointments, one patient app login). The test logins are `mentor.owner@`, `mentor.doctor@`, `mentor.desk@` and `mentor.patient@demo-clinic.example`; passwords are generated and printed once. Production asks for the slug; an existing slug or login is refused. `make seed` stays local-only | Decision 3; Q1 (the partners' data in the same format) |
| C3 | `infra/gcp/`: `docker-compose.prod.yml` (caddy service; no published ports for db, api, clamav, web; no mailpit; `restart: unless-stopped`; log rotation) and `Caddyfile` | One repeatable deploy |
| C4 | `scripts/backup.sh` (`pg_dump`, gzip, upload with the VM's service account) and a systemd timer; restore steps | Backups from day one |
| C5 | `make smoke-live`: `scripts/smoke.sh` against a base URL (health, readiness, pages, security headers) | Proof the deploy works |
| C7 | Docs: RUNBOOK (VM setup, first deploy, update, rollback, backup, restore), ADR for the hosting choice, SECURITY_AND_COMPLIANCE, ARCHITECTURE deploy section, `.env.example`, CHANGELOG | The runbook is the deploy |

Tests: C1 (adapter, wiring in production, the sender path ends with the code and no alert, the
reminder path, config-check); C2 (refusals, idempotence, domain rules through the use cases);
C5 against the local stack. Full suites and CI as usual.

## 6. Who does what

| When | Developer | Agent |
|---|---|---|
| 13 Nov | Console steps 1–3 (done), then 8–15: API, service account, bucket, static IP, VM, firewall, snapshot schedule, DuckDNS, OAuth redirect and test users, Brevo sender, Groq key | Issue and branch; C1–C5, C7 |
| 14 Nov | VM steps 16–20 from the runbook: Docker, clone, `.env`, deploy, `seed --demo`, `make smoke-live`, first backup and restore | Review each step live; fix what shows |
| 15 Nov | Video recording | Deliverable drafts updated with the real address and logins |

## 7. Risks

| Risk | Plan |
|---|---|
| One VM in one zone | Snapshots, off-VM dumps, a tested restore |
| ClamAV memory on the VM | Measure after the first start; 8 GB leaves room |
| DuckDNS or Let's Encrypt down on the day | Caddy retries; fall back to an `sslip.io` name for the static IP |
| Email from a gmail.com sender through Brevo may land in spam (DMARC) | Accepted until `mediease.care` with a verified domain in December |
| Google sign-in consent screen in Testing | Only listed test users can sign in; password logins work for everyone |
| Credit ends 12 Feb 2027 | Developer upgrades to a paid account before then (Q6); a reminder on 25 Jan |

## 8. Answers (developer, 13 Nov 2026)

- **Q1 Usage evidence.** The design partners' 4 weeks of usage live on the developer's other
  website. The developer exports them into the CSV format of `docs/specs/clinic-import.md` and
  runs the import on the VM (RUNBOOK §37); the agent never sees the data (CLAUDE.md "No real
  patient data outside production").
- **Q2 Test logins.** `mentor.owner@`, `mentor.doctor@`, `mentor.desk@` and
  `mentor.patient@demo-clinic.example`, with generated passwords printed once at import. These
  addresses receive no email; a mentor who wants to try *Forgot password* uses their own email
  (an owner invites it as staff, or they sign up as a patient). Not in the "Try this" script.
- **Q3** The demo clinic shares the production database; it is test data and is deleted
  afterwards.
- **Q4** `mediease.duckdns.org`.
- **Q5** Brevo sends from `mediease.official@gmail.com` until the domain is bought in December.
- **Q6** After 12 Feb 2027 the developer buys service until 31 Mar 2027.

## 9. Deployment record (developer, 13–14 Nov 2026)

| Check | Result |
|---|---|
| VM | e2-standard-2, Ubuntu 24.04 x86_64, 40 GB balanced disk, asia-south1-a, static IPv4, dedicated service account (scope `cloud-platform`; roles only on the backup bucket) |
| Software | Docker Engine, Compose v5.7.1, make, unattended-upgrades, 2 GB swap |
| Code | `m9/75-deploy-demo` at `efe7bbf` (the first `make up` stopped at `migrate`: `PUBLIC_BASE_URL` was never passed to the containers; fixed, DEBUG_JOURNAL 2026-11-13) |
| `make up` | Every service healthy, migration `0044`, certificate from Let's Encrypt for `mediease.duckdns.org` (valid to 11 Feb 2027, renewed by Caddy) |
| `make config-check LIVE=1` | Brevo SMTP ok and a test email delivered; Google ok; Groq ok; WhatsApp skipped (`disabled`); push keys set |
| `make import-clinic DEMO=1` | Kesar Bagh Family Clinic: 20 patients, 26 visits, 24 prescriptions, 26 bills, 23 payments, 10 upcoming appointments (12 reminders), 3 follow-up reminders, 6 logins |
| Backups | Timer active; first backup in the bucket; `restore-check.sh` passed (10 tables equal, schema `0044`) |
| `make smoke-live` | Passed: certificate, redirect, health, HSTS, CSP, no Server header, sign-in protection, 413, public clinic page, ports 22/3000/3310/5432/8000 closed from outside |
| Browser | Desk login (Today, Patients, 4 pending follow-ups, Bills); patient login (appointment, prescriptions); Google sign-in after adding the redirect URI and a test user |

Security review in Cloud Shell (14 Nov 2026): SSH only from the IAP range, default SSH/RDP rules
gone, OS Login on and project SSH keys blocked; the bucket private (uniform access, public access
prevention, 30-day deletion) with the VM account limited to object create and view; no
service-account keys. Google sign-in with a new, unlinked account shows no records, as intended.

Open: the mentor's Gmail as a Google test user; the first scheduled backup (03:00 IST) to be
confirmed in the journal.

## 10. M9-P4 — Ops clinic usage (developer, 14 Nov 2026)

Issue #77, branch `m9/77-pilot-hardening` (from `main` after PR #76 merged). Built first, ahead of
P2 and P3, so the Phase 2 video can show the ops console and the design partners' usage evidence
(developer, 14 Nov 2026). Spec: `docs/specs/ops-clinic-usage.md`.

| Decision | Choice | Rejected |
|---|---|---|
| Where | A new page `/ops/usage` ("Clinic usage"), beside the clinics list | Widening the clinics list, which is about onboarding |
| Source | One cross-clinic read model over existing tables, like `SqlAlchemyMessageCostReport`; no migration | A usage table filled by a job (more moving parts for the same counts) |
| Weeks | Monday to Sunday, India time; each clinic's records bucketed in its own timezone | Rolling 7-day windows (harder to compare with a partner's week) |
| People | Distinct active members (`staff.members`) from the database | Adding owners, doctors and front desk (a doctor-owner would count twice) |
| Evidence | CSV made in the browser, for all clinics or one | A server CSV endpoint (the JSON already has every number) |
| Health | Failed messages and dead jobs in 7 days; `MSG_CHANNEL_DISABLED` counted apart as "not sent" | Counting disabled-channel messages as failures (every message fails while messaging is `disabled`) |

UI: the existing ops components (`PageHeader`, `Segmented`, `StatTile`, the shared table and
`KeyValue`), following DESIGN.md; numbers as text beside every bar for screen readers; the detail
row renders only when open. No surface brief existed for this screen, so the developer's
instruction to build it stood in for the design questions (impeccable "operate" mode); the
impeccable detector found nothing on the new files.

## 11. M9-P2 — Alerting (developer, 27 Nov 2026)

Issue #86, branch `m9/86-alerting-security`. Backups and the restore drill landed in P1 (§9);
P2 adds the alerting ARCHITECTURE §10 listed (NFR-03, NFR-04). Answers (developer, 27 Nov 2026):
the developer's own address in `OPS_ALERT_EMAIL`, set later on the VM; the recommendations below.

| Decision | Choice | Rejected |
|---|---|---|
| Outside check | Google Cloud Monitoring uptime check on `/ready` (5 minutes, Google's regions, content `"database":"ok"`), email channel; one request covers Caddy, the certificate, web, API and database | UptimeRobot (a new account for the same result) |
| Inside check | `scripts/watch.sh` on a systemd timer every 5 minutes, beside the backup timer; emails through a small CLI in the API image (`ops_alert`), so the script never holds SMTP credentials and works while the api container is down (`compose run`) | Alerting from inside the app (dies with the app); Cloud Monitoring alerts on logs (needs log shipping) |
| When | Only on a change (new, resolved) and once a day while a problem lasts; "critical" (db, api, web, caddy, Docker) at any hour, warnings 08:00–22:00 IST and held till then | Every run (noise); clinic hours for everything (a night outage would wait) |
| Logs | Stay on the VM (Docker's rotated files) | The Ops Agent and Cloud Logging: cost, and its default storage is outside India (NFR-07) |
| Content | Service names, counts and codes only; the CLI keeps printable characters and caps the body | Log lines or request paths in the email |

Thresholds: 5 API server errors in 5 minutes, dead jobs in 24 hours, a running job stuck over
5 minutes, the oldest due job over 10 minutes, the backup failed or older than 26 hours, the disk
over 85%, the certificate under 14 days; each a `WATCH_*` line in `.env`.

Verified locally (27 Nov 2026): `make watch` all clear on a healthy stack; `make alert-test` sent;
`docker compose stop api` → one `[critical]` email, start → one "resolved"; a stopped worker at
23:00 IST held. Tests: `tests/unit/test_watch_script.py` (the real script against fake `docker`,
`systemctl`, `df`, `openssl`: each check, held warnings, daily repeat, retry after a failed email,
no address) and `tests/unit/delivery/test_ops_alert.py`; shellcheck clean.

Open (developer, on the VM): set `OPS_ALERT_EMAIL`, install the timer and create the uptime check
(RUNBOOK §41), then stop the API once to see both emails.

## 12. M9-P3 — Security review (27 Nov 2026)

Issue #86, branch `m9/86-alerting-security`. The review of `docs/SECURITY_AND_COMPLIANCE.md` §3
against the code and the deployment, with evidence in each row.

| Found | Done |
|---|---|
| `make audit`: the API clean; the web app's Next.js 16.4.3 had seven moderate advisories (production), and dev-only zod (high) and minimatch (moderate) | Next.js 16.4.6; `npm audit fix` for the dev tree (typescript-eslint 8.74, zod 4.6.7, minimatch 11). Both audits now report 0 |
| Staff password sign-in had the per-account lockout but no per-caller limit (the portal's had one) | 30 a minute per caller (`staff-sign-in`), like the portal; an HTTP test |
| PostgreSQL's log printed rows on constraint errors (`DETAIL: Key (phone_e164)=…`, "Failing row contains …", `STATEMENT`) | `log_error_verbosity=terse`, `log_min_error_statement=panic` on `db`; `scripts/log-review.sh` and RUNBOOK §42 |
| The breach procedure had no clocks | RUNBOOK §15: the clinic told within 24 hours, so it can report to the Board within 72 hours (DPDP Rules, Rule 7); CERT-In within 6 hours when reportable; a written timeline |
| No sub-processor list | SECURITY_AND_COMPLIANCE §5 |
| Rows claiming "signed URL" for files, "Pydantic at every boundary", "no string-built SQL" | Reworded to what the code does, with the files named |
| TLS 1.2+, HSTS, encryption at rest, India hosting, no clinical content in messages | Ticked with the evidence (Caddy defaults, Google-managed encryption, `asia-south1`, the template variable kinds) |

Still open: the cross-tenant guard covers one method per URL and not IDs in query strings or
bodies; owner-granted support access (FR-OPS-05); Row-Level Security (post-pilot); point-in-time
recovery; the DPA, patient notice and sharing the sub-processor list (L-04); the log review on the
VM; alerts for sign-in failure spikes and webhook signature failures.

**Patient export and erasure (built 28 Nov 2026, spec `patient-data-requests.md`):** the
developer chose (27 Nov 2026) a support command on the VM, erasure that anonymises and keeps the
clinical record, and an AES-256 zip whose password is told by phone. `make patient-data`
(`delivery/cli/patient_data.py`, `application/patients/data_requests.py`,
`adapters/db/patient_data.py`, a reviewed tenancy exception); new dependency `pyzipper` 0.4.0
(the standard library cannot write encrypted zips; `pip-audit` clean). RUNBOOK §43.
