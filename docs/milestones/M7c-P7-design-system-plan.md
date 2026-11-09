# M7c-P7 — Design system overhaul and module redesign: plan for review

| Field | Value |
|---|---|
| Status | **Approved** by the developer, 9 Nov 2026, with every recommendation (§9: Manrope everywhere, Lucide, wordmark and PDF emblem, no partner names or quotes). Phase 1 built the same day; record in `docs/milestones/M7c-P7-modules.md` |
| Brief | The developer's "Complete Design System Overhaul & Module-by-Module Redesign" (9 Nov 2026), direction *Modern Healthcare SaaS* |
| Proposed system | `DESIGN.md` (status Proposed) |
| Skills installed | `.kiro/skills/impeccable/` (Impeccable 4.8.1, Apache-2.0, project scope, no hooks) and `.kiro/skills/landing-page-design/SKILL.md` (ai-design-skills, MIT, with its LICENSE). Both local: `.kiro/` is git-excluded |

## 1. Current state of the frontend

| Concern | Today | Consequence for the overhaul |
|---|---|---|
| Stack | Next.js 16.4.3, React 19.3, **Tailwind 4.3 configured in CSS** (`@theme` in `src/app/globals.css`, no `tailwind.config`), Motion 14.4, Radix Tabs 1.2.1 only | Tokens go in `@theme`/`:root`; no config file to add |
| Tokens | `brand-50..900` alias Tailwind teal (300–500 missing), `canvas` = slate-50, `radius-card` 12 px, `shadow-card`; everything else uses the raw Tailwind palette (about 830 `slate-*` uses in 127 files) | One edit to the aliases restyles most of the app at once; semantic names need a migration per module |
| Font | System stack, nothing downloaded; Devanagari from the phone | Manrope is a new download on every page; it has no Devanagari glyphs |
| Primitives (`src/components/ui`) | `Button` (4 variants, 2 sizes), `Field` (Text, Select, TextArea, Checkbox), `Card`, `StatTile`, `StatusBadge`, `PageHeader`, `EmptyState`, `Skeleton`, `Tabs`, `Motion`, table constants; `components/Dialog`, `Drawer` (native `<dialog>`), `Menu` (WAI-ARIA menu button); `features/auth/ErrorNotice` (135 uses) | Most of the requested list exists and is accessible: restyle and extend, do not replace |
| Missing | Toast, Tooltip, Breadcrumbs, Pagination, ConfirmDialog, loading button, Alert/Notice, a Brand/Logo component, icons, favicon, OG image, `apps/web/public/` | New components in Phase 1 |
| Duplication | 166 raw `<button>`s vs 93 `<Button>`; 36 hand-written primary buttons; 56 hand-written inputs; 66 hand-written cards vs 8 `<Card>`; the "M" logo drawn by hand **8 times**; the landing page has its own button and card styles | The migration work per module is mostly replacing these with the shared components |
| `cx` | Joins classes without resolving conflicts | Overriding a component's class depends on order; `tailwind-merge` fixes it |
| Tests | 726 Vitest tests, mostly by role and label (8 `testid`s, no class assertions); 31 Playwright files with axe (WCAG 2.1 AA) on 10 specs; the 200 KB patient-page budget measured in 8 specs; **no screenshot tests** | A restyle keeps tests green if roles, names and labels stay. Axe catches contrast regressions |
| Logo | `public/branding/` at the **repository root** (9 files, added by the developer 9 Nov): emblem in `#147D72` and `#DDF3EE`, wordmark in `#172B35`. The PDF still uses the placeholder mark `apps/api/.../pdf/assets/mediease-mark.svg` | Next.js serves only `apps/web/public/`, so the files must move. The wordmark is live `<text>` in Inter: it renders in whatever font the viewer has, and the PDF renderer fetches no fonts. See §9 Q3 |

The palette in the brief matches the new logo exactly (primary `#147D72`, soft `#DDF3EE`, text
`#172B35`), so the logo confirms the direction rather than competing with it.

## 2. Resource and licence review

