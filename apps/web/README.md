# apps/web — MediEase web app

Next.js (App Router, TypeScript) serving three surfaces:

| Route group | Surface | Audience |
|---|---|---|
| `src/app/(clinic)/` | Clinic dashboard: queue, patients, consultation, follow-ups, settings | Owner, doctor, front desk |
| `src/app/(patient)/` | Prescription view (`/p/[token]`), public booking page (`/c/[slug]`, M7) | Patients and parents |
| `src/app/(ops)/` | Onboarding, imports, clinic health | MediEase ops |
| `src/app/(auth)/` | Sign-in | Staff |

## Status

M0-P4: Next.js 16 App Router (TypeScript strict, Tailwind 4), the generated API client in
`src/lib/api/`, the `/status` page (`/` redirects there until M1) and security headers with a
per-request CSP nonce (`src/proxy.ts`). The web `Dockerfile` and compose service arrive in M0-P5.

## Running locally

Node is pinned in `.nvmrc` (on Windows, install it inside WSL — the Windows `npm` cannot run
the Linux toolchain). From the repository root:

```bash
make up            # db -> migrate -> api
make install-web   # npm ci
make dev-web       # http://localhost:3000/status, API_INTERNAL_URL=http://localhost:8000
make lint typecheck test
```

`API_INTERNAL_URL` is required by `next dev`, `next build` and `next start`; a missing or
malformed value stops them with a clear message.

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

The browser calls `/api/*` on this origin; `next.config` rewrites it (and `/health`, `/ready`) to
`API_INTERNAL_URL` (ADR-0006). Server Components call the API directly over the internal network.
Use the wrapper in `src/lib/api/` for both: it attaches `X-Request-ID` and turns error envelopes
into a typed `ApiError` whose `requestId` the UI shows as "Ref: …" (codes in `docs/ERRORS.md`,
including the web-side `WEB_*` codes). The CSRF header joins with sign-in in M1.
