import type { ReactNode } from "react";

import { Logo } from "./Logo";

/**
 * The frame of the screens before the workspace (M6-P2, decision 8A): sign-in, accepting an
 * invitation, choosing a clinic. A centred card on the canvas under the logo; no image. It is the
 * page's `main`. M7c-P7: the MediEase logo replaces the hand-drawn mark.
 */
export function AuthFrame({
  children,
  tagline = "The clinic's day, in one place",
}: {
  children: ReactNode;
  /** The line under the brand mark; the patient portal has its own (M6a-P3). */
  tagline?: string;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center bg-canvas px-4 py-10 sm:py-16">
      <p>
        <Logo size="md" />
      </p>
      <p className="mt-2 text-sm text-slate-700">{tagline}</p>
      <div className="mt-6 w-full max-w-md rounded-card border border-line bg-surface shadow-card">{children}</div>
    </main>
  );
}
