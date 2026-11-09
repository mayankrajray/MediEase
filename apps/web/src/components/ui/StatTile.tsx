"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { cx } from "./cx";
import { m, RISE } from "./Motion";
import { TONES, type Tone } from "./StatusBadge";

/**
 * One number with its label. With `href` the whole tile is a link to the screen it summarises
 * (decision 6A), named by its words ("Waiting 3"). A changed number slides in, so a glance shows
 * what moved; with reduced motion it simply changes. Render inside a `<ul>`.
 *
 * M7c-P7 (M3): three layouts of the same content. `card` is a surface of its own; `segment` is one
 * part of a strip that shares a single surface (`STAT_STRIP`), so five counts read as one
 * summary instead of five boxes; `row` is a list line (label and hint on the left, the number on
 * the right, a chevron when it opens a screen) for counts that sit inside a card.
 */
export type StatLayout = "card" | "segment" | "row";

/** The shared surface of a strip of `segment` tiles: one border, hairlines between the parts. */
export const STAT_STRIP =
  "grid overflow-hidden rounded-card border border-line bg-line shadow-card gap-px";

export function StatTile({
  label,
  value,
  hint,
  href,
  tone = "neutral",
  layout = "card",
}: {
  label: string;
  value: number | string;
  hint?: string;
  href?: string;
  tone?: Tone;
  layout?: StatLayout;
}) {
  const number = (
    <m.span
      key={String(value)}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cx(
        "block font-bold tabular-nums text-slate-900",
        layout === "row" ? "text-2xl leading-8" : "mt-1 text-3xl",
      )}
    >
      {value}
    </m.span>
  );
  const name = (
    <span className="flex items-center gap-2 text-sm font-medium text-slate-700">
      <span aria-hidden="true" className={cx("size-2 shrink-0 rounded-full", TONES[tone].dot)} />
      {label}
    </span>
  );
  const note = hint !== undefined && <span className="mt-0.5 block text-sm text-slate-600">{hint}</span>;

  // A row keeps the reading order label, number, hint (so a link is named "Follow-ups due 2 …")
  // and places them with the grid: the number and chevron on the right, across both lines.
  const body =
    layout === "row" ? (
      <>
        <span className="col-start-1 row-start-1 min-w-0">{name}</span>
        <span className="col-start-2 row-span-2 row-start-1 self-center">{number}</span>
        {hint !== undefined && <span className="col-start-1 row-start-2 min-w-0 text-sm text-slate-600">{hint}</span>}
        {href !== undefined && (
          <ChevronRight aria-hidden="true" className="col-start-3 row-span-2 row-start-1 size-4 self-center text-slate-500 transition-transform duration-200 ease-brand group-hover:translate-x-0.5 motion-reduce:transition-none" />
        )}
      </>
    ) : (
      <>
        {name}
        {number}
        {note}
      </>
    );

  const surface = {
    card: "block h-full rounded-card border border-slate-200 bg-white p-4 shadow-card",
    segment: "block h-full bg-surface px-4 py-3.5",
    row: "grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-0.5 rounded-lg px-3 py-2.5",
  }[layout];
  const hover = {
    card: "hover:border-brand-600 hover:bg-brand-50",
    segment: "hover:bg-brand-50",
    row: "hover:bg-brand-50",
  }[layout];

  return (
    <m.li variants={RISE} className="list-none">
      {href === undefined ? (
        <div className={surface}>{body}</div>
      ) : (
        <Link href={href} className={cx("group", surface, "transition-colors duration-200 ease-brand motion-reduce:transition-none", hover)}>
          {body}
        </Link>
      )}
    </m.li>
  );
}
