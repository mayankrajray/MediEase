import type { ReactNode } from "react";

import { BRAND_FONT } from "@/app/fonts";
import { Logo } from "@/components/ui/Logo";
import { cx } from "@/components/ui/cx";

/**
 * The signed-out frame of applying to join MediEase (M6c-P1): the brand, then one card, wider
 * than sign-in for the form's steps. English only in M6c (D2). No session provider. M7c-P7: the
 * logo and the brand font.
 */
export default function ApplyLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <main lang="en" className={cx(BRAND_FONT, "flex min-h-screen flex-col items-center bg-canvas px-4 py-8 sm:py-12")}>
      <p>
        <Logo size="md" />
      </p>
      <p className="mt-2 text-sm text-slate-700">Apply to join MediEase</p>
      <div className="mt-6 w-full max-w-2xl rounded-card border border-line bg-surface shadow-card">{children}</div>
    </main>
  );
}
