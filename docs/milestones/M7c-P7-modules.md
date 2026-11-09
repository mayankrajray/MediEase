# M7c-P7 — Design system and module redesign: implementation record

Plan: `docs/milestones/M7c-P7-design-system-plan.md`. System: `DESIGN.md`. Product: `PRODUCT.md`.

| Step | Status |
|---|---|
| Phase 1 — shared design system | ✅ built 9 Nov 2026 (below) |
| M1 Marketing landing page | ✅ built 9 Nov 2026; phone header fixed after the developer's review |
| M2 Authentication | ✅ built 9 Nov 2026, awaiting the developer's review |
| M3 Clinic dashboard | ☐ |
| M4 Appointments and queue | ☐ |
| M5 Patient management | ☐ |
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
