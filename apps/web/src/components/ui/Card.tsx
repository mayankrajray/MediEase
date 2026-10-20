import { useId, type ReactNode } from "react";

import { cx } from "./cx";

/**
 * A surface for one topic. With a `title` it is a labelled region (an `h2` names it), so screen
 * reader users can jump between cards; `action` sits beside the title (a link to the full screen).
 */
export function Card({
  title,
  action,
  className,
  children,
}: {
  title?: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const titleId = useId();
  return (
    <section
      aria-labelledby={title === undefined ? undefined : titleId}
      className={cx("rounded-card border border-slate-200 bg-white p-4 shadow-card sm:p-5", className)}
    >
      {title !== undefined && (
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 id={titleId} className="text-base font-semibold text-slate-900">
            {title}
          </h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
