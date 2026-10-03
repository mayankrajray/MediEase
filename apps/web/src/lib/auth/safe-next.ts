/**
 * Where to go after signing in: only a path on this site (an open-redirect
 * guard). `?next=` is attacker-controllable, so anything that could leave the
 * origin or confuse a browser's URL parser is replaced by the fallback.
 */

const PARSER_ORIGIN = "http://next.invalid";
// Backslash (some browsers treat it as "/") and ASCII control characters (tab/newline
// are stripped by URL parsers, which can turn "/\t/evil" into "//evil").
const FORBIDDEN = /[\\\u0000-\u001f\u007f]/;

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
  // Signing in and landing on the sign-in page again would look like a failed sign-in.
  if (url.pathname === "/sign-in" || url.pathname.startsWith("/sign-in/")) {
    return fallback;
  }
  return `${url.pathname}${url.search}${url.hash}`;
}
