"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

/**
 * A side panel on a native `<dialog>` opened with `showModal()`: the browser keeps
 * focus inside it, makes the page behind inert and closes it on Escape, with no
 * library. A descendant marked data-autofocus takes the focus once it is open; otherwise the
 * browser's choice stands. Focus returns to whatever opened it. Render it only while open.
 */
export function Drawer({
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
      className="ml-auto mr-0 h-full max-h-none w-full max-w-lg overflow-y-auto bg-white p-0 shadow-xl backdrop:bg-slate-900/40"
    >
      <div className="flex items-center justify-between border-b border-slate-300 px-5 py-3">
        <h2 id={titleId} className="text-xl font-bold">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-500 px-3 py-1 hover:bg-slate-100"
        >
          Close
        </button>
      </div>
      <div className="space-y-4 p-5">{children}</div>
    </dialog>
  );
}
