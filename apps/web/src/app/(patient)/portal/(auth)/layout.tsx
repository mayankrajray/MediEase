import { cookies } from "next/headers";
import type { ReactNode } from "react";

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
      <p className="mt-2 flex items-center gap-2 text-xl font-bold text-slate-900">
        <span aria-hidden="true" className="grid size-9 place-items-center rounded-xl bg-brand-700 text-base text-white">
          M
        </span>
        MediEase
      </p>
      <p className="mt-1 text-sm text-slate-700">{s.brandTagline}</p>
      <div className="mt-6 w-full max-w-md rounded-card border border-slate-200 bg-white shadow-card">{children}</div>
    </main>
  );
}
