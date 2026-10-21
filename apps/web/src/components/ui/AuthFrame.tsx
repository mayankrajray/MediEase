import type { ReactNode } from "react";

/**
 * The frame of the screens before the workspace (M6-P2, decision 8A): sign-in, accepting an
 * invitation, choosing a clinic. A centred card on the canvas under the brand mark; no image,
 * no web font. It is the page's `main`.
 */
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center bg-canvas px-4 py-10 sm:py-16">
      <p className="flex items-center gap-2 text-xl font-bold text-slate-900">
        <span aria-hidden="true" className="grid size-9 place-items-center rounded-xl bg-brand-700 text-base text-white">
          M
        </span>
        MediEase
      </p>
      <p className="mt-1 text-sm text-slate-700">The clinic&apos;s day, in one place</p>
      <div className="mt-6 w-full max-w-md rounded-card border border-slate-200 bg-white shadow-card">{children}</div>
    </main>
  );
}
