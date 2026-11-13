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
| C2 | `seed --demo`: one realistic invented clinic (a Lucknow general practice: two doctors, a front desk, an owner; about 25 synthetic patients; schedules; past visits, prescriptions, bills and follow-ups over the last 4 weeks; upcoming appointments; one patient app account). Allowed in production only with `--demo --password <chosen>` and a typed confirmation; refuses if the demo clinic exists. `make seed` stays local-only | Decision 3 |
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
  website and will be shared later to load into this database. **Open:** what that data
  contains. Real patient data is not handled by the agent (CLAUDE.md "No real patient data
  outside production"); an import into production is designed separately once the format is
  known.
- **Q2 Test logins.** Invented addresses such as `mentor.staff@demo.example`.
- **Q3** The demo clinic shares the production database; it is test data and is deleted
  afterwards.
- **Q4** `mediease.duckdns.org`.
- **Q5** Brevo sends from `mediease.official@gmail.com` until the domain is bought in December.
- **Q6** After 12 Feb 2027 the developer buys service until 31 Mar 2027.
