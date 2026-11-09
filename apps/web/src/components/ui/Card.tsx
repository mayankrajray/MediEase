import { useId, type ReactNode } from "react";

import { cx } from "./cx";

/**
 * A surface for one topic. With a `title` it is a labelled region (an `h2` names it), so screen
 * reader users can jump between cards; `action` sits beside the title (a link to the full screen)
 * and `description` under it. M7c-P7: surface, hairline border and soft shadow (DESIGN.md §3).
 */
export function Card({
  title,
  description,
  action,
  className,
  children,
}: {
  title?: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const titleId = useId();
  return (
    <section
      aria-labelledby={title === undefined ? undefined : titleId}
      className={cx("rounded-card border border-line bg-surface p-4 shadow-card sm:p-5", className)}
    >
      {title !== undefined && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold text-slate-900">
              {title}
            </h2>
            {description !== undefined && <p className="mt-0.5 text-sm text-slate-700">{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
