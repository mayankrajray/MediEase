# apps/web — MediEase web app

Next.js (App Router, TypeScript) serving three surfaces:

| Route group | Surface | Audience |
|---|---|---|
| `src/app/(clinic)/` | Clinic dashboard: queue, patients, consultation, follow-ups, settings | Owner, doctor, front desk |
| `src/app/(patient)/` | Prescription view (`/p/[token]`), public booking page (`/c/[slug]`, M7) | Patients and parents |
| `src/app/(ops)/` | Ops console (`/ops`; the onboarding screens are planned separately) | MediEase ops |
| `src/app/(auth)/` | Sign-in (`/sign-in`) and invitation acceptance (`/invite/[token]`) | Staff |

## Status

M0-P4: Next.js 16 App Router (TypeScript strict, Tailwind 4), the generated API client in
`src/lib/api/`, the `/status` page and security headers with a per-request CSP nonce
(`src/proxy.ts`). M0-P5: the web `Dockerfile` and compose service.

M1-P6: sign-in, invitation acceptance, the clinic chooser and switcher, and an empty dashboard
shell (`/queue`). `/` redirects to `/queue`; the proxy sends a visitor with no `me_csrf` cookie to
`/sign-in?next=…`.

### How sign-in works in the browser

- The session tokens are HttpOnly and `me_access` is scoped to `/api`, so page requests never carry
  it. The `(clinic)` and `(ops)` layouts therefore render a client `SessionProvider`
  (`src/features/auth/`), which asks `GET /api/v1/me` and sends anyone else to `/sign-in`. This is a
  convenience: the API re-checks everything on every request.
- An expired access token is refreshed once (`src/lib/auth/refresh.ts`). Refresh tokens are single
  use, so refreshes are shared in the tab and serialised across tabs with a Web Lock.
- The active clinic is per tab (`X-Clinic-ID`, sent only for people in several clinics); the last
  choice is remembered in `localStorage` as `mediease.clinic_id` (a preference, not an authority).
- `?next=` and `?reason=` on `/sign-in` are validated on the server (`safeNextPath`,
  `parseSignInReason`).

To try it: `make up && make seed`, then sign in at http://localhost:3000 with the users in
`docs/RUNBOOK.md` §1 (`doctor@sample-clinic.example` belongs to two clinics).

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
`API_INTERNAL_URL` (ADR-0006). Server Components call the API directly over the internal network
(public data only: the session cookies are not available to them). Use the wrapper in
`src/lib/api/` for both: it attaches `X-Request-ID`, copies the `me_csrf` cookie into
`X-CSRF-Token` on POST, can name the clinic (`X-Clinic-ID`), and turns error envelopes into a
typed `ApiError` whose `requestId` the UI shows as "Ref: …" and whose `retryAfterSeconds` carries
`Retry-After` (codes in `docs/ERRORS.md`, including the web-side `WEB_*` codes). From the browser,
use `sessionGet`/`sessionPost` (`src/lib/auth/refresh.ts`) so an expired access token is refreshed
once.
