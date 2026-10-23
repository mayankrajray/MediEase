# ADR-0015: Patient accounts apart from staff, and Google sign-in through the API

| Field | Value |
|---|---|
| Status | Accepted (M6-P3 design proposed 21 Oct 2026; approved by the developer 22 Oct 2026, with decision 5 amended for PRD v1.2) |
| Date | 2026-10-21 (accepted 2026-10-22) |
| Related | PRD v1.2 FR-AUTH-05, FR-AUTH-07, FR-AUTH-08, FR-PRT-01, FR-PRT-05, FR-PRT-06, FR-PUB-03; ADR-0003, ADR-0006; M6a-P3 design |

## Context

PRD v1.1 adds patients who sign in, with Google or with an email and password (FR-PRT-01), and
Google sign-in for staff (FR-AUTH-07).

Today every signed-in person is a staff `user`. ADR-0006 gives them `me_access`, `me_refresh`
and `me_csrf` cookies holding a JWT (audience `mediease`). On every request the API re-reads the
session, the user and their clinic memberships, and grants clinic access only through an active
membership.

A patient must never be able to reach a clinic route. A patient's account holds no clinic data
until a clinic's proof links it (FR-PRT-02, P4). We have no email provider, so an email address
cannot be verified yet.

Credentials for a real Google OAuth client are pending (L-09), but the demo must work on the
local stack without them.

## Decision

1. **Separate accounts.** Patients are `patient_accounts`, a table apart from `users`, with their
   own refresh-token family table. A patient account has no memberships, so no change to staff
   code could grant it clinic access. The same person can hold a staff user and a patient
   account; they are separate.
2. **Separate sessions.**
   - **Cookies:** the portal uses its own cookies, `me_pt_access` (Path `/api/v1/portal`),
     `me_pt_refresh` (Path `/api/v1/portal/auth`) and `me_pt_csrf`.
   - **Tokens:** the portal's JWT audience is `mediease-portal`. The staff verifier refuses that
     audience and the portal verifier refuses `mediease`, so a token of one kind is a 401 on the
     other's routes.
   - **Routes:** portal routes take a new `@patient` policy, under the existing default-deny
     check.
3. **Google is OpenID Connect, handled by the API.** The flow is the Authorization Code flow
   with PKCE:
   - `GET /api/v1/auth/google/start?intent=staff|patient` redirects to Google. The `state`,
     `nonce` and PKCE verifier travel in a short-lived signed HttpOnly cookie.
   - `GET /api/v1/auth/google/callback` exchanges the code. It then verifies the ID token:
     signature (Google's JWKS, RS256), `iss`, `aud` (our client ID), `exp`, `nonce`, and
     `email_verified`.
   - No Google script runs on our pages, so the Content-Security-Policy is unchanged.
   - It is built on PyJWT, which we already use, and `urllib` (`PyJWKClient`); no new
     dependency.
4. **Identities.** `external_identities` maps provider and subject (`sub`) to either a staff
   user or a patient account.
   - **Staff:** Google never creates staff access. The first sign-in links an existing active
     staff user whose email equals Google's verified email. After that the `sub` is matched.
     Platform ops users may not use Google.
   - **Patients:** the first Google sign-in creates a patient account.
5. **Patient passwords.** Email-and-password patient accounts use the same Argon2id hashing,
   minimum length and lockout as staff. The email starts unverified; the account records
   `email_verified_at` (set at once for Google sign-ups, whose email Google has verified).
   - **Amended 22 Oct 2026 (PRD v1.2).** M6a-P4 adds an email provider behind a port
     (FR-AUTH-08): it verifies addresses and sends password-reset links (FR-AUTH-05). Until then
     no email is sent and there is no reset. A password account whose email is unverified cannot
     pass the verified-identity check a booking request needs (FR-PUB-03).
   - Google accounts and password accounts are never merged automatically, even with the same
     address. An unverified address must not let anyone claim another person's account or its
     linked records.
6. **A fake provider for local use.** `GOOGLE_OIDC_PROVIDER=fake` is allowed only in
   `APP_ENV=local` and `test`; start-up refuses it otherwise. It skips Google and returns a
   synthetic verified identity for a `login_hint` email, so the demo and the Playwright journeys
   run without L-09. With `google`, the client ID and secret are required at start-up.

## Alternatives considered

- **One `users` table with a patient flag.** One missing check would give a patient a staff
  route.
- **Shared session cookies with a role claim.** Every route would have to test the claim, and
  the two kinds of session would share one cookie and its compromise path.
- **Google Identity Services in the browser** (an ID token posted to the API). This needs a
  third-party script and CSP changes on every page that shows the button.
- **Authlib or another OAuth library.** It is a new dependency for one flow that PyJWT and the
  standard library already cover.
- **Merging accounts by email.** With unverified addresses, this lets an account creator sit in
  wait for the real owner of that address.

## Consequences

- There are two session stacks to maintain (staff and portal). They share the token, hashing
  and cookie helpers, with different names, paths and audiences.
- Patients cannot reset a forgotten password until the email provider lands in M6a-P4. Until
  then they can use Google, or a clinic can link a new account.
- Sign-up shows whether an email address already has a password account (an account-enumeration
  risk), limited by the public-route rate limits.
- Real Google sign-in waits for L-09. Until then everything else, including the full flow, is
  tested with the fake provider and with signed test tokens against a fake JWKS.
