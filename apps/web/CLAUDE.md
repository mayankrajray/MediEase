# CLAUDE.md — apps/web

Loaded in addition to the root `CLAUDE.md` when working in this folder.

## Rules
- TypeScript strict; no `any`; API types come only from the generated schema (`npm run gen:api`).
- Server Components by default. Add `"use client"` only for interaction, and keep those components small.
- All API calls go through `src/lib/api/`. Never `fetch` the Flask API directly or hard-code its URL.
- No business rules in the UI beyond input hints; the API is the authority.
- Dates and times are formatted in the **clinic** timezone from `/me`, never the browser's.
- Phone numbers are displayed masked except where staff must dial them.
- Errors show the API `message` and "Ref: <request_id>" so staff can report problems usefully.

## Patient pages (`(patient)`)
- Mobile-first, readable at 360 px, < 200 KB total transfer, no client-side analytics SDKs.
- No clinical text in `<title>`, metadata, Open Graph tags or URLs.
- English and Hindi strings live in `src/lib/i18n/`; no hard-coded patient-facing copy in components.
- WCAG 2.1 AA: labels, contrast, focus order, large tap targets.

## Clinic pages (`(clinic)`)
- Designed for a 1366×768 front-desk screen and keyboard use; primary actions in one click.
- Every screen has explicit loading, empty and error states.
- Feature logic lives in `src/features/<feature>/`; routes stay thin.

## Tests
- Components: Vitest + Testing Library, named after requirement IDs.
- Journeys: Playwright specs in `e2e/`, including the 360-px patient page check (FR-RX-07).
