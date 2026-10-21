# TASKS.md — Delivery Plan and Live Status

The single place that says **what is being worked on now**. Agents work only on the phase marked
`▶ ACTIVE`. Update this file at the end of every phase.

Legend: `▶ ACTIVE` · `☐ todo` · `✅ done` · `⏸ blocked` · Requirement IDs refer to `docs/PRD.md`.

---

## Current focus

| Field | Value |
|---|---|
| Active milestone | **M6 — MVP demo: clinic and patient experience** (issue #49, branch `m6/49-mvp-demo`, one PR for the milestone). M5 merged in PR #41 on 20 Oct 2026. Product rules changed to PRD v1.1 the same day |
| Active phase | **M6-P2 — The design system across the existing screens:** designed (`docs/milestones/M6-mvp-demo.md`), awaiting the developer's approval. M6-P1 confirmed 20 Oct 2026 and pushed (draft PR #50) |
| Design notes | `docs/milestones/M6-mvp-demo.md`; M8 already designed in `docs/milestones/M8-multi-clinic-whatsapp.md` |
| Approved plan | `NEXT_STEPS_PLAN.md` (M6 phases, workflow, progress log) |
| Workflow | One issue, one branch, one PR per milestone; phases land as logical commits on that branch; PR is a draft until the milestone is done → CODEOWNERS review → maintainer merge (ADR-0010, ADR-0011) |
| Blockers | W-5: branch protection / CODEOWNERS enforcement on `main` not available on the current GitHub plan (`NEXT_STEPS_PLAN.md` §3.1). `@akhtarjamal10` needs write access before their CODEOWNERS entry takes effect |
| Open decisions | M6-P2 design (8 decisions). Deployment and hosting are skipped for now (developer, 20 Oct 2026). Pending from M5: the live WhatsApp test (L-01, L-02; RUNBOOK §9) and the real SMS provider (L-03). For M8: the BSP partner (L-08). Outside the milestones: #30 (an import over 2 MB through the web origin can answer 500 instead of 413); the M4-P3 suggestions timing test is flaky on CI (150 ms bound) |
| Last updated | 20 Oct 2026 |


---

## Long-lead track (non-code, start now)

These take days to weeks outside our control. They run in parallel with engineering and must be
done before the pilot.

| ID | Task | Owner | Needed by | Status |
|---|---|---|---|---|
| L-01 | Create Meta Business account, verify business, register WhatsApp number | Founder | M5 | ☐ |
| L-02 | Draft and submit utility templates (booking confirmation, prescription ready, prescription updated, follow-up due) in English and Hindi | Product | M5 | ☐ |
| L-03 | SMS provider account + DLT registration (entity, sender ID, templates) | Founder | M5 | ☐ |
| L-04 | Counsel review: DPDP roles, clinic–MediEase data processing agreement, patient notice template, prescription format | Founder | M6 | ☐ |
| L-05 | Choose India-region hosting account; enable billing alerts | Engineering | M6 | ☐ |
| L-06 | Book pilot conversations with Aarogya Hospital (A13), Apollo Diagnostic (A10); Arvind Homoeopathy (A1) as reserve | Founder | M6 | ☐ |
| L-07 | Collect each pilot clinic's current booking flow, Rx format and patient list format | Product | M4 | ☐ |
| L-08 | Choose a WhatsApp BSP with a partner-paid (wholesale) model; MediEase's business verification and website for the partnership (ADR-0014) | Founder | M8 | ☐ |
| L-09 | A Google Cloud OAuth client (free) for Google sign-in, with the local redirect URI | Founder | M6-P3 | ☐ |
| L-10 | A Groq API key (free tier) for the assistant | Founder | M7 | ☐ |

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

## M6 — MVP demo: clinic and patient experience  `▶ ACTIVE`

**Covers:** FR-AUTH-07, FR-PRT-01..04, FR-REM-03, FR-NTF-01, FR-PUB-01..04 (PRD v1.1). **Issue:**
#49, one branch and one PR for all phases (ADR-0011). **Exit:** on the local stack each role lands
on its own dashboard; a patient signs in with Google or email, links a clinic record by invite or
prescription link, and sees appointments, prescriptions, reminders and a medicine plan;
notifications arrive in the app; a public booking request is confirmed by the front desk;
`make e2e` green. Deployment and hosting are out of scope (developer, 20 Oct 2026).

| Phase | Scope | Status |
|---|---|---|
| M6-P1 | Design system (tokens, primitives, Motion, responsive shell); *Today* dashboards for front desk, doctor and owner | ✅ (confirmed 20 Oct 2026; PR #50) |
| M6-P2 | The design system across the existing screens; mobile layouts; motion for drawers, dialogs and lists | ▶ (designed, awaiting approval) |
| M6-P3 | Google sign-in for staff and patients; patient email and password; separate patient sessions | ☐ |
| M6-P4 | Linking a patient account by clinic invite or prescription link; the patient API | ☐ |
| M6-P5 | Patient portal web (mobile-first, English and Hindi) | ☐ |
| M6-P6 | Medicine planner (FR-REM-03) | ☐ |
| M6-P7 | In-app notifications for patients and staff (FR-NTF-01) | ☐ |
| M6-P8 | Public booking page and booking requests (FR-PUB) | ☐ |

## M7 — AI assistant and pitch  `☐`

**Covers:** FR-AI-01..03 (PRD v1.1). **ADR:** 0013. **Exit:** booking by chat works through tools
with a confirmation step; the guard-rail tests (no medical advice) pass; the provider switches by
settings only; the animated landing page tells the story. About 5 phases: the LLM gateway (Groq
first), tools and guard rails, the patient assistant, the staff assistant, the landing page and
demo rehearsal.

## M8 — Multi-clinic WhatsApp and consolidated billing  `☐ (designed)`

**Covers:** FR-BIL-WA-01..02 (PRD v1.1). **ADR:** 0014 (Proposed). **Design:**
`docs/milestones/M8-multi-clinic-whatsapp.md`. About 6 phases; needs L-08 for the live part.

## M9 — Pilot hardening and deployment  `☐`

**Covers:** NFR-03..07, NFR-16, FR-OPS-03. **Exit:** production deployed in India region; restore
drill completed; security checklist signed; two pilot clinics onboarded. (Was M6 before PRD v1.1.)

| Phase | Scope | Status |
|---|---|---|
| M9-P1 | Production compose/infra in `infra/`, TLS, domain, secrets management | ☐ |
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
