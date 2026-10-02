import type { NextConfig } from "next";

import { STATIC_SECURITY_HEADERS } from "./src/lib/security/headers";

/**
 * The API on the internal network, e.g. http://api:8000 in compose or
 * http://localhost:8000 for `make dev-web`. Read when rewrites are built, so a
 * missing or malformed value fails `next dev`, `next build` and `next start`
 * with a clear message instead of a broken proxy.
 */
export function apiInternalUrl(): string {
  const raw = process.env.API_INTERNAL_URL ?? "";
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(
      `API_INTERNAL_URL must be an absolute http(s) URL (got ${raw ? `"${raw}"` : "nothing"}); see .env.example.`,
    );
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`API_INTERNAL_URL must use http or https (got "${url.protocol}").`);
  }
  return url.origin + url.pathname.replace(/\/+$/, "");
}

const nextConfig: NextConfig = {
  // Self-contained server bundle for the web Docker image (M0-P5).
  output: "standalone",
  // Do not advertise the framework in response headers.
  poweredByHeader: false,
  reactStrictMode: true,

  // Same-origin API proxy (ADR-0006): the browser only ever calls this origin.
  async rewrites() {
    const api = apiInternalUrl();
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/health", destination: `${api}/health` },
      { source: "/ready", destination: `${api}/ready` },
    ];
  },

  async headers() {
    return [{ source: "/:path*", headers: [...STATIC_SECURITY_HEADERS] }];
  },
};

export default nextConfig;
