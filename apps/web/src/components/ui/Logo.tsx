import { cx } from "./cx";

/**
 * The MediEase logo (M7c-P7; DESIGN.md §6): the emblem, a teal cross holding a person with a mint
 * leaf, and the wordmark in the interface font. Inline SVG, so the page fetches nothing for it and
 * it scales crisply. The emblem is decorative; the word "MediEase" is the logo's text, so screen
 * readers and tests read the name once. Files for other uses: `public/brand/`.
 *
 * - `size`: the emblem's height (`sm` 28 px for headers, `md` 36 px, `lg` 48 px).
 * - `compact`: the emblem alone on a phone, with the name kept for screen readers.
 * - `tone="onDark"`: white wordmark and mint emblem for dark fills.
 */
const SIZES = { sm: "size-7", md: "size-9", lg: "size-12" } as const;
const WORDS = { sm: "text-lg", md: "text-xl", lg: "text-2xl" } as const;

export function Emblem({ className, tone = "brand" }: { className?: string; tone?: "brand" | "onDark" }) {
  // The logo's own colours (public/brand/mediease-icon.svg). M7c-P7: on light backgrounds the leaf
  // is a deeper mint (#86D0C2) so it stays visible against white (the delivered #DDF3EE was 1.1:1);
  // on dark fills the cross turns mint and the leaf teal.
  const main = tone === "onDark" ? "#DDF3EE" : "#147D72";
  const leaf = tone === "onDark" ? "#147D72" : "#86D0C2";
  return (
    <svg aria-hidden="true" focusable="false" viewBox="12 12 176 176" className={cx("shrink-0", className)}>
      <path
        fill={main}
        fillRule="evenodd"
        d="M 84,16 H 116 C 127,16 136,25 136,36 V 52 C 136,59 138.5,62.5 142,64.5 C 126,71 111,81.5 100,95 C 89,81.5 74,71 58,64.5 C 61.5,62.5 64,59 64,52 V 36 C 64,25 73,16 84,16 Z M 100,48.5 A 13.5,13.5 0 1,0 100,75.5 A 13.5,13.5 0 1,0 100,48.5 Z"
      />
      <path
        fill={main}
        d="M 16,84 C 16,71 26,62 39,63.5 C 67,67 89,86 91.5,116 C 93,137 86,158 73,174.5 V 136 C 73,128 67,122 59,122 H 34 C 24,122 16,114 16,104 V 84 Z"
      />
      <path
        fill={leaf}
        d="M 161,63.5 C 174,62 184,71 184,84 V 104 C 184,114 176,122 166,122 H 146 C 146,108 142,95 135,84 C 141,97 143,115 139,134 C 133,161 109,179 76,184 C 91,168 100,147 102,124 C 104,98 117,79 136,69.5 C 122,81 112,99 109,122 C 107,136 103,148 97,158 C 113,147 123,130 126,108 C 128,95 126,84 123,78 C 134,71 147,65 161,63.5 Z"
      />
    </svg>
  );
}

export function Logo({
  size = "sm",
  compact = false,
  tone = "brand",
  className,
}: {
  size?: keyof typeof SIZES;
  compact?: boolean;
  tone?: "brand" | "onDark";
  className?: string;
}) {
  return (
    <span className={cx("inline-flex items-center gap-2 font-bold tracking-tight", WORDS[size], className)}>
      <Emblem tone={tone} className={SIZES[size]} />
      <span className={cx(tone === "onDark" ? "text-white" : "text-slate-900", compact && "sr-only sm:not-sr-only")}>
        MediEase
      </span>
    </span>
  );
}
