# M6a — Auth, staff workspaces and notification core: design notes

Was "M6 — MVP demo: clinic and patient experience" until PRD v1.2 (22 Oct 2026) split M6 into
M6a–M6d. The P1–P2 records below are unchanged; the old P4–P8 (linking, portal, medicine planner,
notifications for patients, public booking) moved to M6b.

| Field | Value |
|---|---|
| Status | Opened 20 Oct 2026 (issue #49, branch `m6/49-mvp-demo`); plan approved by the developer (items D2–D5 of the demo plan); M6-P1 confirmed by the developer 20 Oct 2026 and pushed (draft PR #50); M6-P2 confirmed 21 Oct 2026 and pushed; re-scoped to M6a by PRD v1.2 on 22 Oct 2026; M6a-P3 design approved 22 Oct 2026 (ADR-0015 Accepted); M6a-P3 built 23 Oct 2026, awaiting confirmation |
| PRD | v1.2 §0 and §8.14 (v1.1 §8.13 where not superseded) |
| ADR | ADR-0013 (for M7), ADR-0014 (for M8); patient accounts and Google sign-in: ADR-0015 (Accepted, P3) |
| Covers | FR-AUTH-05, 07, 08, FR-PRT-01 (account only), FR-ORG-03, FR-ORG-07, FR-UX-01..06, FR-NTF-02..06, FR-APT-08, 09, FR-AUD-03 |
| Issue / branch / PR | #49 · `m6/49-mvp-demo` · one PR for the milestone (ADR-0011) |
| Exit criterion | On the local stack: Owner, Doctor and Front Desk, and a practising owner in both views, each get their own home screen and navigation; staff and patients sign in with Google (fake provider) or a password and stay apart; email verification and password reset work; the owner manages the team on the web; in-app notifications arrive; `make e2e` green |
| Out of scope | Patient linking, portal, medicine planner and booking (M6b); clinic applications, verification and discovery (M6c); billing (M6d); deployment and hosting; the AI assistant (M7); per-clinic WhatsApp and billing (M8, designed); pilot hardening (M9) |

## Phase plan

| Phase | Builds | Design |
|---|---|---|
| P1 | Design system (tokens, primitives, Motion, responsive shell) and the role dashboards' first screen: *Today* for front desk, doctor and owner | Below (confirmed 20 Oct 2026) |
| P2 | The design system across the existing screens (queue, patients, consultation, schedule, follow-ups, ops); mobile layouts; motion for drawers, dialogs and list changes | Below (confirmed 21 Oct 2026) |
| P3 | Accounts: Google sign-in for staff and patients, patient email and password, patient sessions kept apart from staff sessions (ADR-0015) | Below (approved 22 Oct 2026; built 23 Oct 2026) |
| P4 | Email provider behind a port: email verification, password reset by link (FR-AUTH-08, FR-AUTH-05) | Below (approved and built 23 Oct 2026) |
| P5 | Owner Team page: invite, change role, deactivate (FR-ORG-07) | Below (approved and built 23 Oct 2026) |
| P6 | Role workspaces (FR-UX-01..05); the practising owner's Owner / Doctor switch with *My Patients* (FR-UX-06); owner as Doctor 1 in the ops wizard (FR-ORG-03) | Below (approved and built 23 Oct 2026) |
| P7 | Notification service, domain events, in-app channel, notification centre (FR-NTF-02..06) | Below (awaiting approval) |
| P8 | Appointment reminders (FR-APT-08), doctor-leave conflicts (FR-APT-09), owner audit view (FR-AUD-03) | At its start |

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

**Approved by the developer 20 Oct 2026: A on all eight.**

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

### M6-P2 — as built (21 Oct 2026)

- **Foundations.**
  - Drawers and dialogs animate in with CSS (`.me-overlay`, `@starting-style`), with no
    transition under reduced motion.
  - The form fields are in `components/ui/Field`; `components/TextField.tsx` was removed and its
    four users moved over.
  - Responsive tables use `components/ui/table` with `.me-table` in `globals.css`: cards below
    768 px, each cell on one line with its column's name, and explicit ARIA roles.
  - List motion uses `LayoutMotion`. Motion's `domMax` features are a separate chunk loaded on
    first use, by `motion-max.ts`.
  - `AuthFrame` is the frame of the sign-in, invitation and clinic chooser screens.
- **Shell.** `features/shell/Shell.tsx` is shared by `AppShell` and `OpsShell`. The ops console
  now has the sidebar and the Menu drawer.
- **Screens.**
  - Every clinic, ops and auth component moved to the tokens: the brand colour, rounded-lg
    controls, cards for each section and 40 px buttons.
  - A class-name codemod did most of this, and each screen was then reviewed in screenshots at
    1366 and 360 px.
  - On phones, these lists show as cards: the queue, patient search results, pending follow-ups,
    the ops clinic list, a patient's appointments and their message history.
  - Statuses appear as `StatusBadge`; `STATUS_TONES` is in `features/appointments/api.ts`.
  - The queue, the follow-ups and a patient's reminders glide when they reorder.
  - The consent checkboxes became 40 px targets.
  - The patient page `/p/…` took the colour tokens only.
- **No new headless primitive and no API change.** No test was loosened. One empty-state wording
  was kept on purpose so a test still names it. The e2e phone check now looks at the hidden
  header row (`thead`), not a cell, because visually hidden content keeps its box.
- **Verification.**
  - `make lint typecheck contract-check test` are green (API 1588 tests at 98.26%; web 463).
  - `make e2e` is 16/16, including the new `phone-layouts.spec.ts`. That journey covers:
    - the queue as cards, with a card marking its patient arrived;
    - the profile and follow-ups at 360 px, with consent recorded from the phone;
    - reduced motion: the drawer's `transition-duration` is 0 s with reduce and non-zero without.
  - NFR-02: the patient page's first visit is 153,127 bytes on the wire, under 200 KB (147 KB in
    M4).
  - One-off stack checks, not committed: an owner saved the weekly hours, and ops created a
    clinic up to step 2. The doctor's consultation and issue journey is in
    `consultation-keyboard.spec.ts`.
  - The local database was reset (`docker compose down -v`, then `make seed`). Repeated runs on
    one day had filled the e2e extra session, so `sessionRunningNow` hit `SCH_OVERLAP`. This is a
    limit of that test helper with reused local data, not of the app.

Confirmed by the developer on 21 Oct 2026 and pushed to draft PR #50.

---

## M6-P3 — Accounts: Google sign-in for staff and patients, patient email and password

Proposed 21 Oct 2026. Recommendations are marked (rec). ADR-0015 records decisions
1–4 and 6. Covers FR-AUTH-07 and FR-PRT-01. Linking an account to a clinic's record is P4; the
portal screens are P5. P3 delivers only the sign-in, sign-up and sign-out screens and an account
page that says no clinic is linked yet.

**Approved by the developer 22 Oct 2026: A on all eight** (now M6a-P3; ADR-0015 Accepted).
Amendments from PRD v1.2:

- **Decision 5.** "No password reset" and "email stored unverified" now hold only until M6a-P4,
  which adds an email provider (FR-AUTH-08): email verification, and password reset by link
  (FR-AUTH-05). P3 stores `email_verified_at` (null for password sign-ups, set for Google) so P4
  and the verified-identity rule (FR-PUB-03) need no data change. Accounts are still never merged
  automatically.
- **Account page.** It says *No clinic linked yet*; linking and the *Find a doctor* dashboard come
  in M6b (and the directory in M6c), not "P4".
- **Roles.** A membership keeps exactly one role (FR-ORG-03). Google staff matching is by user,
  so a practising owner (an `OWNER` with a linked doctor profile) signs in like any staff member;
  P3 changes no role or permission check.

Facts the design rests on:

- **Staff today** (ADR-0006, M1):
  - **Accounts and cookies:** every signed-in person is a `users` row. They sign in with an
    email or phone number and a password (Argon2id; five failures lock the account for 15
    minutes). The JWT (audience `mediease`) travels in `me_access` on `/api`, the rotating
    refresh token in `me_refresh` on `/api/v1/auth`, and `me_csrf` on `/`.
  - **Every request:** the API re-reads the session, the user and the memberships; clinic access
    exists only through an active membership.
- **Nothing to sign in with yet.** There is no OAuth client (L-09 is pending) and no email
  provider, so no email can be verified or sent.
- **Already available.** The API already has PyJWT with `cryptography` (RS256, `PyJWKClient`)
  and calls out with `urllib`. Public routes have a PostgreSQL rate limiter (M4-P5).
