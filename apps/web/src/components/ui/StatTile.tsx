"use client";

import Link from "next/link";

import { cx } from "./cx";
import { m, RISE } from "./Motion";
import { TONES, type Tone } from "./StatusBadge";

/**
 * One number with its label. With `href` the whole tile is a link to the screen it summarises
 * (decision 6A), named by its words ("Waiting 3"). A changed number slides in, so a glance shows
 * what moved; with reduced motion it simply changes. Use inside a `STAGGER` list.
 */
export function StatTile({
  label,
  value,
  hint,
  href,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  hint?: string;
  href?: string;
  tone?: Tone;
}) {
  const body = (
    <>
      <span className="flex items-center gap-2 text-sm font-medium text-slate-700">
        <span aria-hidden="true" className={cx("size-2 rounded-full", TONES[tone].dot)} />
        {label}
      </span>
      <m.span
        key={String(value)}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="mt-1 block text-3xl font-bold tabular-nums text-slate-900"
      >
        {value}
      </m.span>
      {hint !== undefined && <span className="mt-0.5 block text-sm text-slate-600">{hint}</span>}
    </>
  );
  const surface = "block h-full rounded-card border border-slate-200 bg-white p-4 shadow-card";
  return (
    <m.li variants={RISE} className="list-none">
      {href === undefined ? (
        <div className={surface}>{body}</div>
      ) : (
        <Link
          href={href}
          className={cx(surface, "transition-colors hover:border-brand-600 hover:bg-brand-50 motion-reduce:transition-none")}
        >
          {body}
        </Link>
      )}
    </m.li>
  );
}
