/**
 * Patient-facing words for the portal's sign-in page (M6a-P3). `?reason=` is
 * attacker-controllable, so only these fixed messages are ever shown for it.
 */

import { ApiError } from "@/lib/api/client";
import {
  AUTH_ACCOUNT_DISABLED,
  AUTH_REFRESH_REUSED,
  AUTH_SESSION_EXPIRED,
} from "@/lib/auth/refresh";

export const PRT_INVALID_CREDENTIALS = "PRT_INVALID_CREDENTIALS";
export const PRT_EMAIL_TAKEN = "PRT_EMAIL_TAKEN";
/** The staff password policy applies to patients too (ADR-0015 decision 5). */
export const MIN_PASSWORD_LENGTH = 12;

export const PORTAL_SIGN_IN_REASONS = {
  session_ended: "You were signed out. Please sign in again.",
  session_ended_for_safety: "You were signed out for your safety. Please sign in again.",
  account_disabled: "This account is not active. Contact MediEase support.",
  google_failed: "Google sign-in did not work. Try again, or use your email and password.",
  google_cancelled: "Google sign-in was cancelled.",
  too_many_attempts: "Too many attempts. Wait a minute and try again.",
  password_reset: "Your password was changed. Sign in with the new one.",
} as const;

export type PortalSignInReason = keyof typeof PORTAL_SIGN_IN_REASONS;

export function parsePortalReason(raw: string | null | undefined): PortalSignInReason | undefined {
  return raw !== null && raw !== undefined && Object.hasOwn(PORTAL_SIGN_IN_REASONS, raw)
    ? (raw as PortalSignInReason)
    : undefined;
}

/** Why a portal session ended, when an error says it did. */
export function portalReasonForEndedSession(error: unknown): PortalSignInReason | undefined {
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
