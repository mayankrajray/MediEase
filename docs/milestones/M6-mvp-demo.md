# M6 — MVP demo: clinic and patient experience: design notes

| Field | Value |
|---|---|
| Status | Opened 20 Oct 2026 (issue #49, branch `m6/49-mvp-demo`); plan approved by the developer (items D2–D5 of the demo plan); M6-P1 confirmed by the developer 20 Oct 2026 and pushed (draft PR #50); M6-P2 designed, awaiting approval |
| PRD | v1.1 §0 (C1–C3), §8.13 |
| ADR | ADR-0013 (for M7), ADR-0014 (for M8); patient accounts and Google sign-in get an ADR in P3 |
| Covers | FR-AUTH-07, FR-PRT-01..04, FR-REM-03, FR-NTF-01, FR-PUB-01..04 |
| Issue / branch / PR | #49 · `m6/49-mvp-demo` · one PR for the milestone (ADR-0011) |
| Exit criterion | On the local stack: each role lands on its own dashboard; a patient signs in with Google or email, links a clinic record by invite or prescription link, and sees appointments, prescriptions, reminders and a medicine plan; notifications arrive in the app; a public booking request is confirmed by the front desk; `make e2e` green |
| Out of scope | Deployment and hosting; the AI assistant (M7); per-clinic WhatsApp and billing (M8, designed); pilot hardening (M9) |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Design system (tokens, primitives, Motion, responsive shell) and the role dashboards' first screen: *Today* for front desk, doctor and owner | Below (confirmed 20 Oct 2026) |
| P2 | The design system across the existing screens (queue, patients, consultation, schedule, follow-ups, ops); mobile layouts; motion for drawers, dialogs and list changes | Below (awaiting approval) |
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

Confirmed by the developer on 20 Oct 2026. Pushed to `m6/49-mvp-demo`; draft PR #50.

---

## M6-P2 — The design system across the existing screens

Proposed 20 Oct 2026. Recommendations are marked (rec). No API or contract change is expected.

Facts the design rests on:

- **Screens still in the old style.** About 45 components still use the plain M1–M5 look:
  `blue-800` buttons, `rounded border` boxes and ad-hoc spacing. The biggest are the schedule
  settings, the queue board, patient reminders, the consent panel, the Rx library and builder,
  and the ops wizard.
- **Tables.** The queue, the patient search results, pending follow-ups and the ops clinic list
  are `<table>`s. They do not fit a 360 px screen.
- **Overlays.** `Drawer` and `Dialog` are native `<dialog>` elements opened with `showModal()`.
  The browser keeps focus inside, makes the page inert and handles Escape. Today they appear
  and disappear with no transition.
- **Accessible widgets.** `Menu`, `PatientSearch`, `PatientPicker` and `MedicineCombobox`
  already follow WAI-ARIA and are covered by unit and e2e tests.
- **Tests find things by role and name.** Restyling keeps the tests valid, but rendering the
  same control twice (a table for desktops plus cards for phones) would duplicate every button
  in jsdom, where the CSS that hides one copy does not apply.
- **The patient page.** `/p/…` has its own small look and a 200 KB budget (NFR-02).

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Scope and order | Every clinic, ops and auth screen moves to `components/ui`, one screen at a time, each its own commit, in demo order: (1) sign-in, invite and clinic chooser; (2) queue, booking and cancel; (3) patients (search, register, profile, consent, appointments, reminders, messages); (4) consultation and prescriptions; (5) follow-ups; (6) schedule settings; (7) ops console. The patient page `/p/…` takes the colour tokens only: no Motion, no new JavaScript | B: only the screens on the demo path (the rest would look like a different product) |
| 2 | Tables on a phone | One set of markup per list. From 768 px it is a table; below that, CSS shows each row as a card. Explicit `role="table"`, `row`, `cell` and `columnheader` attributes keep the semantics when `display` changes, and the actions stay in the same buttons | B: render a table and a card list and hide one (duplicate controls, so tests and screen readers see both). C: horizontal scrolling (hard to use at 360 px) |
| 3 | Drawers and dialogs | Animated with CSS only. They slide in (drawers) or fade and scale (dialogs) through `@starting-style` and `transition-behavior: allow-discrete` on `[open]` and `::backdrop`, and `motion-reduce` switches it off. The native `<dialog>` keeps focus, inertness and Escape | B: Motion's `AnimatePresence` (the dialog would have to stay mounted while it animates out, which fights `showModal()` and the focus return the tests cover) |
| 4 | Motion for lists | When a row's status changes it moves to its new place (`layout`), and new rows rise in. This applies to the queue, the follow-ups and the patient's reminders. Layout animation needs Motion's `domMax` features, so they are loaded only when a list first animates (`LazyMotion features={() => import(...)}`); the other screens keep `domAnimation`. Reduced motion is honoured | B: `domMax` everywhere (about 25 KB more JavaScript on every clinic screen). C: no list motion |
| 5 | More headless primitives | None in P2. `Menu` and the three comboboxes already meet WAI-ARIA and have tests; they get our styling only. The next adoption would be named in its own phase (for example toasts in P7) | B: move `Menu` and the comboboxes onto Radix or Downshift (a rewrite of tested keyboard behaviour for no gain to users) |
| 6 | Forms | Our `TextField` becomes a small family in `components/ui/Field`: `TextField`, `SelectField`, `TextAreaField` and `CheckboxField`, all sharing the label, hint, error and `aria-describedby` wiring, plus 40 px touch targets. `useFocusOnError` stays as it is | B: restyle each form in place (the same wiring repeated about 20 times) |
| 7 | Ops console frame | The clinic shell's frame becomes a shared `Shell` component (sidebar, top bar and Menu drawer). Clinic and ops each pass their own navigation; the ops console gets the same responsive layout | B: keep `OpsShell`'s header-only nav (two frames to maintain) |
| 8 | Sign-in and invite | A centred card on the canvas, with the brand mark and the clinic or invite context. The fields are unchanged, so the password-manager hints and labels stay | B: a split screen with an illustration (an image download, and nothing to show yet) |

Fixed points:

- **Behaviour.** No behaviour changes: every existing unit test and Playwright journey passes.
  Markup changes only where a test names a structure (for example a `row` that becomes a styled
  row); a test is updated, never loosened.
- **Accessibility.** WCAG 2.1 AA: contrast of the new shades, focus always visible, targets at
  least 24 px and 40 px for touch, and status in words.
- **Phone checks.** Each converted screen gets a 360 px check: no sideways scrolling and
  actions reachable. The queue, patient profile and follow-ups get it in Playwright; the rest
  get screenshots in the phase record.
- **Budget.** The `/p/…` page stays under 200 KB. The `next build` output is recorded before and
  after.
- **Patient data.** Nothing clinical is added to any screen that did not already show it. Front
  desk still never sees prescription content.

Planned verification:

- **Gates:** `make lint typecheck contract-check test` and `make e2e`, with three 360 px journeys
  added.
- **Stack checks:**
  - Book, arrive and complete a patient from the queue on a phone-sized screen.
  - Register a patient and record consent on the phone layout.
  - A doctor completes a visit and issues a prescription at 1366 px.
  - An owner edits a schedule.
  - Ops create a clinic.
- **Reduced motion:** Playwright with `reducedMotion: "reduce"` shows no transform on a drawer
  or a list change.
- **Failure paths:**
  - An API error inside a drawer still shows the Ref and keeps focus in the drawer.
  - A dialog closed with Escape returns focus to its opener (the existing tests).
