# M7c-P7 — Module redesign: final report (10 Nov 2026)

Branch `m7c/69-demo-polish`, issue #69. Nothing pushed. Module details: `M7c-P7-modules.md`.
Parked work and backlog: `M7d-discovery-booking.md`.

## What was done

| Module | Commit | Gate (lint, typecheck, contract, web suite, full API suite, smoke) |
|---|---|---|
| Phase 1 design system, M1 landing, M2 auth | earlier commits (9 Nov) | passed |
| M3 Clinic dashboard | `fa39f4b`, follow-up `0151fd7` | passed (follow-up covered by the M9/M10 gates) |
| M4 Appointments and queue | `9d2a599`, `07929de` | passed |
| M5 Patient management | `32e5376` | passed |
| M6 Appointment booking | `b96ba79` | passed |
| M7d parked as its own milestone | `8bb94f6` | docs only |
| M7 Patient portal | `3c320a8` | passed: web 89 files, API 2,573 passed at 96.05%, smoke |
| M8 Consultation and prescription pages | `63529a7` | passed: web 89, API 2,573 at 96.05%, smoke |
| M9 AI assistant | `c9216e5` | passed on the M9 tree: web 89, API 2,573 at 96.05%, smoke |
| M10 Billing | `f2307b1` | API 2,573 at 96.04% and smoke passed; the web suite had one timing flake, fixed in `22f0c7a`; a rerun found a second, fixed in `aecdcf4`; then web 89 of 89 |
| Landing weight | `1cd927d` | discovery journey: `/` 204,447 of 204,800 bytes |

No API, schema, contract or backend file changed in M7–M10.

## Full `make e2e` (once, at the end)

**57 of 57 journeys passed** (7.2 min) on a fresh local database, which the developer allowed
to be reset this once (RUNBOOK §1: `mediease_pgdata` removed, `make up`, `make seed`). The API
and workers ran with the CI settings for that run (fake Google sign-in, console LLM, mail into
Mailpit) and were then restarted on `.env`.

Before the reset, a run had 21 failures, none caused by the redesign:

- 16 came from data left by earlier runs: the running session was full, and no free evening
  was left for the "lonely session" helper.
- 4 email journeys failed because `.env` sends real email (M7c-P6) instead of Mailpit.
- 1 was real: `/` reached 206,003 bytes. The shared CSS had grown, and the fix is `1cd927d`.

The run before it also caught an M3 regression: the doctor's name was missing from Today in the
doctor's own view (FR-UX-06). That is fixed in `0151fd7`.

## Page weights (first load at 360 px, NFR-02, budget 200 KB)

`/` 199.7 KB, `/find` 166.6 KB, `/portal` 189–194 KB, other portal tabs 185–194 KB,
`/portal/assistant` 189.8 KB, `/p/<token>` 160.7 KB. The landing page has about 0.3 KB of
headroom, so any landing change must be measured first.

## Design rules applied throughout

DESIGN.md tokens and components only; Lucide icons as decoration with unchanged accessible
names. Patient pages keep the system font, use no Motion library and stay within 200 KB. No
sideways scroll at 320–1440 px (checked by the overflow audit on every screen). Buttons stay
enabled and say what is missing (§8a). Only "in flight" and "unverified email" still disable a
button. Axe runs in the journeys, and it caught two real issues, both fixed: a link whose name
did not match its visible text, and a scroll region that was not focusable.

## Waiting for the developer

1. **M7d** (`M7d-discovery-booking.md`): the four decisions to confirm, then the build (about
   5–6 h).
2. **Backlog B1**: the PDF's layout 4 with the MediEase emblem. It is an API change.
3. **Backlog B2**: patient-page weight headroom.
4. **WhatsApp**: Meta still refuses sends (`OAuthException code 10`). The token's permission is
   a Meta Business setting (M7c-P6).
5. The root `public/branding/` folder can be deleted (the logo now lives in
   `apps/web/public/brand/`).
6. Push and PR: only with your permission (ADR-0011).