| Resource | Licence (checked 9 Nov 2026) | Use |
|---|---|---|
| Impeccable | Apache-2.0 | Installed. `audit`, `critique`, `polish`, `typeset`, `layout` and its `detect` scanner run on each module; `document` keeps DESIGN.md true |
| ai-design-skills `landing-page-design` | MIT | Installed. Governs M1 (landing). Conflicts with the brief are listed in §8 |
| Watermelon UI | MIT (`WatermelonCorp/watermelon-platform`) | May copy individual free components with the licence notice in `THIRD_PARTY.md` |
| Animata | MIT (`codse/animata`) | May copy individual components with the notice |
| Aceternity UI (free) | Aceternity licence: use in end products allowed; **redistributing the source is not** | Our repository is public, so committing its code would redistribute it. Rebuild the patterns ourselves; copy nothing |
| Skiper UI | Terms of service: all rights reserved, personal use | Inspiration only; copy nothing |
| CMS Design System, Australian Health Design System | Public-sector references (CMS repo reports no single licence) | Read for patterns: forms, error summaries, step lists, plain language. Copy no code or assets |
| shadcn/ui | MIT, copy-in components over Radix | Follow its pattern (own the component code, Radix underneath where keyboard behaviour is hard); do **not** run its CLI over the project, which would bring a second styling system |
| Radix UI, Motion, Lucide, Recharts | MIT / MIT / ISC / MIT | See §4 for which are added |
| Practo | Public pages only, with REA (permission given) | Research note before M1 and M6; patterns described in our words, no assets, code or copy |
| Mobbin, Ponytail | Excluded by the brief | — |

## 3. Design direction by surface (Impeccable modes)

| Surface | Mode | What ambition means here |
|---|---|---|
| Landing page (M1) | Persuade | The most expressive surface: scroll reveals, the tagline reveal, product screenshots, Motion allowed |
| Sign-in, apply (M2) | Operate | Calm, one task per screen, clear errors |
| Clinic dashboard, queue, patients, booking, billing, assistant (M3–M6, M9, M10) | Operate | Density, scanability at 1366×768, keyboard first; motion only for state changes |
| Patient portal (M7) | Operate, mobile | 360 px first, under 200 KB, no Motion library, CSS transitions only |
| Prescription page and PDF (M8) | Read | Legibility and print; no motion |

## 4. Dependencies

Existing ones are reused. Proposed additions, each with its reason (AGENTS.md §2):

