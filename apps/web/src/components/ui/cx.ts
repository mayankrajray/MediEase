/**
 * Joins class names, skipping the falsy ones: `cx("a", busy && "b")`. It does not resolve
 * conflicting Tailwind classes: a component that takes `className` lists it last, and a caller
 * overriding a default (padding, width) passes a class the default does not set. M7c-P7 tried
 * tailwind-merge here and removed it: its 8 KB went into every patient page and, with the font,
 * past the 200 KB budget (NFR-02).
 */
export function cx(...parts: readonly (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
