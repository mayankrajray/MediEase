# MediEase design system

| Field | Value |
|---|---|
| Status | **Phase 1 built** (9 Nov 2026): tokens, font, logo and shared components in code; showcase at `/design-system`. Module redesigns follow `docs/milestones/M7c-P7-modules.md` |
| Direction | Modern Healthcare SaaS: calm, light, spacious, trustworthy; brand lives in precise details |
| Plan | `docs/milestones/M7c-P7-design-system-plan.md` |
| Source of truth in code | CSS variables in `apps/web/src/app/globals.css` (`@theme`); components in `apps/web/src/components/ui/` |

One product, one visual language. The landing page may be more expressive; clinic screens favour
density and speed; patient screens favour readability on a 360 px phone.

## 1. Colour

### Brand scale (primary `#147D72`, from the logo)

| Token | Value | Use |
|---|---|---|
| `primary-50` | `#F0F9F7` | Tinted backgrounds, hover on ghost items |
| `primary-100` (primary soft) | `#DDF3EE` | Selected row, current nav item, emblem leaf |
| `primary-200` | `#B8E5DC` | Borders of selected items, focus halo |
| `primary-300` | `#86D0C2` | Decorative only |
| `primary-500` | `#279585` | Charts, icons on white (3:1 or more, not text) |
| `primary-700` (primary) | `#147D72` | Filled buttons, links, focus ring. 5.0:1 on white |
| `primary-800` | `#10645C` | Hover of filled buttons |
| `primary-900` | `#0E504A` | Text on `primary-50/100` |

### Neutrals

The Tailwind `slate-*` palette is retuned to these blue-green greys in `@theme`, so existing
screens follow the brand without markup changes: 50 `#F5F9F8`, 100 `#EEF3F5`, 200 `#E8EEF1`,
300 `#C9D4DA`, 400 `#7D8E97`, 500 `#5F7079`, 600 `#55666F`, 700 `#4A5F6A`, 800 `#20363F`,
900 `#172B35`, 950 `#0F1F27`. New code uses the semantic names below (`bg-surface`,
`border-line`, `text-ink`, …).

| Token | Value | Use |
|---|---|---|
| `background` | `#F5F9F8` | Page behind cards (clinic, ops, portal) |
| `surface` | `#FFFFFF` | Cards, dialogs, tables, inputs |
| `surface-muted` | `#F1F5F6` | Table headers, disabled fields |
| `border` | `#E8EEF1` | Card and table borders, dividers |
| `border-strong` | `#7D8E97` | Input borders (3.4:1 against white, WCAG 1.4.11); `slate-400` |
| `text` | `#172B35` | Primary text, headings |
| `text-secondary` | `#4A5F6A` | Secondary text (6.7:1) |
| `text-muted` | `#64757E` | Hints, captions (4.8:1); never for required information alone |
| `text-on-primary` | `#FFFFFF` | Text on primary fills |

### Semantic

Each status is always shown in **words** as well as colour.

| State | Text / icon | Fill | Border |
|---|---|---|---|
| Success | `#166534` | `#E8F6EE` | `#A7DDBE` |
| Warning / attention | `#7A4E09` | `#FDF3E1` | `#E8A23A` (attention) |
| Error | `#B42318` | `#FDECEA` | `#F2B8B2` |
| Info | `#1F5FAD` | `#EAF2FC` | `#B5CFF0` |
| Disabled | `#8A9AA3` | `#F1F5F6` | `#E1E8EB` |

Attention `#E8A23A` is 2.2:1 on white: a fill, border or icon beside words, never text colour.

## 2. Typography

- **Manrope** on the landing, sign-in, apply, clinic and ops surfaces, weights 400, 500, 600, 700
  (no 800 or 900, no italics in UI chrome). **Patient pages keep the system font**: with Manrope
  their first load measured 213–230 KB against the 200 KB budget (NFR-02, 9 Nov 2026), and the
  developer's approval was conditional on the budget. Devanagari falls back to Noto Sans
  Devanagari (Manrope has no Devanagari glyphs).
