// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import nextConfig, { apiInternalUrl } from "../next.config";
import { CSP_HEADER, config, proxy } from "./proxy";

function nonceOf(csp: string | null): string | undefined {
  return csp?.match(/'nonce-([^']+)'/)?.[1];
}

describe("proxy (per-request CSP)", () => {
  it("sets a CSP with a fresh nonce on every page response", () => {
    const first = proxy(new NextRequest("http://localhost:3000/status"));
    const second = proxy(new NextRequest("http://localhost:3000/status"));

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
