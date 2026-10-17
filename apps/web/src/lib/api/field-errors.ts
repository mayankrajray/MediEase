/** Reading field-level problems out of an API error, for forms (shared by the ops and patient forms). */

import { ApiError } from "./client";

export const REQ_VALIDATION_FAILED = "REQ_VALIDATION_FAILED";

/**
 * Field-level problems from `details.fields[]`, keyed by field name. By default only
 * `REQ_VALIDATION_FAILED` carries them; a caller may name other codes that use the same
 * shape (e.g. `PAT_PHONE_INVALID`, docs/ERRORS.md). The API never echoes submitted
 * values, so the reasons are safe to show.
 */
export function fieldErrors(
  error: unknown,
  codes: readonly string[] = [REQ_VALIDATION_FAILED],
): Readonly<Record<string, string>> {
  if (!(error instanceof ApiError) || !codes.includes(error.code)) {
    return {};
  }
  const fields: unknown = error.details["fields"];
  if (!Array.isArray(fields)) {
    return {};
  }
  const result: Record<string, string> = {};
  for (const entry of fields as unknown[]) {
    if (
      typeof entry === "object" &&
      entry !== null &&
      "field" in entry &&
      typeof entry.field === "string" &&
      "reason" in entry &&
      typeof entry.reason === "string" &&
      !(entry.field in result)
    ) {
      result[entry.field] = entry.reason;
    }
  }
  return result;
}
