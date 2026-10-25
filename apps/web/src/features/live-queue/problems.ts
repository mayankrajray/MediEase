/** Why the live token page cannot show a place (M6b-P6; spec R71). Safe on the server and client. */

import { ApiError } from "@/lib/api/client";
import type { LiveWords } from "@/lib/i18n/patient-notifications";

export type LiveProblem = "invalid" | "expired" | "rate" | "unavailable";

export function liveProblemOf(error: unknown): LiveProblem {
  if (!(error instanceof ApiError)) return "unavailable";
  if (error.status === 410 || error.code === "LINK_EXPIRED") return "expired";
  if (error.status === 404 || error.code === "LINK_INVALID") return "invalid";
  if (error.status === 429) return "rate";
  return "unavailable";
}

export function liveProblemText(words: LiveWords, problem: LiveProblem): string {
  switch (problem) {
    case "expired":
      return words.expired;
    case "invalid":
      return words.invalid;
    case "rate":
      return words.rateLimited;
    default:
      return words.unavailable;
  }
}
