/**
 * Security headers for every web response (docs/SECURITY_AND_COMPLIANCE.md,
 * M0-P4 checklist item).
 *
 * The Content-Security-Policy is nonce-based: src/proxy.ts creates a fresh
 * random nonce per request, Next.js stamps it on the scripts it renders, and
 * the browser runs only scripts carrying it. Injected markup cannot execute,
 * which matters for an app that will show patient data.
 */

export interface CspOptions {
  /** Development needs eval (React debugging) and a websocket (hot reload). */
  readonly isDev: boolean;
}

export function buildContentSecurityPolicy(nonce: string, { isDev }: CspOptions): string {
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    // 'strict-dynamic' lets nonce-approved scripts load Next's chunks; hosts are ignored.
    "script-src": ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(isDev ? ["'unsafe-eval'"] : [])],
    // Inline styles stay allowed: Next and React set style attributes. Styles
    // cannot run code, so this is a much smaller risk than inline scripts.
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'"],
    "connect-src": ["'self'", ...(isDev ? ["ws:"] : [])],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    // The app must never be framed (clickjacking).
    "frame-ancestors": ["'none'"],
  };
  return Object.entries(directives)
    .map(([name, values]) => `${name} ${values.join(" ")}`)
    .join("; ");
}

/** Headers that do not change per request; applied by next.config to every path. */
export const STATIC_SECURITY_HEADERS: readonly { key: string; value: string }[] = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Patient-link tokens will be in URLs (M4): never send a Referer anywhere.
  { key: "Referrer-Policy", value: "no-referrer" },
  // Legacy equivalent of frame-ancestors 'none' for old browsers.
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

/** A base64 nonce from 128 random bits (CSP Level 3 recommends at least 128). */
export function newNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}
