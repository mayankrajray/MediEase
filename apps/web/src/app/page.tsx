import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { TODAY_PATH } from "@/features/auth/landing";
import { Landing } from "@/features/landing/Landing";
import { CSRF_COOKIE, PORTAL_CSRF_COOKIE } from "@/lib/api/csrf";
import { pickLanguage } from "@/lib/i18n/booking-request";
import { landingWords } from "@/lib/i18n/landing";
import { PORTAL_LANGUAGE_COOKIE } from "@/lib/i18n/portal";

type Search = Record<string, string | string[] | undefined>;

export async function generateMetadata({ searchParams }: Readonly<{ searchParams: Promise<Search> }>): Promise<Metadata> {
  const w = landingWords(pickLanguage((await searchParams).lang, undefined));
  // FR-LND-03: the landing page is the one page meant to be found.
  return {
    title: w.title,
    description: w.description,
    robots: { index: true, follow: true },
    alternates: { canonical: "/", languages: { en: "/", hi: "/?lang=hi" } },
    openGraph: { title: w.title, description: w.description, type: "website" },
  };
}

/**
 * `/` (M6c-P8, FR-LND-01): the landing page for a signed-out visitor. Staff with a session go to
 * Today (M6-P1, decision 6A) and patients to their app; the API still checks every request, the
 * cookies here are only a hint (ADR-0006).
 */
export default async function Home({ searchParams }: Readonly<{ searchParams: Promise<Search> }>) {
  const jar = await cookies();
  if (jar.get(CSRF_COOKIE)?.value) redirect(TODAY_PATH);
  if (jar.get(PORTAL_CSRF_COOKIE)?.value) redirect("/portal");
  const language = pickLanguage((await searchParams).lang, jar.get(PORTAL_LANGUAGE_COOKIE)?.value);
  return <Landing language={language} />;
}
