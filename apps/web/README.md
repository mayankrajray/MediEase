# apps/web — MediEase web app

Next.js (App Router, TypeScript) serving three surfaces:

| Route group | Surface | Audience |
|---|---|---|
| `src/app/(clinic)/` | Clinic dashboard: queue, patients, consultation, follow-ups, settings | Owner, doctor, front desk |
| `src/app/(patient)/` | Prescription view (`/p/[token]`), public booking page (`/c/[slug]`, M7) | Patients and parents |
| `src/app/(ops)/` | Onboarding, imports, clinic health | MediEase ops |
| `src/app/(auth)/` | Sign-in | Staff |

## Status

Skeleton only. The Next.js project is created in M0-P4.

## Required `package.json` scripts (CI depends on them)

| Script | Purpose |
|---|---|
| `dev` | Local development server |
| `build` | Production build (`output: "standalone"` for the Docker image) |
| `lint` | ESLint |
| `typecheck` | `tsc --noEmit` |
| `test` | Vitest (CI calls `npm test -- --run`) |
| `e2e` | Playwright (from M3) |
| `gen:api` | Generate `src/lib/api/schema.d.ts` from `contracts/openapi.yaml` |

## API access

The browser calls `/api/*` on this origin; `next.config` rewrites it to `API_INTERNAL_URL`
(ADR-0006). Use the wrapper in `src/lib/api/` — it attaches `X-Request-ID` and the CSRF header and
turns error envelopes into typed errors that show the reference ID to the user.
