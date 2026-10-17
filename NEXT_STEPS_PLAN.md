# NEXT_STEPS_PLAN.md — Approved plan for M3 (Appointments and daily queue)

| Field | Value |
|---|---|
| Status | M3 spec approved by the developer on 17 Oct 2026 (D1–D9); M3-P1 done and confirmed the same day (draft PR #37); M3-P2 approved (1A–7A, D10–D16) and in implementation |
| Scope | Milestone 3 in phase detail; M4–M6 as a roadmap only. Earlier plans are in git history: M0 (PRs #5–#15), M1 (PR #20), M2 (PR #22, merged 17 Oct 2026) |
| Live status | `TASKS.md` is authoritative for what is active. This plan is updated in the same PR as any change to scope, order or approach |
| Design notes | `docs/milestones/M3-appointments-and-queue.md` |
| Workflow rules | `CLAUDE.md` → "Git Workflow"; `CONTRIBUTING.md`; ADR-0010, ADR-0011 |

---

## 1. Problem statement

M2 gave clinics a patient registry. M3 lets them run their day: doctors' weekly schedules and
exceptions become bookable sessions in the clinic's own time zone, in either slot or token mode;
front desk books without double-booking (FR-APT-04); and every screen sees the same live queue
(FR-QUE). Seven of fourteen Phase 1 clinics coordinate this over WhatsApp and phone today
(PRD §2.2, P1).

## 2. Requirements

- Spec: `docs/specs/appointments-and-queue.md` (Approved 17 Oct 2026 with D1–D9). Its acceptance
  criteria AC1–AC6 become tests in the phase that implements them.
- **M3 exit:** front desk books in ≤ 3 interactions; the concurrent double-booking test passes;
  the queue refreshes on every open screen within 5 s.
- Follow `CLAUDE.md`: one phase at a time, design approved before code, `make lint typecheck test`
  green and the developer's confirmation before the next phase.
- Coverage gates stay: ≥ 90% API package, ≥ 80% `domain/` + `application/` (NFR-14).
- Local resources: the WSL VM runs at its 8 GB limit; run `make down` whenever the stack is idle.

## 3. Delivery workflow (ADR-0011)

```
Milestone issue #36 → branch m3/36-appointments-and-queue (from origin/main)
  → per phase: design → approval → logical commits → make lint typecheck test
    → developer confirms → push (with permission) to the same branch
  → one PR for the milestone: draft until P5 is done and the exit criteria hold
  → CI green → review + CODEOWNERS approval → maintainer rebase-merges
```

- Every commit has a Conventional Commits subject, a body (what + why) and `Refs #36`; the last
  commit of M3 carries `Closes #36`.
- Agents never push to `main`, push to the milestone branch only with permission, and never merge.

### 3.1 Open prerequisites

| # | Needed | State |
|---|---|---|
| W-5 | Branch protection / CODEOWNERS enforcement on `main` | **Open:** not available for a private repo on GitHub Free (HTTP 403). Needs GitHub Pro/Team or a public repo |
| — | `@akhtarjamal10` write access, so their CODEOWNERS entry takes effect | Open |
| — | #30: an import over 2 MB through the web origin can answer 500 instead of 413 | Open; outside M3 |

## 4. Phase breakdown

Details, file lists and test plans per phase are in the design notes. Each phase is designed with
`/plan-phase` at its start; P1 is designed in full now.

| Phase | Objective | Requirements | Verify |
|---|---|---|---|
| P1 | Weekly schedules (overnight blocks up to 12 h), whole-day leave and extra sessions, sessions generated lazily per clinic-local date, slot and token mode, `SCHEDULES_MANAGE`, migration `0007` | FR-APT-01, 02; spec R1–R4, R14–R20; AC5 | `make lint typecheck test`; sessions for a date generated once under concurrency; 13:00–10:00 refused, 23:00–01:00 accepted; cross-midnight overlap refused; leave keeps booked sessions |
| P2 | Booking, reschedule and cancel under a session row lock; capacity and slot checks; status history and audit | FR-APT-03, 04, 05, 07; spec R5–R8; AC1, AC2 | Two parallel bookings for one place: one 201, one 409 |
| P3 | Queue state machine and transitions; walk-ins | FR-QUE-01, 02, 04, 05; spec R9–R11, R13; AC3 | Invalid transition 409 `QUE_INVALID_TRANSITION` |
| P4 | Live queue with ETag polling | FR-QUE-03; spec R12; AC4 | Two browsers see a change within 5 s; 304 when unchanged |
| P5 | Web: today's queue board, booking flow, schedule settings; the booking journey in Playwright | FR-APT-03, FR-QUE-01; spec §6; AC6 | Booking in ≤ 3 interactions in `make e2e` |

## 5. Roadmap after M3 (one line each)

- **M4 Visits and prescriptions** — immutable versioned Rx, PDF, signed patient links, bilingual
  360-px page.
- **M5 Messaging and reminders** — job table + worker, WhatsApp adapter + webhooks, reminder rules,
  STOP opt-out.
- **M6 Pilot hardening** — India-region deployment, backups + restore drill, security review,
  two pilot clinics.
## 6. Parallel non-code track

L-01 (Meta Business + WhatsApp number) and L-02 (template approval) are on the critical path for
M5; L-03, L-05 and L-07 should be under way. Details in `TASKS.md`.

## 7. Progress log

| Date | Task | Issue / PR | State |
|---|---|---|---|
| 1–2 Oct 2026 | M0 — Foundation (Tasks 0–6: workflow, db stack, API settings/logging/health, readiness + migrations, web shell, hardened images + CI) | #4–#14 / PRs #5, #7, #9, #11, #13, #15 | Merged; exit criteria met |
| 2 Oct 2026 | Workflow change: one issue, branch and PR per milestone (ADR-0011) | #19 | Committed on `m1/19-identity-tenancy-audit` |
| 2 Oct 2026 | `identity-and-tenancy.md` Approved; M1 plan and design notes | #19 | Committed on `m1/19-identity-tenancy-audit` |
| 2 Oct 2026 | M1-P1 — domain model, ports, UUIDv7, migration `0002`, tenancy-scoped repositories + unit of work, core coverage gate. `make lint typecheck test` green (API 166 tests, package 98%, core 100%); `make up` applies `0002` | #19 / PR #20 | Done; confirmed by the developer 3 Oct 2026 |
| 3 Oct 2026 | M1-P2 design (sign-in, refresh rotation, sign-out, lockout) approved | #19 / PR #20 | Done |
| 3 Oct 2026 | M1-P2 — Argon2id, JWT access + rotating refresh tokens with family revocation, CSRF double submit, lockout, migration `0003`, auth endpoints + contract, `make seed`. `make lint typecheck test` green (API 275 tests, package 99%, core 100%; web 32); on compose: `0003` applied, seed, curl sign-in by email and phone 200, AC1 423 + `Retry-After`, AC2 replay 401 `AUTH_REFRESH_REUSED` and newer token 401, sign-out 204 | #19 / PR #20 | Done; confirmed by the developer 3 Oct 2026 (sign-in on their machine: 200, cookie flags as designed) |
| 3 Oct 2026 | M1-P3 design (authorisation on every route) proposed | #19 / PR #20 | Approved by the developer 3 Oct 2026 |
| 3 Oct 2026 | M1-P3 — access policy on every route (default deny, start-up check), per-request re-check of session/user/membership, clinic resolution with `X-Clinic-ID`, PRD §8.1 permission matrix as domain data, `GET /api/v1/me` and read-only clinic/doctors/staff endpoints, contract 0.3.0 + regenerated web types, HTTP tenancy suite with a cross-clinic guard. `make lint typecheck test` green (API 389 tests, package 99%, core 99%; web 32); on compose with `make seed`: desk `/me` 200 and `/clinic/staff` 403 `PERM_DENIED`, owner `/clinic/staff` 200, own doctor 200 and another clinic's doctor 404 `REQ_NOT_FOUND`, ops `/me` 200 but `/clinic` 403, anonymous 401, and the old `me_access` after sign-out 401. Pushed to `m1/19-identity-tenancy-audit`; CI green (7/7 jobs); PR #20 body updated | #19 / PR #20 | Implemented; awaiting the developer's confirmation |
| 3 Oct 2026 | M1-P4 design (append-only audit log in the same transaction, database-enforced immutability, `v_clinic_activity`) proposed, with one open choice: whether the staff role change moves into P4 so AC5 is proved there (recommended) or stays in P5 | #19 / PR #20 | Approved by the developer 3 Oct 2026, option B (role change in P4) |
| 3 Oct 2026 | M1-P4 — `audit_events` + migration `0004` with two triggers that refuse UPDATE/DELETE/TRUNCATE (AC6), `AuditWriter` on the unit of work so a change is never unaudited (R11), session events + the audited `PATCH /clinic/staff/{id}` role change (AC5), `AUDIT_IP_SALT` and HMAC IP fingerprints, `v_clinic_activity`, contract 0.4.0 + regenerated web types, RUNBOOK §18. `make lint typecheck test` green (API 452 tests, package 99%, core 99%; web 32); on compose: four audit rows with the expected actors, clinics and request IDs, `UPDATE`/`DELETE`/`TRUNCATE` all refused with `AUD_APPEND_ONLY`, `v_clinic_activity` correct after the role change, last-owner demotion 409. Pushed; CI green (7/7) | #19 / PR #20 | Implemented; awaiting the developer's confirmation |
| 3 Oct 2026 | M1-P5 design (ops onboarding, single-use staff invites and acceptance, owner staff and doctor management, onboarding checklist) proposed, with two open choices: whether to keep P5 as one phase or split it into P5a (ops + invites) and P5b (owner management), and whether membership reactivation is in scope | #19 / PR #20 | Approved by the developer 3 Oct 2026: option A (one phase), reactivation out of M1 |
| 3 Oct 2026 | M1-P5 — migration `0005` (invitation columns on `clinic_memberships`, `onboarding_checklists`), invitations as the `INVITED` membership plus a single-use digest, public describe/accept endpoints, the ops console API, owner staff and doctor management, clinic settings, eight new audit actions, contract 0.5.0 + regenerated web types, RUNBOOK §10 rewritten with the real commands. `make lint typecheck test` green (API 545 tests, package 99%, core 99%; web 32) | #19 / PR #20 | Implemented; awaiting the developer's confirmation |
| 3 Oct 2026 | CI fix: the web `npm audit` gate failed on PR #31 because braces (GHSA-vfj7-8cjw-p6xm, no patched version, reachable only through dev-only `eslint-config-next`) is flagged. The blocking step now audits production dependencies (`--omit=dev`, 0 vulnerabilities); the full-tree audit stays as a non-blocking step. Replicated all seven CI jobs locally before pushing | #19 / PR #31 | Pushed (`8ece890`); approved by the developer, option 2 |
| 3 Oct 2026 | M1-P6 design (web sign-in, clinic switcher, empty dashboard shell) proposed, with three open choices: an invitation acceptance page, the scope of the ops console UI, and a second seeded clinic | #19 | Approved by the developer 3 Oct 2026: 1A (invitation page in P6), 2A (`/ops` placeholder, wizard planned separately), 3A (second seeded clinic) |
| 3 Oct 2026 | M1-P6 — `make seed` adds `sample-clinic-two` (idempotent per clinic); API client with POST, CSRF, `X-Clinic-ID`, 204 and `Retry-After`; refresh shared per tab and under a Web Lock; `SessionProvider`, landing rules and clinic choice; sign-in and invitation forms; dashboard shell with switcher, no-access, suspended and empty-queue states; `/ops` placeholder; proxy redirect for visitors without `me_csrf`; smoke checks. `make lint typecheck test` green (API 548 tests, package 98.9%; web 21 files, 209 tests; `tsc`, ESLint and `next build` clean, `gen:api:check` clean); `make smoke` passes with the new checks; on compose through the web origin: two-clinic doctor sign-in, `/clinic` 400 without and 200 with `X-Clinic-ID`, sign-out 204 then `/me` 401, `/queue` 307 without the cookie. Found and recorded: the invite-accept endpoint overwrites an existing account's password (TASKS "Open decisions") | #19 | Implemented; awaiting the developer's confirmation and the browser walk-through |
| 3 Oct 2026 | M1-P6 confirmed by the developer's own browser walk-through: sign-in, a wrong password, the 15-minute lockout after five attempts while other accounts still sign in, the two-clinic switch, and every role's routes including ops | #19 | Confirmed |
| 3 Oct 2026 | Security fix to M1-P5 found during P6: accepting an invitation for an existing account now needs that account's current password and never changes it (spec R13, contract 0.5.1, `security(invites)`); regression test for the takeover, lockout shared with sign-in, rejoin with no active membership | #19 | Implemented; API 554 tests, package 99.0% |
| 3 Oct 2026 | M1-P7 (ops clinics list and the Create clinic wizard) added to M1 at the developer's direction; design in the notes, implemented the same day, web only | #19 | Implemented |
| 3 Oct 2026 | M1 merged by the maintainer (PR #20) and M1-P3 to P7 confirmed by the developer. M2 opened: issue #21, branch `m2/21-patients` from the new `origin/main`; the patients spec approved on decisions D1–D6 (the contact of record for a minor is the guardian's phone) | #21 | M2 active |
| 3 Oct 2026 | M2-P1 - patient domain, clinic code counter, migration `0006`, tenancy-scoped repository, lookup indexes, the 10,000-patient lookup test and the code-allocation concurrency test. Design in `docs/milestones/M2-patients.md`. `make lint typecheck test` equivalents green in WSL (API 663 tests, package coverage 99.1%) | #21 | Implemented; awaiting the developer's confirmation |
| 3 Oct 2026 | M2-P1 confirmed by the developer; branch pushed and draft PR #22 opened. M2-P2 design (register, edit, lookup, the duplicate-phone flow, the code prefix on clinic creation) proposed | #21 / PR #22 | Awaiting the developer's approval of the design |
| 3 Oct 2026 | M2-P2 design approved by the developer. Implemented: four patient endpoints, race-free registration (clinic row locked first), the duplicate-phone 409 with candidates, audit without personal data, clinic-local ages, `patient_code_prefix`, contract 0.6.0 + regenerated web types, seed patients. `make lint typecheck test` equivalents green in WSL (API 723 tests, package coverage 99.0%; web 25 files / 256 tests, tsc and ESLint clean); the two-thread race, 30 parallel registrations and the no-PII-in-logs test pass; on compose through the web origin: lookup by phone, code and name, duplicate 409, `confirm_new` takes the next code, minor without guardian 422, ops 403, audit rows hold codes and field names only | #21 / PR #22 | Implemented; awaiting the developer's confirmation |
| 3 Oct 2026 | M2-P2 confirmed by the developer (tried on their machine) and pushed to PR #22. M2-P3 design (consent, opt-out and opt-in as separate actions, row lock, audit as evidence, one open choice on consent edits while opted out) proposed | #21 / PR #22 | Awaiting the developer's approval of the design |
| 3 Oct 2026 | M2-P3 design approved with option A. Implemented: consent, opt-out and opt-in as three actions, row lock, audit as evidence, `whatsapp_allowed`/`sms_allowed`, contract 0.7.0 + regenerated web types. Added test and CI timeouts after a hung test. API 754 tests at 99.0%, web 256 tests, tsc/ESLint/`gen:api:check` clean, `pip-audit` clean; on compose the whole consent story and its audit rows behave as designed | #21 / PR #22 | Implemented; awaiting the developer's confirmation |
| 5 Oct 2026 | M2-P3 re-checked on `e9c5cb9` (`make lint typecheck test`: API 754 at 99.03%, web 256; `make smoke`; the consent flow on compose; CI 7/7) and confirmed by the developer. M2-P4 design (ops CSV import, dry run by default, report without personal data) approved with 1A (phone-only duplicates imported and flagged) and 2A (blank sex is `UNDISCLOSED`) | #21 / PR #22 | P3 confirmed; P4 in implementation |
| 5 Oct 2026 | M2-P4 — `POST /api/v1/ops/clinics/{id}/patient-imports` (raw `text/csv`, 2 MB / 5,000 rows, dry run by default), the report without personal data, the commit under the clinic lock with one `patient.imported` row each, batched inserts (`add_many`, `record_many`; 5,000 rows in under 2 s), contract 0.8.0 + regenerated web types, RUNBOOK §10 procedure and a synthetic sample file. `make lint typecheck test` green (API 847 tests at 99.09%, core 99%; web 256); `make smoke`; the import flow on the rebuilt compose stack as designed | #21 / PR #22 | Implemented; awaiting the developer's confirmation |
| 17 Oct 2026 | M2-P4 re-checked on a fresh machine (WSL Python 3.12 + Node 24; stack via Docker Desktop's CLI): `make lint typecheck test` (API 847 at 99.09%, core 99%; web 256; `gen:api:check`), `make smoke` 22/22, the import flow as designed, audit rows and logs free of names and phones. Confirmed by the developer. Finding: one 2.2 MB upload through the web origin answered 500 (proxy EPIPE) instead of 413; 22 repeats answered 413 (P5 design, decision 5) | #21 / PR #22 | P4 confirmed |
| 17 Oct 2026 | Dependabot #18 (TypeScript 7) and #28 (ESLint 10) closed with "ignore this major version"; `typescript`, `eslint` and `@types/node` majors ignored in `.github/dependabot.yml` (`dc242c1`). Documentation drift fixed in one `docs:` commit (`4f16cab`). `main`'s secrets scan stays red until PR #22 lands `b994ed3` (the developer's choice) | #21 | Committed locally |
| 17 Oct 2026 | M2-P5 design (web search combobox, registration drawer with the duplicate-phone flow, profile with consent and opt-out, PATCH/PUT in the API client, the wizard's code prefix) proposed with decisions 1–6, including the first Playwright spec for the duplicate-phone journey (4B recommended) | #21 / PR #22 | Awaiting the developer's approval |
| 17 Oct 2026 | M2-P5 approved with every recommendation (1A–6A, 4B) and implemented: header patient search, results page, registration drawer with the duplicate-phone flow, profile with edit, consent, opt-out and opt-in, the wizard's code prefix, PUT/PATCH in the web client, the first Playwright journey (`make e2e`, CI `smoke` job). `make lint typecheck test` green (API 847 at 99.09%; web 314), `make smoke` 24/24, the journey 3/3 in Chromium. Follow-up #30 opened for the 413-through-proxy finding. **M2 complete**; PR #22 marked ready for review | #21 / PR #22 | Done; awaiting review and the maintainer's merge |
| 17 Oct 2026 | M2 rebase-merged by the maintainer (PR #22); `main`'s CI green again (the gitleaks fingerprint). M3 opened: issue #36, branch `m3/36-appointments-and-queue` from the new `origin/main`; `appointments-and-queue.md` Approved with D1–D9; M3-P1 design approved with 1A–6A and the developer's refinements (12-hour maximum block, cross-day overlap, leave on generated dates) | #36 | M3-P1 in implementation |
| 17 Oct 2026 | M3-P1 — weekly blocks (12-hour bound, overlap across midnight and the week), whole-day leave and extra sessions, lazy idempotent session generation in slot or token mode, reconciliation that keeps booked sessions, `SCHEDULES_MANAGE` and the ops schedule route, booking-mode change guard, migration `0007`, contract 0.9.0, seeded schedules. `make lint typecheck test` green (API 911 at 99.08%, core 99%; web 314), `make smoke`, the verify steps on the rebuilt stack as designed | #36 | Confirmed by the developer; pushed, draft PR #37 |
| 17 Oct 2026 | M3-P2 designed and approved by the developer with 1A–7A (spec D10–D16): booking under a session row lock, cancel with a reason, reschedule as cancel + book, closed and adjusted kept sessions, confirmation job deferred to M5 | #36 | Done; accepted by the developer |
| 17 Oct 2026 | M3-P2 — booking in slot or token mode under a session row lock, cancel with a reason, reschedule as cancel + book, status history, closed / resized / retired sessions, migration `0008`, contract 0.10.0. `make lint typecheck test` green (API 967 at 99.11%; web clean), `make smoke`, the verify steps on the rebuilt stack as designed | #36 | Done; accepted by the developer. M3-P3 designed next |
| 17 Oct 2026 | M3-P3 designed; the developer approved the recommended options in advance (spec D17–D22): `{from, to}` transitions on the session's day, walk-ins arrive at once, the queue read without caching (ETag in P4) | #36 | Implemented |
| 17 Oct 2026 | M3-P3 — transitions `{from, to}` on the session's day, walk-ins arrived at once, `GET /api/v1/queue`, contract 0.11.0. `make lint typecheck test` green (API 1024 at 98.94%), `make smoke`, the verify steps on the stack as designed | #36 | Implemented; awaiting the developer's confirmation |
