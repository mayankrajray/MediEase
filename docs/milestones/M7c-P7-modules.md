# M7c-P7 — Design system and module redesign: implementation record

Plan: `docs/milestones/M7c-P7-design-system-plan.md`. System: `DESIGN.md`. Product: `PRODUCT.md`.

| Step | Status |
|---|---|
| Phase 1 — shared design system | ✅ built 9 Nov 2026 (below) |
| M1 Marketing landing page | ✅ built 9 Nov 2026; phone header fixed after the developer's review |
| M2 Authentication | ✅ built 9 Nov 2026; approved by the developer 10 Nov 2026 |
| M3 Clinic dashboard | ✅ built 10 Nov 2026 |
| M4 Appointments and queue | ✅ built 10 Nov 2026; phone fixes approved by the developer 10 Nov |
| M5 Patient management | ✅ built 10 Nov 2026 |
| M6 Appointment booking | ☐ |
| M7 Patient portal | ☐ |
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
