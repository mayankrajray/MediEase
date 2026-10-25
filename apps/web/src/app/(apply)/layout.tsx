import type { ReactNode } from "react";

/**
 * The signed-out frame of applying to join MediEase (M6c-P1): the brand, then one card, wider
 * than sign-in for the form's steps. English only in M6c (D2). No session provider.
 */
export default function ApplyLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <main lang="en" className="flex min-h-screen flex-col items-center bg-canvas px-4 py-8 sm:py-12">
      <p className="flex items-center gap-2 text-xl font-bold text-slate-900">
        <span aria-hidden="true" className="grid size-9 place-items-center rounded-xl bg-brand-700 text-base text-white">
          M
        </span>
        MediEase
      </p>
      <p className="mt-1 text-sm text-slate-700">Apply to join MediEase</p>
      <div className="mt-6 w-full max-w-2xl rounded-card border border-slate-200 bg-white shadow-card">{children}</div>
    </main>
  );
}