- Numbers in tables and tokens use `font-variant-numeric: tabular-nums`.
- Headings `text-wrap: balance`, paragraphs `text-wrap: pretty`.
- Named styles, defined once as utilities (from the landing-page-design skill, Tailwind's scale):

| Style | Size / line | Weight | Use |
|---|---|---|---|
| `heading-1` | 60/60 (48 below 640 px) | 600 | Landing hero only |
| `heading-2` | 48/48 (36) | 600 | Landing section headings |
| `heading-3` | 36/40 | 600 | Landing sub-sections |
| `heading-4` | 30/36 | 600 | Patient page titles |
| `heading-5` | 24/32 | 600 | Clinic page titles |
| `heading-6` | 20/28 | 600 | Card titles, dialog titles |
| `title-3` | 16/24 | 500 | List item titles, nav items |
| `body-3` | 16/24 | 400 | Running text (patient pages, forms) |
| `body-6` | 14/20 | 400 | Dense clinic text, table cells |
| `button-md` / `button-sm` | 16/24 / 14/20 | 600 | Button labels |
| `caption-2` / `caption-5` | 14/20 / 12/16 | 400 | Hints, timestamps, badges |

## 3. Space, radius, elevation

- Spacing: 0, 2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96 px only (Tailwind 0, 0.5, 1, 2, 3, 4, 6,
  8, 10, 12, 16, 20, 24).
- Radius: inputs and buttons `rounded-lg` (8 px); cards and dialogs `rounded-xl` (12 px); badges
  `rounded-full`. Nested shapes: inner radius = outer radius − gap, when above 2 px.
- Elevation: cards `0 1px 2px rgb(23 43 53 / 0.05)`; menus and popovers
  `0 8px 24px rgb(23 43 53 / 0.12)`; dialogs `0 16px 48px rgb(23 43 53 / 0.18)`. No glassmorphism
  outside the landing navigation.
- Borders go all the way round or not at all.

## 4. Motion

- Base curve `cubic-bezier(0.22, 1, 0.36, 1)`. Position and layout 300–500 ms; colour and opacity
  200–300 ms. Only `transform` and `opacity` animate.
- Clinic screens: motion only for state change (a row arriving in the queue, a drawer opening).
- Patient screens: CSS transitions only, no Motion library (200 KB budget).
- Landing page: scroll reveals (32 px rise, 600–800 ms, once) and the tagline word reveal.
- `prefers-reduced-motion`: movement becomes a plain opacity change or nothing.

## 5. Components and states

Every interactive component ships default, hover, active (`scale(0.98)` or 1 px down), focus (2 px
`primary-700` ring, 2 px offset), disabled, loading, success and error states. Targets are at least
24 px; primary touch targets 44 px on patient pages, 40 px on clinic pages.

| Component | Rule |
|---|---|
| Button | `primary` (filled), `secondary` (outlined), `ghost`, `danger`; `sm` 32 px, `md` 40 px, `lg` 48 px; a loading button keeps its width and says what it is doing |
| Field | Label above, "(required)" in words, hint below, error below the hint linked by `aria-describedby`; a form with errors shows an error summary at the top that moves focus to itself |
| Card | `surface`, `border`, 12 px radius, 16–24 px padding; a title makes it a labelled region |
| Table | Header on `surface-muted`, rows 44 px (clinic), tabular numbers, a card per row below 768 px |
| StatusBadge | Words plus one tone; never colour alone |
| Dialog / Drawer | Native `<dialog>` with focus trap and return; ConfirmDialog names the action in its button ("Cancel appointment", never "OK") |
| Toast | For confirmations of background actions only, polite live region, 6 s, never for errors that need action |
| Empty state | What the space is for, and the first action |
| Error | What failed, what to do, and "Ref: <request_id>" (apps/web/CLAUDE.md) |
| Loading | Skeletons shaped like the content; a spinner only inside a button or for waits under 1 s |

## 6. Brand

- Logo files: `apps/web/public/brand/` (copied from `public/branding/` at the repository root, which
  the web app cannot serve). In the interface the logo is the `Logo` component: the emblem as
  inline SVG with the wordmark in Manrope, so no file is fetched. The favicon and app icons are
  `src/app/favicon.ico`, `icon.svg` and `apple-icon.png`.
- Use the full logo in headers, the emblem alone on a phone header (`compact`) and as the favicon,
  `tone="onDark"` on dark fills.
- Clear space around the logo: the height of the emblem's head circle. Never stretch it or add
  effects.
- Next: the wordmark outlined in Manrope for the static files, and the emblem on the prescription
  PDF as layout 4 (M8, Prescriptions module), so issued prescriptions keep their look.
- The leaf is `#86D0C2` on light backgrounds (developer, 9 Nov 2026: the delivered `#DDF3EE` was
  nearly invisible on white). `#DDF3EE` stays in the dark and on-dark versions.

## 7. Voice

Sentence case for headings and buttons. Plain words; specific confirmations ("Appointment booked
for Asha Rao, Tue 11 Nov, 10:30 AM"); errors that say what to do next. No exclamation marks, no
filler ("seamless", "revolutionize"). English and Hindi strings live in `src/lib/i18n/`.

## 8. Accessibility

WCAG 2.1 AA everywhere (axe in Playwright). Contrast pairs above are checked; any new pair is
checked before use. Keyboard: every action reachable, visible focus, logical order, Escape closes
overlays. Status in words, not colour alone.

## 8a. UX principles (developer, 9 Nov 2026; binding for every module)

> Make every interaction predictable, every error actionable, and every screen understandable
> without users thinking about how the application works.

Six principles, in priority order when they conflict:

1. **Trust over convenience.** Never sacrifice data accuracy, privacy or clarity for speed. Never
   silently change a prescription, pick a different slot, or report success before the API
   confirms it.
2. **Clarity over complexity.** A user understands what they see at first glance.
3. **Feedback over silence.** Every meaningful action says how it ended.
4. **Forgiveness over rigidity.** Anticipate mistakes; recover without losing work.
5. **Progressive disclosure over overload.** Show what is needed now; the rest on request.
6. **Consistency over novelty.** Familiar patterns, the same everywhere (Jakob's law).

### The four states of every data-driven section

| State | Rule | Component |
|---|---|---|
| Loading | A skeleton shaped like the content, with a `role="status"` line saying what is loading ("Loading today's queue"), never a bare spinner | `Skeleton` + status text |
| Success | The data, and for an action a confirmation naming what changed | content, `Toast`, `Alert tone="success"` |
| Error | What happened, why when known, what to do next, and a retry when retrying can help; "Ref: <request_id>" for support. Never a stack trace, code name or raw exception | `ErrorNotice`, `Alert tone="danger"` |
| Empty | What the section is for and how to start; the first action as a button | `EmptyState` with `icon` and `action` |

Each section of a dashboard fetches, loads, fails, empties and retries **on its own**: a failed
notifications call shows its own error while the queue keeps working. One section never blanks
the page.

### Where feedback goes

| Placement | When |
|---|---|
| Inline (`Field` error, `ErrorSummary`) | Invalid fields and form validation |
| Toast | Temporary confirmation of a finished action ("Patient updated"); never the only place an error that needs action is shown |
| Modal (`ConfirmDialog`) | A decision that needs attention before it happens: cancelling, deleting, overriding a hold |
| Full-page error | Only when the page cannot work at all (the session ended, the record does not exist) |

For important operations, distinguish **processing** (button `loading`, "Saving…"), **saved**
(after the API answers) and **failed** (in place, with what to do).

Copy for empty states by case: zero appointments → how to book the first; zero patients → how to
add one; zero notifications → "You're all caught up"; no search results → try other words or
clear a filter.

### Forms

- Validate inline as the user leaves a field, and again on submit; keep every value when a
  submit fails.
- Tell **incomplete** from **invalid**: the submit button stays enabled; pressing it with problems
  shows the `ErrorSummary` with each problem linked to its field. A disabled button never hides
  why. (A button may disable while the request is in flight.)
- Character counts where a limit exists ("120 of 200").
- Password requirements are listed and tick off as they are met.
- Accept reasonable formats (phone with spaces, `+91` or a leading 0; dates typed or picked) and
  normalise; the API remains the authority.
- Prefill only what is reliable (the clinic, today, the chosen doctor); never guess clinical data.
- Essential fields first; advanced options behind "More options" (Hick's law). Long forms are split
  into titled sections.

### Familiarity and choice (Jakob's and Hick's laws)

- Primary action at the end of a form row or the top right of a page; cancel to its left.
- One primary button per view; other actions secondary or in a `Menu`.
- The same word for the same thing everywhere (one glossary: `docs/GLOSSARY.md`).
- Calendar and time choices behave like common calendar apps: days left to right, earliest time
  first, past times not offered.
- Group related actions; hide rarely used settings until asked.

### Pointer and hover

Every clickable control shows the pointer cursor and a hover state (colour shift; buttons also lift
1 px and press 1 px on click, not with reduced motion). Disabled controls show the not-allowed
cursor and no hover.

## 9. Component inventory (code)

| Component | File | New in M7c-P7 |
|---|---|---|
| `Button`, `buttonClasses` (`primary`, `secondary`, `ghost`, `danger`; `sm`, `md`, `lg`; `loading`, `icon`) | `components/ui/Button.tsx` | `lg`, `loading`, `icon` |
| `TextField`, `SelectField`, `TextAreaField`, `CheckboxField`, `DateField`, `TimeField`, `ErrorSummary` | `components/ui/Field.tsx` | Date, Time, ErrorSummary |
| `Card` (`title`, `description`, `action`) | `components/ui/Card.tsx` | `description` |
| `TABLE`, `TH`, `TR`, `TD`, `TABLE_WRAP` | `components/ui/table.ts` | |
| `StatusBadge`, `StatTile`, `PageHeader` (`breadcrumbs`), `EmptyState` (`icon`), `Skeleton`, `Tabs` | `components/ui/` | `breadcrumbs`, `icon` |
| `Alert`, `Toast` (`ToastProvider`, `useToast`), `Tooltip`, `Breadcrumbs`, `Pagination`, `Avatar`, `KeyValue`, `Spinner`, `Logo`, `Emblem` | `components/ui/` | all new |
| `Dialog`, `Drawer`, `ConfirmDialog`, `Menu` | `components/` | ConfirmDialog |
| `ErrorNotice` | `features/auth/ErrorNotice.tsx` | restyled |
| `cx` | `components/ui/cx.ts` | unchanged (no tailwind-merge: its 8 KB broke the patient budget); the caller's `className` is last |

The showcase `/design-system` renders all of them with sample data; `e2e/design-system.spec.ts`
runs axe on it at 1366 and 360 px.
