"use client";

import * as RadixToast from "@radix-ui/react-toast";
import { CircleCheck, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { cx } from "./cx";

/**
 * M7c-P7: short confirmations of an action that finished out of view (DESIGN.md §5), on
 * `@radix-ui/react-toast` (polite live region, F8 to reach the viewport, Escape and swipe to
 * dismiss, pauses while hovered or focused). Never for an error that needs action: those stay
 * in the page as `ErrorNotice`. Wrap a surface in `ToastProvider`, then `useToast()(...)`.
 */
export interface ToastInput {
  readonly title: string;
  readonly description?: string;
  readonly tone?: "success" | "info";
}

interface Shown extends ToastInput {
  readonly id: number;
}

const Context = createContext<((toast: ToastInput) => void) | null>(null);

export function useToast(): (toast: ToastInput) => void {
  const show = useContext(Context);
  if (show === null) throw new Error("useToast needs a ToastProvider");
  return show;
}

let next = 1;

export function ToastProvider({ children, label = "Notifications" }: { children: ReactNode; label?: string }) {
  const [toasts, setToasts] = useState<readonly Shown[]>([]);
  const show = useCallback((toast: ToastInput) => {
    const id = next++;
    setToasts((current) => [...current.slice(-2), { ...toast, id }]);
  }, []);
  const value = useMemo(() => show, [show]);

  return (
    <Context.Provider value={value}>
      <RadixToast.Provider duration={6000} label={label}>
        {children}
        {toasts.map((t) => {
          const Icon = t.tone === "info" ? Info : CircleCheck;
          return (
            <RadixToast.Root
              key={t.id}
              // "background": announced politely, never interrupting what the user is doing.
              type="background"
              onOpenChange={(open) => {
                if (!open) setToasts((current) => current.filter((c) => c.id !== t.id));
              }}
              className={cx(
                "flex w-full items-start gap-3 rounded-xl border border-line bg-surface p-4 shadow-pop",
                "data-[state=open]:animate-[me-toast-in_300ms_var(--ease-brand)] motion-reduce:animate-none",
              )}
            >
              <Icon aria-hidden="true" className={cx("mt-0.5 size-5 shrink-0", t.tone === "info" ? "text-info" : "text-success")} />
              <div className="min-w-0 flex-1">
                <RadixToast.Title className="font-semibold text-slate-900">{t.title}</RadixToast.Title>
                {t.description !== undefined && (
                  <RadixToast.Description className="mt-0.5 text-sm text-slate-700">{t.description}</RadixToast.Description>
                )}
              </div>
              <RadixToast.Close
                aria-label="Dismiss"
                className="-m-1 grid size-8 shrink-0 place-items-center rounded-lg text-slate-700 hover:bg-slate-100"
              >
                <X aria-hidden="true" className="size-4" />
              </RadixToast.Close>
            </RadixToast.Root>
          );
        })}
        <RadixToast.Viewport className="fixed bottom-0 right-0 z-50 flex w-full max-w-sm flex-col gap-2 p-4 outline-none" />
      </RadixToast.Provider>
    </Context.Provider>
  );
}
