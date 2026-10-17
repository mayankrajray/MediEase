/**
 * The patient page's view cookie (M4-P5 decision 3A). It holds the API's signed 30-minute view
 * token, HttpOnly, scoped to this link's page path, so one link's cookie is never sent to another
 * link's page; the API checks it on every read.
 */

export const VIEW_COOKIE = "me_rx_view";

export function pagePath(token: string): string {
  return `/p/${encodeURIComponent(token)}`;
}

/** Problems the challenge can report back to the page in its `?e=` query. */
export type Problem = "failed" | "locked" | "rate" | "unavailable" | "invalid" | "expired" | "revoked";

const PROBLEMS: ReadonlySet<string> = new Set(["failed", "locked", "rate", "unavailable", "invalid", "expired", "revoked"]);

export function readProblem(value: string | string[] | undefined): Problem | undefined {
  return typeof value === "string" && PROBLEMS.has(value) ? (value as Problem) : undefined;
}

/** An API error code to the problem the page shows; anything unknown is "unavailable". */
export function problemFor(code: string): Problem {
  switch (code) {
    case "LINK_CHALLENGE_FAILED":
    case "REQ_VALIDATION_FAILED":
      return "failed";
    case "LINK_LOCKED":
      return "locked";
    case "LINK_RATE_LIMITED":
      return "rate";
    case "LINK_INVALID":
      return "invalid";
    case "LINK_EXPIRED":
      return "expired";
    case "LINK_REVOKED":
      return "revoked";
    default:
      return "unavailable";
  }
}
