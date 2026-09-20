# ADR-0006: Cookie-based JWT sessions through a same-origin API proxy

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-15 |
| Related | FR-AUTH-01..04, SECURITY_AND_COMPLIANCE.md |

## Context

Staff use browsers on shared clinic computers. Tokens in `localStorage` are exposed to XSS.
Cross-origin cookies between a Next.js origin and a separate API origin cause `SameSite` and CORS
problems that are hard to debug.

## Decision

- The browser only talks to the web origin. Next.js rewrites `/api/*` to the Flask API on the
  internal network. Webhooks are routed to the API directly by the reverse proxy.
- Access token: JWT, 15 minutes. Refresh token: opaque random value, 14 days, stored hashed,
  rotated on every use; reuse revokes the token family.
- Both in `HttpOnly` cookies (`Secure` outside local, `SameSite=Lax`). CSRF protected with a
  double-submit token on state-changing requests.
- Passwords hashed with Argon2id. Lockout after 5 failures for 15 minutes.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Tokens in localStorage + Authorization header | XSS exposure of long-lived credentials |
| Server-side sessions in Redis | Adds a service we do not otherwise need yet |
| Third-party auth (Auth0, Clerk, Cognito) | Cost per user, data residency questions, and less control over clinic-specific roles; revisit for SSO/OTP scale |
| NextAuth in the web app | Splits identity logic away from the API that enforces authorisation |

## Consequences

- No CORS configuration needed for the browser.
- The web server is in the request path for all API calls (small latency cost).
- OTP sign-in (FR-AUTH-06) reuses the messaging port later.
