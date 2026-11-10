import type { ReactNode } from "react";

import { cx } from "./cx";

/** One accent per status (decision 1A). Each pair is AA on its own background. */
export type Tone = "neutral" | "brand" | "waiting" | "active" | "done" | "missed" | "danger";

export const TONES: Record<Tone, { readonly badge: string; readonly dot: string }> = {
  neutral: { badge: "bg-slate-100 text-slate-800 ring-slate-300", dot: "bg-slate-500" },
  brand: { badge: "bg-brand-50 text-brand-900 ring-brand-200", dot: "bg-brand-600" },
  waiting: { badge: "bg-amber-50 text-amber-900 ring-amber-300", dot: "bg-amber-500" },
  active: { badge: "bg-sky-50 text-sky-900 ring-sky-300", dot: "bg-sky-600" },
  done: { badge: "bg-emerald-50 text-emerald-900 ring-emerald-300", dot: "bg-emerald-600" },
  missed: { badge: "bg-rose-50 text-rose-900 ring-rose-300", dot: "bg-rose-600" },
  danger: { badge: "bg-red-50 text-red-900 ring-red-300", dot: "bg-red-700" },
};

/** A status in words, with colour only as a second cue (never colour alone). */
export function StatusBadge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={cx(
        // M7c-P7 (M4 phone fix): one line, so a pill never becomes a tall ellipse in a narrow
        // column; a cell lets the table grow, and the phone card gives it the full width.
        "inline-flex max-w-full shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-sm font-medium ring-1 ring-inset",
        TONES[tone].badge,
      )}
    >
      <span aria-hidden="true" className={cx("size-1.5 rounded-full", TONES[tone].dot)} />
      {children}
    </span>
  );
}
