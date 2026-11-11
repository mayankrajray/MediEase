import { Languages } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/ui/Logo";
import type { PortalLanguage } from "@/lib/i18n/portal";

/** The public booking pages' bar (M7d): the logo home and the language switch, which keeps the
 * page's date and time (`switchHref`). */
export function PublicHeader({ language, switchHref, switchTo, switchLabel }: Readonly<{ language: PortalLanguage; switchHref: string; switchTo: string; switchLabel: string }>) {
  const other = language === "hi" ? "en" : "hi";
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/85">
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
        <Link href={language === "hi" ? "/?lang=hi" : "/"} className="flex min-h-11 items-center">
          <Logo />
        </Link>
        <Link
          href={switchHref}
          lang={other}
          aria-label={switchLabel}
          className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-surface px-3 text-sm font-semibold text-slate-900 transition-colors hover:border-brand-300 hover:bg-brand-50"
        >
          <Languages aria-hidden="true" className="size-4" />
          {switchTo}
        </Link>
      </div>
    </header>
  );
}
