"use client";

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";

/**
 * A side panel on a native `<dialog>` opened with `showModal()`: the browser keeps
 * focus inside it, makes the page behind inert and closes it on Escape, with no
 * library. A descendant marked data-autofocus takes the focus once it is open; otherwise the
 * browser's choice stands. Focus returns to whatever opened it. Render it only while open. It slides
 * in from its side with CSS (M6-P2 decision 3A, `.me-overlay` in globals.css), not with reduced motion.
 */
export function Drawer({
  title,
  onClose,
  side = "right",
  children,
}: {
  title: string;
  onClose: () => void;
  /** M6-P1: the phone menu opens from the left, where the sidebar sits on a wide screen. */
  side?: "left" | "right";
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (dialog !== null && !dialog.open) {
      // jsdom has no showModal; a real browser always does.
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      // Focus only once the dialog is open: children's effects run before this one, and a
      // child's own focus() then does not reliably stick (it stopped doing so under jsdom
      // 30.1.2). A field marked data-autofocus (the patient search, M3-P5) is where the
      // person starts typing.
      dialog.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    }
    return () => opener?.focus();
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      className={`me-overlay ${side === "left" ? "me-drawer-left ml-0 mr-auto max-w-xs" : "me-drawer-right ml-auto mr-0 max-w-lg"} h-full max-h-none w-full overflow-y-auto bg-surface p-0 shadow-modal backdrop:bg-slate-950/40`}
    >
      <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-line bg-surface/95 px-5 py-3 backdrop-blur">
        <h2 id={titleId} className="heading-6 text-slate-900">
          {title}
        </h2>
        <Button variant="ghost" size="sm" onClick={onClose} className="-mr-2" icon={<X className="size-5" />}>
          <span className="sr-only">Close</span>
        </Button>
      </div>
      <div className="space-y-4 p-5">{children}</div>
    </dialog>
  );
}
