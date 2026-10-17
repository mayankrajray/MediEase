/** Small, pure helpers for the ops forms. */

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
