import { cx } from "./cx";

/**
 * M7c-P7: a person's initials in a circle, beside their name (never instead of it, so it is
 * decorative). No photos: patient images are never shown in lists.
 */
export function initials(name: string): string {
  const words = name
    .replace(/^(dr|mr|mrs|ms)\.?\s+/i, "")
    .split(/\s+/)
    .filter(Boolean);
  const first = words[0]?.[0] ?? "";
  const last = words.length > 1 ? (words.at(-1)?.[0] ?? "") : "";
  return `${first}${last}`.toUpperCase();
}

export function Avatar({ name, size = "md", className }: { name: string; size?: "sm" | "md"; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-grid shrink-0 place-items-center rounded-full bg-brand-100 font-semibold text-brand-900",
        size === "sm" ? "size-7 text-xs" : "size-9 text-sm",
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
