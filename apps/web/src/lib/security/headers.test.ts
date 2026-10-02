// @vitest-environment node
import { describe, expect, it } from "vitest";

import { STATIC_SECURITY_HEADERS, buildContentSecurityPolicy, newNonce } from "./headers";

function directive(csp: string, name: string): string[] {
  const entry = csp.split("; ").find((d) => d.startsWith(`${name} `));
  return entry ? entry.split(" ").slice(1) : [];
}

describe("Content-Security-Policy", () => {
  const prod = buildContentSecurityPolicy("abc123", { isDev: false });

  it("allows scripts only with the request's nonce, never inline or eval in production", () => {
    const scripts = directive(prod, "script-src");
    expect(scripts).toContain("'nonce-abc123'");
    expect(scripts).toContain("'strict-dynamic'");
    expect(scripts).not.toContain("'unsafe-inline'");
    expect(scripts).not.toContain("'unsafe-eval'");
  });

  it("forbids framing, plugins and foreign form targets", () => {
    expect(directive(prod, "frame-ancestors")).toEqual(["'none'"]);
    expect(directive(prod, "object-src")).toEqual(["'none'"]);
    expect(directive(prod, "form-action")).toEqual(["'self'"]);
    expect(directive(prod, "base-uri")).toEqual(["'self'"]);
    expect(directive(prod, "connect-src")).toEqual(["'self'"]);
  });

  it("relaxes only what next dev needs in development", () => {
    const dev = buildContentSecurityPolicy("n", { isDev: true });
    expect(directive(dev, "script-src")).toContain("'unsafe-eval'");
    expect(directive(dev, "connect-src")).toContain("ws:");
  });
});

describe("newNonce", () => {
  it("is 128-bit base64 and unique per call", () => {
    const nonces = new Set(Array.from({ length: 50 }, newNonce));
    expect(nonces.size).toBe(50);
    for (const nonce of nonces) {
      expect(atob(nonce)).toHaveLength(16);
    }
  });
});

describe("static security headers", () => {
  it("send nosniff, no referrer and deny framing", () => {
    const headers = Object.fromEntries(STATIC_SECURITY_HEADERS.map((h) => [h.key, h.value]));
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["Referrer-Policy"]).toBe("no-referrer");
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["Permissions-Policy"]).toContain("camera=()");
  });
});
