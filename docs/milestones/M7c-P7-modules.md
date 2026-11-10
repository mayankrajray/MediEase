# M7c-P7 — Design system and module redesign: implementation record

Plan: `docs/milestones/M7c-P7-design-system-plan.md`. System: `DESIGN.md`. Product: `PRODUCT.md`.

| Step | Status |
|---|---|
| Phase 1 — shared design system | ✅ built 9 Nov 2026 (below) |
| M1 Marketing landing page | ✅ built 9 Nov 2026; phone header fixed after the developer's review |
| M2 Authentication | ✅ built 9 Nov 2026; approved by the developer 10 Nov 2026 |
| M3 Clinic dashboard | ✅ built 10 Nov 2026 |
| M4 Appointments and queue | ✅ built 10 Nov 2026; phone fixes approved by the developer 10 Nov |
| M5 Patient management | ✅ built 10 Nov 2026; approved by the developer 10 Nov |
| M6 Appointment booking | ✅ built 10 Nov 2026 |
| M7 Patient portal | ✅ built 10 Nov 2026 |
| M8 Prescriptions (and the PDF's layout 4 with the MediEase emblem) | ☐ |
| M9 AI assistant | ☐ |
| M10 Billing | ☐ |

## Decisions (developer, 9 Nov 2026)

All recommendations of the plan approved: Manrope on every surface including patient pages;
Lucide icons; the wordmark re-set in Manrope and the emblem on the prescription PDF through a new
layout version; partner names, logos and quotes never published; product facts recorded in
`PRODUCT.md`. The timeline is the developer's.

## Phase 1 — shared design system (built 9 Nov 2026)

**What changed**

- Tokens in `src/app/globals.css`: the brand scale on `#147D72` (all of 50–950), the `slate-*`
  neutrals retuned to the brand greys (so every existing screen moved without markup changes),
  semantic colours, shadows, `ease-brand`, and the named text styles as utilities.
- Manrope self-hosted (`src/app/fonts`, 25 KB, OFL) through `next/font/local`
  (`src/app/fonts.ts`), applied by the landing, sign-in, apply, clinic, ops and design-system
  surfaces. **Not on patient pages**: measured with it, `/portal/medicines` was 230 KB, `/portal`
  223 KB and `/c/sample-clinic` 215 KB against the 200 KB budget; without it they are 179–196 KB.
  The approval was "everywhere if the budget allows", so patient pages keep the system font.
- Brand: the logo files copied to `apps/web/public/brand/`; the `Logo` component replaced the
  eight hand-drawn "M" marks (landing, apply, auth frame, portal sign-in, portal shell, find,
  public clinic page, clinic and ops shell); favicon, `icon.svg` and `apple-icon.png`; the proxy
  lets the icons, `/brand/` and `/design-system` through without a session.
- Components restyled: Button (new `lg`, `loading`, `icon`), Field family (focus, invalid and
  disabled states, error icon), Card (`description`), table, PageHeader (`breadcrumbs`),
  EmptyState (`icon`), Dialog, Drawer (icon close button, still named "Close"), ErrorNotice,
  AuthFrame, Shell header and sidebar.
- Components added: Alert, Toast (Radix, polite), Tooltip (Radix), Breadcrumbs, Pagination,
  Avatar, KeyValue, Spinner, Logo/Emblem, DateField, TimeField, ErrorSummary, ConfirmDialog.
- Dependencies added (exact pins): `lucide-react` 1.70.0, `@radix-ui/react-toast` 1.3.1,
  `@radix-ui/react-tooltip` 1.4.1. `tailwind-merge` was tried and removed (8 KB on every patient
  page).
- Showcase `/design-system` with every component in its states, sample data only.
- Docs: `DESIGN.md`, `PRODUCT.md`, `THIRD_PARTY.md`, `components/ui/README.md`.

**Protected:** no API, schema, business-rule or test-selector change; accessible names of every
control kept (the drawer's close button is still "Close").

**Verification (9 Nov 2026)**

| Check | Result |
|---|---|
| `make test-web` | 88 files passed (11 new design-system tests) |
| `make lint-web typecheck-web contract-check` | clean |
| Playwright, all 55 journeys, API on the console model, fake Google, console WhatsApp and Mailpit (as CI) | all passed: 50 in one run; 4 booking journeys hit the booking-request rate limit from repeated runs and passed on rerun; `discovery` failed once on axe `document-title` while the page was still navigating, then passed twice |
| axe (WCAG 2.1 AA) on the retuned colours | passes on every journey that runs it, and on `/design-system` at 1366 and 360 px |
| Patient budget (NFR-02) | `/` 194 KB, `/find` 163 KB, `/c/…` 180 KB, `/portal` 189–190 KB, `/portal/medicines` 194 KB, `/p/…` 156 KB: all under 200 KB |
| `impeccable detect` on the changed UI | no findings |

**Open:** the mint leaf of the logo is nearly invisible on white (DESIGN.md §6); the outlined
wordmark and the PDF emblem come with M8.

## After the Phase 1 review (developer, 9 Nov 2026)

- Phase 1 passed review. The developer's UX principles are binding and recorded in DESIGN.md §8a
  (four states, feedback placement, forms, empty states, graceful degradation, success feedback,
  Jakob's and Hick's laws, "trust over convenience"); PRODUCT.md principles updated.
- The logo's leaf is `#86D0C2` on light backgrounds (component, `public/brand/mediease-icon.svg`,
  `mediease-logo.svg`, `src/app/icon.svg`); the dark versions keep `#DDF3EE`.
- Every clickable control shows the pointer cursor (a base rule for buttons, tabs, menu items,
  selects, summaries, labels, checkboxes and file inputs; not-allowed when disabled), and buttons
  get a hover state: colour, a 1 px lift and a deeper shadow, pressed 1 px on click, none with
  reduced motion.

## M1 — Marketing landing page (built 9 Nov 2026)

**Existing:** one long page of equal cards (problem, features, roles with a single-side border,
patients, pricing, trust, FAQ), two competing calls to action in the hero, its own button and card
styles, a hand-drawn logo, no motion. Workflows kept: the clinic path (*Apply*), the patient path
(*Find a doctor*, the patient app's sign-in), the language switch, the PII-free analytics events
(`data-analytics`), the emergency note, indexable metadata.

**Research:** Practo's public pages (`docs/milestones/M7c-P7-practo-research.md`): short benefit
tiles, plain words, a grouped footer; no testimonials, health content or app push taken.

**Plan (landing-page-design skill, layout A: classic hero and sections):** one offer (MediEase for
the clinic's day) to one buyer (the clinic owner or administrator) with one primary action
(*Apply to join MediEase*); the patient path keeps its own section.

| # | Section | Notes |
|---|---|---|
| 1 | Floating translucent navigation | Logo, anchors, staff sign-in, language, *Apply to join*; full-height phone menu on `<details>` (no script), icon morphs, links rise 60 ms apart |
| 2 | Hero | Heading one sentence a line (680 px), subheading, *Apply* primary, *Find a doctor* as a text link (not a competing button), three true proof points, a drawing of the queue screen made of the product's own components with sample patients |
| 3 | Problem | Three numbered cards |
| 4 | Tagline reveal (B11) | "Fewer calls to the front desk. More time for the patient in front of you." Words turn from slate-400 (3.4:1, AA for large text) to full colour in reading order |
| 5 | For clinics | The 5-minute promise, four benefit cards with icons |
| 6 | How joining works | Apply → we check every doctor (2 working days) → start your first day |
| 7 | A screen for each person | Owner, doctor, front desk; *Apply* again with the demo offer |
| 8 | For patients | *Find a doctor*, the patient sign-in, the emergency note |
| 9 | Pricing | The three pilot plans from `PLANS`; no invented badges |
| 10 | Privacy and safety | Four facts with icons |
| 11 | Questions | Six, one added (WhatsApp messages at cost) |
| 12 | Final call to action | Dark brand band, *Apply to join MediEase* |
| 13 | Footer | Grouped by audience, only working links, a faint emblem |

**Motion:** `LandingMotion` (a few hundred bytes, no library): sections below the fold rise 32 px
and fade in once (IntersectionObserver); the tagline's words colour in on scroll (one
rAF-throttled listener). Nothing is hidden without JavaScript or with reduced motion.

**Copy:** English and Hindi in `src/lib/i18n/landing.ts` (new: proof, preview, tagline, how
joining works, final call to action, footer groups, one FAQ). No partner names, quotes, logos,
statistics or invented prices. The Hindi needs the same native review as the rest (L-07).

**Gaps found (not built, need content):** privacy policy and terms pages (the skill's footer
requirement; text from counsel, L-04), a custom 404, an OG image.

**Verification (9 Nov 2026):** lint, typecheck, contract check clean; landing and component tests
pass (one new landing test: one primary action above the fold, the preview, the three steps,
nothing hidden without motion); Playwright `discovery` (landing at 360 px to a booking request,
axe) passes; `/` first load **202 KB of the 204.8 KB budget**, so the next landing change must
measure first; `design-system` journeys pass. Screenshots reviewed at 1366 px.

### M1 follow-up (developer's iPhone SE check, 9 Nov 2026)

"Apply to join" showed in the phone header (`hidden` lost to the button's own `inline-flex`; cx
does not merge classes): it is now wrapped and hidden below 640 px. The open phone menu was a thin
strip over the hero: the bar's backdrop-filter made it the containing block of the menu's fixed
panel. While the menu is open the bar drops its blur and the page stops scrolling; choosing a link
closes the menu. `e2e/landing.spec.ts` checks both at 375×667 and the desktop header.

## M2 — Authentication (built 9 Nov 2026)

**Screens:** staff sign-in, forgot and reset password, invitation; the clinic chooser; patient
sign-in, sign-up, forgot and reset password, email confirmation; both signed-out frames.

**Existing problems (inventory):** checks only on submit; the reset form's "not the same" message
on the wrong field and never cleared; no error summary, focus or announcement for client errors;
no character counts; the 12-character rule a static hint (and the invitation relied on the
browser's tooltip); two forms with hand-built inputs; only staff sign-in could show the password;
native validation on some forms and not others; the locked "Sign in" button not described by the
lock message.

**Shared changes:** `TextField` gains `onBlur`, a character `counter`, `requiredMark`, an extra
description and a ref; new `PasswordField` (a *Show password* / *Hide password* button in words,
`aria-pressed`; rules that tick off as typed, with each rule's state for screen readers; an
`invalid` state for a wrong password whose words are in the alert; `errorLive` for a message that
must be announced); `looksLikeEmail`; `formWords` (English and Hindi) for the shared messages.

**Per screen (behaviour and API calls unchanged):**

| Screen | Change |
|---|---|
| Staff sign-in | Inline "Enter your email or phone number." / "Enter your password." on an empty submit, focus on the first, nothing sent; loading button; while locked the disabled button is described by the lock message; the labels keep their exact words |
| Forgot password | The address is checked when leaving the field and before sending; the confirmation is a success message |
| Reset password | Rules tick off as typed; each field checked on leaving it and re-checked while fixed; "not the same" on the second field; focus to the first problem |
| Invitation | `PasswordField` with the rules; a short password is caught before sending (it used to go to the API); the mismatch stays an announced alert on the second field; a skeleton while the invitation loads |
| Patient sign-in | Email checked on leaving it; *Show password*; a wrong password marks the field |
| Patient sign-up | Every field checked on leaving it, the name's "n of 200" count, the rule ticking off, focus to the first problem, everything kept on failure; the API's own field reasons still show under the fields |
| Email confirmation | Success message; loading button |
| Clinic chooser | Clinic cards with initials, hover lift and a chevron; the current clinic ringed |
| Signed-out frames | The logo links back to the home page; the design system's card |

**Test changed for a real behaviour change:** `AcceptInviteForm.test.tsx`: a short password is now
caught in the form (no API call, focus on the field); the API's refusal is still tested with a
long password.

**Verification (9 Nov 2026):** lint, typecheck and contract check clean; `make test-web` 89 files
passed (5 new M2 tests); `make smoke` passed; Playwright 56 of 57 journeys passed on the CI fakes.
The one failure, `clinic-application`, was the API's limit of 5 applications per IP per day
(`ONB_RATE_LIMITED`, "Too many applications") from today's repeated runs, not this change; it
passed earlier on 9 Nov. The API suite was last run in full on this branch at `7f4578b` (2,573
passed, 96.05%); no API file has changed since.

## M3 — Clinic dashboard (built 10 Nov 2026)

The developer approved M2 by asking for M3–M10 in one run (10 Nov 2026): every module built in
order, the full API suite and `make smoke` after each, and the full `make e2e` once at the end.
No per-module review gate this time; each module below is reviewable on its own commit.

**Screens:** Today (owner, doctor, front desk, the practising owner's two views), the clinic and
ops shell (sidebar, phone header, menu drawer), the notification bell's drawer and the
notification settings page.

**Existing problems (screenshots at 1366 and 375 px, 10 Nov):** five equal count cards and a team
row of half-width cards (the "hero metric" template); cards inside cards ("Follow-ups and
messages" held four bordered tiles, each session a bordered box inside "Sessions"); the quick
actions on a row of their own; a tall empty band under *Next up* because the right column set the
row height; every list rose in on load (orchestrated entrance, against DESIGN.md §4); two filled
*Register* buttons on the front desk's screen (header and quick action); fifteen undifferentiated
sidebar links for an owner; the booking-requests count overlapping its label; on a phone the bell
wrapped to a line of its own; the team counts failed silently (rendered nothing).

**Changes (behaviour and API calls unchanged):**

| Area | Change |
|---|---|
| Page header | The quick actions sit at the top right of the page (the first is the page's one primary action) |
| Counts | One strip: a single surface with hairlines between the five counts, each still a link named "Waiting 3 …"; every count has a hint ("With the doctor now", "Seen today", "Did not come") |
| Layout | Two independent columns from 1024 px: the day's work (*Next up*, *Sessions*) wide, what to follow up narrow (*Team*, *Follow-ups and messages*); on a phone the day's work comes first |
| Follow-ups and messages, Team | List rows (label and hint on the left, the number on the right, a chevron when it opens a screen) instead of cards in a card; `StatTile` gained `layout="segment" | "row"` keeping the reading order label, number, hint |
| Sessions | One row per session: hours with a clock icon, the doctor (not repeated in a doctor's own view), status in words, the booked line, and a capacity bar that repeats the line for the eye (decorative) |
| Empty states | *No one is waiting* offers *Book an appointment* (roles that book); *No sessions today* offers *Open schedule settings* (roles that manage schedules) |
| Team | Its own section with loading, error (with *Try again*) and ready states, so a failure no longer disappears or touches the rest of Today |
| Last 7 days | Each bar labelled with its number, a baseline, table header on the muted surface |
| Motion | No entrance stagger; a changed number still slides in; the bars grow when the tab opens |
| Sidebar | Lucide icons and five groups (Daily work, Patients, Billing, Clinic, Help and alerts) without reordering any link; 36 px rows so an owner's sixteen links fit 768 px; sticky with its own scroll; 256 px wide; the waiting count inline after the label |
| Header | *Register patient* is secondary with an icon (one primary per page) and icon-only below 640 px (the name stays); the clinic name truncates and the role pill hides below 640 px, so the bell stays on the first line; the clinic switcher fits a phone; *Menu* has an icon; ops links have icons |
| Notifications | Drawer: Lucide bell, an unread dot beside the "Unread:" words, the empty state's icon. Settings: a saved switch is confirmed in the success tone beside the switches |

**Not added:** `recharts` (planned for M3). The only chart is seven bars with a table beside
them; drawing them in CSS costs nothing on the clinic bundle and keeps the table as the
accessible source.

**Tests:** the existing Today, workspace, bell and component tests pass unchanged (link names,
regions, list names and nav order kept).

## M4 — Appointments and queue (built 10 Nov 2026)

**Screens:** the queue board (front desk and doctor), its walk-in, no-show, cancel and attach
dialogs, booking requests (open and answered) with *Accept*, *Propose another time* and
*Decline*, bookings to move, the doctor's *My schedule*, the owner's schedule settings, and the
patient's live token page (`/q/…`).

**Existing problems:** the queue's title, filters and actions on one wrapping row, with the
primary *Book* in the middle of the day buttons and *Add walk-in* in a one-off style; the action
outcome as bare green text; "Loading the queue…" as a line of text; no retry on a failed queue or
doctor list; the no-show dialog and cancel dialog built by hand; *Cancel appointment*, *Accept and
book*, *Offer this time* and *Decline request* disabled until complete, so the person was not told
what was missing (DESIGN.md §8a); the decline and record forms hand-built inputs; schedule
settings with hand-built inputs and buttons, no loading state, a plain "No doctors yet." and an
unbounded leave list (63 rows in the demo data); the live token page without the brand.

**Changes (behaviour and API calls unchanged):**

| Area | Change |
|---|---|
| Queue header | Title and date left; *Add walk-in* (secondary) then *Book* (the one primary) at the top right, each with an icon |
| Queue filters | Doctor and day in one bar: *Previous day* and *Next day* with chevrons (icon only below 640 px, names kept), the date, *Today* when away from today |
| Queue states | Every outcome in one polite `StatusMessage` (success tone, still "Asha Rao marked arrived at 10:42."); a row-shaped skeleton while loading; *Try again* on a failed queue and doctor list; an icon on each empty state |
| Queue rows | Shared `Button`s; tabular codes and dues; the closed-session warning in the warning tone with an icon |
| No-show | `ConfirmDialog` (names kept: *Go back*, *Mark no-show*) |
| Cancel, Decline | Reasons as choice cards; the note a `TextField` with "n of 200"; the action stays enabled and, pressed too early, says "Choose why the appointment is cancelled." / "Say why in the note." / "Choose what the patient should be told." under the field, moves focus there and sends nothing; loading buttons |
| Accept, Propose | The record and the time as choice cards; the new record on the shared fields; pressed too early, "Choose which record this is, or create a new one.", "Fill in the new record's name, sex and age." or "Choose the time to offer."; loading buttons; a retry when the record lookup fails |
| Booking requests | `Segmented` (Open, Answered), `StatusMessage`, row skeleton, "You're all caught up." on an empty inbox, actions kept on one line from 768 px |
| Bookings to move | `StatusMessage`, row skeleton, icon empty state; *Cancel* secondary beside the primary *Reschedule* (the cancel dialog still asks) |
| My schedule | Every weekday listed, a day off reads "Not working"; leave as a badge; icon empty states with what to do |
| Schedule settings | Shared inputs, labels and buttons; cards on the design system; a skeleton while loading; *Try again*; a leave list longer than ten collapses behind *Show all N*; the kept-sessions warning in the warning tone |
| Live token page | The logo and the language switch on top, the place card on the semantic tones (success for "your turn", danger for cancelled), problems as `Alert`s; still the system font and no Motion (patient budget) |

**Shared additions:** `StatusMessage` (the screen's live region, success tone), `ListSkeleton`
(row-shaped loading with its status line), `Segmented` (toggle group), `CHOICE_CARD` and
`CHOICE_INPUT` (radio and checkbox cards), `INPUT_BASE` (an input without full width; `cx` does not
merge classes, so `w-24` beside `w-full` lost).

**Tests changed for a real behaviour change:** `QueueBoard.test.tsx` (D14): the cancel button is
enabled and an early press shows the two messages, moves focus to the note and sends nothing;
`BookingRequests.test.tsx` (R36): an early *Accept and book* says to choose the record and sends
nothing.

### M4 follow-up (developer's iPhone SE check, 10 Nov 2026)

The developer found booking requests unusable on a 375 px phone: the page scrolled sideways
(461 px wide), the phone number and reason ran out of their cards, and every badge became a tall
ellipse; the notification drawer also scrolled sideways. Most users work on a phone, so phone
quality is not negotiable.

**Causes:** the shared phone-card layout of `me-table` made each named cell a flex row, so a
cell's several lines (date, doctor, "first asked") sat side by side and long values (names with
digits, `+91…` numbers) could not shrink; `StatusBadge` wrapped its words inside a fully rounded
pill; drawers and dialogs let one long word widen the panel.

**Fixes:**

| Where | Change |
|---|---|
| Every phone card (`globals.css`, `.me-table`) | A named cell is a grid: the column's name in a 6.5 rem first column, everything the cell holds stacked in the second (`minmax(0, 1fr)`); cards and cells `min-width: 0` and `overflow-wrap: anywhere`, so nothing pushes a card wider than the screen and no data is cut |
| `StatusBadge` | One line (`white-space: nowrap`, `max-width: 100%`): a pill stays a pill |
| `Drawer`, `Dialog` | `overflow-x: hidden` on the panel and wrapping content: they scroll only vertically; notification titles wrap |
| Booking requests (one markup, `max-md:` order) | Below 768 px each request is a card built for a phone, with no column names: the patient first (name, age and record, a tappable phone link 44 px tall with an icon), then when and with whom, the reason when there is one, the hold badge beside "Reply by", then *Accept* full width and *Propose time* and *Decline* side by side, all 44 px tall. From 768 px it stays the table, actions on one line |

**Checked:** an overflow audit (each element's right edge against the viewport) at 375×667 on
booking requests, Today with the notification drawer open, the queue and bookings to move:
no sideways scroll anywhere (the only element past the edge is the visually hidden table header
row, clipped). Screenshots at 375 and 1366 px with three fresh requests seeded.

## M5 — Patient management (built 10 Nov 2026)

The developer approved M4 after the phone fixes and asked for the ui-ux-pro-max skill
(`uipro init --ai kiro`, ui-ux-pro-max-cli 2.15.0, MIT) before M5. It installed into
`.kiro/steering/` (git-excluded); `ui-ux-pro-max` loads on demand (`inclusion: auto`) and the six
extra skills it brought (brand, banner, slides, design, design-system, ui-styling) are manual so
they never load unasked. Its UX search was used for the form and record-page checks.

**Screens:** the header patient search, the search results page, Register patient (drawer) and
its duplicate-phone step, the patient profile with its edit form, consent, patient app, and the
appointments, visits, prescriptions, bills, reminders and message-history sections; My patients.

**Existing problems:** registration and editing checked nothing before sending (an empty form
went to the API); hand-built selects and buttons; the age choice as bare radios; no character
count; the profile one long column of equal cards with the code in monospace above the name;
"Loading …" and "No …" as plain lines in every section; results "Searching…" as text and a bare
"No patient matches" with no next step; the patient app's unlink and consent's opt-out in
one-off red styles.

**Changes (behaviour and API calls unchanged):**

| Area | Change |
|---|---|
| Register and edit | `usePatientForm`: each field checked on leaving it and re-checked as it is fixed ("Enter the patient's full name.", "Enter a 10-digit mobile, or the number with its country code.", "The date of birth cannot be after today.", "Enter the age in whole years.", "Enter the parent or guardian's name." for a minor); a submit with problems shows them under the fields, lists two or more at the top, moves focus to the first and sends nothing; everything typed is kept; the API's own field answers still land on the field. Name counts "n of 200"; phone hint says spaces and a leading 0 are fine; age as two choice cards; shared selects; loading buttons; *Cancel* in the drawer |
| Duplicate phone | Warning tone with an icon; each person with initials; *Use this patient* full width on a phone |
| Profile | Breadcrumb; a header with initials, name, the code as a chip, age and sex, *Under 18* and *No messages* badges; from 1024 px the working sections on the left and details, consent and patient app on the right; on a phone details first. The phone link is 44 px tall on a phone. A saved edit says "Details for … saved." A missing patient is an empty state with *Search patients* |
| Profile sections | One card style, `heading-6` titles, row skeletons with their words, dashed empty boxes, the shared success message, shared buttons and inputs; card headers wrap so *Book for …* goes full width on a phone |
| Consent | The state as a badge in words; the question in a quoted box; WhatsApp and SMS as choice cards; opt-out confirm in the danger tone with *Cancel* focused |
| Patient app | Shared buttons, a spinner while checking, the invite link input that wraps on a phone, the QR centred on a phone |
| Search | A search icon, initials and two-line matches 44 px tall, a spinner while searching, "Try the phone number or the code, or register the patient." when nothing matches |
| Results page | Header line with the query; empty start as an empty state; no match offers *Register a new patient*; row skeleton; initials |
| My patients | Search in a filter bar with an icon; row skeleton; initials; icon empty states; *Show more* centred with a loading state |
| Phone cards (all lists) | A badge or button in a phone card keeps its own width (`justify-self: start`) instead of stretching across the card |

**Shared additions:** `RowsSkeleton`, `Avatar size="lg"`.

**Tests added:** `RegisterPatientDrawer.test.tsx`: an empty submit (messages, summary, focus,
nothing sent), a short phone flagged on leaving and cleared when fixed, a future date of birth
caught, the name's count. Existing patient, profile, portal-card and search tests pass unchanged.

**Checked:** screenshots and the overflow audit at 1366 and 375 px on the profile, results (match
and no match), the register drawer and My patients: no sideways scroll.

## M6 — Appointment booking (built 10 Nov 2026)

The developer approved M5 on a phone (profile and Register patient) and asked for M6.

**Screens:** the staff booking drawer (book and reschedule, opened from the queue, a profile,
follow-ups and bookings to move) and its patient picker; the patient side of booking: Find a
doctor, the public clinic page and a doctor's profile with their free times, and the request form
behind them. Patient pages keep the system font and no Motion (200 KB budget).

**Existing problems:** the drawer was one undivided column of hand-built controls, slots as bare
radios with small text, the online-request override in a one-off amber style, and *Confirm
booking* disabled until complete without saying why; the picker without icons or 44 px rows; on
a phone the clinic page put every time below every doctor (a tap on *See times* showed nothing
new on screen), and each session took a full-width button, so a fortnight of times ran to about
6,000 px at 375 px; find, clinic and request pages used one-off borders and text-only problems;
the request form's *Send request* stayed disabled until the phone and the emergency box were
filled, without saying so.

**Changes (behaviour and API calls unchanged):**

| Area | Change |
|---|---|
| Booking drawer | Three numbered steps (Patient, Doctor and day, Time); the chosen patient as a row with initials and *Change patient*; shared doctor select; the date with *Day before* / *Day after* buttons, today as the earliest; sessions as choice cards (token sessions show the next token and places left), slots as a 3–4 column grid of 44 px time chips with *Held* marked; row skeleton; "No sessions on … Try the next day." |
| Confirm | A sticky footer with the choice in words ("Bina Shah · Tue, 10 Nov, next token 2") and a full-width *Confirm booking* (or *Confirm new time*) that stays enabled: pressed too early it says "Choose the patient first." (focus back to the search) or "Choose a time." and sends nothing |
| Override | The held-time question in the warning tone; *Choose another time* (focused) beside a danger *Book anyway …* |
| Patient picker | Search icon, initials, 44 px rows, a spinner, a dashed "No patient matches" box |
| Clinic and doctor page | Sticky header (logo links home); the emergency note in the warning tone with an icon; the clinic card with address icon, *Call*, *Directions*, *Share*, *Copy link* as a two-column grid on a phone, and how requests work in an info box; doctor cards with initials, the fee as a chip, hours and languages with icons, *See times* as the primary button, the chosen doctor ringed; choosing a doctor scrolls their times into view (a jump with reduced motion) |
| Free times | *Go to a day* shortcuts (4 a row on a phone); each day one card with one row per session: the time span and places left beside a short *Ask* (its accessible name is still "Ask for this session"); slot sessions a grid of time chips; skeletons while loading, a danger box with *Try again*, a dashed box when nothing is free |
| Find a doctor | The form as one card with icons in the search and place fields, a full-width *Search* on a phone; *Doctors* and *Clinics* as a segmented switch; result cards with initials, place, a "Free from …" line with an icon, and the profile as a full-width button; problems in the danger tone; an icon empty state |
| Request form | The request summarised as Doctor, Clinic, When (one sentence for screen readers); *Send request* enabled: pressed with problems it says under each field what is missing ("Enter a phone number the clinic can call.", "Enter a 10-digit mobile number…", "Please confirm this is not an emergency…"; age and sex when the clinic asks), lists two or more, focuses the first and sends nothing. Still disabled for an unconfirmed email, described by the note that says so. Sent: a success notice and *Go to My appointments* as a button. New words in English and Hindi (`booking-request.ts`; the Hindi needs the same native review, L-07) |
| Shared | `SelectField` gains `requiredMark`; `PortalCard` on the design tokens |

**Tests changed for a real behaviour change:** `booking-requests.test.tsx` (R9): *Send request*
is enabled; an early press shows both messages, focuses the phone and sends nothing.
**Added:** `Booking.test.tsx`: Confirm before choosing a patient.

**Checked:** screenshots at 375 and 1366 px (drawer, clinic page, times, find) with the overflow
audit: no sideways scroll. First-load transfer at 360 px: `/c/sample-clinic` 184.6 KB (183.5
before the times rework), `/find` 163.9 KB, `/find?q=Sample` 166.2 KB, all under 200 KB.

## M7 — Patient portal (built 10 Nov 2026)

The developer asked (10 Nov 2026) to finish M7–M10 with no backend change, and to park the
discovery and booking redesign as its own milestone, M7d (`M7d-discovery-booking.md`). Find a
doctor, the clinic and doctor pages and the request form are therefore not in this module.

**Screens:** the signed-in portal shell (header, language switch, bell, tab bar), Home (fresh and
linked), My appointments (requests, clinic groups, live queue), My medicines (Today and Courses,
dose marks, reminders, history), My prescriptions (list, reports, bills, the frame of one
prescription), Notifications, Account, and the two record-linking screens. The prescription
itself (`PrescriptionView`) is M8.

**Existing problems:** text-only tabs in 12 px words; links as underlined text with no target
shape; every card the same weight, so the next appointment did not lead; status pills as outlined
ovals in three ad hoc colours; *Previous day* and *Next day* wrapped to two lines at 375 px; dose
states as plain text; checkboxes and radios as bare 20 px inputs; empty states as one sentence;
the verify banner and the unlink confirmation in one-off amber and red.

**Changes (behaviour, API calls, words and accessible names unchanged unless listed):**

| Area | Change |
|---|---|
| Shell | Tabs with a Lucide icon over the word (the icon in a pill when current, a 3 px bar above it); on 768 px and wider one row under the header with the bar below. Safe-area padding for phones with a home bar. Sticky header; the language switch as a pill with an icon; the bell is the Lucide bell with a ringed count. No prefetch of the tab, logo and bell targets (it cost about 7 KB on every first visit; a tap still loads the page) |
| Shared | `PortalCard` gains a decorative `icon`, an `action` at the heading's end and `highlight`; `PortalTitle`; `PORTAL_LINK` (a 44 px text link with a chevron); `DateTile` (weekday, day, month); appointment, request, dose and bill states use `StatusBadge` tones, the word always saying the state |
| Home | The next appointment leads as the highlighted card with *See all* at its heading, the clinic, a date tile and the badge; the latest prescription with *Open* beside it; *Find a doctor* as a whole-card link with one line under it (linked accounts); the assistant as a card. The fresh dashboard keeps one primary action and the invitation question as a disclosure with a chevron |
| My appointments | Clinic cards with *Call the clinic* as a button at the heading; *Upcoming* and *Past* as small labels; rows with date tiles (muted when past); *Live queue* as a primary button with an icon; requests with their badge, the clinic's suggestion in an info box, *Accept this time* and *No thanks* as buttons with a spinner on the one pressed; an empty state with *Find a doctor* |
| My medicines | *Today* / *Courses* as one segmented control; the day as a card with round arrow buttons (named *Previous day* and *Next day*; the words show from 640 px) and the date in the middle, *Today* above it; slot cards with a sunrise, sun, sunset or moon icon; each medicine with a pill icon; the dose state as a badge; *Taken* and *Skipped* as equal buttons; the safety note in the info tone with *Contact your clinic* as a call button; courses, reminder choices and history on the design tokens; empty states |
| My prescriptions | Rows with a document icon, the doctor's name as the link and the whole row as its target, the date and an *Updated by the doctor* badge, a chevron; reports and bills with icons, the bill's state as a badge, *Open* and *Receipt (PDF)* as small buttons; the one-prescription frame with *Back* and a full-width *Download PDF* on a phone |
| Notifications | Rows with a bell avatar (filled when unread) and an unread dot; *Mark all as read* as a button; the empty state with a title (*Nothing yet*) and what will appear |
| Account | The person's card with initials, email and a *Verified* badge, sign-in method; languages, notification switches as choice cards (44 px); times in the shared input style, four across from 640 px; each clinic as a bordered card with address and phone icons; *Unlink* in the danger outline with an icon, the confirmation in the danger tone; *Sign out* full width with an icon; the verify banner in the warning tone |
| Record linking | The invite's person in a card; the last-4 input centred in large monospace; buttons 48 px; *Linked* as a success card |

**Words changed:** `findHelp` ("Search by doctor, clinic or specialty.") under *Find a doctor*;
the notification empty text split into `emptyTitle` ("Nothing yet") and `empty` (what will appear),
English and Hindi (the Hindi needs the same native review, L-07).

**Test changed for a real behaviour change:** `notifications.test.tsx`: the empty state's title
and text are separate.

**Accessibility:** `axe` caught *label-content-name-mismatch* on the first version of the
*Find a doctor* tile (named by its title only); the tile's visible words now name it.

**Checked (10 Nov 2026):** screenshots of the seven screens at 320, 375, 768 and 1366 px with the
overflow audit: no sideways scroll. First-load transfer at 360 px, before → after:

| Page | Before | After |
|---|---|---|
| `/portal` | 191.8 KB | 193.7 KB |
| `/portal/appointments` | 193.3 KB | 192.4 KB |
| `/portal/medicines` | 189.8 KB | 190.9 KB |
| `/portal/prescriptions` | 189.6 KB | 190.9 KB |
| one prescription | 186.7 KB | 190.2 KB |
| `/portal/notifications` | 182.1 KB | 185.4 KB |
| `/portal/account` | 187.8 KB | 190.4 KB |

The first build measured 197–200 KB: the tab bar's five links and the header's two prefetched
their pages on load. Ten decorative icons were also dropped from the medicines screen. Repeated
builds move these numbers by about 3 KB.

Playwright journeys on the CI fakes, all passed: `portal-screens`, `portal-linking`,
`portal-accounts`, `medicine-plan`, `dose-tracking`, `patient-notifications`, `booking-answers`.
