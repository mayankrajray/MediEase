import { cookies } from "next/headers";
import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/ui/Logo";
import { WithoutErrorRef } from "@/features/auth/ErrorNotice";
import { LanguageCookieSwitch } from "@/features/portal/LanguageCookieSwitch";
import { PORTAL_LANGUAGE_COOKIE, parsePortalLanguage, portalStrings } from "@/lib/i18n/portal";

/**
 * The portal's signed-out frame (M6a-P3; M6b-P2 decision 1A): the sign-in card, in the language of
 * the `me_pt_lang` cookie, with its switch. No staff `SessionProvider` here (ADR-0015).
 */
export default async function PortalAuthLayout({ children }: Readonly<{ children: ReactNode }>) {
  const language = parsePortalLanguage((await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  const s = portalStrings(language);
  return (
    <main lang={language} className="flex min-h-screen flex-col items-center bg-canvas px-4 py-10 sm:py-16">
      <div className="flex w-full max-w-md justify-end">
        <LanguageCookieSwitch language={language} />
      </div>
      <Link href="/" className="mt-2 rounded-lg p-1">
        <Logo size="md" />
      </Link>
      <p className="mt-2 text-sm text-slate-700">{s.brandTagline}</p>
      <div className="mt-8 w-full max-w-md rounded-2xl border border-line bg-surface shadow-pop">
        <WithoutErrorRef>{children}</WithoutErrorRef>
      </div>
    </main>
  );
}
