import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "./Logo";

/**
 * The frame of the screens before the workspace (M6-P2, decision 8A): sign-in, accepting an
 * invitation, choosing a clinic. A centred card on the canvas under the logo; no image. It is the
 * page's `main`. M7c-P7 (M2): the logo links back to the MediEase home page (a way back from
 * every page), and the card is the design system's surface.
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
      <Link href="/" className="rounded-lg p-1">
        <Logo size="md" />
      </Link>
      <p className="mt-2 text-sm text-slate-700">{tagline}</p>
      <div className="mt-8 w-full max-w-md rounded-2xl border border-line bg-surface shadow-pop">{children}</div>
    </main>
  );
}
