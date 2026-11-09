import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";

export type AlertTone = "info" | "success" | "warning" | "danger";

const TONES: Record<AlertTone, { readonly box: string; readonly icon: string; readonly Icon: typeof Info }> = {
  info: { box: "border-info-line bg-info-soft", icon: "text-info", Icon: Info },
  success: { box: "border-success-line bg-success-soft", icon: "text-success", Icon: CircleCheck },
  warning: { box: "border-warning-line bg-warning-soft", icon: "text-warning", Icon: TriangleAlert },
  danger: { box: "border-danger-line bg-danger-soft", icon: "text-danger", Icon: CircleAlert },
};

/**
 * M7c-P7: a message inside the page (DESIGN.md §1 semantic colours). The tone is a second cue:
 * the `title` and words say what happened. Static notices need no role; pass `role="status"` for
 * a polite update or `role="alert"` for an error that appears after an action.
 */
export function Alert({
  tone = "info",
  title,
  children,
  action,
  role,
  className,
}: {
  tone?: AlertTone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  role?: "status" | "alert";
  className?: string;
}) {
  const { box, icon, Icon } = TONES[tone];
  return (
    <div role={role} className={cx("flex gap-3 rounded-xl border p-4 text-slate-900", box, className)}>
      <Icon aria-hidden="true" className={cx("mt-0.5 size-5 shrink-0", icon)} />
      <div className="min-w-0 flex-1 space-y-1">
        {title !== undefined && <p className="font-semibold">{title}</p>}
        {children !== undefined && <div className="text-pretty text-slate-800">{children}</div>}
        {action !== undefined && <div className="pt-2">{action}</div>}
      </div>
    </div>
  );
}
