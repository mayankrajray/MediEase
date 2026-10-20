# M6 — MVP demo: clinic and patient experience: design notes

| Field | Value |
|---|---|
| Status | Opened 20 Oct 2026 (issue #49, branch `m6/49-mvp-demo`); plan approved by the developer (items D2–D5 of the demo plan); M6-P1 approved 20 Oct 2026 (A on all six, decision 2 amended), built and verified locally; awaiting the developer's confirmation |
| PRD | v1.1 §0 (C1–C3), §8.13 |
| ADR | ADR-0013 (for M7), ADR-0014 (for M8); patient accounts and Google sign-in get an ADR in P3 |
| Covers | FR-AUTH-07, FR-PRT-01..04, FR-REM-03, FR-NTF-01, FR-PUB-01..04 |
| Issue / branch / PR | #49 · `m6/49-mvp-demo` · one PR for the milestone (ADR-0011) |
| Exit criterion | On the local stack: each role lands on its own dashboard; a patient signs in with Google or email, links a clinic record by invite or prescription link, and sees appointments, prescriptions, reminders and a medicine plan; notifications arrive in the app; a public booking request is confirmed by the front desk; `make e2e` green |
| Out of scope | Deployment and hosting; the AI assistant (M7); per-clinic WhatsApp and billing (M8, designed); pilot hardening (M9) |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Design system (tokens, primitives, Motion, responsive shell) and the role dashboards' first screen: *Today* for front desk, doctor and owner | Below (approved) |
| P2 | The design system across the existing screens (queue, patients, consultation, schedule, follow-ups, ops); mobile layouts; motion for drawers, dialogs and list changes | At its start |
| P3 | Accounts: Google sign-in for staff and patients, patient email and password, patient sessions kept apart from staff sessions (ADR) | At its start |
| P4 | Linking a patient account to a clinic's record by clinic invite or prescription link; the patient API (appointments, prescriptions, reminders, per clinic) | At its start |
| P5 | Patient portal web: mobile-first, English and Hindi, with Motion | At its start |
| P6 | Medicine planner (FR-REM-03): a dose schedule derived only from the prescribed lines | At its start |
| P7 | In-app notifications for patients and staff (FR-NTF-01) | At its start |
| P8 | Public booking page and booking requests (FR-PUB-01..04) | At its start |

---

## M6-P1 — Design system and the *Today* dashboards

Proposed 20 Oct 2026. Recommendations are marked (rec).

**Approved 20 Oct 2026: A on all six, with decision 2 amended by the developer.** "I would not
switch wholesale to shadcn just because it's popular. Build your small MediEase design system
yourself and selectively use shadcn/headless primitives where accessibility and interaction
complexity justify them." So the primitives stay ours, and a headless primitive is adopted one
component at a time, only where its keyboard and screen-reader behaviour is worth not
re-implementing. P1 adopts one: `@radix-ui/react-tabs` 1.2.1 (the primitive shadcn/ui's Tabs
wraps) behind our `components/ui/Tabs`, for roving focus, arrow, Home and End keys and the
tab/tabpanel wiring. Everything else in P1 is plain markup (cards, tiles, badges), and the
mobile menu reuses our native-`<dialog>` `Drawer`, which already gives focus trapping, an inert
page and Escape for free. Each later adoption (for example a combobox or a toast) is named in
its phase's design.

Facts the design rests on:

- **Styling today.** The web uses Tailwind 4 with no theme: plain slate and blue, one
  `globals.css`, no shared UI components beyond `Drawer` and `Dialog`. The header nav does not
  adapt to phones.
- **Landing.** After sign-in a clinic member lands on `/queue`; ops land on `/ops`.
- **No summary data.** There is no summary endpoint. The queue (`GET /api/v1/queue`), pending
  follow-ups and message health exist separately.
- **Patient pages.** They have a 200 KB budget (NFR-02), so any animation library must stay off
  `/p/…`.
- **Motion.** Motion (formerly Framer Motion) is `motion` 14.4.0 on npm, for React 18 and 19,
  imported from `motion/react`.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Look | Minimal and calm. Tokens go in Tailwind 4's `@theme`: one brand colour (teal) with neutral slate, one accent per status, 8 px rhythm, rounded cards, a soft shadow and the system font stack (Devanagari renders with the phone's own font; nothing is downloaded). Status always appears in words as well as colour | B: a web font such as Inter (adds a download and a build-time fetch; can be added later) |
