import type { ReactNode } from "react";

import { cx } from "./cx";

/**
 * M7c-P7: a record's details as label and value pairs (a `<dl>`), one column on a phone and two
 * from 640 px. A missing value says so in words.
 */
export function KeyValue({
  items,
  className,
}: {
  items: readonly { readonly label: string; readonly value: ReactNode }[];
  className?: string;
}) {
  return (
    <dl className={cx("grid gap-x-6 gap-y-3 sm:grid-cols-2", className)}>
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-sm text-slate-700">{item.label}</dt>
          <dd className="mt-0.5 break-words font-medium text-slate-900">{item.value ?? "Not recorded"}</dd>
        </div>
      ))}
    </dl>
  );
}
