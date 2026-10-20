import type { ReactNode } from "react";

/** Nothing to show yet, said plainly, with the next step when there is one. */
export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-card border border-dashed border-slate-300 bg-white px-4 py-8 text-center">
      <p className="font-semibold text-slate-900">{title}</p>
      {children !== undefined && <div className="mx-auto mt-1 max-w-prose text-slate-700">{children}</div>}
      {action !== undefined && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