| 2 | Components | Small primitives in `components/ui/`: `Button`, `Card`, `StatTile`, `StatusBadge`, `PageHeader`, `EmptyState`, `Skeleton`, `Tabs`. P1 uses them on the new screens; P2 moves the old ones over | B: a component library such as shadcn/ui (many files to own, and it duplicates our `Drawer` and `Dialog`) |
| 3 | Motion | `motion` 14.4.0, pinned, through `LazyMotion` and `m` so only the features used are loaded. `MotionConfig reducedMotion="user"` honours the system setting. Used in clinic, ops and (P5) portal screens, never on `/p/…` | B: CSS transitions only (no shared or list animation; less of the "slide" feel asked for) |
| 4 | Shell | Responsive: a left sidebar from 1024 px, a top bar with a menu drawer below that, the same `NAV_ITEMS` and permission filter, a *Today* entry first | B: keep the header nav (breaks on a 360 px phone) |
| 5 | Data for *Today* | One endpoint, `GET /api/v1/dashboard/today` (contract 0.22.0): counts only, computed in SQL in the clinic's zone, shaped by role. **Front desk** sees today's booked, waiting, in consultation, done and no-shows, the next three tokens or slots (code, first name, time), pending follow-ups and today's failed messages. **Doctor** sees their own sessions, the next patient and their counts. **Owner** sees the clinic counts plus a 7-day strip (visits, no-show rate, messages sent). `CLINIC_VIEW`; the owner strip needs `USAGE_METRICS_VIEW`. No clinical text | B: build *Today* in the browser from `/queue` and others (several calls, no 7-day view, slower on phones) |
| 6 | Landing | Clinic members land on `/today`; *Queue* stays a click away and keeps its URL. Each tile links to the screen it summarises | B: keep `/queue` as the landing (the dashboard would be easy to miss) |

Fixed points:

- **Screens.** Responsive from 360 px; WCAG 2.1 AA.
- **Loading and errors.** Every load has a skeleton, an error with the `Ref` and *Try again*.
- **Refresh.** The numbers refresh with the queue's 5-second rhythm while the tab is visible,
  using the ETag pattern of `/queue`.
- **Contract.** The endpoint goes in `contracts/openapi.yaml` with generated types.
- **Tests.**
  - API: tenancy (another clinic's counts never mix) and each role's shape.
  - Web: unit tests for each tile.
  - One Playwright journey: sign in, then *Today*, then a tile click.

Planned verification:

- **Gates:** `make lint typecheck contract-check test`, and `make e2e` with the new journey.
- **Stack checks:**
  - after booking, arriving and completing patients, the counts match the queue;
  - a doctor sees only their own sessions;
  - front desk sees no owner strip.
- **Phone check:** a check at 360 px.
- **Failure paths:**
  - the API down shows the `Ref`;
  - another clinic's numbers never appear.

### M6-P1 — as built (20 Oct 2026)

- **API.** `GET /api/v1/dashboard/today` (`GetToday`, `delivery/http/dashboard.py`), backed by a
  tenant-scoped `DashboardReads` port (`adapters/db/dashboard.py`). Every query filters every
  table by the clinic, joins included. The pending follow-up count shares its SQL with
  `/follow-ups/pending` (`adapters/db/reminders.py`), so the number is always the list's length.
  Scope `DOCTOR` comes from the caller's doctor profile; `week` comes with `USAGE_METRICS_VIEW`,
  which doctors hold too, so a doctor sees their own week without message counts.
- **Web.**
  - Tokens are in `globals.css`.
  - Primitives are in `components/ui/` (README there). Tabs use `@radix-ui/react-tabs` 1.2.1, the
    only headless primitive adopted.
  - Motion runs through `MotionProvider`, mounted in `AppShell` and `OpsShell` only.
  - The shell is responsive. On a phone, Sign out moves into the Menu drawer and the header shows
    the brand mark only.
  - `features/dashboard/` holds `TodayDashboard`, `useToday` (polls with an ETag) and `labels`.
  - `TODAY_PATH` replaces `QUEUE_PATH` as the landing page.
  - The Playwright journeys now sign in to `/today` and open the queue from the sidebar
    (`queue-support.ts` `signInAs`, `openQueue`).
- **Dependencies added (pinned).** `motion` 14.4.0 provides the animation that decision 3A asked
  for. `@radix-ui/react-tabs` 1.2.1 is the accessible tabs primitive under the amended decision 2
  and brings 7 small `@radix-ui` packages with it. `npm audit --omit=dev` finds 0
  vulnerabilities. The full-tree audit still shows the dev-only braces advisory, recorded in the
  CHANGELOG since #19.
- **Verification.**
  - `make lint typecheck contract-check test` are green.
  - API: 1,588 tests (10 new) at 98.26% coverage. Web: 463 tests in 50 files.
  - `make up`, `make seed` and `make smoke` are green; `make e2e` is 13/13, including the new
    `today-dashboard.spec.ts`.
  - Stack checks: for desk, doctor and owner, the counts match `/queue` status by status. A doctor
    gets scope `DOCTOR` and `messages_failed` null. Front desk gets `week` null; the owner and the
    doctor get 7 days.
  - With the API stopped, the web origin answers 500 for the endpoint. The screen's error-with-Ref
    and *Try again* path is covered by a unit test; it was not seen in a browser.
  - Screenshots taken at 1366 px and 360 px. At 360 px there is no sideways scrolling (asserted in
    the e2e journey).
  - A doctor seeing only their own sessions is proved by the integration test with a second
    doctor. The seed has one doctor, so on the stack the doctor's numbers equal the clinic's.
  - A web test runner fix is recorded in DEBUG_JOURNAL (20 Oct 2026).
