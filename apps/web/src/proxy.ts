/**
 * Runs before every page request (Next.js 16 "proxy", formerly middleware).
 *
 * 1. Creates a per-request CSP nonce and passes the policy on the *request* so
 *    Next.js can read the nonce and stamp it on the scripts it renders, and on the
 *    *response* so the browser enforces it. API paths are excluded: they are
 *    rewritten to the Flask API and return JSON, not pages.
 * 2. Sends a visitor who has no `me_csrf` cookie to /sign-in. That cookie is the
 *    only session cookie a page request carries (`me_access` is scoped to /api,
 *    ADR-0006), so its absence means "never signed in, or signed out". This is a
 *    convenience that saves a signed-out visitor from seeing the dashboard shell,
 *    not a security check: a stale or forged cookie just reaches the client-side
 *    session provider, which asks the API, and the API enforces access on every
 *    request (M1-P6 design, concepts 2 and 3).
 */

import { type NextRequest, NextResponse } from "next/server";

import { CSRF_COOKIE, PORTAL_CSRF_COOKIE } from "@/lib/api/csrf";
import { isPortalPath } from "@/lib/auth/safe-next";
import { buildContentSecurityPolicy, newNonce } from "@/lib/security/headers";

export const CSP_HEADER = "Content-Security-Policy";

const SIGN_IN_PATH = "/sign-in";
const PORTAL_SIGN_IN_PATH = "/portal/sign-in";
const PUBLIC_PATHS: ReadonlySet<string> = new Set([
  SIGN_IN_PATH,
  "/status",
  "/livez",
  // M6a-P3: the patient portal's own sign-in and sign-up.
  PORTAL_SIGN_IN_PATH,
  "/portal/sign-up",
  // M6a-P4: asking for a reset link (staff and patients).
  "/forgot-password",
  "/portal/forgot-password",
  // M6c-P1: applying to join MediEase needs no account (FR-ONB-01, ADR-0020).
  "/apply",
  // M6c-P5 (FR-DIS-06): for crawlers.
  "/robots.txt",
  "/sitemap.xml",
]);
// /p/<token>: the patient's prescription page (M4-P5); the token and the last-4 check guard it.
// M6a-P4: emailed reset and verification links; the token in the path is the authority.
const PUBLIC_PREFIXES: readonly string[] = [
  "/invite/",
  "/p/",
  // M6b-P4: a clinic's public page; the clinic's slug in the path is the whole address (FR-PUB-01).
  "/c/",
  // M6b-P6: the live token page; the signed token in the path is the authority (ADR-0019).
  "/q/",
  // M6c-P1: the application's emailed confirmation link; the token in the path is the authority.
  "/apply/confirm/",
  "/reset-password/",
  "/portal/reset-password/",
  "/portal/verify-email/",
];

/** Pages anyone may open without a session. */
export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.has(pathname) || PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export function proxy(request: NextRequest): NextResponse {
  const csp = buildContentSecurityPolicy(newNonce(), {
    isDev: process.env.NODE_ENV === "development",
  });

  const { pathname, search } = request.nextUrl;
  // The portal has its own session (ADR-0015 decision 2): its pages look for the portal's
  // CSRF cookie and send a signed-out visitor to the portal's sign-in, never the staff one.
  const portal = isPortalPath(pathname);
  const hint = portal ? PORTAL_CSRF_COOKIE : CSRF_COOKIE;
  const hasSessionHint = Boolean(request.cookies.get(hint)?.value);

  if (!hasSessionHint && !isPublicPath(pathname)) {
    const signIn = new URL(portal ? PORTAL_SIGN_IN_PATH : SIGN_IN_PATH, request.url);
    if (pathname !== "/" && pathname !== "/portal") {
      signIn.searchParams.set("next", `${pathname}${search}`);
    }
    const redirect = NextResponse.redirect(signIn);
    redirect.headers.set(CSP_HEADER, csp);
    return redirect;
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(CSP_HEADER, csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set(CSP_HEADER, csp);
  return response;
}

export const config = {
  matcher: [
    {
      // Everything except API paths (rewritten to Flask), static build assets and the favicon.
      source: "/((?!api/|health$|ready$|_next/static|_next/image|favicon.ico).*)",
      // Prefetches do not render HTML, so they need no nonce.
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
