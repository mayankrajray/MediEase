/** Small, pure helpers for the ops forms. */

import { ApiError } from "@/lib/api/client";

const MAX_SLUG_LENGTH = 63;
const MAX_SPECIALTIES = 20;

/** A URL segment for a clinic name: lower-case words joined by single hyphens (the API's rule). */
export function suggestSlug(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, MAX_SLUG_LENGTH)
    .replace(/-+$/g, "");
}

/** "General Medicine, Paediatrics" -> ["General Medicine", "Paediatrics"]; empties and repeats dropped. */
export function parseSpecialties(text: string): string[] {
  const seen = new Set<string>();
  for (const part of text.split(",")) {
    const name = part.trim();
    if (name !== "") seen.add(name);
  }
  return [...seen].slice(0, MAX_SPECIALTIES);
}

/** Optional text fields are sent as null when left empty. */
export function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/**
 * Field-level problems from a `REQ_VALIDATION_FAILED` (`details.fields[]`), keyed by
 * field name. The API never echoes submitted values, so the reasons are safe to show.
 */
export function fieldErrors(error: unknown): Readonly<Record<string, string>> {
  if (!(error instanceof ApiError) || error.code !== "REQ_VALIDATION_FAILED") {
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
