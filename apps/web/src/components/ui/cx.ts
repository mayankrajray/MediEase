/** Joins class names, skipping the falsy ones: `cx("a", busy && "b")`. */
export function cx(...parts: readonly (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