- **The proxy.** It sends anyone without `me_csrf` to `/sign-in`, except on public paths.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Where patient accounts live | A new `patient_accounts` table and `patient_refresh_tokens`, apart from `users`. They are not tenant data. A patient account has no memberships, so no staff route can ever serve it. The same person may have both a staff user and a patient account | B: `users` with a patient flag (one missed check gives a patient a staff route) |
| 2 | Keeping the sessions apart | Portal cookies `me_pt_access` (Path `/api/v1/portal`), `me_pt_refresh` (Path `/api/v1/portal/auth`) and `me_pt_csrf`. JWT audience `mediease-portal`; each verifier refuses the other's audience (401). Portal routes under `/api/v1/portal/…` with a new `@patient` access policy, inside the existing default-deny check. Web pages under `/portal/…` with their own sign-in redirect in the proxy | B: the staff cookies with a role claim (every route would have to check it) |
| 3 | How Google sign-in works | OpenID Connect Authorization Code flow with PKCE, run by the API. `GET /api/v1/auth/google/start?intent=staff\|patient&next=` redirects to Google; `state`, `nonce`, the PKCE verifier, the intent and `next` sit in a 10-minute signed HttpOnly cookie. `GET /api/v1/auth/google/callback` exchanges the code and verifies the ID token: RS256 against Google's JWKS, `iss`, `aud`, `exp`, `nonce` and `email_verified`. It then sets the staff or the portal cookies and redirects to a safe `next`. No Google script on our pages, so the CSP is unchanged. Behind an `OidcPort`; PyJWT and `urllib` only, no new dependency | B: Google Identity Services in the browser (a third-party script and CSP changes). C: Authlib (a dependency for one flow) |
| 4 | Who a Google sign-in is | `external_identities` (provider, `sub`, and a staff user or a patient account).<br>**Staff:** the first sign-in links an existing active staff user whose email equals Google's verified email; after that only the `sub` is matched. It never creates staff access. An unknown address returns to `/sign-in` with "No MediEase staff account uses this Google address". Platform ops users may not use Google.<br>**Patients:** the first sign-in creates a patient account (the name and email from Google) | B: match staff by email every time (an address that moves at Google would move the access with it). C: let Google create staff accounts (against FR-AUTH-07) |
| 5 | Patient email and password | Sign-up takes a name, email and password, then signs the patient in. The same Argon2id, 10-character minimum and five-failure lockout as staff. The email is stored unverified. There is no password reset by email until an email provider exists; a patient who forgets uses Google or a new clinic invite (P4). Google and password accounts are never merged automatically, even with the same address, so an unverified address cannot claim someone's account or their linked records | B: email verification and reset now (needs a paid email provider; noted as a later item). C: merge by email (account takeover by whoever registered the address first) |
| 6 | Working without L-09 | `GOOGLE_OIDC_PROVIDER=google\|fake`. `fake` is allowed only with `APP_ENV` `local` or `test`, and start-up refuses it elsewhere. It skips Google: `/start` goes straight to `/callback` with a synthetic verified identity for the `login_hint` email, through the same matching and cookie code. With `google`, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are required. The redirect URI is `PUBLIC_BASE_URL` + `/api/v1/auth/google/callback` (through the web origin's rewrite) | B: wait for L-09 (blocks the demo). C: a mock Google server container (more to run, and it proves little more) |
| 7 | Abuse and privacy | Sign-up, sign-in and Google's start and callback are rate limited per caller fingerprint with the M4-P5 limiter. Errors are generic ("email or password is incorrect"). Audit events are `patient_account.created`, `patient.signed_in` and `staff.signed_in_google`, with a new actor type `PATIENT`; IDs only, no email. Sign-up does reveal that an address already has a password account; this is accepted and rate limited (ADR-0015) | B: a sign-up that hides existing addresses (needs email delivery to finish the sign-up) |
| 8 | Web screens | `/sign-in` (staff) gains *Continue with Google*. New `/portal/sign-in` and `/portal/sign-up` in the `AuthFrame` card, with Google and email forms. `/portal` (the account) shows the name, how they signed in, *No clinic linked yet* (linking arrives in M6b) and *Sign out*. Mobile-first at 360 px; English only in P3 (Hindi arrives with the portal in P5) | B: one sign-in page that asks "staff or patient?" (staff and patients would see each other's options) |

Fixed points:

- **Contract.** 0.23.0 with the portal and Google routes; generated web types.
- **Migration.** `0020`: `patient_accounts`, `patient_refresh_tokens`, `external_identities` and
  the `PATIENT` actor type. `docs/DATA_MODEL.md` updated.
- **Settings.** `GOOGLE_OIDC_PROVIDER`, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in
  `.env.example`. The secret is a `SecretStr` and never logged.
- **Unchanged.** No staff behaviour changes for password sign-in. Every existing test and
  journey passes.
- **New error codes in `docs/ERRORS.md`:** `AUTH_GOOGLE_NO_STAFF_ACCOUNT`,
  `AUTH_GOOGLE_FAILED`, `PRT_EMAIL_TAKEN` and `PRT_INVALID_CREDENTIALS`.

Planned verification:

- **Unit:**
  - **ID token:** signature, `iss`, `aud`, `exp`, `nonce` and `email_verified`, each refused when
    wrong, with test RSA keys and a fake JWKS.
  - **Flow cookie:** `state` mismatch, an expired flow cookie, and PKCE.
  - **Start-up:** the fake provider refused in production.
- **Integration (PostgreSQL):**
  - **Patient sign-up and sign-in:** sign up, sign in, the lockout, refresh rotation and reuse,
    sign out.
  - **Google staff matching:** a first sign-in links an active staff user by verified email,
    later ones match by `sub`; ops users, unknown addresses and inactive users are refused.
  - **Google patients:** the first sign-in creates the account.
- **Separation (permanent suite):**
  - A portal token is 401 on every staff and clinic route, and a staff token is 401 on every
    portal route.
  - A patient account never appears in clinic staff lists or memberships.
- **Playwright:**
  - A patient signs up by email, sees their account at 360 px and signs out.
  - A patient signs in with Google (fake).
  - The seeded doctor uses *Continue with Google* (fake) and lands on Today.
  - Failure path: an unknown Google address on the staff page shows the message.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

### M6a-P3 — as built (23 Oct 2026)

- **API.**
  - **Accounts and sessions.** `domain/portal/account.py` (`PatientAccount`, `SignInMethod`) and
    `domain/identity/external.py` (`ExternalIdentity`). Use cases are in
    `application/portal/use_cases.py`: sign-up, sign-in, refresh, sign-out and
    `AuthenticatePatient`. Portal sessions are issued by `PatientSessionIssuer`
    (`application/portal/sessions.py`) into `patient_refresh_tokens`, with a second
    `JwtAccessTokenIssuer` on audience `mediease-portal`.
  - **Routes.** `delivery/http/portal.py` serves `/api/v1/portal/...`. `@patient` and
    `current_patient()` are in `access.py`. The cookie sets are in `session_cookies.py`
    (`STAFF_COOKIES`, `PORTAL_COOKIES`). `csrf.py` checks portal paths against `me_pt_csrf`.
  - **Google.** The flow is `application/auth/google.py` (`StartGoogleSignIn`,
    `CompleteGoogleSignIn`), behind the new `ports/oidc.py`. It runs on
    `adapters/oidc/google.py` (PyJWT `PyJWKSet` over Google's JWKS, injectable transport) or
    `adapters/oidc/fake.py`. The flow cookie `me_oidc` is a JWT with its own audience
    (`adapters/security/jwt_flow.py`). `delivery/http/google.py` answers only with redirects and
    checks `next` again (`safe_next`). `bootstrap.build_oidc` refuses `fake` outside local and
    test.
  - **Rate limits** (`application/auth/rate_limit.py`, the M4-P5 table): 10 sign-ups, 30
    sign-ins and 30 Google starts or callbacks per caller per minute (`AUTH_RATE_LIMITED`, with
    `Retry-After`).
  - **Audit.** Actor type `PATIENT` on entity `patient_account`. New actions:
    `patient_account.created`, `patient.signed_in`, `patient.sign_in_failed`,
    `patient.signed_out`, `patient.refresh_reused` and `staff.signed_in_google` (with `linked`).
  - **Database and contract.** Migration `0020`; contract 0.23.0. The retention purge also
    removes expired portal tokens.
- **Web.**
  - **Shared code.** `lib/api/client.ts` takes a `csrfCookie` option. `lib/auth/refresh.ts`
    shares a refresh per lock name. `lib/auth/portal-session.ts` provides `portalGet` and
    `portalPost`. `safe-next.ts` has `safePortalNextPath` and `safeStaffNextPath`.
  - **Proxy.** It sends `/portal/*` without `me_pt_csrf` to `/portal/sign-in`, and
    `/portal/sign-in` and `/portal/sign-up` are public.
  - **Screens.**
    - `features/auth/GoogleButton.tsx` is a plain link that passes a typed email as
      `login_hint`. It appears on `/sign-in`, which also gains Google reasons.
    - `features/portal/` holds the sign-in, sign-up and account screens, under
      `app/(patient)/portal/`. They use `AuthFrame` with a patient tagline.
- **Decisions held as designed.** Two refinements:
  - The password minimum is the staff policy's 12 characters (`domain/identity/password.py`),
    not the 10 the design table said; "the same as staff" is what the design meant.
  - `email_verified_at` is stored now, so M6a-P4 needs no data change.
- **No new dependency.** The local venv and `node_modules` were re-installed from the lockfiles
  (`make install-api`, `make install-web`).
- **Verification.**
  - **Gates.** `make lint typecheck contract-check` are green. The full API run had 1,671 tests,
    with 97.75% package coverage and 98% on `domain/` + `application/`. The portal-token purge
    test was added after that run and passes with the purge and portal files. Web: 51 files, 493
    tests.
  - **Timing test.** The known flaky M4-P3 suggestions timing test failed once under load in the
    full run and passed on its own (TASKS "Open decisions").
  - **Stack.** `make up`, `make seed` and `make smoke` are green. `make e2e` is 20/20, including
    `portal-accounts.spec.ts`:
    - email sign-up at 360 px, the account page, sign-out and sign-in again, and a staff page
      refused to the portal session;
    - patient Google sign-in (fake);
    - the seeded doctor's *Continue with Google* to Today;
    - the failure path, an unknown staff Google address, with its message.
  - **Separation suite.** `tests/tenancy/test_portal_separation.py` calls every staff route
    with a portal token (also copied into `me_access`): all 401. It calls every `@patient`
    route with a staff token: all 401.
  - **Not verified.** Real Google sign-in waits for L-09. The Google adapter is tested only
    against signed test tokens and an in-memory JWKS.

Confirmed by the developer on 23 Oct 2026 and pushed to draft PR #50.

---

## M6a-P4 — Email provider: verification and password reset

Proposed 23 Oct 2026. Recommendations are marked (rec). ADR-0016 (Proposed) records decisions
1, 2, 4 and 5. Covers FR-AUTH-08 and FR-AUTH-05 (PRD v1.2). Invitation emails and the Team page
are P5. The `EMAIL` notification channel comes with the notification service (P7).

Facts the design rests on:

- **Nothing sends email today.**
  - Staff invitation links are shown to ops or the owner, who share them by hand.
  - A patient password account stores `email_verified_at` as null (P3).
  - A locked-out staff member is reset by ops (RUNBOOK §17).
- **The job queue exists** (M5-P1, the outbox).
  - A change enqueues a job in its own transaction, the worker sends it, and failures retry with
    backoff.
  - Job payloads are stored in plain text, so a secret must never be in one.
- **Secrets stored as digests.** Invitation and refresh secrets are SHA-256 digests of random
  values (`Sha256RefreshTokenSecrets`), looked up by digest.
- **Rate limits.** The per-caller limiter (`public_rate_limits`) is reused from M4-P5/M6a-P3.
- **Free tiers, checked on 23 Oct 2026.** All three providers below accept plain SMTP, so one
  SMTP adapter serves any of them.
  - **Brevo:** 300 emails a day, forever ([Brevo help](https://help.brevo.com/hc/en-us/articles/8292912279954-Add-or-remove-emails-from-your-plan)).
  - **Resend:** 3,000 a month and at most 100 a day ([Resend limits](https://resend.com/docs/knowledge-base/resend-sending-limits)).
  - **Amazon SES:** the only one with a Mumbai region. Third-party reports of AWS's July 2026
    pricing plans say the 12-month free tier no longer applies to new accounts ([classmethod](https://dev.classmethod.jp/en/articles/ses-pricing-plans-price-list-api-sesv2-api/));
    I could not load AWS's own pricing page to confirm.
- **Local mail catcher.** Mailpit is an SMTP catcher with an HTTP API for tests; v1.32.0 is
  current and carries security fixes ([releases](https://github.com/axllent/mailpit/releases)).

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Port and adapter | An `EmailPort` (`send(EmailMessage) -> provider_message_id`) with one **SMTP adapter** on the standard library (`smtplib`, STARTTLS or implicit TLS, login). It works with Brevo, Resend, SES and Mailpit alike, so changing provider is a settings change. A `console` adapter (logs the masked recipient and the subject, never the link) is for unit tests; it is refused in production, like messaging | B: each provider's HTTP API or SDK (a dependency and code per provider) |
| 2 | Provider (L-11) | **Brevo free** (300 a day) for the pilot, sending from a verified domain with SPF, DKIM and DMARC. Its free tier has the most daily headroom. Email addresses are processed outside India, so the privacy notice must name Brevo as a processor (counsel, L-04) | B: Resend free (100 a day, US). C: SES in Mumbai (keeps data in India, NFR-07, but is no longer free for a new account; the right choice if counsel requires India-only processing) |
| 3 | Mail on the local stack | A **Mailpit** container (`axllent/mailpit:v1.32.0`, pinned). SMTP is on the compose network only; the inbox UI is on `127.0.0.1:8025`. It is the local default (`EMAIL_PROVIDER=smtp`, `SMTP_HOST=mailpit`), so local sign-ups really "send". Playwright reads the links through Mailpit's API | B: the console adapter only (e2e could not follow a link) |
| 4 | Sending | Through the **job queue**. The request enqueues `send_auth_email` with only `{purpose, account kind, account id}`. The worker creates the token, stores its digest, renders the message and sends it. A retry makes a new token and retires the unused older one, so **no secret ever sits in the database**. The request never waits for SMTP | B: send inside the request (slow, and an SMTP outage fails the sign-up). C: create the token in the request and put it in the payload (a usable secret at rest) |
| 5 | Tokens | A new `email_tokens` table (platform data).<br>• **Columns:** `purpose` (`VERIFY_EMAIL` \| `RESET_PASSWORD`), a staff `user_id` or a `patient_account_id`, the email it was sent to, `token_hash` (unique), `expires_at`, `used_at`, `superseded_at`.<br>• **Lifetimes:** verification 24 hours, reset 30 minutes.<br>• **Rules:** single use; a new token supersedes the account's earlier unused one of the same purpose; a token is refused if the account's email has changed since it was sent; purged 30 days after expiry | B: signed stateless tokens (a reset could not be made single-use) |
| 6 | Email verification | Patient password accounts only.<br>• **When:** sent at sign-up; *Resend the email* on `/portal`, at most 3 an hour per account.<br>• **The link** opens `/portal/verify-email/{token}`, a page with a *Verify my email* button that POSTs. A mail scanner that pre-fetches the link therefore consumes nothing. Success sets `email_verified_at`.<br>• **On `/portal`:** a banner until the email is verified.<br>• **No blocking yet:** M6b's booking requests will require a verified email (FR-PUB-03); nothing is blocked in P4.<br>• **Staff are not verified in P4:** their address came from the clinic's own invitation, and Google sign-in uses Google's verification | B: verify by GET (a scanner could verify an address nobody opened). C: verify staff too (every existing staff user would have to act at once) |
| 7 | Password reset | **Staff** (`/sign-in` → *Forgot password?*) and **patients** (`/portal/sign-in`).<br>• **Request** (`POST /api/v1/auth/password-reset`, `/api/v1/portal/auth/password-reset`): always **202 with the same body**, whether or not the account exists. Rate limited per caller (5 a minute) and, silently, per account (3 an hour).<br>• **Who gets nothing:** a staff user with only a phone number (ops still reset them, RUNBOOK §17) and platform ops users.<br>• **Google-only patients:** they get a "you sign in with Google" email instead of a link.<br>• **Complete** (`.../password-reset/complete` with the token and the new password): applies the password policy, clears the lockout, **revokes every session of that account**, marks the token used and sends a "your password was changed" email.<br>• **Then:** it does not sign the person in; they return to sign-in with a "Password changed" message. For a patient password account a completed reset also verifies the email, which it has just proved | B: sign in after the reset (a leaked link would then also open a session). C: leave staff to ops (FR-AUTH-05 asks for both) |
| 8 | Messages and privacy | Plain text plus a minimal HTML version, in English. Hindi patient emails come with the portal's Hindi in M6b. From `MediEase <no-reply@<domain>>`. No clinical content, no images, and the provider's open and click tracking off. Links only to `PUBLIC_BASE_URL`. Logs and audit carry IDs and the masked address (`a***@example.com`), never the token or the full address | B: rich branded templates (more to test, nothing to brand yet) |

Fixed points:

- **Audit actions:**
  - `auth.password_reset_requested` (only when an account exists and a link was sent);
  - `auth.password_reset` (STAFF);
  - `patient.password_reset` and `patient.email_verified` (PATIENT).
- **Errors:**
  - `AUTH_TOKEN_INVALID` (404): unknown, used or superseded, one answer for all three;
  - `AUTH_TOKEN_EXPIRED` (410);
  - `REQ_VALIDATION_FAILED` for a weak password;
  - `AUTH_RATE_LIMITED` (429).
- **Settings, all in `.env.example`:**
  - `EMAIL_PROVIDER` (`smtp` \| `console`) and `EMAIL_FROM`;
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` (a `SecretStr`);
  - `SMTP_SECURITY` (`starttls` \| `tls` \| `none`, where `none` is allowed only in local and test).
- **Migration and contract.** Migration `0021` (`email_tokens`); contract 0.24.0. The compose
  `mailpit` service appears in the stack because the application uses it.
- **Web pages:**
  - *Forgot password?* links;
  - `/forgot-password` and `/portal/forgot-password`;
  - `/reset-password/{token}` and `/portal/reset-password/{token}`;
  - `/portal/verify-email/{token}`;
  - the verification banner with *Resend the email*.
  - All are mobile-first at 360 px. They join the proxy's public pages, except the banner.
- **Unchanged.** Staff and patient sign-in behaviour; every existing test and journey passes.

Planned verification:

- **Unit:**
  - token lifecycle: expiry, single use, superseding, a changed email;
  - the SMTP adapter against a fake `smtplib` (STARTTLS, login, a refused recipient, a timeout);
  - settings: `console` and `SMTP_SECURITY=none` refused in production;
  - rendering: no token or full address in any log line.
- **Integration (PostgreSQL):**
  - a reset request for a real and for an unknown email answers the same 202, and only the real
    one enqueues a job;
  - the job sends through a fake port and stores only a digest;
  - completing a reset revokes the account's sessions, so an old refresh is 401;
  - a reused or expired link is refused;
  - verification sets `email_verified_at`;
  - the per-account and per-caller limits hold.
- **Playwright with Mailpit:**
  - a patient signs up, opens the email in Mailpit, verifies, and the banner is gone;
  - a staff member resets a forgotten password, the old session ends and the new password signs
    in;
  - failure path: opening the reset link a second time shows that it was already used.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

**Approved by the developer 23 Oct 2026: A on all eight** (ADR-0016 Accepted).

### M6a-P4 — as built (23 Oct 2026)

- **API.**
  - **Tokens.** `domain/identity/email_token.py` defines `EmailToken`, its lifetimes, and
    `TokenInvalid`/`TokenExpired`. `User` and `PatientAccount` gain `clear_lockout`, and
    `PatientAccount` gains `verify_email`.
  - **Email port.** `ports/email.py`, with `adapters/email/smtp.py` (STARTTLS, TLS or none;
    failures sorted into retryable and permanent) and `adapters/email/console.py`.
  - **The send job.** `application/auth/emails.py` holds `enqueue_auth_email` and the
    `SendAuthEmail` handler for the new system kind `send_auth_email`. The handler re-reads the
    account and skips one that no longer qualifies. It supersedes earlier tokens, stores a new
    digest, commits, then sends. Wording is in `email_templates.py`.
  - **Use cases.** `application/auth/password_reset.py`: `RequestPasswordReset`,
    `CompletePasswordReset`, `VerifyEmail` and `ResendVerification`. Sign-up now enqueues the
    verification email.
  - **Sessions and routes.**
    - `RefreshTokenRepository.revoke_all_for_owner` serves staff and portal tokens alike.
    - The new routes are in `delivery/http/auth.py` and `portal.py`; the anonymous ones are
      CSRF-exempt.
    - `bootstrap.build_email` refuses `console` in production. The worker registers the handler.
  - **Database and contract.**
    - Migration `0021` adds `email_tokens` and the system kind.
    - The retention purge also removes email tokens.
    - Contract 0.24.0.
- **Compose.** A `mailpit` service (`axllent/mailpit:v1.32.0`, hardened, port 8025 on localhost).
  The API and worker environment now names the email and Google settings explicitly.
- **Web.**
  - `ForgotPasswordForm` and `ResetPasswordForm` are shared by staff and patients.
  - `VerifyEmail` is a page with a button.
  - The `/portal` banner offers *Resend the email*.
  - *Forgot password?* links are on both sign-in pages, plus a `password_reset` reason.
  - The proxy's public pages gain `/forgot-password`, `/portal/forgot-password` and the
    `reset-password` and `verify-email` link prefixes.
  - Link pages send no referrer.
- **Journey fix.** `reminders-follow-ups.spec.ts` FR-REM-07 skipped cancelling an earlier booking
  whose session has already ended. The API refuses that with `APT_NOT_MODIFIABLE`, so the
  journey failed when re-run after clinic hours. This is not a behaviour change, and the
  assertion is unchanged.
- **Verification.**
  - **Gates.** `make lint typecheck contract-check test` are green. API: 1,707 tests, 97.61%
    package coverage and 97% on `domain/` + `application/`. Web: 52 files, 503 tests.
  - **Stack.** `make up` (with `mailpit` healthy) and `make smoke` are green. `make e2e` is
    22/22, including `password-reset.spec.ts`:
    - a patient confirms their email from the Mailpit link at 360 px and the banner goes;
    - a fresh staff member resets a forgotten password, their old session gets 401 and the new
      password signs in;
    - failure path: the same link a second time says it is not valid any more.
  - **Not verified.** Real delivery through Brevo and its SPF, DKIM and DMARC wait for L-11.

Confirmed by the developer on 23 Oct 2026 and pushed to draft PR #50.

---

## M6a-P5 — The owner's Team page

Proposed 23 Oct 2026; approved by the developer the same day (A on all eight). Recommendations
are marked (rec). Covers FR-ORG-07 (PRD v1.2), on top of
FR-ORG-04. No ADR: it reuses ADR-0016 for the invitation email. Doctor profiles and "owner as
Doctor 1" are P6.

Facts the design rests on:

- **The API exists since M1-P4 and M1-P5**, under `STAFF_MANAGE`, which only owners hold:
  - `GET /api/v1/clinic/staff`;
  - `POST /api/v1/clinic/staff` (invite, returns `accept_url` once);
  - `PATCH /api/v1/clinic/staff/{membership_id}` (role and/or `DEACTIVATED`).

  Last-owner protection (`CLN_LAST_OWNER`) and the audit (`staff.invited`, `staff.role_changed`,
  `staff.deactivated`) are already in place.
- **What the list returns.** It gives `membership_id`, `user_id`, `full_name`, `role` and
  `status` only: no email or phone, no invitation expiry, no doctor-profile link.
- **Invitations.** Re-inviting an `INVITED` member issues a new secret that retires the old link.
  A `DEACTIVATED` member cannot be re-invited (`CLN_MEMBER_EXISTS`, M1). The secret is made in
  the request and returned once, which is how the ops wizard shows its copy-link box
  (`AcceptLink`).
- **Email exists since P4.** The `send_auth_email` worker pattern makes a secret at send time and
  stores only its digest (ADR-0016 decision 4).
- **The web app.** There is no staff screen for clinic members. Navigation is
  `features/shell/nav.ts` (`requires` a permission). The P2 primitives (responsive table, Drawer,
  Dialog, Field) are ready.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Where | `/team` in the clinic workspace, a sidebar item *Team* that `requires: STAFF_MANAGE`, so only owners see it. The API already refuses everyone else (403) | B: under `/settings/team` (one more level for the owner's most common admin task) |
| 2 | What the list shows | Every member: name, role, status in words (*Active*, *Invited*, *Deactivated*), email or phone, and for an invitation when it expires. The list API gains `email`, `phone_e164`, `invite_expires_at` and `has_doctor_profile`, read-only (contract 0.25.0). Active first, then invited, then deactivated. A table from 768 px and cards below, like P2 | B: names and roles only (an owner cannot tell two invitations apart or see which have expired) |
| 3 | Inviting | A drawer with name, role (Owner, Doctor, Front desk) and email or phone.<br>• **With an email:** the invitation is **emailed by the worker**. A new clinic job `send_staff_invite` makes the secret at send time and stores its digest on the membership, as ADR-0016 does. The owner sees "Invitation emailed to a\*\*\*@…", and *Resend* re-sends it, which retires the old link.<br>• **Phone only:** the link is shown once with *Copy link*, as ops do today, to share on WhatsApp. An emailed invitation never shows a link, so no second copy exists | B: always show the link and send no email (FR-AUTH-08 lists invitation emails). C: email *and* show the link (two live copies of one secret) |
| 4 | Changing a role | A *Change role* action per row opens a dialog with the three roles, then PATCH.<br>• **Last owner:** the API's `CLN_LAST_OWNER` message is shown as it is.<br>• **Demoting yourself:** an owner doing so is told first that they will lose this page, and after saving they land on Today | B: an inline select per row (an accidental change is one tap away) |
| 5 | Deactivating | *Deactivate* behind a confirmation dialog that says what happens: signed out on their next request, the member stays in the list.<br>• **Not yourself:** the action is hidden for your own row. The last-owner rule already covers a sole owner; this also stops a co-owner locking themselves out by mistake | B: allow deactivating yourself (a support call to undo) |
| 6 | Bringing someone back | *Re-invite* on a deactivated member. The domain gains `DEACTIVATED → INVITED`: a new invitation with a new secret, sent as in decision 3, audited as `staff.reinvited`. The identity spec's "no way back in M1" is amended. The person keeps their user and history; they accept the invitation and are `ACTIVE` again | B: no way back (re-hiring needs ops and a new user) |
| 7 | Doctor profiles | Shown, not managed: a *Doctor profile* badge where one is linked. Linking, and the owner as Doctor 1, are P6 (FR-ORG-03, FR-UX-06) | B: manage profiles here too (overlaps P6) |
| 8 | Screen behaviour | Loading skeleton; an error with its Ref and *Try again*; every change updates the row in place with a status message. 360 px and WCAG 2.1 AA. The front desk and doctors never see *Team* | — |

Fixed points:

- **Data.**
  - **Migration `0022`:**
    - `jobs` gains the clinic kind `send_staff_invite`;
    - `clinic_memberships` keeps the digest it already has;
    - the domain's status transitions add `DEACTIVATED → INVITED`.

    `docs/DATA_MODEL.md` and `docs/specs/identity-and-tenancy.md` are updated.
  - **Audit:** `staff.invited` and `staff.reinvited`, with `delivery: email | link`; no address
    and no secret.
  - **Contract:** 0.25.0. The invite answer has `accept_url` only for a phone-only invitation,
    and new `delivery` and `email_masked` fields; there is a new
    `POST /api/v1/clinic/staff/{membership_id}/resend`.
- **Errors.** `CLN_MEMBER_EXISTS` stays for an active or invited member.
  `CLN_INVALID_TRANSITION` covers resending to someone not invited.
- **Rate limit.** 10 invitations an hour per clinic, and *Resend* at most 3 an hour per member,
  both on the M4-P5 table.
- **Unchanged.** The ops wizard keeps its copy-link flow until M6c (FR-ONB-08). Every existing
  test and journey passes.

Planned verification:

- **Unit:**
  - the domain's re-invite transition and the last-owner rule;
  - the invitation email's wording;
  - the web Team screen's states and actions.
- **Integration (PostgreSQL):**
  - an emailed invitation stores only a digest, and the link works once;
  - resend retires the old link;
  - a phone-only invitation returns the link;
  - re-inviting a deactivated member returns them `ACTIVE` with their history;
  - doctors and front desk get 403 on every staff route;
  - another clinic's member is 404 (tenancy suite).
- **Playwright:**
  - the owner invites a front-desk member by email, the person accepts from the Mailpit link and
    signs in;
  - the owner changes their role, then deactivates them, and their next request is refused;
  - failure path: demoting the only owner shows the last-owner message.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

### M6a-P5 — as built (23 Oct 2026)

Approved A on all eight. Two points differ from the fixed points above:

- **No migration `0022`.** The database lists only the *system* job kinds
  (`ck_jobs_system_kind`); a clinic kind such as `send_staff_invite` needs no schema change, and
  the `DEACTIVATED → INVITED` transition is domain code. The migration head stays `0021`.
- **Re-invite is `POST /api/v1/clinic/staff`** with the member's email or phone, not a separate
  route: the same use case finds the deactivated membership and brings it back. *Resend*
  (`POST /staff/{id}/resend`) is for a member still `INVITED` only.

What was built:

- **Domain.** `ClinicMembership.reinvite(role)` (`DEACTIVATED → INVITED`, clears the old
  invitation and acceptance) and `withdraw_invite()` (retires a pending link at once).
  `StaffMember` gains `email`, `phone_e164`, `invite_expires_at` (invited only) and
  `has_doctor_profile` (an active doctor profile at this clinic). Audit action `staff.reinvited`.
- **Application.**
  - `InviteStaff` takes `by_owner`: an owner's invitation to someone with an email address is
    emailed (`delivery: email`), otherwise a link is made and returned once (`delivery: link`).
    Ops invitations are always links (FR-ONB-08, M6c).
  - `ResendStaffInvite`, and `enqueue_staff_invite` (payload: the membership ID only).
  - `SendStaffInvite` (`application/clinics/invite_email.py`), the handler for the clinic job
    kind `send_staff_invite`: it re-reads the membership, skips one no longer invited or an
    account disabled, makes the secret, stores its digest, commits, then sends. A failed send
    retries with a new secret. The wording is `email_templates.staff_invite`.
  - Limits on the M4-P5 counter table, hour windows: 10 invitations per clinic, 3 resends per
    member; over either is `CLN_INVITE_RATE_LIMITED` (429, `Retry-After`).
- **HTTP and contract 0.25.0.** `StaffMember` has the four new fields (required, nullable); the
  owner's invite answers `TeamInvitation` (`delivery`, `email_masked`, `accept_url` null when
  emailed); new `POST /api/v1/clinic/staff/{membership_id}/resend`. The ops invitation answer is
  unchanged apart from the new member fields.
- **Web.** `/team` (sidebar *Team*, `requires: STAFF_MANAGE`): `features/team/` with the table
  that becomes cards below 768 px, a skeleton, the error with its Ref and *Try again*, an
  `InviteDrawer` (also *Invite back*, prefilled), and dialogs for *Change role* (warning before
  demoting yourself, then a reload on Today), *Deactivate* (hidden on your own row) and a
  resent link. Every change updates its row and says so in a status line.
- **Tests changed because the behaviour changed (decision 3A).** Two onboarding tests took the
  owner's invitation link from the response: the M1 exit criterion now takes it from the emailed
  message, and the R13 takeover regression now uses an ops invitation (an owner's emailed one is
  never shown, so the link-holder there is ops). The P4 password-reset journey takes its
  invitation from Mailpit. No assertion was loosened.
- **Verification.**
  - **Gates.** `make lint typecheck contract-check test` green. API: 1,728 tests, 97.58%
    package coverage, 97% on `domain/` + `application/` (the M4-P3 suggestions timing test
    failed once in the full run under load and passed alone, as before). Web: 53 files, 515
    tests.
  - **Stack.** `make up` and `make smoke` green. `make e2e` 24/24 with `team.spec.ts`:
    - the owner invites a front-desk member by email from `/team`, the person joins from the
      Mailpit link in their own browser, the owner makes them a Doctor, then deactivates them,
      and their next request is 403 `AUTH_ACCOUNT_DISABLED`;
    - failure path: demoting the only owner warns first, then shows "A clinic needs at least one
      owner." with its Ref.

    A first `make e2e` run overlapped with the stack's containers being replaced and five
    journeys could not reach `web:3000`; the run straight after was 24/24 with no change.
  - **Not verified.** Real delivery through Brevo waits for L-11, as in P4.

Confirmed by the developer on 23 Oct 2026 and pushed to draft PR #50.

---

## M6a-P6 — Role workspaces, the practising owner's switch, owner as Doctor 1

Proposed 23 Oct 2026; approved by the developer the same day (A on all eight). Recommendations
are marked (rec). Covers FR-UX-01..06, FR-ORG-03 and the
"Doctor 1" part of FR-ONB-08 (PRD v1.2). No ADR: no new dependency, no change to the
permission model (one role per membership stays).

Facts the design rests on:

- **Permissions.** `permissions_for` gives an `OWNER` with a linked doctor profile one extra
  permission, `CLINICAL_WRITE`. Nothing else knows about a "practising owner".
- **`/me`.** Each membership carries its role and permissions only: no `doctor_id`, no
  `has_doctor_profile`. The web could only guess a practising owner from `CLINICAL_WRITE`.
- **Today.** One endpoint shaped by role (M6-P1, 5A). Scope `DOCTOR` is given only to role
  `DOCTOR` with a profile. A practising owner always gets the clinic view.
- **Queue.** `GET /queue?doctor_id=` exists. The web opens on the doctor linked to the signed-in
  user (D27), so a practising owner's queue already opens on their own day.
- **Patients.** There is no patient list, only a search (`GET /patients?q=`, at most 20).
  Nothing answers "the patients I have seen". `visits.doctor_id` holds the link, with no index
  on it.
- **Follow-ups.** `GET /follow-ups/pending` has no doctor filter.
- **Schedules.** A doctor may read a schedule (`DOCTORS_VIEW`) but not change one
  (`SCHEDULES_MANAGE` is the owner's).
- **Navigation.** One list, `NAV_ITEMS`, filtered by permission. Every member lands on `/today`.
  No role-specific nav, home or workspace exists.
- **Linking a doctor profile.** `POST/PATCH .../doctors` accept `user_id`, but only for an
  `ACTIVE` member. During ops onboarding the owner is still `INVITED`, so the wizard cannot
  link them. Nothing links a profile when an invitation is accepted.
- **Seed.** No practising owner exists. The seeded doctor works in two clinics.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | What a workspace is | A **view** chosen in the web app, never a permission: `OWNER`, `DOCTOR` or `FRONT_DESK`, from the membership's role. A practising owner (role `OWNER` with a doctor profile) chooses `OWNER` or `DOCTOR`; the choice is remembered per clinic in the browser, and Owner is the default. The URLs stay the same (`/today`, `/queue`…); each workspace shapes them. The API never sees the view, apart from Today's `view` parameter (decision 4) | B: a URL tree per workspace (`/doctor/today`; every page and link doubled). C: the view in the session or the token (a "switch" that changes what the API allows, which FR-UX-06 forbids) |
| 2 | How the web knows about the doctor profile | `/me` gains `doctor_id` (nullable) on each membership: the caller's active doctor profile at that clinic. It drives the switch, *My Patients* and the queue's default | B: infer it from `CLINICAL_WRITE` (true of every `DOCTOR` too, and gives no ID) |
| 3 | Navigation per workspace (FR-UX-04) | Three lists; an item appears only once its page exists:<br>• **Owner:** Today, Queue, Patients, Follow-ups, Team, Schedule.<br>• **Doctor:** Today, My queue, My patients, My follow-ups, My schedule (read-only).<br>• **Front desk:** Today, Queue, Patients, Follow-ups.<br>Booking requests (M6b), payments (M8) and notifications (P7) join in their phases. A page left out of a workspace's nav stays reachable by URL when the role is allowed, because the switch changes the view only | B: one list with role badges (the same menu for everyone; FR-UX-05 asks for different ones) |
| 4 | Each workspace's home (FR-UX-01..03, 05) | *Today*, shaped by workspace, with three quick actions:<br>• **Owner:** the clinic overview, 7-day strip and every doctor's sessions, plus a *Team* tile (active members, pending invitations, read from `GET /clinic/staff`). Actions: *Invite someone*, *Schedule settings*, *Open the queue*.<br>• **Doctor:** my sessions, my next patients, my week. Actions: *Open my queue*, *My patients*, *My follow-ups*.<br>• **Front desk:** today's counts as now. Actions: *Register a patient*, *Book an appointment*, *Add a walk-in* (the existing drawers).<br>API: `GET /dashboard/today?view=doctor\|clinic`. A `DOCTOR` with a profile always gets the doctor view. An owner with a profile may ask for either. `view=doctor` without a profile is 409 `CLN_NO_DOCTOR_PROFILE`. Front desk gets the clinic view only | B: separate home pages per role (three pages repeating one endpoint). C: an owner home with revenue and booking-request rates now (no data until M6b/M8; shown when it exists) |
| 5 | *My Patients* (FR-UX-02, 06) | **`GET /api/v1/my-patients?q=&limit=&offset=`**: patients with at least one visit by the caller's own doctor profile in this clinic, most recent visit first. Each row: code, name, age and sex, the last visit's date and the number of visits. No clinical text. `q` narrows by name, code or phone. 50 a page. Needs `CLINICAL_VIEW` and a doctor profile (else 409 `CLN_NO_DOCTOR_PROFILE`). Not audited, like the search: it shows who, not what. Migration `0022` adds `ix_visits_clinic_id_doctor_id_started_at`. Web: `/my-patients`, rows open the patient profile | B: also patients only booked with me (a patient who never came is not "mine" yet; *My queue* shows them). C: audit every listing (one row per page view adds noise and no protection; opening a visit is already audited) |
| 6 | The switch (FR-UX-06) | A two-option control, **Owner \| Doctor**, in the shell header next to the role pill. It is shown only for an `OWNER` with `doctor_id`, and works as a radio group from the keyboard. Switching opens that workspace's Today and announces "Doctor view". Permissions are unchanged in either view. An owner without a profile, a doctor and the front desk see no switch | B: in the user menu (hidden; an owner switches several times a day). C: a separate sign-in per view |
| 7 | What "mine" means in the Doctor workspace | • *My queue*: the queue opened on my doctor, as D27 already does; the doctor picker stays so they can cover a colleague.<br>• *My follow-ups*: `GET /follow-ups/pending` gains an optional `doctor_id`; the Doctor workspace sends its own, with *All doctors* one click away.<br>• *My schedule*: my weekly hours, leave and extra sessions, read-only (the existing `GET` with `DOCTORS_VIEW`). Changing them stays the owner's (`SCHEDULES_MANAGE`) | B: lock a doctor to their own queue (cover between doctors is normal). C: let doctors edit their own schedule (a permission change; not asked for) |
| 8 | Owner as Doctor 1, and linking later (FR-ORG-03, FR-ONB-08) | • **Ops wizard:** inviting the **owner** gets a checkbox *The owner also practises here* and a choice among the doctors added in step 2 (Doctor 1 preselected). The invitation request gains an optional `doctor_id`. The API then links that unlinked profile to the invited owner's user **in the same transaction**, allowed for an `INVITED` owner in this request only. The owner gains `CLINICAL_WRITE` once their membership is `ACTIVE`, that is on accepting. `staff.invited` and `doctor.updated` record it.<br>• **Afterwards:** the owner's Team page gets *Link doctor profile* for an active member with none (themselves included, "I also practise here"), using the existing `PATCH /clinic/doctors/{id}` with `user_id` | B: a pending link on the invitation, applied at acceptance (a new column and a second state for one fact). C: reorder the wizard to invite before adding doctors (breaks the M1-P7 flow and its journey) |

Fixed points:

- **Seed.** A third clinic, `sample-solo-clinic`: a practising owner
  (`owner@sample-solo-clinic.example`, with a linked doctor profile) and a front desk. It is the
  common solo-practice case, and idempotent per clinic, so existing databases gain it with
  `make seed`. RUNBOOK §1 lists it.
- **Contract 0.26.0.**
  - `Membership.doctor_id`;
  - `view` on Today;
  - `GET /my-patients`;
  - `doctor_id` on pending follow-ups;
  - `doctor_id` on both invitation requests.
- **Errors.** `CLN_NO_DOCTOR_PROFILE` (409). A `doctor_id` that is unknown, already linked, or
  sent with a role other than owner is 422 `REQ_VALIDATION_FAILED` on `doctor_id`.
- **Unchanged.**
  - One role per membership and the permission matrix;
  - the front desk never sees clinical content (§8.1);
  - every page's API check.
  - Every existing test and journey passes.

Planned verification:

- **Unit:**
  - workspace resolution (role, `doctor_id`, the remembered choice, a stale choice ignored);
  - each workspace's nav and quick actions;
  - the switch's visibility and keyboard use;
  - *My Patients* states.
- **Integration (PostgreSQL):**
  - Today `view=doctor` for a practising owner returns only their sessions, and is 409 without
    a profile;
  - `/my-patients` lists only patients this doctor saw, newest first, is 409 without a profile
    and 403 for the front desk;
  - another clinic's visits never appear (tenancy suite);
  - the pending follow-ups' `doctor_id`;
  - inviting an owner with `doctor_id` links the profile, and acceptance makes `CLINICAL_WRITE`
    effective;
  - the refusals on `doctor_id`.
- **Playwright at 1366×768 (FR-UX-05):**
  - the owner, the doctor and the front desk each sign in; the home heading, the nav and the
    first three actions differ;
  - the practising owner switches to Doctor and sees only their own sessions and patients, and
    switching back restores the owner nav;
  - failure path: an owner without a profile sees no switch, and `/my-patients` explains that
    it is for doctors.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

### M6a-P6 — as built (23 Oct 2026)

Approved A on all eight. Where the build differs from the text above:

- **The seeded clinic is `sample-family-clinic`, not a solo one.** It has the practising owner
  ("Dr. Family Owner"), a second doctor and a front desk. With a colleague in the same clinic,
  "only my sessions and patients" is actually tested.
- **The page heading stays *Today*.** Each workspace's home differs in its subtitle (*Clinic
  overview*, *My day*, *Front desk*), its content and its three quick actions. That is what the
  FR-UX-05 journey compares.
- **Quick actions open their drawers** through `?invite=1` on `/team` and `?book=1` or
  `?walk-in=1` on `/queue`. The *Open the queue* header button became the owner's *See the
  queue* action.

What was built:

- **API.**
  - `ClinicAccess`, `MembershipView` and `/me` carry `doctor_id`.
  - `GetToday` takes `View`: `_doctor_view` gives a `DOCTOR` with a profile their own day as
    before; an owner with an active profile gets theirs with `view=doctor`; otherwise
    `view=doctor` raises `NoDoctorProfile` (`CLN_NO_DOCTOR_PROFILE`, 409).
  - `ListMyPatients` (`application/patients/my_patients.py`) uses the lookup box's parsing and
    `VisitRepository.patients_seen_by` (a grouped read: last visit and count). The route is
    `GET /api/v1/my-patients` (`CLINICAL_VIEW`). Migration `0022` adds
    `ix_visits_clinic_id_doctor_id_started_at`.
  - `GET /follow-ups/pending` takes `doctor_id`.
  - `InviteStaffCommand.doctor_id` on both invitation routes. `InviteStaff._link_doctor` accepts
    an owner's invitation only, and an active doctor profile that is unlinked or already this
    person's. It records `doctor.updated` (`via: owner_invite`) and adds `doctor_id` to the
    invitation's audit metadata.
  - Seed: `_Person.practises` and a per-person registration number.
  - Contract 0.26.0.
- **Web.**
  - `features/shell/workspace.ts`: the workspace from the role and the remembered choice, each
    workspace's navigation and quick actions.
  - `WorkspaceProvider`, mounted per clinic by `WorkspaceGuard`.
  - `WorkspaceSwitch`: a radio group in the header that announces "Doctor view".
  - `nav.ts` keeps only `visibleNav`.
  - Today: the workspace subtitle, quick actions, and the owner's *Team* tile from
    `GET /clinic/staff`; `useToday` sends `view=doctor` for a practising owner's Doctor view.
  - New pages `/my-patients` (`MyPatients`) and `/my-schedule` (`MySchedule`, read-only).
  - *My follow-ups*: an *Only my patients* checkbox, on by default.
  - The ops wizard's invite step: *The owner also practises here*, with a choice of the doctors
    from step 2, Doctor 1 preselected.
  - Team: *Link doctor profile* (and "I also practise here" on your own row) through the
    existing `PATCH /clinic/doctors/{id}`.
- **Journey hardening (no assertion loosened).** These failures showed up from rerunning the
  journeys many times on one database within the hour:
  - `password-reset.spec.ts` now invites through the second clinic's owner, so reruns use up the
    first clinic's 10-an-hour invitation limit more slowly. It retries filling the email field
    if the page hydrates after the fill and clears it.
  - `sessionRunningNow` waits out an earlier run's extra session that is about to end instead of
    failing with `SCH_OVERLAP`.
  - Rerunning the journeys more than about five times within one hour on the same database still
    reaches that invitation limit, by design.
- **Verification.**
  - **Gates.** `make lint typecheck contract-check test` green. API: 1,743 tests, 97.46%
    package coverage, 97% on `domain/` + `application/`. Web: 55 files, 530 tests.
  - **Stack.** `make up`, `make seed` (adds `sample-family-clinic`) and `make smoke` green.
    `make e2e` 27/27 with `workspaces.spec.ts` at 1366×768:
    - the owner, the doctor and the front desk have different menus and first three actions;
    - the practising owner switches to Doctor, sees only *Dr. Family Owner*'s sessions and only
      their own patient (not the colleague's), switches back, and the choice survives a reload;
    - failure path: an owner without a profile has no switch, and `/my-patients` says why.
  - **Not verified.** The ops wizard's Doctor 1 path in a browser journey; it is covered by the
    wizard's unit tests and the API integration test.

Confirmed by the developer on 23 Oct 2026 and pushed to draft PR #50.

---

## M6a-P7 — Notification service, domain events and the notification centre

Proposed 23 Oct 2026. Recommendations are marked (rec). Covers FR-NTF-02..06 (PRD v1.2 C11), with
ADR-0017 (Proposed). It replaces FR-NTF-01 for staff. Notifications for patients in the app wait
for M6b, because patient accounts are linked to clinic patients there (FR-PRT-06).

Facts the design rests on:

- **No events today.** Nothing publishes or subscribes. The audit log records what happened, but
  it is a write-only trail, not an event stream.
- **Two features send WhatsApp themselves:**
  - booking and rescheduling enqueue `send_booking_confirmation` (key
    `booking_confirmed:{appointment}`);
  - issuing a prescription enqueues `send_rx_link` (key `rx_link:{prescription}`).

  Both handlers re-check consent and facts at send time, and the sender sends at most once per
  key (M5-P2).
- **Reminders and other sends.** Reminders (`send_reminder`) have their own scheduler, with quiet
  hours, revisions and the SMS fallback. The STOP confirmation answers an inbound message.
- **Where a message fails.** A message becomes `FAILED` in two places: the sender's final failure
  and the delivery webhook. Both already run a hook in that transaction (the SMS fallback). Staff
  are never told.
- **The outbox.** The job table is one: a job commits with its change, and a dedupe key makes it
  idempotent.
- **Patient accounts** (M6a-P3) hold no clinic data, so the app cannot notify a patient yet.
- **Finding recipients.** Memberships give each member's role; the appointment's doctor gives
  `doctors.user_id`.
- **The web shell** has a header group (name and Sign out) that is hidden on a phone, and a menu
  drawer. `lib/api/poll.ts` polls with an ETag and pauses in a hidden tab.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | How events flow (FR-NTF-02, 06) | **Published and dispatched in the change's transaction** (ADR-0017). A use case calls `publish(uow, event)`, where the event is a frozen dataclass of IDs and enums. `NotificationService` resolves recipients and preferences, writes in-app rows (unique per recipient and event key, so a replay adds nothing) and asks external channels to deliver. WhatsApp delivers by enqueuing the existing send job with its existing key. The event exists exactly when the change commits | B: a dispatch job per event (a poll's delay for in-app, twice the jobs). C: an events table with its own dispatcher (a second queue). D: a broker (ADR-0005 rejected one at this scale) |
| 2 | The event catalogue in P7 (FR-NTF-04, what exists today) | • `appointment.booked`, `appointment.rescheduled`: WhatsApp to the patient (the M5 confirmation, consent re-checked), and in-app to the appointment's doctor.<br>• `appointment.cancelled`: in-app to the doctor (there is no cancellation template; L-02 adds one later).<br>• `appointment.arrived`: in-app to the doctor ("Asha · SC-0004 has arrived, token 4").<br>• `prescription.issued`: WhatsApp link to the patient (M5).<br>• `message.failed`: in-app to the front desk and the owners, linking to the patient.<br>• `staff.joined`: in-app to the owners when an invitation is accepted.<br>Booking requests (M6b), medicine due (M6b), application decided (M6c), subscription notices (M6d), appointment reminders and leave conflicts (P8) join in their phases | B: notify every role of everything (noise; the front desk sees the queue anyway) |
| 3 | What moves behind the service | The **booking confirmation** and the **prescription link**: their call sites publish events, and the handlers, keys, consent checks and messages stay as they are. **Unchanged:** reminders keep their scheduler (a reminder is due at a time, not raised by a change; quiet hours and the SMS fallback live there). The STOP confirmation is a protocol reply. P8 reviews reminders when appointment reminders arrive | B: move reminders and the fallback too (rewrites working M5 logic for no user-visible gain) |
| 4 | Storing notifications | Migration `0023`:<br>• **`notifications`**, tenant data: `recipient_user_id`, `kind`, `event_key`, `title` (≤ 160 chars), `link` (an in-app path), `entity_type`, `entity_id`, `created_at`, `read_at`. Unique `(clinic_id, recipient_user_id, event_key)`; index `(clinic_id, recipient_user_id, created_at DESC)`.<br>• **`notification_preferences`**: `(user_id, clinic_id, kind, channel)` → `enabled`, with one row only when changed from the default.<br>The title is rendered when the notification is created, from a typed catalogue: a first name with a code, a doctor, a time, a role or a count. **Nothing clinical has a type** (FR-MSG-04). English at MVP | B: render on the web from params (two places to keep free of clinical text). C: keep notifications in the audit table (append-only, cannot hold read state) |
| 5 | Preferences (FR-NTF-03) | **Staff:** each member turns each kind on or off for in-app on a *Notifications* settings page (`/settings/notifications`). Everything starts on. Staff WhatsApp and email are not offered yet: there are no staff templates or consent. **Patients:** their WhatsApp and SMS preference **is** the existing consent and opt-out (M2-P3), so nothing new is stored. The service obeys it, and the send handlers check it again | B: a separate patient preference store (two truths beside consent, a DPDP risk) |
| 6 | The notification centre (FR-NTF-05) | • **Badge:** a *Notifications* button in the header, visible at every width, with the unread count in words for screen readers ("3 unread").<br>• **List:** opening it shows a drawer with the latest 30, newest first, unread in bold, each linking to its item (the appointment's queue day, the patient, the Team page). *Mark all as read* is there too.<br>• **Polling:** `GET /notifications/summary` every 15 s with an ETag, paused in a hidden tab. New arrivals are announced in a polite live region; there are no toasts.<br>• **API:** `GET /notifications`, `POST /notifications/{id}/read` and `POST /notifications/read-all` (`CLINIC_VIEW`), each caller's own only. Another member's notification is 404 | B: push by SSE or WebSocket (ADR needed; polling already serves the queue). C: a full notifications page instead of a drawer (one more click for a glance) |
| 7 | Quiet hours (FR-NTF-05, FR-REM-04) | **In-app ignores quiet hours.** Patient WhatsApp raised by the patient's own action (a confirmation, a prescription link) goes at once, as in M5. Scheduled reminders keep FR-REM-04 in their scheduler. The service carries a per-kind `respects_quiet_hours` flag so P8's appointment reminders use it | B: hold every WhatsApp until 08:00 (a 21:30 walk-in waits overnight for their confirmation) |
| 8 | Retention, volume and audit | Notifications are purged **90 days** after creation by the existing purge job. Preferences are kept. Reading is not audited (a convenience, not a disclosure). Changing a preference is. A dispatch does at most one query per lookup (recipients, preferences, insert), checked by a test | B: keep forever (personal data with no purpose after 90 days) |

Fixed points:

- **Code.**
  - `domain/notifications/` holds the event types, `NotificationKind` and the title catalogue.
  - `application/notifications/` holds `publish`, `NotificationService`, the channels and the
    use cases.
  - The ports gain `NotificationRepository` and `PreferenceRepository`.
- **Call sites.** `book.py`, `reschedule.py`, the cancellation, the queue's arrival transition,
  the prescription issue, the sender's final failure, the webhook's `FAILED` transition, and
  `AcceptInvite`.
- **Migration `0023`.**
  - **Tables:** the two above.
  - **Audit:** action `notification.preferences_changed`.
  - **Docs:** `docs/DATA_MODEL.md`, the reminders-and-messaging spec and ARCHITECTURE §8.
- **Contract 0.27.0.** The four notification routes, `GET/PUT /notifications/preferences`, and
  the `Notification` and `NotificationSummary` schemas.
- **Web.**
  - `features/notifications/`: the bell, the drawer, the poller and the preferences page.
  - The *Notifications* settings item joins every workspace's navigation.
  - The bell lives in `Shell`'s identity group, so a phone shows it too.
- **Unchanged.** Every M5 message (the same keys, consent checks and audit), the reminders
  scheduler, and every existing test and journey.

Planned verification:

- **Unit:**
  - each event's recipients and channels;
  - the title catalogue refusing a clinical kind;
  - preferences turning a kind off;
  - the bell's count and the drawer's states.
- **Integration (PostgreSQL):**
  - a booking writes the doctor's notification and the same confirmation job as before, in one
    transaction (a rollback leaves neither);
  - publishing twice adds nothing;
  - a failed message notifies the front desk and the owners once, through the webhook or the
    sender;
  - the read and read-all routes act on the caller's own notifications only;
  - another clinic's notifications are 404 and never listed (tenancy suite);
  - the purge removes rows older than 90 days.
- **Playwright:**
  - the front desk books a patient, and the doctor's bell shows 1. Opening it shows "Asha ·
    SC-0004 booked for …", the link opens the queue on that day, and the badge clears;
  - failure path: with the doctor's *Appointment booked* preference turned off, a booking adds
    nothing.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

### M6a-P7 — as built (24 Oct 2026)

Approved A on all eight. Where the build differs from the text above:

- **The channels are two code paths in `NotificationService`, not an interface.** In-app writes
  rows; WhatsApp calls the M5 `enqueue_booking_confirmation` and `enqueue_rx_link`. A `Channel`
  protocol waits for a third channel that delivers something (ADR-0017 "As built").
- **Which failures notify.** `MessageFailed` is published where a message turns `FAILED` after a
  definite answer: the sender's final failure and the webhook's `FAILED` status. An unknown outcome
  (`MSG_OUTCOME_UNKNOWN`, the message may have arrived) and a send skipped because consent or the
  facts changed do not, as with the SMS fallback.
- **`ProcessWebhookEvent` now requires the ID port**, so no wiring can silently skip the notice.
- **A staff join's key includes the acceptance time**, so somebody invited back after a
  deactivation is announced again.
- **`/queue?date=YYYY-MM-DD`** opens the queue on that day (anything else is ignored); the page is
  keyed by the day, so a second link followed from the queue shows the new day.

What was built:

- **API.**
  - `domain/notifications/`: the seven events (`events.py`), `NotificationKind`, `Channel`,
    `KINDS` (label, `respects_quiet_hours`), the typed title values `PatientRef`, `Place`,
    `PersonName` and `RoleLabel`, the title functions, `Notification` and `Preference`.
  - `ports/notifications.py`: `NotificationRepository` and `PreferenceRepository`, reached as
    `uow.tenant(...).notifications` and `.notification_preferences`.
  - `adapters/db/notifications.py`: insert with `ON CONFLICT DO NOTHING`, the preference upsert.
    Migration `0023` (two tables, CHECKs on kinds and channels).
  - `application/notifications/service.py`: `publish` and `NotificationService.dispatch`.
    Recipients: the appointment's doctor (when linked to an active member), or the active owners
    and front desk. The actor and members who turned the kind off are dropped. One query per
    lookup.
  - Call sites: `BookAppointment`, `RescheduleAppointment`, `CancelAppointment`,
    `TransitionAppointment` (to `ARRIVED`), `AddWalkIn`, `IssuePrescription`, `AcceptInvite`,
    the sender's `_finish` and `ProcessWebhookEvent`.
  - `application/notifications/use_cases.py` and `delivery/http/notifications.py`: the six
    routes, all `CLINIC_VIEW`. Contract 0.27.0.
  - Retention: `notifications` purged 90 days after creation by the existing purge job; audit
    action `notification.preferences_changed`.
- **Web.**
  - `features/notifications/`: `NotificationBell` (header identity group, visible at every width;
    the summary polled every 15 s with its ETag; a drawer with the latest 30, unread first in
    weight and in words; *Mark all as read*; a polite live region for arrivals) and
    `NotificationPreferences` at `/settings/notifications` (one checkbox per kind, saved at once).
  - *Notifications* is the last item of every workspace's navigation.
- **Journey helper fix (no assertion changed).** `sessionRunningNow` failed with `SCH_OVERLAP`
  when the last extra session had ended under 10 minutes earlier; it now starts the new one at
  that end (docs/DEBUG_JOURNAL.md, 24 Oct 2026).
- **Verification.**
  - **Gates.** `make lint typecheck contract-check test` green. API: 1,775 tests (before the
    reschedule test was added), 97.50% package coverage, 97% on `domain/` + `application/`. Web:
    56 files, 536 tests.
  - **New tests.** `tests/integration/test_notifications_http.py` (16): a desk booking tells the
    doctor and queues the same confirmation job; a reschedule, an arrival, a walk-in and a
    cancellation tell the doctor; publishing again adds nothing and a rollback leaves nothing; the
    actor is not told; a failed send tells the owners and desk once; an accepted invitation tells
    the owners; a preference turned off stops it and is audited once; the channel and body checks;
    summary ETag and 304, read, another member's 404, read-all; the limit; four statements per
    dispatch; the 90-day purge. Plus the webhook `FAILED` path (`test_webhooks_http.py`), the
    repository and HTTP tenancy suites, migration `0023` up and down, and the domain unit tests.
  - **Stack.** `make up`, `make seed` and `make smoke` green. Full Playwright suite 29/29, with
    `notifications.spec.ts`:
    - the front desk books with *Dr. Sample Doctor*; within one poll the doctor's bell reads
      "Notifications, 1 unread"; the drawer shows "Notify · SC-… booked for …"; opening it goes to
      `/queue?date=…` (*Today's queue*) and the count clears;
    - failure path: with *A patient is booked with me* off, a booking adds nothing; it is turned
      back on afterwards.
  - **Run note.** The journeys ran with the Playwright image mounting the Windows path, because
    the WSL path mount came up empty in this session (`make e2e` uses the WSL path). Same image,
    same tests, same stack.
  - **Not verified.** The live-region announcement of a new arrival has no automated test (it
    needs a second poll); it was not checked with a screen reader.

Confirmed by the developer on 24 Oct 2026 and pushed to draft PR #50 (`91f501e`).

---

## M6a-P8 — Appointment reminders, bookings to move after leave, the owner's audit log

Proposed 24 Oct 2026. Recommendations are marked (rec). Covers FR-APT-08, FR-APT-09 and FR-AUD-03
(PRD v1.2). It is the last M6a phase: when it is confirmed, PR #50 leaves draft.

Facts the design rests on:

- **Reminders (M5-P4) are follow-ups only.**
  - `reminders.kind` is `FOLLOW_UP` and `source` is `PRESCRIPTION` or `MANUAL`. `source_id` is a
    foreign key to prescriptions and `created_by` is required (migration `0017`).
  - The `send_reminder` job carries a revision (an older job does nothing). It defers out of
    21:00–08:00 to 08:00 (FR-REM-04), re-reads consent, needs the clinic's phone, and hands
    `follow_up_due` to the sender. The SMS fallback (off by default) hangs off its failure.
  - Booking, rescheduling and cancelling do not touch reminders.
- **Templates.** `booking_confirmed`, `rx_ready`, `rx_updated`, `follow_up_due` and
  `opt_out_confirmed` exist, in English and Hindi. There is no appointment-reminder and no
  cancellation template. A new one is a data change plus Meta approval (L-02); the console
  provider sends it locally.
- **Leave over a booked day is allowed and cancels nothing** (appointments spec R16, R17). The
  day's booked sessions become `CLOSED`, which refuses new bookings
  (`APT_SESSION_CLOSED`). `AddException` returns those "kept" sessions, and the Schedule page lists
  them for the owner. Nobody else sees them, and no list of the affected patients exists. A
  weekly schedule change behaves the same way.
- **Cancel and reschedule** work from a closed session. `CancelReason` already has
  `DOCTOR_UNAVAILABLE` and `CLINIC_REQUEST`. Every role holds `APPOINTMENTS_MANAGE`. There is no
  bulk action.
- **Audit.** `audit_events` is append-only, with an index on `(clinic_id, occurred_at)`.
  Metadata holds only IDs, enums and codes, never names, phones or clinical text. Nothing in the
  application reads it (the tenancy suite's reviewed exception says FR-AUD-03 must scope its own
  query and add cases there). Ops read it with psql (RUNBOOK §18). There is no `AUDIT_VIEW`
  permission.
- **The notification service (P7)** already receives `AppointmentBooked`, `AppointmentRescheduled`
  and `AppointmentCancelled` in the change's transaction. ADR-0017 left reminders on their own
  scheduler, because a reminder is due at a time rather than raised by a change.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Where appointment reminders live (FR-APT-08) | **The existing `reminders` table and send job.** Migration `0024` adds kind `APPOINTMENT`, source `APPOINTMENT` and a nullable `appointment_id` (foreign key, with a CHECK: set exactly for that source). `follow_up_date` holds the visit date for both kinds. `created_by` becomes nullable ("the system": a booking from the public page in M6b has no staff user). The status machine, revisions, quiet hours, consent, the clinic-phone check, the profile's *Reminders* list and the SMS fallback all apply unchanged | B: a separate `appointment_reminders` table (a second status machine, job, fallback and UI for the same idea) |
| 2 | When they are sent (FR-APT-08 default "evening before + 2 hours before") | Two reminders per booking:<br>• **evening before** at 19:00 clinic time on the day before;<br>• **before the visit** a set number of hours before the slot, or before the session's start for tokens.<br>**Skipped** when the due time is less than 60 minutes after the booking or not before the visit; the confirmation has just said it. **Quiet hours** apply as for follow-ups: a 07:00 reminder for a 09:00 visit goes at 08:00, and one that the deferral would push to or past the start is not sent. Walk-ins get none | B: one reminder only (the PRD asks for two). C: a reminder the morning of the visit at a fixed hour (wrong for evening sessions) |
| 3 | Configuring them (FR-APT-08 "configurable") | **Per clinic, by the owner**, on the Schedule settings page: *Evening before* on or off, and *Before the visit* off or 1–6 hours (default on and 2). Two columns on `clinics`, changed through the existing `PATCH /clinic` (`CLINIC_MANAGE`) and audited as `clinic.updated`. A change applies to bookings made or moved after it; reminders already scheduled stay as they are | B: per doctor (no demand yet). C: re-plan every future reminder on a change (a bulk job for a rare action) |
| 4 | Keeping them in step with the booking | **The notification service schedules them**, since it already receives the events in the booking's transaction. `AppointmentBooked` creates the reminders. `AppointmentRescheduled` cancels the old appointment's and creates the new one's. `AppointmentCancelled` cancels them. Each change audits `reminder.scheduled` or `reminder.cancelled` as SYSTEM. **At send time** the job also checks that the appointment is still `BOOKED` and its session `OPEN`. Otherwise the reminder is cancelled by the system with `REM_APPOINTMENT_CHANGED`: an arrival, a no-show, or a session closed by leave. Staff may cancel one on the profile; moving one is refused with `REM_FOLLOWS_APPOINTMENT` (409, "move the appointment instead"). **No backfill:** bookings made before P8 ships get none | B: a sweep that finds due appointments every 5 minutes (a second source of truth beside the reminder rows; no per-reminder status to show) |
| 5 | The message (FR-MSG-04) | New template **`appointment_reminder`** (utility, English and Hindi, version 1): "Reminder: your appointment at {{clinic_name}} with {{doctor_name}} is {{date_time_or_token}}. To change it, call {{clinic_phone}}." With the existing variable kinds, it is the same for both reminders, plus an SMS wording for the fallback. It needs Meta approval (L-02); the console sends it until then | B: two templates, "tomorrow" and "today" (twice the approvals for a word) |
| 6 | Bookings to move after leave (FR-APT-09) | **A derived list, not a new table:** the live appointments (`BOOKED` or `ARRIVED`) from today on whose session is `CLOSED`. That covers leave and a changed weekly schedule alike.<br>• **API:** `GET /api/v1/appointments/to-move?doctor_id` (`APPOINTMENTS_MANAGE`), each with the patient's code, first name and masked phone, the doctor, the old place and the reason (`LEAVE` or `SCHEDULE_CHANGED`).<br>• **Web:** a *Bookings to move* page reached from a Today tile ("3 bookings to move") for the front desk and the owner, and a banner on the queue for that day. Each row has *Reschedule* (the existing drawer, the patient and doctor chosen) and *Cancel* (reason *Doctor unavailable* preselected).<br>• **Telling staff:** a new in-app kind `schedule.bookings_to_move` goes to the front desk and owners when a leave or schedule change closes booked sessions ("Dr. Sample on leave 24 Oct: 3 bookings to move"), except to the person who made it | B: cancel them all automatically (patients lose their place without a word). C: refuse leave over booked days (leave is a fact; the owner then cannot record it) |
| 7 | Telling the patient (FR-APT-09 "patients are notified") | **Rescheduled:** the existing booking confirmation goes for the new place (P7, unchanged). **Cancelled by the clinic:** with reason `DOCTOR_UNAVAILABLE` or `CLINIC_REQUEST`, the service enqueues `send_cancellation_notice`, a new clinic job with key `appointment_cancelled:{appointment}`. It uses the new template **`appointment_cancelled`** ("Your appointment at {{clinic_name}} with {{doctor_name}} on {{date_time_or_token}} is cancelled. Please call {{clinic_phone}} to book again."). Consent is re-checked at send time, and quiet hours defer it to 08:00. A patient's own cancellation, a duplicate and `OTHER` send nothing. Needs L-02 | B: a message for every cancellation (a patient who cancelled does not need telling). C: in-app only (patients have no app yet; M6b) |
| 8 | The owner's audit log (FR-AUD-03) | **A new permission `AUDIT_VIEW`, owners only.**<br>• **API:** `GET /api/v1/audit-events?from&to&category&actor_user_id&cursor` returns 50 a page, newest first, with a keyset cursor on `(occurred_at, id)` and a range of at most 92 days. `GET /api/v1/audit-events/export?from&to` returns CSV of at most 92 days and 20,000 rows; cells starting with `=`, `+`, `-` or `@` are prefixed with `'`. Both run through a reviewed read-only `SqlAlchemyAuditReader` that always filters by the request's clinic, with tenancy-suite cases.<br>• **Rows:** the time in the clinic's zone; who (the member's current name and role, or "MediEase support" for ops, "System", "Patient link"); the action as words from a catalogue grouped into categories (Sign-in, Team, Patients, Appointments, Clinical records, Prescriptions and links, Messages and reminders, Schedule, Settings); the record (type, and the patient's code for patient records); and the allow-listed metadata. IP hashes are never shown.<br>• **Exports are audited** (`audit.exported` with the range and row count, FR-AUD-01 "data exports"); viewing is not.<br>• **Web:** *Audit log* in the owner's menu (`/settings/audit`): filters, *Load more* and *Export CSV* | B: let doctors see their own actions (later, if asked). C: export as PDF (CSV opens in a spreadsheet, which is what an owner does with it). D: show raw JSON metadata (unreadable, and new keys would appear unreviewed) |

Fixed points:

- **Migration `0024`:**
  - `reminders`: kind and source CHECKs, `appointment_id` and its CHECK, `created_by` nullable,
    and an index on `(appointment_id)`;
  - `clinics`: `reminder_evening_before` (boolean, default true) and `reminder_hours_before`
    (smallint 0–6, default 2);
  - `notifications` and `notification_preferences`: the kind CHECKs gain
    `schedule.bookings_to_move`.
- **Code.**
  - `domain/reminders/rules.py`: `appointment_reminder_times`.
  - `application/notifications/service.py`: schedules and cancels the reminders and enqueues
    the cancellation notice.
  - `SendReminder`: chooses its template by kind and checks the appointment.
  - `application/appointments/to_move.py`.
  - `application/audit/` read use cases with the action catalogue.
  - `SqlAlchemyAuditReader`.
  - `AUDIT_VIEW` in the permission matrix.
- **Contract 0.28.0:** the clinic's two reminder settings; `kind` and `appointment_id` on
  `Reminder`; `GET /appointments/to-move`; both audit routes; the new notification kind.
- **Errors:** `REM_FOLLOWS_APPOINTMENT` (409), `AUD_RANGE_TOO_LONG` (422). `REM_APPOINTMENT_CHANGED`
  is a reminder's error code, not an HTTP error.
- **Templates:** `appointment_reminder` and `appointment_cancelled` in `templates.yaml` (L-02 adds
  both to the approval list).
- **Docs:** DATA_MODEL, API, ERRORS, the appointments and reminders specs (R16/R17 gain "listed
  for the front desk"), RUNBOOK §18 (the owner's view) and a new RUNBOOK entry for reminders that
  did not go, SECURITY_AND_COMPLIANCE (the export), and ADR-0017's consequences (appointment
  reminders are scheduled by the service).
- **Unchanged:** follow-up reminders, the booking confirmation, quiet hours, the SMS fallback rule,
  and every existing test and journey.

Planned verification:

- **Unit:**
  - reminder times for slots and tokens: evening before, hours before, the 60-minute skip,
    quiet-hours deferral and the not-before-the-visit skip;
  - the audit catalogue covering every `AuditAction` (a test fails when an action has no label);
  - CSV cell escaping.
- **Integration (PostgreSQL):**
  - a booking schedules two reminders in its transaction, and a rollback leaves none;
  - a reschedule cancels the old reminders and schedules the new ones;
  - a cancellation cancels them;
  - the send job skips and cancels an arrived or leave-closed booking;
  - moving an appointment reminder is a 409;
  - a clinic with both settings off schedules none;
  - leave over a booked day lists the bookings, tells the desk and the owners, and a cancellation
    with *Doctor unavailable* enqueues the notice while a patient's own cancellation does not;
  - the audit list filters, pages and stays within the clinic;
  - another clinic's events never appear (tenancy suite);
  - the export is CSV, is bounded and is audited;
  - front desk and doctors get 403.
- **Playwright:**
  - the owner adds leave on a booked day; the front desk sees the Today tile, opens *Bookings to
    move*, reschedules one patient and cancels another, and the list empties;
  - the owner opens *Audit log*, filters to Appointments and sees those changes with names, then
    exports CSV;
  - failure path: the front desk opening `/settings/audit` is told it is for owners.
- **Gates:** `make lint typecheck contract-check test`, `make smoke` and `make e2e`.

### M6a-P8 — as built (24 Oct 2026)

Approved A on all eight. Where the build differs from the text above:

- **No reminders for a patient without WhatsApp consent at booking.** The send job still reads
  consent again; skipping at booking keeps the profile free of rows that could never send.
- **A second reminder code, `REM_TOO_LATE`.** A reminder whose time could not be kept is not
  scheduled at all; if the worker only reaches one after the visit started (an outage), the system
  cancels it with this code instead of sending.
- **The bookings-to-move notice comes from three changes**: adding leave, removing an extra
  session, and replacing the weekly schedule, and only when booked sessions were kept.
- **The Today tile shows only when something needs moving.**
- **The audit reader is a reviewed tenancy exception**, not a `TenantScopedRepository`:
  `audit_events.clinic_id` is nullable and the table is append-only. It is reachable only as
  `uow.tenant(clinic).audit_log` and filters every table it joins by that clinic.
- **The booking drawer's reschedule target needs only the appointment ID**, so *Bookings to move*
  reuses it from its own rows.
- **The cancellation notice is a message of `source_type` `APPOINTMENT`**, beside the booking
  confirmation.
- **The SMS fallback also covers appointment reminders** (behind the same flag).

What was built:

- **API.**
  - Migration `0024`: `reminders` gains kind and source `APPOINTMENT`, `appointment_id` (CHECKs,
    index) and a nullable `created_by`; `clinics` gains `reminder_evening_before` and
    `reminder_hours_before` (0–6); the notification kind `schedule.bookings_to_move`.
  - `domain/reminders/rules.py::appointment_reminder_times`; `Reminder.for_appointment`;
    `Clinic.change_reminders`; the audit catalogue `domain/audit/catalogue.py` (a test fails when
    an action has no words); `Permission.AUDIT_VIEW` (owners).
  - `application/reminders/appointment.py` (schedule, cancel, the send-time check);
    `SendReminder` and the SMS fallback send `appointment_reminder` for these;
    `application/messaging/cancellation.py` (`send_cancellation_notice`,
    `appointment_cancelled`); both templates in `templates.yaml` (en, hi, and an SMS wording for
    the reminder).
  - The notification service schedules, replaces and cancels the reminders on the appointment
    events, enqueues the cancellation notice, and handles the new `BookingsToMove` event
    (published by `AddException`, `RemoveException` and `ReplaceSchedule`).
  - `PATCH /reminders/{id}` refuses moving an appointment reminder (`REM_FOLLOWS_APPOINTMENT`).
  - `GET /appointments/to-move` (`ListBookingsToMove`); Today's `bookings_to_move`.
  - `GET /audit-events` and `/audit-events/export` (`ListAuditEvents`, `ExportAuditEvents`,
    `SqlAlchemyAuditReader`); errors `AUD_RANGE_TOO_LONG`; audit action `audit.exported`.
  - Clinic reminder settings on `GET`/`PATCH /clinic`. Contract 0.28.0.
- **Web.**
  - *Appointment reminders* card on Schedule settings (owners).
  - `/bookings-to-move` (`BookingsToMove`): who and where, reason, *Reschedule* (the booking
    drawer) and *Cancel* (*Doctor unavailable* preselected); the Today tile; a banner on the queue
    under a closed session that still has patients.
  - `/settings/audit` (`AuditLog`): range and category filters, *Load more*, *Export CSV*; *Audit
    log* in the owner's menu; others are told it is for owners.
  - Reminders on the profile name their kind; an appointment reminder has no *Move*.
- **Verification.**
  - **Gates.** `make lint typecheck contract-check test` green. API: 1,810 tests, 97.48% package
    coverage. Web: 58 files, 546 tests.
  - **New tests.** `test_appointment_reminders_http.py` (9: the two times, consent and settings,
    reschedule and cancel, the 409, sending the template, leave cancelling a due reminder, the
    list, the notice, the cancellation notice and its send, a schedule change, another clinic);
    `test_audit_log_http.py` (11: words and people, filters and paging, bad ranges and filters,
    owners only, another clinic, the CSV and its own audit); unit tests for the times, the
    catalogue, the clinic settings and the title; the tenancy suites (the audit log case), migration
    `0024` up and down; web tests for the settings card, the list, the tile and the audit page.
  - **Stack.** `make up`, `make seed` and `make smoke` green. Full Playwright suite 32/32, with:
    - `bookings-to-move.spec.ts`: the owner adds leave on a day two patients are booked; the front
      desk opens the Today tile, moves one to the next day and cancels the other as *Doctor
      unavailable*, and both leave the list (the leave is removed afterwards);
    - `audit-log.spec.ts`: the owner filters to Appointments, sees the front desk's cancellation
      in words and exports CSV; failure path: the front desk has no menu item and is told the log
      is for owners.
  - **Run note.** As in P7, Playwright ran with the same image mounting the Windows path. The
    known timing test `test_suggestions_over_20000_issued_lines_answer_quickly` failed once on
    load (177 ms against 150 ms) in the first full run and passed in the final run.
  - **Not verified.** Real WhatsApp sends of `appointment_reminder` and `appointment_cancelled`
    (L-02); the queue's closed-session banner is not checked in a browser journey.
