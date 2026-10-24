"use client";

import { useRouter } from "next/navigation";

import { PORTAL_LANGUAGE_COOKIE, type PortalLanguage, portalStrings } from "@/lib/i18n/portal";

const YEAR_SECONDS = 365 * 24 * 60 * 60;

/** Remembers the signed-out pages' language in `me_pt_lang` (spec R21); not a secret. */
export function rememberPortalLanguage(language: PortalLanguage): void {
  document.cookie = `${PORTAL_LANGUAGE_COOKIE}=${language}; path=/; max-age=${YEAR_SECONDS}; samesite=lax`;
}

/** The language switch of the sign-in and sign-up pages (M6b-P2, decision 2A). */
export function LanguageCookieSwitch({ language }: Readonly<{ language: PortalLanguage }>) {
  const router = useRouter();
  const other: PortalLanguage = language === "hi" ? "en" : "hi";
  const s = portalStrings(language);
  return (
    <button
      type="button"
      lang={other}
      aria-label={s.switchLanguageLabel}
      onClick={() => {
        rememberPortalLanguage(other);
        router.refresh();
      }}
      className="inline-flex min-h-11 items-center rounded-lg border border-slate-400 bg-white px-3 text-sm font-medium text-slate-900 hover:bg-slate-100"
    >
      {s.switchLanguage}
    </button>
  );
}
