# TASKS.md — Delivery Plan and Live Status

The single place that says **what is being worked on now**. Agents work only on the phase marked
`▶ ACTIVE`. Update this file at the end of every phase.

Legend: `▶ ACTIVE` · `☐ todo` · `✅ done` · `⏸ blocked` · Requirement IDs refer to `docs/PRD.md`.

---

## Current focus

| Field | Value |
|---|---|
| Active milestone | **M9 — Pilot hardening and deployment** (issue #75, branch `m9/75-deploy-demo` on `main` after M7e merged in PR #74 on 13 Nov 2026) |
| Active phase | **M9-P1 — Go live for the Phase 2 demo on Google Cloud** (one Compute Engine VM in Mumbai, Docker Compose, PostgreSQL in Docker, Caddy on `mediease.duckdns.org`) |
| Design notes | `docs/milestones/M9-deploy-demo.md`; M7e (done) in `docs/milestones/M7e-pwa-push.md`; M8 designed in `docs/milestones/M8-multi-clinic-whatsapp.md` (skipped for now by the developer) |
| Approved plan | `NEXT_STEPS_PLAN.md` §0 (M9-P1); M7e, M7d, M7c and M7 below it as history |
| Workflow | One issue, one branch, one PR per milestone; phases land as logical commits on that branch; PR is a draft until the milestone is done → CODEOWNERS review → maintainer merge (ADR-0010, ADR-0011) |
| Blockers | W-5: branch protection / CODEOWNERS enforcement on `main` not available on the current GitHub plan (`NEXT_STEPS_PLAN.md` §3.1). `@akhtarjamal10` needs write access before their CODEOWNERS entry takes effect |
| Open decisions | L-09 (Google sign-in), L-10 (Groq key) and L-11 (Brevo email) are done (9 Nov 2026). The issue #49 title still says "MVP demo" (rename on GitHub by the developer). Deployment and hosting are skipped for now (developer, 20 Oct 2026). Pending from M5: the live WhatsApp test (L-01, L-02; RUNBOOK §9) and the real SMS provider (L-03). For M8: the BSP partner (L-08). Outside the milestones: #30 (an import over 2 MB through the web origin can answer 500 instead of 413); the M4-P3 suggestions timing test checks the index plan in CI and the 150 ms bound locally (11 Nov 2026) |
| Last updated | 13 Nov 2026 |


---

## Long-lead track (non-code, start now)

These take days to weeks outside our control. They run in parallel with engineering and must be
done before the pilot.

| ID | Task | Owner | Needed by | Status |
|---|---|---|---|---|
| L-01 | Create Meta Business account, verify business, register WhatsApp number | Founder | M5 | ☐ |
| L-02 | Draft and submit utility templates (booking confirmation, prescription ready, prescription updated, follow-up due; from M6a-P8 appointment reminder and appointment cancelled) in English and Hindi | Product | M5 | ☐ |
| L-03 | SMS provider account + DLT registration (entity, sender ID, templates) | Founder | M5 | ☐ |
| L-04 | Counsel review: DPDP roles, clinic–MediEase data processing agreement, patient notice template, prescription format | Founder | M6 | ☐ |
| L-05 | Choose India-region hosting account; enable billing alerts | Engineering | M6 | ☐ |
| L-06 | Book pilot conversations with Aarogya Hospital (A13), Apollo Diagnostic (A10); Arvind Homoeopathy (A1) as reserve | Founder | M6 | ☐ |
| L-07 | Collect each pilot clinic's current booking flow, Rx format and patient list format | Product | M4 | ☐ |
| L-08 | Choose a WhatsApp BSP with a partner-paid (wholesale) model; MediEase's business verification and website for the partnership (ADR-0014) | Founder | M8 | ☐ |
| L-09 | A Google Cloud OAuth client (free) for Google sign-in, with the local redirect URI | Founder | M6a-P3 | ✅ (9 Nov 2026; set in the developer's `.env` and tested by the developer) |
| L-10 | A Groq API key (free tier) for the assistant | Founder | M7 | ✅ (9 Nov 2026; set in the developer's `.env` and tested by the developer) |
| L-11 | A free-tier transactional email account (Brevo recommended, ADR-0016) with a verified sending domain (SPF, DKIM, DMARC) and SMTP credentials; listed as a processor in the privacy notice (L-04) | Founder | M6a-P4 | ✅ (9 Nov 2026; account, domain and SMTP set in the developer's `.env` and tested by the developer; the privacy-notice listing stays with L-04) |

---

## M0 — Foundation  `✅`

**Outcome:** a reproducible local stack with typed configuration, structured logging, health and
readiness, a migration step, and CI. No business features.
**Covers:** NFR-12, NFR-15. **Exit:** `make up` → `GET /health` 200, `GET /ready` 200 with the
database up and 503 with it down; CI green on a PR.

| Phase | Scope | Verify | Status |
|---|---|---|---|
| M0-P1 | Repository skeleton, `.env.example`, `docker-compose.yml` with PostgreSQL, `Makefile` basics | `make up && make psql` → `select 1;` returns 1 | ✅ |
| M0-P2 | Flask app factory (composition root), typed settings (fail fast on missing config), JSON logging with `request_id` middleware, `/health` | `curl -i localhost:8000/health` → 200 + `X-Request-ID` header; start with a missing required setting → process exits with a clear message | ✅ |
| M0-P3 | SQLAlchemy engine + `/ready` checking the database; Alembic set up with an empty baseline; minimal API `Dockerfile`; `migrate` one-off service and `api` service in compose (`api` depends on `db` healthy + `migrate` completed successfully) | `make up` alone runs db → migrate (exit 0) → api healthy; stop db → `/ready` 503 with `code=READY_DB_UNAVAILABLE`; `make migrate` exits 0 | ✅ |
| M0-P4 | Next.js app shell, generated API client from `contracts/openapi.yaml`, status page calling `/health` | open `localhost:3000/status` → shows API healthy and the request ID | ✅ |
| M0-P5 | Harden API `Dockerfile`, add web `Dockerfile` (non-root, multi-stage), full compose (`web`, `api`, `db`, `migrate`) started by one command, CI workflow (lint, typecheck, test, build) | fresh clone → `make up` brings up every service with no manual steps; PR shows green checks | ✅ |

---

## M1 — Identity, tenancy and audit  `✅`

**Covers:** FR-ORG-01..04, FR-AUTH-01..04, FR-AUD-01..02, FR-OPS-01, FR-OPS-04.
**Spec:** `docs/specs/identity-and-tenancy.md` (Approved 2 Oct 2026). **Issue:** #19, one branch
and one PR for all phases (ADR-0011).
**Exit:** an ops user onboards a clinic with an owner, doctor and front desk; each signs in and sees
only their clinic; the tenancy test suite proves isolation.

| Phase | Scope | Status |
|---|---|---|
| M1-P1 | Domain: Clinic, User, ClinicMembership, Doctor, Role; tables + migration `0002`; tenancy-scoped repository base + unit of work; add the ≥ 80% coverage gate on `domain/` + `application/` (NFR-14) | ✅ |
| M1-P2 | Password hashing, sign-in, refresh rotation, sign-out, lockout (FR-AUTH-01..04) | ✅ |
| M1-P3 | Authorisation: role + clinic membership check on every route; permission matrix tests | ✅ |
| M1-P4 | Audit log (append-only) written in the same transaction as the change; non-clinical support views (`v_clinic_activity`); audited staff role change | ✅ |
| M1-P5 | Ops console: create clinic → doctors → owner invite; single-use staff invites and acceptance; onboarding checklist timestamps; staff invite and deactivate | ✅ |
| M1-P6 | Web: sign-in, clinic switcher (for multi-clinic users), empty dashboard shell | ✅ |
| M1-P7 | Web: ops clinics list and the Create clinic wizard (clinic → doctors → owner invite, elapsed time; spec §6) | ✅ |

## M2 — Patients  `✅`

**Covers:** FR-PAT-01..06, FR-PAT-08. **Spec:** `docs/specs/patients.md` (Approved 3 Oct 2026). **Issue:** #21, one branch and one PR for all phases (ADR-0011). **Exit:** register, find and update patients; phone
duplicates surfaced; 10k-patient lookup p95 < 500 ms.

| Phase | Scope | Status |
|---|---|---|
| M2-P1 | Patient domain (phone normalisation, guardian model, age, consent, clinic-scoped code) + migration `0006` + indexes + tenancy-scoped repository + the 10,000-patient lookup test (AC4) | ✅ |
| M2-P2 | Register / edit / lookup endpoints; duplicate-phone flow | ✅ |
| M2-P3 | Consent and language preference; opt-out state | ✅ |
| M2-P4 | Ops CSV import with dry-run report | ✅ |
| M2-P5 | Web: patient search bar (global), registration drawer, patient profile | ✅ |

## M3 — Appointments and daily queue  `✅`

**Covers:** FR-APT-01..07, FR-QUE-01..05. **Spec:** `docs/specs/appointments-and-queue.md` (Approved 17 Oct 2026). **Issue:** #36, one branch and one PR for all phases (ADR-0011), merged in PR #37 on 17 Oct 2026. **Exit:** front desk books in ≤ 3 interactions;
concurrent double-booking test passes; queue refreshes on all screens within 5 s.

| Phase | Scope | Status |
|---|---|---|
| M3-P1 | Doctor schedules, sessions, exceptions; slot and token generation (clinic timezone aware) | ✅ |
| M3-P2 | Booking, reschedule, cancel with row-level locking and capacity checks | ✅ |
| M3-P3 | Queue state machine and transitions; walk-ins | ✅ |
| M3-P4 | Live queue updates (polling with ETag first; SSE only if polling proves insufficient — ADR required) | ✅ |
| M3-P5 | Web: today's queue board, booking flow, schedule settings | ✅ |

## M4 — Visits and digital prescriptions  `✅`

**Covers:** FR-VIS-01..03, FR-VIS-05, FR-RX-01..10. **Spec:** `docs/specs/prescriptions.md` (Approved 17 Oct 2026, D1-D5). **ADR:** 0012. **Issue:** #38, one branch and one PR for all phases (ADR-0011). **Exit:** doctor issues an Rx from the queue;
PDF prints correctly; patient link passes the 360-px acceptance test.

| Phase | Scope | Status |
|---|---|---|
| M4-P1 | Visit record, history view, 24-hour lock and addenda | ✅ |
| M4-P2 | Prescription domain: items, instructions, versioning, immutability | ✅ |
| M4-P3 | Favourites and Rx templates; clinic-history autocomplete (no external drug data) | ✅ |
| M4-P4 | PDF rendering port + adapter; letterhead with registration number | ✅ |
| M4-P5 | Signed patient links, last-4-digit check, open audit; bilingual patient page; `scripts/inspect_link_token.py` | ✅ |
| M4-P6 | Web: consultation screen (history + notes + Rx builder), keyboard-first | ✅ |

## M5 — Messaging and reminders  `✅ (live WhatsApp test pending)`

**Covers:** FR-MSG-01..05, FR-MSG-07, FR-REM-01, 02, 04, 05, 07, FR-APT-06.
**Exit:** a reminder scheduled in the app is delivered through the WhatsApp test number, status
flows back through the webhook, and opt-out stops further sends. Depends on L-01, L-02.

| Phase | Scope | Status |
|---|---|---|
| M5-P1 | Job table, worker process, `SKIP LOCKED` claiming, retries with backoff, dead-letter state, stale-lock reaper; `v_job_health`, `v_message_health` views | ✅ (`v_message_health` moves to P2 with the `messages` table) |
| M5-P2 | `MessagingPort`; console adapter; template registry versioned in repo | ✅ |
| M5-P3 | WhatsApp Cloud API adapter; webhook signature verification; idempotent status updates; status reconciliation job | ✅ (live Meta test pending L-01/L-02) |
| M5-P4 | Reminder scheduling rules (quiet hours, consent, follow-up defaults); pending follow-ups list; automatic no-show job | ✅ |
| M5-P5 | Inbound STOP handling; SMS adapter (fallback behind a flag); per-clinic cost ledger | ✅ (real SMS provider pending L-03) |
| M5-P6 | Web: reminder status on patient profile and visit; pending follow-ups page; ops monthly messaging costs (P5 decision 7A) | ✅ |
| M5 pending | **Live WhatsApp test** through Meta's test number: a reminder scheduled in the app delivered, its statuses back through the webhook, a STOP stopping further sends (the exit criterion). Needs the developer's credentials (L-01, L-02); procedure RUNBOOK §9. Also the real SMS provider (L-03) | ⏳ pending credentials |

## M6a — Auth, staff workspaces and notification core  `✅ (merged 24 Oct 2026, PR #50)`

**Covers:** FR-AUTH-05, 07, 08, FR-PRT-01 (account only), FR-ORG-03, FR-ORG-07, FR-UX-01..06,
FR-NTF-02..06, FR-APT-08, 09, FR-AUD-03 (PRD v1.2). **Issue:** #49, one branch and one PR for all
phases (ADR-0011). Was "M6 — MVP demo" until PRD v1.2. **Exit:** on the local stack Owner, Doctor
and Front Desk, and a practising owner in both views, each get their own home screen and
navigation; staff and patients sign in with Google (fake provider) or a password and stay apart;
email verification and password reset work; the owner manages the team on the web; in-app
notifications arrive; `make e2e` green. Deployment and hosting are out of scope (developer, 20 Oct
2026).

| Phase | Scope | Status |
|---|---|---|
| M6a-P1 | Design system (tokens, primitives, Motion, responsive shell); *Today* dashboards for front desk, doctor and owner | ✅ (confirmed 20 Oct 2026; PR #50) |
| M6a-P2 | The design system across the existing screens; mobile layouts; motion for drawers, dialogs and lists | ✅ (confirmed 21 Oct 2026; PR #50) |
| M6a-P3 | Google sign-in for staff and patients; patient email and password; separate patient sessions (FR-AUTH-07, FR-PRT-01; ADR-0015) | ✅ (confirmed 23 Oct 2026; PR #50) |
| M6a-P4 | Email provider behind a port: email verification for patient password accounts, password reset by link for staff and patients (FR-AUTH-08, FR-AUTH-05; ADR-0016); L-11 | ✅ (confirmed 23 Oct 2026; PR #50) |
| M6a-P5 | Owner Team page: invite (emailed, or a link for phone-only), change role, deactivate, re-invite (FR-ORG-07, on the existing FR-ORG-04 API) | ✅ (confirmed 23 Oct 2026; PR #50) |
| M6a-P6 | Role workspaces: Owner, Doctor and Front Desk navigation and home (FR-UX-01..05); the practising owner's Owner / Doctor switch with *My Patients* (FR-UX-06); the ops wizard marks the owner as Doctor 1 in the same step (FR-ORG-03) | ✅ (confirmed 23 Oct 2026; PR #50) |
| M6a-P7 | Notification service with domain events and the in-app channel; notification centre per role (FR-NTF-02..06; replaces FR-NTF-01) | ✅ (confirmed 24 Oct 2026; PR #50) |
| M6a-P8 | Appointment reminders (FR-APT-08), doctor-leave conflicts (FR-APT-09), owner audit view (FR-AUD-03) | ✅ (confirmed 24 Oct 2026; PR #50 merged) |

## M6b — Patient identity, portal and booking requests  `✅`

**Covers:** FR-PRT-02..07, FR-BKG-01..08, FR-PUB-01..04, FR-REM-03, FR-QUE-06, NFR-18 (PRD v1.2).
Own issue, branch and PR. **Exit:** a patient links clinic records by invite, prescription link or
an accepted request; sees My Appointments per clinic, prescriptions, reminders and a medicine plan;
requests a slot on `/c/{slug}` and front desk accepts it from the inbox; cross-clinic isolation
tests pass. Issue #51, branch `m6b/51-patient-portal-booking`; design notes
`docs/milestones/M6b-patient-portal-booking.md`.

| Phase | Scope | Status |
|---|---|---|
| M6b-P1 | Linking (clinic invite, prescription link) and the read-only patient API; portal tenancy suite (FR-PRT-02, 03, 06 b-c, NFR-18) | ✅ (confirmed and pushed 24 Oct 2026; draft PR #52) |
| M6b-P2 | Portal web: fresh dashboard, My Appointments by clinic, prescriptions, reminders, English and Hindi (FR-PRT-03, 04, 05, 07) | ✅ (pushed 24 Oct 2026, PR #52) |
| M6b-P3 | Prescription structure (frequency patterns, bedtime warning, explicit duration and start, instruction codes), the medicine-plan engine, *Medicines* tab, reminder preferences (FR-REM-03; FR-RX amended) | ✅ (pushed 25 Oct 2026, PR #52) |
| M6b-P3b | Dose tracking: Taken / Skipped, Not recorded derived, private health data and its lifecycle (FR-REM-03) | ✅ (pushed 25 Oct 2026, PR #52) |
| M6b-P4 | Public page `/c/{slug}` and booking requests with a soft hold (FR-PUB-01..04, FR-BKG-01..03, 07) | ✅ (pushed 26 Oct 2026, PR #52) |
| M6b-P5 | Front-desk inbox: accept with linking, decline, propose, expiry (FR-BKG-04..06, 08, FR-PRT-06 a) | ✅ (pushed 26 Oct 2026, PR #52) |
| M6b-P6 | Patient notifications and the live token link (FR-NTF-04, 05 for patients, FR-REM-03, FR-QUE-06) | ✅ (pushed 26 Oct 2026; PR #52 merged 26 Oct 2026) |

## M6c — SaaS clinic onboarding, verification and discovery  `✅ (PR #54, merged 26 Oct 2026)`

**Covers:** FR-ONB-01..10, FR-DIS-01..08, FR-LND-01..03, NFR-17, NFR-19 (PRD v1.2). Issue #53,
branch `m6c/53-onboarding-discovery`, one PR. Design notes
`docs/milestones/M6c-onboarding-verification-discovery.md` (approved 26 Oct 2026); ADR-0020.
Application status, clinic status, verification and listing are modelled separately (PRD §8.14).
**Exit:** a pending, approved-but-unlisted or suspended clinic is invisible in discovery; an
`ACTIVE`, verified and listed clinic is found by clinic search and by doctor search and requested
within one session.

Locked decisions (26 Oct 2026): **D1** a clinic becomes `ACTIVE` when the owner accepts the
existing invitation; **D2** `/apply` is English-only in M6c; **D3** the application says MediEase
will reply within 2 working days; **D4** issue #53, branch from the latest `main` after PR #52.

| Phase | Scope | Status |
|---|---|---|
| M6c-P1 | The application: `/apply` for a clinic or a solo doctor, certificates, the verified email, lifecycle states, limits, the duplicate flag (FR-ONB-01, 02, 07) | ✅ (pushed 26 Oct 2026) |
| M6c-P2 | Reviewer workflow: ops roles, queue, per-doctor checks, decision with a reason, applicant emails (no status page, R37) (FR-ONB-03, 05) | ✅ (built 26 Oct 2026, pushed) |
| M6c-P3 | Approval through the one creation path (a prefilled approve form); clinic and doctor verification; `has_public_page` = `ACTIVE` ∧ verified (FR-ONB-04, 06, 08) | ✅ (built 26 Oct 2026, pushed) |
| M6c-P4 | Suspension and listing; the one discoverability rule (FR-ONB-05, 09, 10) | ✅ (built 26 Oct 2026, pushed) |
| M6c-P5 | Public clinic and doctor profiles (FR-DIS-03, 06, 07) | ✅ (built 26 Oct 2026, pushed) |
| M6c-P6 | Clinic and doctor search (FR-DIS-01, 02, 04, 05) | ✅ (built 26 Oct 2026, pushed) |
| M6c-P7 | Discovery to booking (FR-DIS-08) | ✅ (built 26 Oct 2026, pushed) |
| M6c-P8 | Landing page v1 (FR-LND-01..03) | ✅ (built 26 Oct 2026, pushed) |

## M6d — Billing and documents  `✅` (merged in PR #64, 26 Oct 2026)

**Covers:** FR-BIL-01..07, FR-VIS-04, FR-SUB-01 (PRD v1.2). Issue #63, branch
`m6d/63-billing-and-documents`, one PR. Design notes `docs/milestones/M6d-billing-and-documents.md`
(approved 26 Oct 2026). **Exit:** the daily collection matches recorded payments; plan limits are
enforced on every path that adds a doctor or a user; `make e2e` green.

Locked decisions (26 Oct 2026, all on the recommendations): **D1** bill numbers per financial
year; **D2** doctors record payments on their own bills; **D3** no GST fields; **D4** Solo = 1
doctor and 2 users counting the owner; **D5** the trial starts at `ACTIVE`, its end only flags;
**D6** receipts by link and QR, WhatsApp once a template is approved; **D7** front desk may upload
reports it cannot open; **D8** the public fee is the consultation price; **D9** issue #63.

| Phase | Scope | Status |
|---|---|---|
| M6d-P1 | Fee schedule: services, default and per-doctor prices, *Fees* page, the public fee from it (FR-BIL-01) | ✅ (built 26 Oct 2026) |
| M6d-P2 | Bills from a visit or for a patient; discounts; issue with a number; credit notes (FR-BIL-02, 07) | ✅ (built 26 Oct 2026) |
| M6d-P3 | Payments (cash, UPI, card; partial), refunds, dues (FR-BIL-03, 05) | ✅ (built 26 Oct 2026) |
| M6d-P4 | Receipt PDFs, the receipt link, bills in the portal (FR-BIL-04) | ✅ (built 26 Oct 2026) |
| M6d-P5 | Daily collection by mode and doctor, CSV (FR-BIL-06) | ✅ (built 26 Oct 2026) |
| M6d-P6 | Report attachments on visits (FR-VIS-04) | ✅ (built 26 Oct 2026) |
| M6d-P7 | Plans, trial and limits (FR-SUB-01) | ✅ (built 26 Oct 2026) |

## M7 — AI assistant (M7a) and verified prescription uploads (M7b)  `✅ (merged 27 Oct 2026, PR #66; follow-up PR #68)`

**Covers:** FR-AI-01..04, FR-RX-11, FR-UPL-01..05, NFR-20 (PRD v1.3 C15, C16). Issue #65, branch
`m7/65-assistant-and-verified-uploads`, one PR. **ADRs:** 0013, 0023, 0024. **Exit:** booking by
chat works through tools with a confirmation step; the guard-rail tests pass; the provider
switches by settings only; new prescriptions print the verification code and QR; an uploaded
MediEase prescription is scanned, identified and verified before the assistant may use it, and the
assistant reads only the database record; uploads are deleted after their outcome; `make e2e`
green. The animated landing-page polish moved to the backlog (PRD C15).

Locked decisions (27 Oct 2026): **D1** split into M7a and M7b on one branch; **D2** QR payload
`MEDIEASE-RX:1:<uuid>`; **D3** superseded uploads are chosen explicitly; **D4** no OCR; **D5** clinic
logos deferred; **D6** uploads never shown to staff, deleted after the outcome; **D7** the picker for
linked patients.

| Phase | Scope | Status |
|---|---|---|
| M7a-P1 | Layout 3: MediEase mark, verification code and QR (FR-RX-11) | ✅ (built 27 Oct 2026) |
| M7a-P2 | LLM gateway, Groq first, console adapter (FR-AI-03) | ✅ (built 27 Oct 2026) |
| M7a-P3 | Assistant core: tools as the caller, signed confirmations, guard rails, explanation (FR-AI-01, 02, 04) | ✅ (built 27 Oct 2026) |
| M7a-P4 | Patient assistant and the prescription picker (FR-AI-01, 04) | ✅ (built 27 Oct 2026) |
| M7a-P5 | Staff assistant (FR-AI-01) | ✅ (built 27 Oct 2026) |
| M7b-P6 | Upload and quarantine; #30 (FR-UPL-01, NFR-20) | ✅ (built 27 Oct 2026) |
| M7b-P7 | ClamAV on a separate upload worker (FR-UPL-02) | ✅ (built 27 Oct 2026) |
| M7b-P8 | Identifier extraction, no OCR (FR-UPL-03) | ✅ (built 27 Oct 2026) |
| M7b-P9 | Verification: own, representative, superseded (FR-UPL-04) | ✅ (built 27 Oct 2026) |
| M7b-P10 | Handoff to the assistant, cleanup, portal UI, journeys (FR-UPL-05) | ✅ (built 27 Oct 2026) |

## M7c — Demo polish, real configuration and Phase 2 deliverables  `▶ ACTIVE`

**Covers:** FR-AI-01..04 (spec assistant R15–R21) and the developer's feedback of 9 Nov 2026.
Issue #69, branch `m7c/69-demo-polish`, one PR. **Design:** `docs/milestones/M7c-demo-polish.md`.
**Exit:** the developer's failing conversations work (the doctor's advice, Hinglish, booking only
what is still open, asking which doctor); the provider switches between Groq, Mistral and NVIDIA by
settings only; WhatsApp, Google sign-in and email pass a live test with the developer; the redesigned
frontend passes `make e2e`; the Phase 2 deliverable documents are drafted with every placeholder in
`deliverables/PLACEHOLDERS.md`. Phase 2 is due 15 Nov 2026.

Build order (approved): P3 → P1 → P2 → P5 → P6 → P4 → P7 → P8.

| Phase | Scope | Status |
|---|---|---|
| M7c-P3 | Staff assistant: hide ended and full sessions and past slots, refuse them before the confirmation, ask which doctor, today and tomorrow in the prompt (R18–R20) | ✅ (built 9 Nov 2026) |
| M7c-P1 | The doctor's advice is read from the record; the guard lets "what did the doctor suggest" through (R15, R16) | ✅ (built 9 Nov 2026) |
| M7c-P2 | Hinglish understood; romanised Hindi in the guard rails (R17) | ✅ (built 9 Nov 2026) |
| M7c-P5 | Mistral and NVIDIA providers beside Groq, by settings only (R1) | ✅ (built 9 Nov 2026) |
| M7c-P6 | Real configuration: WhatsApp, Google sign-in, Brevo email, live tests with the developer; `.env.example` clean-up | ◐ Brevo (test email sent), Google sign-in (developer) and Groq pass; WhatsApp reads the number but Meta refuses sends with `OAuthException code 10` (the token's access to the WhatsApp account's payment, a Meta Business setting). Rechecked 11 Nov 2026 after a new token: the token reads the number (quality GREEN) but a send still fails with code 10 "Viewer cannot access the provided Paid Message Account" (also in the worker's log at 06:02 UTC); `.env` was last changed 10 Nov 05:34 UTC |
| M7c-P4 | Safe Markdown in the chat (R21) | ✅ (built 9 Nov 2026) |
| M7c-P7 | Landing page and frontend redesign: design system (Phase 1) then modules M1–M10 (`docs/milestones/M7c-P7-modules.md`) | ✅ Phase 1 and modules M1–M10 built and gated (9–10 Nov 2026); full `make e2e` 57/57; report `docs/milestones/M7c-P7-final-report.md` |
| M7c-P8 | Demo rehearsal, full suites and `make e2e`, Phase 2 deliverable documents | ☐ |

## M7d — Patient discovery, clinic and doctor profiles, booking redesign  `✅ (merged 12 Nov 2026, PR #72)`

**Design:** `docs/milestones/M7d-discovery-booking.md` (the developer's brief of 10 Nov 2026, the
audit, data gaps, decisions and the reference image `M7d-reference-image.png`). Front end only: no
API, schema or contract change. Issue #71, branch `m7d/71-discovery-booking` (from `main` after
M7c merged, 11 Nov 2026), PR #72, one PR. Phase plan and UX rules approved 11 Nov 2026 (§7 of the
design).

| Phase | Scope | Status |
|---|---|---|
| M7d-P1 | Search: icons centred on the inputs; result cards with one "Next available" line, no schedules | ✅ 11 Nov 2026: web 750 tests, lint, typecheck; no sideways scroll at the seven widths |
| M7d-P2 | `availability.ts` + `AppointmentPicker`: today selected, next 4 dates and the native calendar (14 days), morning/afternoon/evening, three each until "Show all", places-left badges, 60 s staleness guard | ✅ 11 Nov 2026: 16 new tests (rules on a fixed clock; every picker state); lint, typecheck |
| M7d-P3 | Doctor profile on `/c/[slug]/doctors/[doctor]`: real facts only, About with Read more, the picker, sticky "Request this time" | ✅ 11 Nov 2026: 7 tests (disabled until chosen, re-check before leaving, one tap, taken time, failed check, address state, Hindi); 188 KB first load; no sideways scroll at seven widths |
| M7d-P4 | Clinic page: text hero, the date strip and the doctors free on that date, no filters | ✅ 11 Nov 2026: 7 tests; discovery and booking journeys 6/6 (CI settings); 189.6 KB first load (doctor page 191.8 KB); no sideways scroll at seven widths |
| M7d-P5 | Confirmation: appointment summary, "Pay at the clinic", total = fee, the request form, ending at "Requested" | ✅ 12 Nov 2026: 2 new tests (summary and payment, one send, token session, unknown fee); portal, booking and i18n suites 88; lint, typecheck |
| M7d-P6 | Journeys and full `make e2e`, screenshots at seven widths, page weights, specs and milestone record | ✅ 12 Nov 2026: `make lint typecheck contract-check`; API 2583 (95.87%), web 776; `make smoke`; full Playwright suite (design §8); no sideways scroll at seven widths; request page 195.8 KB |

## M7e — Installable app (PWA) and web push notifications  `◐ (active)`

**Design:** `docs/milestones/M7e-pwa-push.md` (decisions of 11 Nov 2026, audit, phases E1–E5,
open points §7). Issue #73, branch `m7e/73-pwa-push` (rebased onto `main` after M7d merged in
PR #72, 12 Nov 2026), PR #74, one PR. Nothing is built yet.

| Phase | Scope | Status |
|---|---|---|
| M7e-E1 | Installable app: manifest, icons, service worker, offline page, install prompt | ✅ 12 Nov 2026: 24 unit tests (cache rules on the real `sw.js`, manifest and icons, prompts, gate, nonce script, proxy); `pwa` journey 2/2; portal pages 194–197 KB, `/` and `/find` unchanged; design §8 |
| M7e-A11 | Client addresses (moved up from M9 by the developer, 12 Nov 2026) and the public read limit as a setting, after CI's shared-address 429 | ✅ 12 Nov 2026: API 81 and web 124 tests; checked on the real stack (own budget per edge address, browser-sent address ignored); design §8 |
| M7e-E2 | Push subscriptions per device (migration `0043`), API and contract | ✅ 12 Nov 2026: migration `0043`, ADR-0025, spec `web-push.md` R10–R21, contract 0.52.0; 37 domain, 13 HTTP, 4 contract and 1 migration test; tenancy and policy guards extended |
| M7e-E3 | Delivery: `send_push` jobs, `WebPushPort`, generic text, expiry and retries | ✅ 12 Nov 2026: spec `web-push.md` R30–R38 (quiet hours included), `pywebpush` 2.5.0, settings `PUSH_PROVIDER`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`; 60 unit and 16 integration tests; checked on the local stack (held to 08:00 IST, then sent by the console adapter); design §8 |
| M7e-E4 | Appointment and follow-up reminders for app users | ✅ 13 Nov 2026: spec `web-push.md` R40–R46, migration `0044`, contract 0.53.0, status `SENT_IN_APP`; 7 integration, 3 domain, 1 migration and 1 web test; 6 journeys 10/10; design §8 |
| M7e-E5 | Settings, offline, docs, full suites and real-device checks | ✅ 13 Nov 2026: spec `web-push.md` R50–R57, `make vapid-keys`, service worker alerts, both settings screens; journey `push-settings`; Android checked on two phones (staff and patient alerts, Chrome and installed app, app closed), two fixes from it; iPhone check pending (none available) |

## M8 — Multi-clinic WhatsApp and consolidated billing  `☐ (designed)`

**Covers:** FR-BIL-WA-01..02 (PRD v1.1). **ADR:** 0014 (Proposed). **Design:**
`docs/milestones/M8-multi-clinic-whatsapp.md`. About 6 phases; needs L-08 for the live part.

## M9 — Pilot hardening and deployment  `▶`

**Covers:** NFR-03..07, NFR-16, FR-OPS-03. **Exit:** production deployed in India region; restore
drill completed; security checklist signed; two pilot clinics onboarded. (Was M6 before PRD v1.1.)
**Issue:** #75, branch `m9/75-deploy-demo`. **Design:** `docs/milestones/M9-deploy-demo.md`
(Google Cloud, one VM in Mumbai, approved 13 Nov 2026).

| Phase | Scope | Status |
|---|---|---|
| M9-P1 | Go live for the Phase 2 demo: C1 messaging `disabled`, C2 `make import-clinic` (CSV, bundled demo), C3 `infra/gcp/` compose override and Caddy (TLS on `mediease.duckdns.org`), C4 backups and the restore drill, C5 `make smoke-live`, C7 docs; secrets in an owner-only `.env` on the VM | ▶ ACTIVE — code done 13 Nov 2026; the VM deploy and live check next |
| M9-P2 | Backups, restore drill, uptime and error alerting | ☐ |
| M9-P3 | Security review against `docs/SECURITY_AND_COMPLIANCE.md` checklist; dependency scan; audited export and `scripts/erase_patient.py` procedures | ☐ |
| M9-P4 | Ops clinic-health view; usage metrics for the pilot scorecard | ☐ |
| M9-P5 | Pilot runbook rehearsal: onboard a test clinic end-to-end in < 60 min | ☐ |

---

## Backlog (post-pilot, ordered by evidence)

| ID | Item | Requirement | Evidence |
|---|---|---|---|
| — | Vaccination schedules and due-date reminders | FR-VAX | A3 |
| — | Broadcast announcements to patient groups | FR-BRD | A1 |
| — | Specialty templates | FR-TPL | A13 |
| — | Advanced search and filters | FR-PAT-07 | A11, A12 |
| — | Appointment reminders, SMS fallback on by default, patient live token link | FR-APT-08, FR-REM-06, FR-QUE-06 | — |
| — | Analytics dashboard | FR-ANL | — |
| — | Pharmacy and clinic drug inventory (PRD v1.1 C6) | — | Developer's request |
| — | Animated landing-page polish and demo rehearsal (moved out of M7, PRD v1.3 C15) | FR-LND | — |
| — | OCR of the printed verification code (Tesseract first), only if the pilot's "no identifier" rate shows a need (ADR-0023) | FR-UPL-03 | — |
| — | ABDM / ABHA integration | — | Open question (PRD §14.3) |

The public booking page moved into M6-P8 and billing into M8 (PRD v1.1).

---

## Completed

| Milestone / phase | Date | Commit |
|---|---|---|
| Planning pack (PRD, agent files, architecture, ADRs) | 15 Sep 2026 | — |
| M0 implementation plan approved; workflow and commit standards adopted (ADR-0010) | 1 Oct 2026 | #4 / PR #5 |
| M0-P1 — local database stack verified; `.gitattributes` and `CODEOWNERS` added | 1 Oct 2026 | #6 |
| M0-P2 — API package, typed settings, JSON logging, request IDs, error envelope, `/health` | 2 Oct 2026 | #8 / PR #9 |
| M0-P3 — `/ready`, Alembic baseline, minimal API Dockerfile, compose `migrate` + `api` | 2 Oct 2026 | #10 / PR #11 |
| M0-P4 — Next.js shell, generated API client, `/status`, nonce CSP and security headers | 2 Oct 2026 | #12 / PR #13 |
| M0-P5 — hardened images, web container, full compose, CI gates (images, smoke, security, boundaries, coverage) | 2 Oct 2026 | #14 |
| **M0 — Foundation** (exit criteria met: fresh clone → `make up` → all healthy; CI green) | 2 Oct 2026 | #6, #8, #10, #12, #14 |
| M1 — Identity, tenancy and audit (merged in PR #20) | 3 Oct 2026 | #19 |
| **M2 — Patients** (exit criteria met: register, find and update patients; shared phones surfaced; 10,000-patient lookup p95 well under 500 ms) | 17 Oct 2026 | #21 / PR #22 |
| **M5 — Messaging and reminders** (code complete and verified against the console provider and a fake Graph API; closed by the developer with the live WhatsApp test pending L-01/L-02 and the real SMS provider pending L-03) | 20 Oct 2026 | #40 / PR #41 |
