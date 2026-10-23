/**
 * Words for things the API does not say for us: why a person landed on the
 * sign-in page, and how long a lock lasts. Everything else shows the API's own
 * `message` (safe to display, docs/ERRORS.md) with "Ref: <request_id>".
 */

import {
  ApiError,
  WEB_API_BAD_RESPONSE,
  WEB_API_UNREACHABLE,
} from "@/lib/api/client";
import {
  AUTH_ACCOUNT_DISABLED,
  AUTH_REFRESH_REUSED,
  AUTH_SESSION_EXPIRED,
} from "@/lib/auth/refresh";

export const AUTH_LOCKED = "AUTH_LOCKED";
export const AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS";

/** Why the sign-in page was opened (allow-listed: `?reason=` is attacker-controllable). */
export const SIGN_IN_REASONS = {
  session_ended: "Your session ended. Please sign in again.",
  session_ended_for_safety:
    "Your session was ended for safety. Please sign in again. If this keeps happening, tell your clinic owner.",
  account_disabled: "This account has been deactivated. Contact your clinic owner.",
  // M6a-P3: where a Google sign-in comes back when it did not finish (ADR-0015).
  google_failed: "Google sign-in did not work. Try again, or sign in with your password.",
  google_cancelled: "Google sign-in was cancelled.",
  google_no_account:
    "No MediEase staff account uses this Google address. Sign in with your password, or ask your clinic owner to invite this address.",
  too_many_attempts: "Too many attempts. Wait a minute and try again.",
  // M6a-P4: back from a completed reset.
  password_reset: "Your password was changed and every session was ended. Sign in with the new one.",
} as const;

export type SignInReason = keyof typeof SIGN_IN_REASONS;

export function parseSignInReason(raw: string | null | undefined): SignInReason | undefined {
  return raw !== null && raw !== undefined && Object.hasOwn(SIGN_IN_REASONS, raw)
    ? (raw as SignInReason)
    : undefined;
}

/** The sign-in reason that explains an error that ended the session, if it is one. */
export function reasonForEndedSession(error: unknown): SignInReason | undefined {
  if (!(error instanceof ApiError)) return undefined;
  switch (error.code) {
    case AUTH_SESSION_EXPIRED:
      return "session_ended";
    case AUTH_REFRESH_REUSED:
      return "session_ended_for_safety";
    case AUTH_ACCOUNT_DISABLED:
      return "account_disabled";
    default:
      return undefined;
  }
}

/** "about 14 minutes", "1 minute", "30 seconds". Rounds up: never promise a shorter wait. */
export function formatWait(seconds: number): string {
  const safe = Math.max(1, Math.ceil(seconds));
  if (safe < 60) return `${safe} ${safe === 1 ? "second" : "seconds"}`;
  const minutes = Math.ceil(safe / 60);
  return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}

export interface ErrorText {
  readonly message: string;
  readonly requestId: string;
  readonly code: string;
}

/** What to show for a failed API call: the API's message plus the ref to quote. */
export function describeError(error: unknown): ErrorText {
  if (error instanceof ApiError) {
    return { message: error.message, requestId: error.requestId, code: error.code };
  }
  return {
    message: "Something went wrong. Please try again.",
    requestId: "",
    code: "WEB_UNEXPECTED",
  };
}

/** Errors worth a "Try again" button: the failure was in reaching or reading the API, not in the request. */
export function isRetryable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === WEB_API_UNREACHABLE ||
      error.code === WEB_API_BAD_RESPONSE ||
      error.status >= 500)
  );
}
