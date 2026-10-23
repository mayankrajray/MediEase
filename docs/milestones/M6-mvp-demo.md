# M6a — Auth, staff workspaces and notification core: design notes

Was "M6 — MVP demo: clinic and patient experience" until PRD v1.2 (22 Oct 2026) split M6 into
M6a–M6d. The P1–P2 records below are unchanged; the old P4–P8 (linking, portal, medicine planner,
notifications for patients, public booking) moved to M6b.

| Field | Value |
|---|---|
| Status | Opened 20 Oct 2026 (issue #49, branch `m6/49-mvp-demo`); plan approved by the developer (items D2–D5 of the demo plan); M6-P1 confirmed by the developer 20 Oct 2026 and pushed (draft PR #50); M6-P2 confirmed 21 Oct 2026 and pushed; re-scoped to M6a by PRD v1.2 on 22 Oct 2026; M6a-P3 design approved 22 Oct 2026 (ADR-0015 Accepted) |
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
| P3 | Accounts: Google sign-in for staff and patients, patient email and password, patient sessions kept apart from staff sessions (ADR-0015) | Below (approved 22 Oct 2026) |
| P4 | Email provider behind a port: email verification, password reset by link (FR-AUTH-08, FR-AUTH-05) | At its start |
| P5 | Owner Team page: invite, change role, deactivate (FR-ORG-07) | At its start |
| P6 | Role workspaces (FR-UX-01..05); the practising owner's Owner / Doctor switch with *My Patients* (FR-UX-06); owner as Doctor 1 in the ops wizard (FR-ORG-03) | At its start |
| P7 | Notification service, domain events, in-app channel, notification centre (FR-NTF-02..06) | At its start |
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
