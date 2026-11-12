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

  it("M6c-P8: lets a signed-out visitor see the landing page", () => {
    const response = proxy(signedOut("http://localhost:3000/"));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
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

  it.each(["/sign-in", "/invite/abc123", "/status", "/livez", "/p/AQFrMQ.x.y"])("never redirects the public page %s", (path) => {
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
    expect(
      [
        "/sign-in",
        "/status",
        "/livez",
        "/invite/x",
        "/p/x",
        "/portal/sign-in",
        "/portal/sign-up",
        "/forgot-password",
        "/reset-password/x",
        "/portal/forgot-password",
        "/portal/reset-password/x",
        "/portal/verify-email/x",
        // M6b-P6: the live token page (ADR-0019).
        "/q/x",
        // M6c-P1: applying and confirming.
        "/apply",
        "/apply/confirm/x",
        // M6c-P5, P6, P8: crawlers, directory search and the landing page.
        "/robots.txt",
        "/sitemap.xml",
        "/find",
        "/",
      ].every(isPublicPath),
    ).toBe(true);
    expect(["/finder", "/queue", "/ops", "/invite", "/portal", "/portal/x", "/q", "/portal/notifications", "/apply/x"].some(isPublicPath)).toBe(false);
    // M6b-P1: linking needs a signed-in patient; the proxy sends others to sign in and back.
    expect(["/portal/link/x", "/portal/link/prescription/x"].some(isPublicPath)).toBe(false);
  });

  it("M7e-E1: the installable app's files load without a session; nothing near them does", () => {
    expect(["/manifest.webmanifest", "/sw.js", "/sw-register.js", "/offline.html", "/icons/icon-192.png", "/icons/maskable-512.png"].every(isPublicPath)).toBe(true);
    expect(["/sw", "/offline", "/icons", "/manifest.json", "/sw.js/x"].some(isPublicPath)).toBe(false);
    for (const path of ["/sw.js", "/manifest.webmanifest", "/offline.html"]) {
      expect(proxy(signedOut(`http://localhost:3000${path}`)).status).toBe(200);
    }
  });
});

describe("proxy (patient portal, M6a-P3, ADR-0015)", () => {
  const portal = (url: string, cookie: string) => new NextRequest(url, { headers: { cookie } });

  it("FR-PRT-01: sends a signed-out visitor to the portal's own sign-in, never the staff one", () => {
    const response = proxy(signedOut("http://localhost:3000/portal/appointments?x=1"));

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/portal/sign-in");
    expect(location.searchParams.get("next")).toBe("/portal/appointments?x=1");
  });

  it("does not remember the portal home", () => {
    const response = proxy(signedOut("http://localhost:3000/portal"));

    expect(response.headers.get("location")).toBe("http://localhost:3000/portal/sign-in");
  });

  it("ADR-0015: a staff session hint does not open the portal, nor a portal hint the staff pages", () => {
    expect(proxy(portal("http://localhost:3000/portal", "me_csrf=staff")).status).toBe(307);
    expect(proxy(portal("http://localhost:3000/queue", "me_pt_csrf=patient")).status).toBe(307);
  });

  it("lets a visitor with the portal hint through to the portal", () => {
    expect(proxy(portal("http://localhost:3000/portal", "me_pt_csrf=patient")).status).toBe(200);
  });

  it.each(["/portal/sign-in", "/portal/sign-up"])("never redirects %s", (path) => {
    expect(proxy(signedOut(`http://localhost:3000${path}`)).status).toBe(200);
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

  it("M7e (A11): matches pages and API paths, but not static assets or the two large-upload routes", () => {
    const source = config.matcher[0]?.source ?? "";
    // Next compiles `source` as a path pattern; its regex group is plain JS regex.
    const pattern = new RegExp(`^${source}$`);
    for (const path of [
      "/_next/static/chunk.js",
      "/_next/image",
      "/favicon.ico",
      "/api/v1/portal/prescription-uploads",
      "/api/v1/ops/clinics/0192f0a0-0000-7000-8000-0000000000e2/patient-imports",
    ]) {
      expect(pattern.test(path), path).toBe(false);
    }
    for (const path of ["/", "/status", "/healthcheck-page", "/api/v1/me", "/health", "/ready", "/api/v1/portal/prescription-uploads/x"]) {
      expect(pattern.test(path), path).toBe(true);
    }
  });
});

describe("proxy (M7e, A11: the browser's address for the API)", () => {
  const SECRET = "a-trusted-proxy-secret-of-at-least-32-chars";
  const forwarded = (response: Response, name: string) => response.headers.get(`x-middleware-request-${name}`);
  const request = (url: string, headers: Record<string, string>) => new NextRequest(url, { headers });

  it("an API call passes through with no CSP and no sign-in redirect, even signed out", () => {
    const response = proxy(signedOut("http://localhost:3000/api/v1/public/clinics/sample-clinic"));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get(CSP_HEADER)).toBeNull();
  });

  it("removes the address and secret a browser sends, whether or not forwarding is on", () => {
    const spoofed = { "x-mediease-client-ip": "198.51.100.9", "x-mediease-proxy-secret": "guess" };
    for (const env of [{}, { TRUSTED_PROXY_SECRET: SECRET, CLIENT_IP_HEADER: "x-real-ip" }]) {
      for (const [key, value] of Object.entries(env)) vi.stubEnv(key, value);
      for (const path of ["/api/v1/me", "/find"]) {
        const response = proxy(request(`http://localhost:3000${path}`, spoofed));
        expect(forwarded(response, "x-mediease-client-ip"), path).not.toBe("198.51.100.9");
        expect(forwarded(response, "x-mediease-proxy-secret"), path).not.toBe("guess");
      }
    }
  });

  it("with a secret and the edge's header set, adds the edge's address (the last hop) and the secret", () => {
    vi.stubEnv("TRUSTED_PROXY_SECRET", SECRET);
    vi.stubEnv("CLIENT_IP_HEADER", "X-Forwarded-For");
    for (const path of ["/api/v1/public/search/doctors", "/c/sample-clinic"]) {
      const response = proxy(request(`http://localhost:3000${path}`, { "x-forwarded-for": "198.51.100.9, 203.0.113.7" }));
      expect(forwarded(response, "x-mediease-client-ip"), path).toBe("203.0.113.7");
      expect(forwarded(response, "x-mediease-proxy-secret"), path).toBe(SECRET);
    }
  });

  it("adds nothing without a secret, or when the edge's header is missing", () => {
    vi.stubEnv("CLIENT_IP_HEADER", "x-real-ip");
    const without = proxy(request("http://localhost:3000/api/v1/me", { "x-real-ip": "203.0.113.7" }));
    expect(forwarded(without, "x-mediease-client-ip")).toBeNull();
    vi.stubEnv("TRUSTED_PROXY_SECRET", SECRET);
    const missing = proxy(request("http://localhost:3000/api/v1/me", {}));
    expect(forwarded(missing, "x-mediease-client-ip")).toBeNull();
    expect(forwarded(missing, "x-mediease-proxy-secret")).toBeNull();
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
