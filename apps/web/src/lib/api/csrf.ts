/**
 * The CSRF double-submit key (ADR-0006).
 *
 * Sign-in sets `me_csrf` as a cookie scripts *can* read (unlike the HttpOnly
 * session tokens). Every unsafe request copies it into `X-CSRF-Token`; a
 * cross-site page can make the browser send the cookie but cannot read it, so
 * it cannot set the matching header.
 */

export const CSRF_COOKIE = "me_csrf";
/** The patient portal's own key (M6a-P3, ADR-0015): portal requests send this one instead. */
export const PORTAL_CSRF_COOKIE = "me_pt_csrf";

/** The value of one cookie in a `document.cookie`-style string, or undefined. */
export function parseCookie(cookies: string, name: string): string | undefined {
  for (const part of cookies.split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() !== name) continue;
    const raw = part.slice(separator + 1).trim();
    try {
      return decodeURIComponent(raw);
    } catch {
      return raw;
    }
  }
  return undefined;
}

/** The current CSRF token, or undefined on the server or when signed out. */
export function readCsrfToken(cookie: string = CSRF_COOKIE): string | undefined {
  if (typeof document === "undefined") {
    return undefined;
  }
  return parseCookie(document.cookie, cookie);
}
