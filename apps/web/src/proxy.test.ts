// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import nextConfig, { apiInternalUrl } from "../next.config";
import { CSP_HEADER, config, isPublicPath, proxy } from "./proxy";

function nonceOf(csp: string | null): string | undefined {
  return csp?.match(/'nonce-([^']+)'/)?.[1];
}

/** A page request carrying the readable session hint cookie. */
function signedIn(url: string, value = "csrf-token"): NextRequest {
  return new NextRequest(url, { headers: { cookie: `me_csrf=${value}` } });
}

const signedOut = (url: string) => new NextRequest(url);

describe("proxy (sign-in hint)", () => {
  it("FR-AUTH-01: sends a visitor with no session cookie to sign in, remembering the page and query", () => {
    const response = proxy(signedOut("http://localhost:3000/queue?day=today"));

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.origin).toBe("http://localhost:3000");
    expect(location.pathname).toBe("/sign-in");
    expect(location.searchParams.get("next")).toBe("/queue?day=today");
  });

  it("does not remember the home page", () => {
    const response = proxy(signedOut("http://localhost:3000/"));

    expect(response.headers.get("location")).toBe("http://localhost:3000/sign-in");
  });

  it("puts the CSP, with its own nonce, on the redirect too", () => {
    const response = proxy(signedOut("http://localhost:3000/queue"));

    expect(nonceOf(response.headers.get(CSP_HEADER))).toBeTruthy();
  });

  it("lets a visitor with the session cookie through to the page", () => {
    const response = proxy(signedIn("http://localhost:3000/queue"));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(nonceOf(response.headers.get(CSP_HEADER))).toBeTruthy();
  });

  it("treats an empty cookie as no cookie", () => {
    const response = proxy(signedIn("http://localhost:3000/queue", ""));

    expect(response.status).toBe(307);
  });

  it.each(["/sign-in", "/invite/abc123", "/status", "/livez"])("never redirects the public page %s", (path) => {
    const response = proxy(signedOut(`http://localhost:3000${path}`));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it.each(["/invite", "/invitex/abc", "/sign-in/extra", "/statuses", "/ops", "/select-clinic"])(
    "still guards %s",
    (path) => {
      expect(proxy(signedOut(`http://localhost:3000${path}`)).status).toBe(307);
    },
  );

  it("isPublicPath names exactly the public pages", () => {
    expect(["/sign-in", "/status", "/livez", "/invite/x"].every(isPublicPath)).toBe(true);
    expect(["/", "/queue", "/ops", "/invite"].some(isPublicPath)).toBe(false);
  });
});

describe("proxy (per-request CSP)", () => {
  it("sets a CSP with a fresh nonce on every page response", () => {
    const first = proxy(signedIn("http://localhost:3000/status"));
    const second = proxy(signedIn("http://localhost:3000/status"));

    const a = nonceOf(first.headers.get(CSP_HEADER));
    const b = nonceOf(second.headers.get(CSP_HEADER));
    expect(a).toBeTruthy();
    expect(b).toBeTruthy();
    expect(a).not.toBe(b);
  });

  it("matches pages but not API paths or static assets", () => {
    const source = config.matcher[0]?.source ?? "";
    // Next compiles `source` as a path pattern; its regex group is plain JS regex.
    const pattern = new RegExp(`^${source}$`);
    for (const path of ["/api/v1/me", "/health", "/ready", "/_next/static/chunk.js"]) {
      expect(pattern.test(path), path).toBe(false);
    }
    for (const path of ["/", "/status", "/healthcheck-page"]) {
      expect(pattern.test(path), path).toBe(true);
    }
  });
});

describe("next.config rewrites (ADR-0006 same-origin proxy)", () => {
  it("send /api/*, /health and /ready to API_INTERNAL_URL", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000/");
    const rewrites = await nextConfig.rewrites?.();
    expect(rewrites).toEqual([
      { source: "/api/:path*", destination: "http://api:8000/api/:path*" },
      { source: "/health", destination: "http://api:8000/health" },
      { source: "/ready", destination: "http://api:8000/ready" },
    ]);
  });

  it.each(["", "api:8000", "ftp://api:8000"])("reject API_INTERNAL_URL=%j clearly", (value) => {
    vi.stubEnv("API_INTERNAL_URL", value);
    expect(() => apiInternalUrl()).toThrow(/API_INTERNAL_URL must/);
  });

  it("hide X-Powered-By and produce a standalone build", () => {
    expect(nextConfig.poweredByHeader).toBe(false);
    expect(nextConfig.output).toBe("standalone");
  });
});
