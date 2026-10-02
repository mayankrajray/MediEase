/**
 * Runs before every page request (Next.js 16 "proxy", formerly middleware).
 *
 * Creates a per-request CSP nonce and passes the policy on the *request* so
 * Next.js can read the nonce and stamp it on the scripts it renders, and on the
 * *response* so the browser enforces it. API paths are excluded: they are
 * rewritten to the Flask API and return JSON, not pages.
 */

import { type NextRequest, NextResponse } from "next/server";

import { buildContentSecurityPolicy, newNonce } from "@/lib/security/headers";

export const CSP_HEADER = "Content-Security-Policy";

export function proxy(request: NextRequest): NextResponse {
  const csp = buildContentSecurityPolicy(newNonce(), {
    isDev: process.env.NODE_ENV === "development",
  });

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
