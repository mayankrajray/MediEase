import type { ReactNode } from "react";

/**
 * Nothing to show yet, said plainly, with the next step when there is one. M7c-P7: an optional
 * decorative `icon` above the title (DESIGN.md §5: a composed "getting started" view).
 */
export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-dashed border-slate-300 bg-surface px-4 py-10 text-center">
      {icon !== undefined && (
        <div aria-hidden="true" className="mx-auto mb-3 grid size-11 place-items-center rounded-full bg-brand-50 text-brand-700">
          {icon}
        </div>
      )}
      <p className="font-semibold text-slate-900">{title}</p>
      {children !== undefined && <div className="mx-auto mt-1 max-w-prose text-pretty text-slate-700">{children}</div>}
      {action !== undefined && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}
