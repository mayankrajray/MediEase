/**
 * Where to go after signing in: only a path on this site (an open-redirect
 * guard). `?next=` is attacker-controllable, so anything that could leave the
 * origin or confuse a browser's URL parser is replaced by the fallback.
 */

const PARSER_ORIGIN = "http://next.invalid";
// Backslash (some browsers treat it as "/") and ASCII control characters (tab/newline
// are stripped by URL parsers, which can turn "/\t/evil" into "//evil").
const FORBIDDEN = /[\\\u0000-\u001f\u007f]/;
const SIGN_IN_PAGES = ["/sign-in", "/portal/sign-in", "/portal/sign-up"];

export function safeNextPath(raw: string | null | undefined, fallback = "/"): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || FORBIDDEN.test(raw)) {
    return fallback;
  }
  let url: URL;
  try {
    url = new URL(raw, PARSER_ORIGIN);
  } catch {
    return fallback;
  }
  if (url.origin !== PARSER_ORIGIN) {
    return fallback;
  }
  // Signing in and landing on a sign-in page again would look like a failed sign-in.
  if (SIGN_IN_PAGES.some((page) => url.pathname === page || url.pathname.startsWith(`${page}/`))) {
    return fallback;
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

/** True for `/portal` and the pages under it (the patient portal, M6a-P3). */
export function isPortalPath(pathname: string): boolean {
  return pathname === "/portal" || pathname.startsWith("/portal/");
}

/**
 * `safeNextPath` for the patient portal: the result also stays inside `/portal`, so a patient
 * sign-in can never be sent to a staff page (and the API checks the same, ADR-0015).
 */
export function safePortalNextPath(raw: string | null | undefined, fallback = "/portal"): string {
  const next = safeNextPath(raw, fallback);
  return isPortalPath(new URL(next, PARSER_ORIGIN).pathname) ? next : fallback;
}

/** `safeNextPath` for staff: never into the patient portal. */
export function safeStaffNextPath(raw: string | null | undefined, fallback: string): string {
  const next = safeNextPath(raw, fallback);
  return isPortalPath(new URL(next, PARSER_ORIGIN).pathname) ? fallback : next;
}
