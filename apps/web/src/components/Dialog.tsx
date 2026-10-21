"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

/**
 * A centred modal on a native `<dialog>` (`showModal()`): focus stays inside, the page behind
 * is inert, Escape closes, a descendant marked data-autofocus takes the focus once it is open,
 * and focus returns to what opened it. For confirmations and short
 * forms (M3-P5); side panels use `Drawer`. Render it only while open. It fades and rises in with CSS
 * (M6-P2 decision 3A, `.me-overlay` in globals.css), not at all with reduced motion.
 */
export function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (dialog !== null && !dialog.open) {
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
      className="me-overlay me-dialog m-auto w-[calc(100%-2rem)] max-w-md rounded-card bg-white p-0 shadow-xl backdrop:bg-slate-900/40"
    >
      <h2 id={titleId} className="border-b border-slate-200 px-5 py-3 text-lg font-semibold">
        {title}
      </h2>
      <div className="space-y-4 p-5">{children}</div>
    </dialog>
  );
}
