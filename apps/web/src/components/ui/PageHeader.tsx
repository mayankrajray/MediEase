import type { ReactNode } from "react";

/**
 * The page's one `h1`, a line under it, and its main actions (wrapping under it on a phone).
 * M7c-P7: `breadcrumbs` (a `Breadcrumbs`) sits above the title on nested screens.
 */
export function PageHeader({
  title,
  description,
  actions,
  breadcrumbs,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  breadcrumbs?: ReactNode;
}) {
  return (
    <div className="mb-6 space-y-2">
      {breadcrumbs}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="heading-5 text-slate-900">{title}</h1>
          {description !== undefined && <p className="mt-1 text-pretty text-slate-700">{description}</p>}
        </div>
        {actions !== undefined && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}