| Package | Why | Where it loads | Decision |
|---|---|---|---|
| Manrope via `next/font/google` | The brief's font. `next/font` downloads it at **build time** and serves it from our origin, so the nonce CSP needs no change | Every page (§9 Q1) | **Built** with `next/font/local` from a vendored file (no build-time network); every surface except patient pages, which measured over 200 KB with it |
| `lucide-react` (or Phosphor, §8) | One icon set instead of none; tree-shaken per icon | Every page, only the icons used | Add |
| `tailwind-merge` | Lets a component accept `className` overrides safely; `cx` becomes a wrapper | Every page, about 7 KB gzip | **Removed during the build**: with the font it pushed patient pages past 200 KB |
| `@radix-ui/react-toast`, `@radix-ui/react-tooltip` | Live-region and focus behaviour that is costly to get right by hand (the ui README's rule for adopting a primitive) | Clinic and ops only | Add |
| `recharts` | Dashboard charts (M3) | Clinic dashboard only, loaded with `next/dynamic` | Add in M3, not Phase 1 |
| Radix Dialog, Dropdown, Select, Popover | Our native `<dialog>`, `Menu` and native `<select>` already pass axe and keyboard tests | — | **Not added** |
| A date-picker library | Native `<input type="date|time">` is accessible on phones and matches the booking flow's validation | — | **Not added**; style the native control |
| `class-variance-authority`, shadcn CLI, Storybook | Variant maps are a few lines with our `Record` pattern; Storybook is a second build | — | **Not added** |

## 5. Phase 1: the shared design system

Order of work, each step reviewable on its own:

1. **Tokens** (`globals.css`): the colour scale, semantic colours, surfaces, text, borders, radius,
   shadow, spacing and motion tokens of `DESIGN.md`, as CSS variables in `@theme` (the single source
   of truth). The old names stay as aliases (`brand-700` → the new primary, `canvas` → the new
   background), so every screen moves to the new palette at once without a markup change.
2. **Typography**: Manrope with weights 400–700, the named text styles (`heading-1` … `caption-5`)
   as utilities, Devanagari fallback, `text-wrap: balance/pretty`.
3. **Brand**: move `public/branding/` into `apps/web/public/brand/`, a `Logo` component (full,
   emblem, mono, on-dark) replacing the 8 hand-drawn marks, the favicon, apple icon and an OG image.
4. **Components**, restyled or new, every one with default, hover, active, focus, disabled,
   loading, success and error states, keyboard behaviour and reduced motion:
   - restyled: Button (adds loading and icon slots, `lg` size), Field family (adds error summary),
     Card, Table, StatusBadge, Tabs, Menu (dropdown), Dialog, Drawer, EmptyState, Skeleton,
     ErrorNotice, PageHeader, Shell sidebar and header;
   - new: Toast, Tooltip, Breadcrumbs, Pagination, ConfirmDialog, Alert (info, success, warning,
     error), Spinner for inline waits only, DateField/TimeField (styled native controls), Avatar
     initials, KeyValue list for record details.
5. **Showcase**: a `/design-system` route rendering every component in every state, built only when
   `NODE_ENV` is not production, with one Playwright spec running axe on it at 1366 and 360 px.
6. **Records**: `DESIGN.md` finalised from what was built; `THIRD_PARTY.md` for any copied
   component; `docs/milestones/M7c-P7-modules.md` with one section per module.

Phase 1 exit: lint, typecheck, `make test-web` and `make e2e` green; axe clean on the showcase; the
patient-page budget specs still under 200 KB; before and after screenshots of five key screens
attached to the PR.

## 6. Phase 2: modules

Order as in the brief, M1 landing → M10 billing. Each module follows the brief's 12-step workflow,
and its record holds: the existing workflows and states, the problems found (Impeccable `critique`
and `audit`), the plan, screenshots before and after at 1366 and 360 px, the tests run, and
`impeccable detect` results. **No module starts before the previous one is reviewed.**

Protected in every module (brief §8): API calls stay in `src/lib/api`, business rules stay in the
API, roles, names and labels used by tests stay unless a test is updated for a real change, and no
backend file changes. A module that needs an API change stops and asks.

## 7. Timeline against the Phase 2 deadline (15 Nov, 6 days)

The full plan (design system plus ten modules, each with a review gate) is more than 6 days of
work. Proposal:

| By | Work | Why |
|---|---|---|
| 10–11 Nov | Phase 1 tokens, font, logo, core components | The token aliases alone give every screen the new palette, font and logo before the demo |
| 12–13 Nov | M1 landing, M2 authentication | What the mentor and partners see first |
| 13–14 Nov | Deployment (Vercel, Supabase) and the WhatsApp live test; P8 rehearsal | Required for the live review |
| After 15 Nov | M3–M10 | In the brief's order, one review each |

## 8. Conflicts to settle

| # | Conflict | Proposal |
|---|---|---|
| C1 | The landing skill bans Inter; the logo's wordmark is set in Inter | Re-set the wordmark in Manrope, outlined as paths (§9 Q3) |
| C2 | The skill allows only Phosphor, Solar or Iconamoon icons; the brief lists Lucide | Your call (§9 Q2); either is fine technically |
| C3 | The skill puts a text gradient on the hero heading | Skip it: the brief says avoid excessive gradients; flat `#172B35` heading |
| C4 | The skill's floating translucent navigation and scroll reveals | Landing page only; never on clinic or patient screens |
| C5 | Attention `#E8A23A` is 2.2:1 on white | Use as a fill or border with dark text (`#5C3A06`), never as text colour |
| C6 | Primary `#147D72` is 5.0:1 on white and 4.7:1 on the background | Passes AA for text; the current teal-700 is 5.5:1, so small grey-on-teal combinations are rechecked by axe |
| C7 | The skill's single-side card border ban | Today's role cards use a left border: redesigned in M1 |

## 9. Questions for the developer

1. **Font on patient pages.** Manrope costs roughly 20–40 KB on the first visit (measured in Phase 1
   before deciding). Load it on patient pages too (one brand everywhere, still under 200 KB), or
   keep the system font there? *Recommendation: load it everywhere if the measured budget allows.*
2. **Icons: Lucide** (the brief) **or Phosphor** (the landing skill)? *Recommendation: Lucide.*
3. **Logo.** May I re-set the wordmark in Manrope and convert it to paths (so it looks the same in
   every browser and on the prescription PDF), and replace the PDF's placeholder mark with your
   emblem? The PDF change needs a new prescription layout version (layout 4) so prescriptions
   already issued keep their look (spec R13–R14). Or is a designer delivering a final outlined logo?
4. **Product facts for PRODUCT.md** (Impeccable needs one round before it writes it): who decides to
   buy at a clinic (owner, doctor?), which surface matters most to your partners today, and any
   proof the landing page may show (partner names and quotes need their permission; otherwise the
   page shows no testimonials).
5. **Deadline plan in §7:** agree, or do you want a different cut?
