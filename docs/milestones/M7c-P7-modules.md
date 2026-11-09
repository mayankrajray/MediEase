# M7c-P7 — Design system and module redesign: implementation record

Plan: `docs/milestones/M7c-P7-design-system-plan.md`. System: `DESIGN.md`. Product: `PRODUCT.md`.

| Step | Status |
|---|---|
| Phase 1 — shared design system | ✅ built 9 Nov 2026 (below) |
| M1 Marketing landing page | ☐ next |
| M2 Authentication | ☐ |
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
