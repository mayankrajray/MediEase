"use client";

import type { ReactNode } from "react";

import { Dialog } from "@/components/Dialog";
import { Button } from "@/components/ui/Button";

/**
 * M7c-P7: "are you sure" on the shared `Dialog` (DESIGN.md §5). The confirm button names the
 * action ("Cancel appointment", never "OK"); `danger` makes it red for an action that cannot be
 * undone. `busy` keeps it open with a loading button while the call runs. Escape and the second
 * button keep everything as it was. Render it only while open.
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel = "Keep it",
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: {
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog title={title} onClose={onClose}>
      {children !== undefined && <div className="text-pretty text-slate-700">{children}</div>}
      <div className="flex flex-wrap justify-end gap-2 pt-2">
        <Button onClick={onClose} disabled={busy} data-autofocus>
          {cancelLabel}
        </Button>
        <Button variant={danger ? "danger" : "primary"} loading={busy} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
